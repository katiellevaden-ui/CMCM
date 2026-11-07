"""
visualize.py
------------
Pictures for the paper. Each function saves one PNG in the results/ folder.

  network.png     the building as a network (nodes = places, arrows = where you can go)
  evacuation.png  people out over time, one line per scenario
  exits.png       people per exit, one group of bars per scenario
  spread.png      last-out time over many runs, one box per scenario

Scenarios come from scenarios.py: add one there and it shows up here automatically.
Run:  python visualize.py
"""
import os

import matplotlib.pyplot as plt

from building import INFO, NEXT, SEATS
from simulate import run, summary
from scenarios import SCENARIOS, RUNS

RESULTS = "results"           # all pictures are saved in this folder
os.makedirs(RESULTS, exist_ok=True)   # create it if it doesn't exist yet

TOTAL = sum(SEATS.values())   # 1326 people
LIMIT = 180                   # required evacuation time (s)

# -----------------------------------------------------------------------------
# Style: a colorblind-safe palette, used in a FIXED order.
# Each scenario keeps the same color in every plot (color follows the scenario).
# -----------------------------------------------------------------------------
PALETTE = [
    "#6668E2", "#CF568C","#E4954F","#303039",
    "#5433E5", "#F58CC8","#378744","#3D7BD7",
]
INK, INK_2, MUTED = "#25232B", "#514D59", "#77727D"
GRID, AXIS = "#EAE7ED", "#B8B2BF"                   

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True,
    "axes.labelcolor": INK_2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.titlesize": 12, "axes.titleweight": "normal", "axes.titlecolor": INK,
    "axes.titlelocation": "left", "font.size": 10,
    "legend.frameon": False, "legend.labelcolor": INK_2,
})


def scenario_color(name):
    """Color of a scenario = its position in SCENARIOS (never changes between plots)."""
    return PALETTE[list(SCENARIOS).index(name) % len(PALETTE)]


def limit_line(ax, vertical=True):
    """The 180 s requirement, as a quiet dashed line with a label."""
    if vertical:
        ax.axvline(LIMIT, color=INK_2, ls=(0, (4, 3)), lw=1)
    else:
        ax.axhline(LIMIT, color=INK_2, ls=(0, (4, 3)), lw=1)


# -----------------------------------------------------------------------------
# 1. The network
#    Top: floor-1 spots -> exits.   Bottom: balcony spots -> stairs -> exits.
# -----------------------------------------------------------------------------
def spread(names, x, top, bottom):
    """Place nodes evenly in a column from y=top to y=bottom."""
    return {n: (x, top - k * (top - bottom) / max(len(names) - 1, 1))
            for k, n in enumerate(names)}


def draw_network():
    floor1 = [f"S{i}" for i in range(1, 17)]
    balcony = [f"S{i}" for i in range(17, 23)]
    stairs = ["X", "Y", "Z", "W"]
    exits = list("ABCDEFGH")

    pos = {}
    pos.update(spread(floor1, 1, 1.0, 0.25))      # floor 1, upper part
    pos.update(spread(stairs, 1, 0.08, -0.25))    # stairs, below floor 1
    pos.update(spread(balcony, 0, 0.12, -0.3))    # balcony, left of the stairs
    pos.update(spread(exits, 3, 1.0, -0.25))      # exits, right

    fig, ax = plt.subplots(figsize=(10, 8))

    # arrows: every "where can I go next" in NEXT
    for a in NEXT:
        for b in NEXT[a]:
            ax.annotate("", xy=pos[b], xytext=pos[a],
                        arrowprops=dict(arrowstyle="->", color=AXIS, lw=0.7,
                                        shrinkA=10, shrinkB=10))

    # nodes: spot size = number of people who start there
    colors = {"spot": PALETTE[0], "stair": PALETTE[6], "exit": PALETTE[1]}
    for name, (x, y) in pos.items():
        kind = INFO[name]["kind"]
        size = 60 + 3 * SEATS.get(name, 0) if kind == "spot" else 300
        ax.scatter(x, y, s=size, color=colors[kind], edgecolor="white", linewidth=1.5, zorder=3)
        ax.text(x, y, name, ha="center", va="center", fontsize=7, color="white", zorder=4)

    for x, y, label in [(1, 1.07, "Floor-1 spots"), (1, 0.15, "Stairs"),
                        (0, 0.19, "Balcony spots"), (3, 1.07, "Exits")]:
        ax.text(x, y, label, ha="center", fontsize=10, color=INK_2)
    ax.set_xlim(-0.4, 3.4)
    ax.set_ylim(-0.36, 1.12)
    ax.axis("off")
    ax.set_title("Bailey Hall as a network (dot size = people starting there)")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "network.png"), dpi=150)
    plt.close(fig)
    print("saved results/network.png")


