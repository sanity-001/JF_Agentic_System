"""
Gaussian Fitting Module
Handles Gaussian functions, Gaussian+erfc fitting, peak detection, etc.
"""
import numpy as np
import multiprocessing as mp
from scipy.special import erfc
from scipy.optimize import curve_fit
from functools import partial
import math
from ..core.config import Config


def gaussian(x, A, mu, sigma):
    """Gaussian function

    Args:
        x: Independent variable
        A: Amplitude
        mu: Mean
        sigma: Standard deviation


    Returns:
        Gaussian function value
    """
    return A * np.exp(-(x - mu)**2 / (2 * sigma**2))


def gauss_erfc_model(x, A_gauss, mu, sigma, A_erfc):
    """Gaussian + erfc combined model

    Args:
        x: Independent variable
        A_gauss: Gaussian amplitude
        mu: Mean
        sigma: Standard deviation
        A_erfc: erfc amplitude

    Returns:
        Combined model value
    """
    return A_gauss * np.exp(-(x - mu)**2 / (2 * sigma**2)) + A_erfc * erfc((x - mu) / (np.sqrt(2) * sigma))


def estimate_peak_by_hist(series, bins=80, range_min=100.0, range_max=500.0):
    """Quickly estimate peak position via histogram peak location

    Args:
        series: Data series
        bins: Number of histogram bins
        range_min: Range minimum
        range_max: Range maximum

    Returns:
        Peak position
    """
    hist, edges = np.histogram(series, bins=bins, range=(range_min, range_max))
    if hist.sum() == 0:
        return np.nan
    idx = int(np.argmax(hist))
    center = 0.5 * (edges[idx] + edges[idx+1])
    return center


