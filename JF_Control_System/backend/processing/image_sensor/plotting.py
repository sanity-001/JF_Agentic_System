"""
Plotly chart builders — convert numpy arrays to interactive Plotly figures.

All functions return go.Figure for use with st.plotly_chart().
"""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from ..core.config import Config


def build_heatmap(data, title, width=600, height=300, cmap="viridis",
                  xlabel="Pixel X", ylabel="Pixel Y", clabel="Value",
                  zmin=None, zmax=None):
    """2D array → go.Heatmap with colorbar. Y-axis inverted (sensor convention)."""
    vmin = zmin if zmin is not None else float(np.nanpercentile(data, 1))
    vmax = zmax if zmax is not None else float(np.nanpercentile(data, 99))

    fig = go.Figure(go.Heatmap(
        z=data,
        colorscale=cmap,
        zmin=vmin,
        zmax=vmax,
        colorbar=dict(title=clabel),
        hovertemplate="x: %{x}<br>y: %{y}<br>value: %{z:.2f}<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        width=width,
        height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_dark",
        paper_bgcolor=Config.UI_THEME_BG,
        plot_bgcolor=Config.UI_THEME_SURFACE,
        font=dict(color=Config.UI_TEXT_SECONDARY, size=10),
    )
    fig.update_yaxes(autorange="reversed")
    return fig


def build_histogram(data, title, bins=200, width=600, height=300,
                    xlabel="Value", ylabel="Counts", range_vals=None,
                    show_mean=True):
    """1D array → go.Histogram with optional mean line."""
    flat = np.asarray(data).flatten()
    flat = flat[~np.isnan(flat)]

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=flat,
        nbinsx=bins,
        xbins=dict(start=range_vals[0], end=range_vals[1]) if range_vals else None,
        marker_color=Config.UI_ACCENT,
        opacity=0.75,
        hovertemplate="Value: %{x:.2f}<br>Count: %{y}<extra></extra>",
    ))

    if show_mean and len(flat) > 0:
        mean_val = float(np.nanmean(flat))
        fig.add_vline(x=mean_val, line_dash="dash", line_color="#ef4444",
                     annotation_text=f"Mean: {mean_val:.2f}")

    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        width=width,
        height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_dark",
        paper_bgcolor=Config.UI_THEME_BG,
        plot_bgcolor=Config.UI_THEME_SURFACE,
        font=dict(color=Config.UI_TEXT_SECONDARY, size=10),
    )
    return fig


