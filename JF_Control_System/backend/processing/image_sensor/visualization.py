"""Visualization module for heatmaps, histograms, fitting curves, and gain maps."""

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import ListedColormap, BoundaryNorm
from scipy.special import erfc
from ..core.config import Config
from .gaussian_fitting import gaussian


class Visualizer:
    """Static visualization methods."""

    @staticmethod
    def plot_heatmap(img_array, title="Heatmap", xlabel="Pixel X", ylabel="Pixel Y",
                    cmap='viridis', vmin=None, vmax=None, colorbar_label="Value",
                    output_path=None, figsize=(8, 6)):
        """Plot a 2D heatmap.

        Args:
            img_array: 2D image array.
            title: Plot title.
            xlabel: X-axis label.
            ylabel: Y-axis label.
            cmap: Colormap name or object.
            vmin: Minimum value for color scale.
            vmax: Maximum value for color scale.
            colorbar_label: Colorbar label.
            output_path: If set, save to file instead of showing.
            figsize: Figure size in inches.
        """
        fig, ax = plt.subplots(figsize=figsize)
        im = ax.imshow(
            img_array, cmap=cmap, interpolation='nearest',
            vmin=vmin, vmax=vmax, origin='upper'
        )
        ax.invert_yaxis()
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cbar.set_label(colorbar_label)
        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, bbox_inches='tight', dpi=150)
            plt.close(fig)
            print(f"Saved: {output_path}")
        else:
            plt.show()

    @staticmethod
    def plot_side_by_side(img1, img2, title1="Image 1", title2="Image 2",
                         cmap='viridis', vmin=None, vmax=None, colorbar_label="Value",
                         output_path=None, figsize=(12, 6)):
        """Plot two heatmaps side by side for comparison.

        Args:
            img1: First image array.
            img2: Second image array.
            title1: Title for first image.
            title2: Title for second image.
            cmap: Colormap.
            vmin: Shared minimum for color scale.
            vmax: Shared maximum for color scale.
            colorbar_label: Colorbar label.
            output_path: Save path (None to display).
            figsize: Figure size in inches.
        """
        fig, axes = plt.subplots(1, 2, figsize=figsize)

        im1 = axes[0].imshow(img1, cmap=cmap, interpolation='nearest', vmin=vmin, vmax=vmax)
        axes[0].set_title(title1)
        axes[0].set_xlabel('Pixel X')
        axes[0].set_ylabel('Pixel Y')
        axes[0].invert_yaxis()
        fig.colorbar(im1, ax=axes[0], label=colorbar_label)

        im2 = axes[1].imshow(img2, cmap=cmap, interpolation='nearest', vmin=vmin, vmax=vmax)
        axes[1].set_title(title2)
        axes[1].set_xlabel('Pixel X')
        axes[1].set_ylabel('Pixel Y')
        axes[1].invert_yaxis()
        fig.colorbar(im2, ax=axes[1], label=colorbar_label)

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, bbox_inches='tight')
            plt.close(fig)
            print(f"Saved: {output_path}")
        else:
            plt.show()

    @staticmethod
    def plot_histogram(data, bins=100, integral=True, range_vals=None, title="Histogram",
                      xlabel="Value", ylabel="Counts", output_path=None,
                      color='blue', alpha=0.7, text_lines=False):
        """Plot a 1D histogram with optional mean line annotation.

        Args:
            data: 1D or 2D data array (flattened internally).
            bins: Number of bins or bin edges array.
            integral: If True, compute bin edges with step=1 for integer ADU values.
            range_vals: (min, max) range tuple.
            title: Plot title.
            xlabel: X-axis label.
            ylabel: Y-axis label.
            output_path: Save path (None to display).
            color: Histogram line color.
            alpha: Histogram transparency.
            text_lines: If True, draw mean line annotation.
        """
        if integral:
            if range_vals is None:
                range_vals = (np.nanmin(data), np.nanmax(data))
            if range_vals[1] - range_vals[0] < 10:
                bins = np.arange(range_vals[0] - 50, range_vals[1] + 50, 1)
            else:
                bins = np.arange(range_vals[0] - 0.5, range_vals[1] + 1.5, 1)
        else:
            bins = bins
        plt.figure(figsize=(10, 6))
        plt.hist(data.flatten(), bins=bins, range=range_vals, alpha=alpha,
                color=color, histtype='step')
        if text_lines:
            plt.axvline(x=np.nanmean(data), color='red', linestyle='--',
                       label=f'Mean: {np.nanmean(data):.2f}')
            plt.legend()
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, bbox_inches='tight')
            plt.close()
            print(f"Saved: {output_path}")
        else:
            plt.show()

    @staticmethod
    def plot_relative_change_histogram(change_map, bins=100, title="Relative Change Histogram",
                                   xlabel="Relative Change (%)", ylabel="Counts",
                                   output_path=None):
        """Plot histogram of relative change percentages with +/-1% and +/-5% bands.

        Args:
            change_map: Relative change map (percentage values).
            bins: Number of bins.
            title: Plot title.
            xlabel: X-axis label.
            ylabel: Y-axis label.
            output_path: Save path (None to display).
        """
        plt.figure(figsize=(10, 6))
        plt.hist(change_map.flatten(), bins=bins, range=(-15, 15), color='blue', alpha=0.7, histtype='step')
        plt.axvspan(-1.0, 1.0, color='blue', alpha=0.1)
        plt.text(-1, change_map.size*0.03, '+/-1%', color='blue', fontsize=15)
        within_1pct = np.sum((change_map <= 1.0) & (change_map >= -1.0)) / change_map.size * 100
        plt.text(-1, change_map.size*0.025, f'{within_1pct:.4f}%', color='blue', fontsize=12)
        plt.axvspan(-5.0, 5.0, color='orange', alpha=0.1)
        plt.text(3, change_map.size*0.03, '+/-5%', color='orange', fontsize=15)
        within_5pct = np.sum((change_map <= 5.0) & (change_map >= -5.0)) / change_map.size * 100
        plt.text(3, change_map.size*0.025, f'{within_5pct:.4f}%', color='orange', fontsize=12)
        plt.axvline(x=1.0, color='red', linestyle='--')
        plt.axvline(x=-1.0, color='red', linestyle='--')
        plt.axvline(x=5.0, color='green', linestyle='--')
        plt.axvline(x=-5.0, color='green', linestyle='--')
        plt.title(title)
        plt.xlim(-15, 15)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)

        if output_path:
            plt.savefig(output_path, bbox_inches='tight')
            plt.close()
            print(f"Saved: {output_path}")
        else:
            plt.show()

    @staticmethod
    def plot_relative_change(change_map, title="Relative Change",
                            vmax=5, output_path=None):
        """Plot relative change heatmap with coolwarm colormap.

        Args:
            change_map: Relative change map.
            title: Plot title.
            vmax: Maximum absolute value for color scale.
            output_path: Save path (None to display).
        """
        plt.figure(figsize=(8, 6))
        im = plt.imshow(change_map, cmap='coolwarm', vmin=-vmax, vmax=vmax, origin='upper')
        plt.colorbar(im, label='Relative Change (%)')
        plt.title(title)
        plt.xlabel('Pixel X')
        plt.ylabel('Pixel Y')
        plt.gca().invert_yaxis()
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, bbox_inches='tight')
            plt.close()
            print(f"Saved: {output_path}")
        else:
            plt.show()

    @staticmethod
    def plot_gain_submaps(change_map, output_dir=None):
        """Plot 2x4 sub-region heatmaps and per-subregion histograms.

        Args:
            change_map: Relative change map (512, 1024).
            output_dir: Output directory for saved figures.
        """
        abs95 = np.nanpercentile(np.abs(change_map), 99.99)
        vmax = max(abs95, 0.2)
        sub_rows, sub_cols = 2, 4

        # Sub-region heatmaps
        fig, axes = plt.subplots(sub_rows, sub_cols, figsize=(16, 8))
        for sr in range(sub_rows):
            for sc in range(sub_cols):
                ax = axes[sr, sc]
                r0, r1 = sr * 256, (sr + 1) * 256
                c0, c1 = sc * 256, (sc + 1) * 256
                sub_map = change_map[r0:r1, c0:c1]
                im = ax.imshow(sub_map, cmap='coolwarm', vmin=-vmax, vmax=vmax)
                ax.invert_yaxis()
                ax.set_title(f'Submap R{sr}C{sc}')
                ax.set_xlabel('Pixel X')
                ax.set_ylabel('Pixel Y')
                fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        plt.tight_layout()

        if output_dir:
            out_path = os.path.join(output_dir, "gain_submaps.png")
            fig.savefig(out_path, bbox_inches='tight')
            plt.close(fig)
            print(f"Saved: {out_path}")
        else:
            plt.show()

        # Per-subregion histograms
        for sr in range(sub_rows):
            for sc in range(sub_cols):
                r0, r1 = sr * 256, (sr + 1) * 256
                c0, c1 = sc * 256, (sc + 1) * 256
                sub_map = change_map[r0:r1, c0:c1]
                within_1pct = np.sum((sub_map <= 1.0) & (sub_map >= -1.0)) / sub_map.size * 100
                within_5pct = np.sum((sub_map <= 5.0) & (sub_map >= -5.0)) / sub_map.size * 100

                plt.figure(figsize=(8, 6))
                plt.hist(sub_map.flatten(), bins=100, range=(-15, 15), color='blue', alpha=0.7, histtype='step')
                plt.axvspan(-1.0, 1.0, color='blue', alpha=0.1)
                plt.text(-1, sub_map.size*0.03, f'+/-1%:\n{within_1pct:.2f}%', color='blue', fontsize=15)
                plt.axvspan(-5.0, 5.0, color='orange', alpha=0.1)
                plt.text(3, sub_map.size*0.03, f'+/-5%:\n{within_5pct:.2f}%', color='orange', fontsize=15)
                plt.axvline(x=1.0, color='red', linestyle='--')
                plt.axvline(x=-1.0, color='red', linestyle='--')
                plt.axvline(x=5.0, color='green', linestyle='--')
                plt.axvline(x=-5.0, color='green', linestyle='--')
                plt.title(f'Histogram of Relative Change R{sr}C{sc}')
                plt.xlim(-15, 15)
                plt.xlabel('Relative Change (%)')
                plt.ylabel('Counts')

                if output_dir:
                    out_path = os.path.join(output_dir, f"submap_hist_R{sr}C{sc}.png")
                    plt.savefig(out_path, bbox_inches='tight')
                    plt.close()
                    print(f"Saved: {out_path}")
                else:
                    plt.show()

    @staticmethod
    def plot_gaussian_fit(bin_centers, hist, popt, perr, title="Gaussian Fit",
                         xlabel="ADU", ylabel="Counts", output_path=None,
                         x_range=None):
        """Plot histogram with overlaid Gaussian fit curve and parameter box.

        Args:
            bin_centers: Bin center positions.
            hist: Histogram counts.
            popt: Fitted parameters [A, mu, sigma].
            perr: Parameter standard errors.
            title: Plot title.
            xlabel: X-axis label.
            ylabel: Y-axis label.
            output_path: Save path (None to display).
            x_range: X-axis range for fit curve.
        """
        plt.figure(figsize=(10, 6))
        plt.bar(bin_centers, hist, width=bin_centers[1]-bin_centers[0],
               alpha=0.7, label='Data', color='lightblue')

        if x_range is None:
            x_range = (bin_centers.min(), bin_centers.max())
        x_fit = np.linspace(x_range[0], x_range[1], 500)
        y_fit = gaussian(x_fit, *popt)
        plt.plot(x_fit, y_fit, 'r-', linewidth=2, label='Gaussian Fit')

        param_text = (f"Gaussian Fit Parameters:\n"
                     f"A = {popt[0]:.1f} +/- {perr[0]:.1f}\n"
                     f"mu = {popt[1]:.2f} +/- {perr[1]:.2f}\n"
                     f"sigma = {popt[2]:.2f} +/- {perr[2]:.2f}")
        plt.text(0.05, 0.95, param_text, transform=plt.gca().transAxes,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.title(title)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, bbox_inches='tight')
            plt.close()
            print(f"Saved: {output_path}")
        else:
            plt.show()

    @staticmethod
    def plot_gauss_erfc_fit(bin_centers, hist, popt, perr, peak_x, title="K-alpha Peak Fit",
                           xlabel="ADU (shifted)", ylabel="Counts", output_path=None,
                           x_range=None):
        """Plot histogram with Gauss+erfc composite fit and gain annotation.

        Args:
            bin_centers: Bin center positions.
            hist: Histogram counts.
            popt: Fitted parameters [A_gauss, mu, sigma, A_erfc].
            perr: Parameter standard errors.
            peak_x: Peak position from model search.
            title: Plot title.
            xlabel: X-axis label.
            ylabel: Y-axis label.
            output_path: Save path (None to display).
            x_range: X-axis range for fit curve.
        """
        plt.figure(figsize=(10, 6))
        plt.bar(bin_centers, hist, width=bin_centers[1]-bin_centers[0],
               alpha=0.7, label='Data', color='lightgreen')

        if x_range is None:
            x_range = (bin_centers.min(), bin_centers.max())
        x_fit = np.linspace(x_range[0], x_range[1], 500)

        y_total = (popt[0] * np.exp(-(x_fit - popt[1])**2 / (2 * popt[2]**2))
                   + popt[3] * erfc((x_fit - popt[1]) / (np.sqrt(2) * popt[2])))
        y_gauss = gaussian(x_fit, popt[0], popt[1], popt[2])
        y_erfc = popt[3] * erfc((x_fit - popt[1]) / (np.sqrt(2) * popt[2]))

        plt.plot(x_fit, y_total, 'r-', linewidth=2, label='Total Fit')
        plt.plot(x_fit, y_gauss, 'b--', linewidth=1.5, label='Gaussian Component')
        plt.plot(x_fit, y_erfc, 'g--', linewidth=1.5, label='erfc Component')

        gain0 = peak_x / Config.ENERGY_KEV_FACTOR
        param_text = (f"Gaussian + erfc Fit:\n"
                     f"A_gauss = {popt[0]:.2f} +/- {perr[0]:.2f}\n"
                     f"mu = {popt[1]:.4f}\n"
                     f"sigma = {popt[2]:.4f}\n"
                     f"A_erfc = {popt[3]:.2f} +/- {perr[3]:.2f}\n"
                     f"Peak x = {peak_x:.4f}\n"
                     f"Gain0(8KeV) = {gain0:.4f} [ADU/keV]")
        plt.text(0.05, 0.95, param_text, transform=plt.gca().transAxes,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
                fontsize=9)

        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.title(title)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, bbox_inches='tight')
            plt.close()
            print(f"Saved: {output_path}")
        else:
            plt.show()

    @staticmethod
    def plot_gain_heatmap(gain_img, frame_idx, output_path=None):
        """Plot 3-category gain map (Low/Mid/High).

        Args:
            gain_img: Gain code image (values 0-3).
            frame_idx: Frame index for title.
            output_path: Save path (None to display).
        """
        mapping = {3: 0, 1: 1, 0: 2, 2: 1}
        mapped = np.full(gain_img.shape, np.nan, dtype=float)
        for k, v in mapping.items():
            mapped[gain_img == k] = v

        cmap = ListedColormap(['#d62728', '#ff7f0e', '#1f77b4'])
        norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap.N)

        fig, ax = plt.subplots(figsize=(12, 6))
        im = ax.imshow(mapped, cmap=cmap, norm=norm, interpolation='nearest')
        ax.set_title(f"Gain map (frame {frame_idx}) - Low / Mid / High")
        ax.set_xlabel("col")
        ax.set_ylabel("row")
        ax.gca().invert_yaxis()

        cbar = fig.colorbar(im, ax=ax, ticks=[0, 1, 2])
        cbar.ax.set_yticklabels(['Low (11)', 'Mid (01/10)', 'High (00)'])
        cbar.set_label("Gain category")

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, bbox_inches='tight')
            plt.close(fig)
            print(f"Saved: {output_path}")
        else:
            plt.show()