def fit_pixel_full(series, gauss_guess=None, full_range=(100,500), bins=100,
                   sub_range=(280.0,380.0), only_gaussian=False, noise_range=(-100,100),
                   return_details=False, use_raw_for_noise=True, baseline_series=None):
    """Perform full fitting on a pixel series (first fit the noise peak and shift data, then fit the signal peak)

    Args:
        series: Pixel value series (illuminated data after baseline subtraction, used for signal peak fitting)
        gauss_guess: Gaussian initial guess (retained for compatibility)
        full_range: Full fitting range
        bins: Number of histogram bins
        sub_range: Sub-range (used for initial value estimation)
        only_gaussian: Whether to do single Gaussian fitting only
        noise_range: Noise peak fitting range
        return_details: Whether to return detailed information
                       - False (default): Returns a single gain value, used for full-pixel fitting
                       - True: Returns a triple (noise_peak, signal_peak, gain), used for single-pixel visualization
        use_raw_for_noise: Controls the data source for noise peak fitting
                          - True (default): Fit noise peak on series (illuminated data after baseline subtraction)
                          - False: Fit noise peak on baseline_series (baseline data)
        baseline_series: Baseline data series (must be provided when use_raw_for_noise=False)

    Returns:
        When return_details=False: gain (float gain value, returns np.nan on failure)
        When return_details=True: (noise_peak, signal_peak, gain) or (np.nan, np.nan, np.nan)
    """
    # Select data source for noise peak fitting
    if use_raw_for_noise:
        noise_fit_data = series
    else:
        if baseline_series is None:
            if return_details:
                return np.nan, np.nan, np.nan
            else:
                return np.nan
        noise_fit_data = baseline_series - np.mean(baseline_series)

    # First fit the noise peak to obtain the noise peak mean
    noise_mask = (noise_fit_data >= noise_range[0]) & (noise_fit_data <= noise_range[1])
    noise_data = noise_fit_data[noise_mask]
    noise_peak = np.nan

    if noise_data.size >= 10:
        hist_noise, edges_noise = np.histogram(noise_data, bins=50, range=noise_range)
        if hist_noise.sum() > 0:
            centers_noise = 0.5 * (edges_noise[:-1] + edges_noise[1:])
            A_noise = float(hist_noise.max())
            mu_noise = float(centers_noise[np.argmax(hist_noise)])
            sigma_noise = (noise_range[1] - noise_range[0]) / 6
            try:
                popt_noise, _ = curve_fit(
                    gaussian, centers_noise, hist_noise,
                    p0=[A_noise, mu_noise, sigma_noise],
                    bounds=([0.0, noise_range[0], 1e-2], [np.inf, noise_range[1], noise_range[1]-noise_range[0]]),
                    maxfev=Config.MAXFEV_DEFAULT
                )
                noise_peak = float(popt_noise[1])
            except (RuntimeError, ValueError):
                noise_peak = mu_noise  # Use histogram peak if fitting fails

    # If noise peak fitting fails, return nan
    if np.isnan(noise_peak):
        if return_details:
            return np.nan, np.nan, np.nan
        else:
            return np.nan

    # Subtract noise peak mean from all ADU values
    series_corrected = series - noise_peak

    # Fit the main peak (X-ray peak of illuminated data), using corrected data and corrected range
    corrected_full_range = (full_range[0] - noise_peak, full_range[1] - noise_peak)

    mask = (series_corrected >= corrected_full_range[0]) & (series_corrected <= corrected_full_range[1])
    data = series_corrected[mask]
    if data.size < 10:
        # Keep return type consistent when data is insufficient
        return (np.nan, np.nan, np.nan) if return_details else np.nan

    # Default initial values (from histogram when no sub-range fitting), using corrected range
    hist, edges = np.histogram(data, bins=bins, range=corrected_full_range)
    centers = 0.5 * (edges[:-1] + edges[1:])
    A0 = float(hist.max()) if hist.sum() > 0 else 1.0
    mu0 = float(centers[np.argmax(hist)]) if hist.sum() > 0 else 0.5*(corrected_full_range[0]+corrected_full_range[1])
    sigma0 = 5.0

    # Prepare sub-range variables
    centers_sub = None
    hist_sub = None

    # Optional: perform single Gaussian fitting in sub-range to improve initial values
    if sub_range is not None:
        corrected_sub_range = (sub_range[0] - noise_peak, sub_range[1] - noise_peak)
        sub_min, sub_max = float(corrected_sub_range[0]), float(corrected_sub_range[1])
        bins_sub = min(25, max(10, int(bins//2)))
        sub_mask = (series_corrected >= sub_min) & (series_corrected <= sub_max)
        sub_data = series_corrected[sub_mask]
        if sub_data.size >= 10:
            hist_sub, edges_sub = np.histogram(sub_data, bins=bins_sub, range=(sub_min, sub_max))
            if hist_sub.sum() > 0:
                centers_sub = 0.5 * (edges_sub[:-1] + edges_sub[1:])
                A0 = float(np.max(hist_sub))
                mu0 = float(centers_sub[np.argmax(hist_sub)])
                sigma0 = (sub_max - sub_min) / 6
                # Attempt single Gaussian fitting to improve initial values
                try:
                    popt_g, _ = curve_fit(
                        gaussian, centers_sub, hist_sub, p0=[A0, mu0, sigma0],
                        bounds=([0.0, sub_min, 1e-2], [np.inf, sub_max, sub_max-sub_min]),
                        maxfev=Config.MAXFEV_DEFAULT
                    )
                    A0, mu0, sigma0 = float(popt_g[0]), float(popt_g[1]), float(abs(popt_g[2]))
                except (RuntimeError, ValueError):
                    pass

    # If only single Gaussian fitting is done
    signal_peak = np.nan
    if only_gaussian:
        try:
            if centers_sub is not None and hist_sub is not None and hist_sub.sum() > 0:
                popt_g, _ = curve_fit(
                    gaussian, centers_sub, hist_sub, p0=[A0, mu0, sigma0],
                    bounds=([0.0, sub_min, 1e-2], [np.inf, sub_max, sub_max-sub_min]),
                    maxfev=Config.MAXFEV_DEFAULT
                )
                signal_peak = float(popt_g[1])
            else:
                popt_g, _ = curve_fit(
                    gaussian, centers, hist, p0=[A0, mu0, sigma0],
                    bounds=([0.0, corrected_full_range[0], 1e-2], [np.inf, corrected_full_range[1], corrected_full_range[1]-corrected_full_range[0]]),
                    maxfev=Config.MAXFEV_DEFAULT
                )
                signal_peak = float(popt_g[1])
        except (RuntimeError, ValueError):
            signal_peak = float(mu0)

        if not np.isnan(signal_peak):
            gain = signal_peak / Config.ENERGY_KEV_FACTOR
            gain_val = float(gain)
            if return_details:
                return noise_peak, signal_peak, gain_val
            else:
                return gain_val
        else:
            if return_details:
                return np.nan, np.nan, np.nan
            else:
                return np.nan

    # erfc initial value
    A_erfc0 = max(1.0, 0.5 * A0)

    # Final fitting with gauss+erfc
    lb = [0.0, mu0 - max(50.0, sigma0 * 5.0), 1e-2, 0.0]
    ub = [np.inf, mu0 + max(50.0, sigma0 * 5.0), (corrected_full_range[1] - corrected_full_range[0]), np.inf]
    try:
        popt, pcov = curve_fit(
            gauss_erfc_model, centers, hist,
            p0=[A0, mu0, sigma0, A_erfc0],
            bounds=(lb, ub),
            maxfev=Config.MAXFEV_FULL
        )
        x_search = np.linspace(corrected_full_range[0], corrected_full_range[1], 5000)
        y = gauss_erfc_model(x_search, *popt)
        signal_peak = float(x_search[np.argmax(y)])
    except Exception:
        signal_peak = float(mu0)

    if not np.isnan(signal_peak):
        gain = signal_peak / Config.ENERGY_KEV_FACTOR
        gain_val = float(gain)
        if return_details:
            return noise_peak, signal_peak, gain_val
        else:
            return gain_val
    else:
        if return_details:
            return np.nan, np.nan, np.nan
        else:
            return np.nan

def fit_noisepeak_full(series, noise_range=(-100,100), bins=50, use_raw_for_noise=True, baseline_series=None):
    """Fit the noise peak and return the noise peak mean

    Args:
        series: Pixel value series
        noise_range: Noise peak fitting range
        bins: Number of histogram bins

    Returns:
        noise_peak: Noise peak mean (returns np.nan on failure)
    """
    # Select data source for noise peak fitting
    if use_raw_for_noise:
        noise_fit_data = series
    else:
        if baseline_series is None:
            return np.nan
        noise_fit_data = baseline_series - np.mean(baseline_series)

    noise_mask = (noise_fit_data >= noise_range[0]) & (noise_fit_data <= noise_range[1])
    noise_data = noise_fit_data[noise_mask]
    noise_peak = np.nan

    if noise_data.size >= 10:
        hist_noise, edges_noise = np.histogram(noise_data, bins=bins, range=noise_range)
        if hist_noise.sum() > 0:
            centers_noise = 0.5 * (edges_noise[:-1] + edges_noise[1:])
            A_noise = float(hist_noise.max())
            mu_noise = float(centers_noise[np.argmax(hist_noise)])
            sigma_noise = (noise_range[1] - noise_range[0]) / 6
            try:
                popt_noise, _ = curve_fit(
                    gaussian, centers_noise, hist_noise,
                    p0=[A_noise, mu_noise, sigma_noise],
                    bounds=([0.0, noise_range[0], 1e-2], [np.inf, noise_range[1], noise_range[1]-noise_range[0]]),
                    maxfev=Config.MAXFEV_DEFAULT
                )
                noise_peak = float(popt_noise[1])
            except (RuntimeError, ValueError):
                noise_peak = mu_noise  # Use histogram peak if fitting fails
    # If noise peak fitting fails, return nan
    if np.isnan(noise_peak):
        return np.nan

    return noise_peak

