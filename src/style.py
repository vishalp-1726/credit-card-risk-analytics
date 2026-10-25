"""One chart style for the whole project, so every chart looks the same."""
import matplotlib.pyplot as plt

# colours, always used in this order (colour-blind safe)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
# a channel always gets the same colour; co-brand is always yellow
CHANNEL_COLORS = {"Branch": SERIES[0], "DSA": SERIES[1], "Digital": SERIES[2], "Fintech Co-brand": SERIES[3]}
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]   # light to dark
BACKGROUND, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"


def apply_style():
    plt.rcParams.update({
        "figure.facecolor": BACKGROUND, "axes.facecolor": BACKGROUND, "savefig.facecolor": BACKGROUND,
        "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
        "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
        "xtick.color": INK_2, "ytick.color": INK_2, "font.size": 10,
        "lines.linewidth": 2, "legend.frameon": False, "figure.dpi": 110,
        "axes.prop_cycle": plt.cycler(color=SERIES),
    })


def save(fig, name):
    """Save a chart as reports/figures/<name>.png."""
    from src.config import FIGURES
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.png", bbox_inches="tight", dpi=150)
    print(f"saved reports/figures/{name}.png")
