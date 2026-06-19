"""
Gain analysis module.
Handles gain map computation, relative change analysis, and photon energy calculation.
"""
import os
import math
import numpy as np
import multiprocessing as mp
from time import time
from ..core.config import Config
from .gaussian_fitting import estimate_peak_by_hist, fit_pixel_full, fit_noisepeak_full


class GainAnalyzer:
    """Gain analysis utilities."""

    @staticmethod
    def compute_photon_energy(adu_map, gain_map):
        """Compute photon energy map: adu / gain."""
        photon_energy = adu_map / gain_map
        return np.nan_to_num(photon_energy, nan=0.0)

    @staticmethod
    def relative_change_map(map1, map2):
        """Compute relative change percentage between two maps."""
        with np.errstate(divide='ignore', invalid='ignore'):
            change_map = (map2 - map1) / np.maximum(map1, 1e-9) * 100.0
        return change_map

    @staticmethod
    def mark_large_changes(change_map, threshold=5.0):
        """Mark pixels where absolute relative change exceeds threshold."""
        marked_map = np.zeros(change_map.shape, dtype=np.uint8)
        marked_map[np.abs(change_map) > threshold] = 1

        marked_indices = np.argwhere(marked_map == 1)
        if len(marked_indices) > 0:
            print(f"Marked {len(marked_indices)} pixels with relative change > {threshold}%")
            sample_size = min(10, len(marked_indices))
            print("Sample marked pixel positions (row, col):")
            for idx in marked_indices[np.random.choice(len(marked_indices), size=sample_size, replace=False)]:
                print(f"  ({idx[0]}, {idx[1]})")

        return marked_map

    @staticmethod
    def merge_left_right_maps(left_map, right_map):
        """Merge left and right half-panel maps into full image."""
        H, W = left_map.shape
        all_map = np.zeros((H, W))
        all_map[:, :W // 2] = left_map[:, :W // 2]
        all_map[:, W // 2:] = right_map[:, W // 2:]
        return all_map


# ---------------------------------------------------------------------------
# Internal: unified block-level processing
# ---------------------------------------------------------------------------

def _process_block(pe_block, bins, hist_range, noise_range, use_raw_for_noise, mode):
    """Process a column block of pixels.

    Args:
        pe_block: Pixel data block (n_frames, H, W_block), baseline-subtracted.
        bins: Histogram bin count.
        hist_range: Histogram range (min, max).
        noise_range: Noise peak fitting range (min, max).
        use_raw_for_noise: Whether to fit noise peak from signal data.
        mode: 'gain' or 'noise'.

    Returns:
        (result_map, extra_map) where extra_map is None unless mode=='gain'
        and use_raw_for_noise is True.
    """
    n_frames, H, Wb = pe_block.shape
    results = np.full((H, Wb), np.nan, dtype=np.float32)
    extra = np.full((H, Wb), np.nan, dtype=np.float32) if (mode == 'gain' and use_raw_for_noise) else None

    for r in range(H):
        for c in range(Wb):
            series = pe_block[:, r, c]
            if np.all(np.isnan(series)) or np.std(series) < 1e-6:
                continue

            if use_raw_for_noise:
                noise_peak = estimate_peak_by_hist(series, bins=bins,
                                                   range_min=noise_range[0],
                                                   range_max=noise_range[1])
                if np.isnan(noise_peak):
                    continue

                if mode == 'noise':
                    results[r, c] = noise_peak
                else:
                    series_corrected = series - noise_peak
                    signal_peak = estimate_peak_by_hist(series_corrected, bins=bins,
                                                        range_min=hist_range[0] - noise_peak,
                                                        range_max=hist_range[1] - noise_peak)
                    if not np.isnan(signal_peak):
                        results[r, c] = signal_peak / Config.ENERGY_KEV_FACTOR
                        if extra is not None:
                            extra[r, c] = np.mean(series_corrected)
            else:
                peak = estimate_peak_by_hist(series, bins=bins,
                                             range_min=hist_range[0],
                                             range_max=hist_range[1])
                if not np.isnan(peak):
                    if mode == 'gain':
                        results[r, c] = peak / Config.ENERGY_KEV_FACTOR
                    else:
                        results[r, c] = peak

    return results, extra


# ---------------------------------------------------------------------------
# Internal: unified full-map computation
# ---------------------------------------------------------------------------

def _compute_pixel_map(raw_path, out_dir, output_filename, mode,
                       header_size=112, frame_shape=(512, 1024),
                       memmap_path=None, block_width=64, bins=100,
                       hist_range=(100, 500), baseline_memmap=None,
                       use_baseline=False, full_fit=False, full_fit_workers=None,
                       only_gaussian=False, make_memmap_func=None,
                       use_raw_for_noise=False):
    """Unified pixel-map computation for both gain and noise-peak maps.

    Args:
        raw_path: Path to the raw file.
        out_dir: Output directory.
        output_filename: Name of the output .npy file.
        mode: 'gain' or 'noise'.
        ... (other args match original compute_gainmap / compute_noisepeakmap)

    Returns:
        (result_map, extra_map_or_None)
    """
    os.makedirs(out_dir, exist_ok=True)

    size = os.path.getsize(raw_path)
    frame_bytes = header_size + np.prod(frame_shape) * 2
    n_frames = size // frame_bytes
    if n_frames == 0:
        raise ValueError("No frames found in raw file")

    if memmap_path is None:
        memmap_path = os.path.join(out_dir, "frames_memmap.dat")

    print(f"Creating/using memmap at {memmap_path}...")
    if make_memmap_func is not None:
        mm = make_memmap_func(raw_path, memmap_path, dtype='<u2', force=False)
    else:
        raise ValueError("make_memmap_func is required")

    H, W = frame_shape
    result_map = np.full((H, W), np.nan, dtype=np.float32)
    extra_map = np.full((H, W), np.nan, dtype=np.float32) if (mode == 'gain' and use_raw_for_noise) else None

    # Load baseline if requested
    baseline = None
    if use_baseline and baseline_memmap is not None:
        if isinstance(baseline_memmap, str):
            baseline = np.load(baseline_memmap, allow_pickle=True)
        elif isinstance(baseline_memmap, np.ndarray):
            baseline = baseline_memmap
        else:
            raise ValueError(f"baseline_memmap must be str or ndarray, got {type(baseline_memmap)}")

    # Choose full-fit function based on mode
    if full_fit_workers is None:
        full_fit_workers = min(24, os.cpu_count() or 4)

    col_blocks = [(c, min(W, c + block_width)) for c in range(0, W, block_width)]
    start_t = time()

    for bi, (cs, ce) in enumerate(col_blocks):
        print(f"[{bi + 1}/{len(col_blocks)}] Processing columns {cs}:{ce}...")
        block = np.array(mm[:, :, cs:ce], copy=False)

        if baseline is not None:
            baseline_block = baseline[:, cs:ce]
            block_processed = block - baseline_block[None, :, :]
        else:
            block_processed = block

        # Run block-level processing
        block_result, block_extra = _process_block(
            block_processed, bins=bins, hist_range=hist_range,
            noise_range=(-100, 100), use_raw_for_noise=use_raw_for_noise,
            mode=mode
        )
        result_map[:, cs:ce] = block_result
        if extra_map is not None and block_extra is not None:
            extra_map[:, cs:ce] = block_extra

        # Optional full-fit refinement
        if full_fit:
            to_refine = [(r, col) for r in range(H) for col in range(cs, ce)
                         if not np.isnan(result_map[r, col])]
            if to_refine:
                pool = mp.Pool(processes=full_fit_workers)
                tasks = []
                for (r, col) in to_refine:
                    series = block_processed[:, r, col - cs].astype(np.float64)
                    if mode == 'gain':
                        tasks.append(pool.apply_async(fit_pixel_full, args=(
                            series, None, hist_range, 100, (280.0, 380.0),
                            only_gaussian, (-100, 100), False, use_raw_for_noise, None
                        )))
                    else:
                        tasks.append(pool.apply_async(fit_noisepeak_full, args=(
                            series, (-100, 100), 50, use_raw_for_noise, None
                        )))

                for i, res in enumerate(tasks):
                    result = res.get()
                    if mode == 'gain':
                        gain = result[2] if isinstance(result, tuple) and len(result) == 3 else result
                        if not math.isnan(gain):
                            r, col = to_refine[i]
                            result_map[r, col] = gain
                    else:
                        if not math.isnan(result):
                            r, col = to_refine[i]
                            result_map[r, col] = result

                pool.close()
                pool.join()

    elapsed = time() - start_t
    print(f"Done. Elapsed {elapsed:.1f}s. Saving results...")
    out_npy = os.path.join(out_dir, output_filename)
    np.save(out_npy, result_map)
    print(f"Saved NPY -> {out_npy}")

    if extra_map is not None:
        extra_path = os.path.join(out_dir, "mean_corrected_ADU_map.npy")
        np.save(extra_path, extra_map)
        print(f"Saved NPY -> {extra_path}")

    return result_map, extra_map


# ---------------------------------------------------------------------------
# Public API: thin wrappers
# ---------------------------------------------------------------------------

def compute_gainmap(raw_path, out_dir, header_size=112, frame_shape=(512, 1024),
                    memmap_path=None, block_width=64, bins=100, hist_range=(100, 500),
                    baseline_memmap=None, use_baseline=False, workers=None,
                    full_fit=False, full_fit_workers=None, only_gaussian=False,
                    make_memmap_func=None, use_raw_for_noise=False):
    """Compute the full-sensor gain map (ADU/keV)."""
    return _compute_pixel_map(
        raw_path, out_dir, "gain_map.npy", "gain",
        header_size=header_size, frame_shape=frame_shape,
        memmap_path=memmap_path, block_width=block_width, bins=bins,
        hist_range=hist_range, baseline_memmap=baseline_memmap,
        use_baseline=use_baseline, full_fit=full_fit,
        full_fit_workers=full_fit_workers, only_gaussian=only_gaussian,
        make_memmap_func=make_memmap_func, use_raw_for_noise=use_raw_for_noise
    )


def compute_noisepeakmap(raw_path, out_dir, header_size=112, frame_shape=(512, 1024),
                         memmap_path=None, block_width=64, bins=100, hist_range=(100, 500),
                         baseline_memmap=None, use_baseline=False, workers=None,
                         full_fit=False, full_fit_workers=None, only_gaussian=False,
                         make_memmap_func=None, use_raw_for_noise=False):
    """Compute the full-sensor noise peak position map."""
    return _compute_pixel_map(
        raw_path, out_dir, "noise_peak_map.npy", "noise",
        header_size=header_size, frame_shape=frame_shape,
        memmap_path=memmap_path, block_width=block_width, bins=bins,
        hist_range=hist_range, baseline_memmap=baseline_memmap,
        use_baseline=use_baseline, full_fit=full_fit,
        full_fit_workers=full_fit_workers, only_gaussian=only_gaussian,
        make_memmap_func=make_memmap_func, use_raw_for_noise=use_raw_for_noise
    )