def build_fit_plot(bin_centers, hist, popt, perr, title,
                   width=400, height=350, xlabel="ADU", ylabel="Counts"):
    """Histogram + Gaussian fit curve + parameter annotation."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=bin_centers, y=hist,
        name="Data", marker_color="rgba(147,197,253,0.6)",
        hovertemplate="x: %{x:.2f}<br>count: %{y}<extra></extra>",
    ))

    x_fit = np.linspace(bin_centers.min(), bin_centers.max(), 500)
    y_fit = popt[0] * np.exp(-(x_fit - popt[1]) ** 2 / (2 * popt[2] ** 2))
    fig.add_trace(go.Scatter(
        x=x_fit, y=y_fit,
        name="Gaussian Fit", line=dict(color="#ef4444", width=2),
        hovertemplate="x: %{x:.2f}<br>fit: %{y:.1f}<extra></extra>",
    ))

    annotation = (
        f"A = {popt[0]:.1f} ± {perr[0]:.1f}<br>"
        f"μ = {popt[1]:.2f} ± {perr[1]:.2f}<br>"
        f"σ = {popt[2]:.2f} ± {perr[2]:.2f}"
    )
    fig.add_annotation(
        x=0.02, y=0.95, xref="paper", yref="paper",
        text=annotation, showarrow=False,
        bgcolor="rgba(30,41,59,0.9)", font=dict(color=Config.UI_TEXT_PRIMARY, size=10),
        align="left", borderpad=8,
    )

    fig.update_layout(
        title=title, xaxis_title=xlabel, yaxis_title=ylabel,
        width=width, height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_dark",
        paper_bgcolor=Config.UI_THEME_BG,
        plot_bgcolor=Config.UI_THEME_SURFACE,
        font=dict(color=Config.UI_TEXT_SECONDARY, size=10),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def build_erfc_fit_plot(bin_centers, hist, popt, perr, peak_x,
                        title="K-alpha Peak Fit", width=400, height=350,
                        xlabel="ADU (shifted)", ylabel="Counts"):
    """Histogram + Gaussian+erfc composite model with gain annotation."""
    from scipy.special import erfc

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=bin_centers, y=hist,
        name="Data", marker_color="rgba(134,239,172,0.5)",
        hovertemplate="x: %{x:.2f}<br>count: %{y}<extra></extra>",
    ))

    x_fit = np.linspace(bin_centers.min(), bin_centers.max(), 500)
    y_total = (popt[0] * np.exp(-(x_fit - popt[1]) ** 2 / (2 * popt[2] ** 2))
               + popt[3] * erfc((x_fit - popt[1]) / (np.sqrt(2) * popt[2])))
    y_gauss = popt[0] * np.exp(-(x_fit - popt[1]) ** 2 / (2 * popt[2] ** 2))
    y_erfc = popt[3] * erfc((x_fit - popt[1]) / (np.sqrt(2) * popt[2]))

    fig.add_trace(go.Scatter(x=x_fit, y=y_total, name="Total Fit",
                             line=dict(color="#ef4444", width=2)))
    fig.add_trace(go.Scatter(x=x_fit, y=y_gauss, name="Gaussian",
                             line=dict(color="#3b82f6", width=1.5, dash="dash")))
    fig.add_trace(go.Scatter(x=x_fit, y=y_erfc, name="erfc",
                             line=dict(color="#22c55e", width=1.5, dash="dash")))

    gain0 = peak_x / Config.ENERGY_KEV_FACTOR
    annotation = (
        f"A_gauss = {popt[0]:.2f} ± {perr[0]:.2f}<br>"
        f"μ = {popt[1]:.4f}<br>"
        f"σ = {popt[2]:.4f}<br>"
        f"A_erfc = {popt[3]:.2f} ± {perr[3]:.2f}<br>"
        f"Peak x = {peak_x:.4f}<br>"
        f"Gain = {gain0:.4f} ADU/keV"
    )
    fig.add_annotation(
        x=0.02, y=0.95, xref="paper", yref="paper",
        text=annotation, showarrow=False,
        bgcolor="rgba(30,41,59,0.9)", font=dict(color=Config.UI_TEXT_PRIMARY, size=9),
        align="left", borderpad=8,
    )

    fig.update_layout(
        title=title, xaxis_title=xlabel, yaxis_title=ylabel,
        width=width, height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_dark",
        paper_bgcolor=Config.UI_THEME_BG,
        plot_bgcolor=Config.UI_THEME_SURFACE,
        font=dict(color=Config.UI_TEXT_SECONDARY, size=10),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def build_side_by_side(data1, data2, title1, title2,
                       cmap="viridis", width=600, height=300,
                       clabel="Value", zmin=None, zmax=None):
    """Two heatmaps side by side in make_subplots 1×2."""
    vmin = zmin if zmin is not None else float(min(
        np.nanpercentile(data1, 1), np.nanpercentile(data2, 1)))
    vmax = zmax if zmax is not None else float(max(
        np.nanpercentile(data1, 99), np.nanpercentile(data2, 99)))

    fig = make_subplots(rows=1, cols=2, subplot_titles=[title1, title2],
                        horizontal_spacing=0.08)
    fig.add_trace(go.Heatmap(
        z=data1, colorscale=cmap, zmin=vmin, zmax=vmax,
        colorbar=dict(title=clabel, len=0.45, y=0.75),
        hovertemplate="x: %{x}<br>y: %{y}<br>value: %{z:.2f}<extra></extra>",
    ), row=1, col=1)
    fig.add_trace(go.Heatmap(
        z=data2, colorscale=cmap, zmin=vmin, zmax=vmax,
        colorbar=dict(title=clabel, len=0.45, y=0.25),
        hovertemplate="x: %{x}<br>y: %{y}<br>value: %{z:.2f}<extra></extra>",
    ), row=1, col=2)

    fig.update_layout(
        width=width, height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_dark",
        paper_bgcolor=Config.UI_THEME_BG,
        plot_bgcolor=Config.UI_THEME_SURFACE,
        font=dict(color=Config.UI_TEXT_SECONDARY, size=10),
    )
    fig.update_yaxes(autorange="reversed", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=1, col=2)
    return fig


def build_gain_overlay(gain_img, frame_idx, width=600, height=300):
    """3-category gain code heatmap (High/Mid/Low) with discrete colormap."""
    mapped = np.full(gain_img.shape, np.nan, dtype=float)
    mapped[gain_img == 3] = 0  # Low (red)
    mapped[gain_img == 1] = 1  # Mid (orange)
    mapped[gain_img == 0] = 2  # High (blue)
    mapped[gain_img == 2] = 1  # Also Mid

    colorscale = [
        [0.0, "#d62728"],    # Low
        [0.33, "#d62728"],
        [0.33, "#ff7f0e"],   # Mid
        [0.66, "#ff7f0e"],
        [0.66, "#1f77b4"],   # High
        [1.0, "#1f77b4"],
    ]

    fig = go.Figure(go.Heatmap(
        z=mapped,
        colorscale=colorscale,
        zmin=0, zmax=2,
        colorbar=dict(
            tickvals=[0.33, 1.0, 1.66],
            ticktext=["Low (11)", "Mid (01/10)", "High (00)"],
            title="Gain",
        ),
        hovertemplate="x: %{x}<br>y: %{y}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Gain Code Map — Frame {frame_idx}",
        xaxis_title="Pixel X",
        yaxis_title="Pixel Y",
        width=width, height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_dark",
        paper_bgcolor=Config.UI_THEME_BG,
        plot_bgcolor=Config.UI_THEME_SURFACE,
        font=dict(color=Config.UI_TEXT_SECONDARY, size=10),
    )
    fig.update_yaxes(autorange="reversed")
    return fig
