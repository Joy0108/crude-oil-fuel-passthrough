"""One consistent, quiet chart style for every figure in the report."""
import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from config import END_MONTH, MARKET_REGIME_END  # noqa: E402

# Validated categorical slots 1-3 (blue, orange, aqua) + neutral chrome
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE, REGIME_FILL = "#e1e0d9", "#c3c2b7", "#fcfcfb", "#f0efec"

DAILY_PRICING_START = pd.Timestamp("2017-06-16")
ADMINISTERED_START = pd.Timestamp(MARKET_REGIME_END) + pd.offsets.MonthBegin(1)
STUDY_END = pd.Timestamp(END_MONTH) + pd.offsets.MonthEnd(0)


def apply_style() -> None:
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 10,
        "text.color": INK, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
        "axes.titlesize": 11.5, "axes.titleweight": "semibold", "axes.titlelocation": "left",
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.6,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
        "lines.linewidth": 2.0, "legend.frameon": False, "legend.fontsize": 9,
        "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight",
    })


def mark_regimes(ax, label: bool = True) -> None:
    """Shade the administered-pricing era and mark the switch to daily pricing."""
    ax.axvspan(ADMINISTERED_START, STUDY_END, color=REGIME_FILL, zorder=0, lw=0)
    ax.axvline(DAILY_PRICING_START, color=AXIS, lw=0.9, zorder=1)
    if label:
        y = ax.get_ylim()[1]
        ax.text(DAILY_PRICING_START, y, " daily pricing", color=MUTED, fontsize=8, va="top")
        ax.text(ADMINISTERED_START, y, " administered pricing", color=MUTED, fontsize=8, va="top")


def year_axis(ax) -> None:
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