# -----------------------------------------------------------------------------
# 2. People out over time, one line per scenario (one run each, seed 0)
# -----------------------------------------------------------------------------
def draw_evacuation_curves(names=None):
    names = names or list(SCENARIOS)
    fig, ax = plt.subplots(figsize=(8, 5))
    for name in names:
        people = run(0, SCENARIOS[name])
        times = sorted(p.t_exit for p in people if p.t_exit is not None)
        ax.step(times, range(1, len(times) + 1), where="post",
                color=scenario_color(name), lw=2, label=name)

    limit_line(ax)
    ax.text(LIMIT + 3, TOTAL * 0.04, f"{LIMIT} s requirement", fontsize=9, color=INK_2)
    ax.set_ylim(0, TOTAL * 1.05)
    ax.set_xlabel("Time since alarm (s)")
    ax.set_ylabel("People out of the building")
    ax.set_title(f"Evacuation of {TOTAL} people (one run per scenario)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "evacuation.png"), dpi=150)
    plt.close(fig)
    print("saved results/evacuation.png")


# -----------------------------------------------------------------------------
# 3. People per exit, one group of bars per scenario (one run each, seed 0)
#    With many scenarios, pass only the ones to compare: draw_exit_use(["normal", ...])
# -----------------------------------------------------------------------------
def draw_exit_use(names=None):
    names = names or list(SCENARIOS)
    exits = list("ABCDEFGH")
    width = 0.8 / len(names)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for k, name in enumerate(names):
        use = summary(run(0, SCENARIOS[name]))["exit_use"]
        x = [i + (k - (len(names) - 1) / 2) * width for i in range(len(exits))]
        ax.bar(x, [use.get(e, 0) for e in exits], width=width * 0.9,
               color=scenario_color(name), label=name)

    ax.set_xticks(range(len(exits)))
    ax.set_xticklabels(exits)
    ax.grid(axis="x", visible=False)
    ax.set_xlabel("Exit")
    ax.set_ylabel("People")
    ax.set_title("People per exit (one run per scenario)")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "exits.png"), dpi=150)
    plt.close(fig)
    print("saved results/exits.png")


# -----------------------------------------------------------------------------
# 4. Spread over many runs: last-out time, one box per scenario
#    (shows how much the result varies with random reaction times and choices)
# -----------------------------------------------------------------------------
def draw_spread(names=None, runs=RUNS):
    names = names or list(SCENARIOS)
    data = [[summary(run(seed, SCENARIOS[name]))["t_last"] for seed in range(runs)]
            for name in names]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    box = ax.boxplot(data, patch_artist=True, widths=0.5,
                     medianprops=dict(color=INK, lw=1.5),
                     whiskerprops=dict(color=MUTED), capprops=dict(color=MUTED),
                     flierprops=dict(marker="o", markersize=5, markerfacecolor="none",
                                     markeredgecolor=MUTED))
    for patch, name in zip(box["boxes"], names):
        patch.set_facecolor(scenario_color(name))
        patch.set_alpha(0.8)
        patch.set_edgecolor("white")

    ax.set_xticks(range(1, len(names) + 1))
    ax.set_xticklabels(names)
    ax.grid(axis="x", visible=False)
    limit_line(ax, vertical=False)
    ax.text(len(names) + 0.45, LIMIT + 4, f"{LIMIT} s requirement",
            ha="right", fontsize=9, color=INK_2)
    ax.set_ylim(min(LIMIT - 15, min(map(min, data)) - 10), max(map(max, data)) + 15)
    ax.set_ylabel("Last person out (s)")
    ax.set_title(f"Last-out time over {runs} runs")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "spread.png"), dpi=150)
    plt.close(fig)
    print("saved results/spread.png")


if __name__ == "__main__":
    draw_network()
    draw_evacuation_curves()
    draw_exit_use()
    draw_spread()
