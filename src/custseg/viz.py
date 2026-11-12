"""Matplotlib house style shared by every figure (same palette as the Power BI report).

Rules: categorical hues in fixed slot order, never cycled; one hue light->dark for magnitude;
thin marks, recessive grid, text in ink colours (never the series colour), no dual axes.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = CATEGORICAL
SEQ_BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf",
            "#1c5cab", "#184f95", "#104281", "#0d366b"]
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
SURFACE, GRID, NEUTRAL = "#fcfcfb", "#e6e5e0", "#c3c2b7"
GOOD, WARNING, SERIOUS, CRITICAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"

BLUES = LinearSegmentedColormap.from_list("seq_blue", SEQ_BLUE)

# Segment identity colours (shared with Power BI). Checked on all colour pairs (OKLab delta-E, light mode):
# lightness/chroma/contrast PASS, normal-vision worst pair dE 18.7, CVD worst pair dE 7.9 (floor band -> segments are
# always direct-labelled). Colour follows the segment name, never its rank.
SEGMENT_PALETTE = {
    "At Risk": "#D9653B",          # terracotta coral - valuable but slipping away
    "Hibernating": "#C266C0",      # orchid - dormant
    "New Customers": "#139C85",    # teal - fresh
    "Loyal Customers": "#3558D4",  # royal indigo - proven repeaters
}
SEGMENT_FALLBACK = ["#D9653B", "#3558D4", "#139C85", "#C266C0"]


def setup() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlecolor": INK, "axes.titlesize": 11,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.labelsize": 9,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID,
        "grid.linewidth": 0.6, "axes.axisbelow": True, "xtick.color": MUTED, "ytick.color": MUTED,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8, "legend.frameon": False,
        "font.family": "DejaVu Sans", "lines.linewidth": 2, "figure.dpi": 110, "savefig.dpi": 140,
        "savefig.bbox": "tight", "axes.prop_cycle": matplotlib.cycler(color=CATEGORICAL),
    })


def save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def hbar(ax, labels, values, color=BLUE, fmt="{:,.0f}", title=None):
    """Horizontal bars, largest on top, value labels at bar end, value axis hidden."""
    y = range(len(labels))[::-1]
    ax.barh(list(y), values, color=color, height=0.68)
    ax.set_yticks(list(y), labels)
    ax.tick_params(axis="y", colors=INK2, length=0)
    ax.xaxis.set_visible(False)
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    vmax = max(values) if len(values) else 1
    for yi, v in zip(y, values):
        ax.text(v + vmax * 0.01, yi, fmt.format(v), va="center", fontsize=8, color=INK2)
    ax.set_xlim(0, vmax * 1.15)
    if title:
        ax.set_title(title)
    return ax


setup()
