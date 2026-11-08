"""
visualize.py
------------
Figures for the paper, built around the two scenario layers in scenarios.py
(3 audiences x 8 events = 24 scenarios). Everything is saved in results/.

  network.png     the building as a network
  evacuation.png  people out over time: students vs concert vs concert + CM (all runs)
  evacuation_events.png  people out over time: one panel per audience, one line per event
  compare_cm_cameras.png  students vs concert + Crowd Managers vs students + cameras
  summary.png     time until everyone (100%) and 95% are out, all 24 scenarios
  spread.png      last-out time over RUNS runs: one panel per audience, one box per event
  exits.png       people per exit A-H: students vs concert vs concert + CM

Run:  python visualize.py          (uses RUNS from scenarios.py, e.g. 20)
      python visualize.py 5        (quick version with 5 runs per scenario)
"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm, LinearSegmentedColormap

from building import INFO, NEXT, SEATS
from simulate import run, summary
from scenarios import AUDIENCES, EVENTS, SCENARIOS, RUNS, mean_and_ci

RESULTS = "results"
os.makedirs(RESULTS, exist_ok=True)
TOTAL = sum(SEATS.values())   # 1326 people
LIMIT = 180                   # required evacuation time (s)

# ---------------------------------------------------------------------------
# Style: blue / pink / black everywhere.
# ---------------------------------------------------------------------------
BLUE, PINK, BLACK = "#2a78d6", "#d6457f", "#1f1f24"   # the three colours of every figure
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
# each audience keeps its colour in every figure
AUDIENCE_COLOR = {"students": BLUE, "concert": PINK, "concert + CM": BLACK}
# heat maps: green = faster than 180 s, white = 180 s, red = slower
# (not blue/pink, so they are not mistaken for the audience colours)
GREEN_RED = LinearSegmentedColormap.from_list(
    "green_red", ["#1e6b3a", "#5aa469", "#f7f7f7", "#d9534f", "#8b1a1a"])

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.labelcolor": INK_2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.titlesize": 11, "axes.titlecolor": INK, "axes.titlelocation": "left",
    "font.size": 9, "legend.frameon": False, "legend.labelcolor": INK_2,
})


def name(audience, event):
    return f"{audience} | {event}"


def save(fig, filename):
    fig.savefig(os.path.join(RESULTS, filename), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("saved", os.path.join(RESULTS, filename))


# ---------------------------------------------------------------------------
# Run every scenario once here, and reuse the results in all figures
# ---------------------------------------------------------------------------
def run_all(runs):
    """results[scenario] = list of summaries (one per seed);
    curves[scenario] = list of sorted exit times, one list per seed (for the evacuation curves)."""
    results, curves = {}, {}
    for k, (scen, settings) in enumerate(SCENARIOS.items(), 1):
        print(f"  running {k}/{len(SCENARIOS)}: {scen}")
        results[scen], curves[scen] = [], []
        for s in range(runs):
            people = run(s, settings)
            results[scen].append(summary(people))
            curves[scen].append(sorted(p.t_exit for p in people if p.t_exit is not None))
    return results, curves


# ---------------------------------------------------------------------------
# 1. The network
# ---------------------------------------------------------------------------
def spread_column(names, x, top, bottom):
    return {n: (x, top - k * (top - bottom) / max(len(names) - 1, 1))
            for k, n in enumerate(names)}


def draw_network():
    pos = {}
    pos.update(spread_column([f"S{i}" for i in range(1, 17)], 1, 1.0, 0.25))
    pos.update(spread_column(["X", "Y", "Z", "W"], 1, 0.08, -0.25))
    pos.update(spread_column([f"S{i}" for i in range(17, 23)], 0, 0.12, -0.3))
    pos.update(spread_column(list("ABCDEFGH"), 3, 1.0, -0.25))

    fig, ax = plt.subplots(figsize=(10, 8))
    for a in NEXT:
        for b in NEXT[a]:
            ax.annotate("", xy=pos[b], xytext=pos[a],
                        arrowprops=dict(arrowstyle="->", color=AXIS, lw=0.7,
                                        shrinkA=10, shrinkB=10))
    colors = {"spot": "#9a8aa6", "stair": "#9b9a97", "exit": "#8fa58c"}   # Morandi purple / gray / green
    for n, (x, y) in pos.items():
        kind = INFO[n]["kind"]
        size = 60 + 3 * SEATS.get(n, 0) if kind == "spot" else 300
        ax.scatter(x, y, s=size, color=colors[kind], edgecolor="white", linewidth=1.5, zorder=3)
        ax.text(x, y, n, ha="center", va="center", fontsize=7, color="white", zorder=4)
    for x, y, label in [(1, 1.07, "Floor-1 spots"), (1, 0.15, "Stairs (land in floor-1 spots)"),
                        (0, 0.19, "Balcony spots"), (3, 1.07, "Exits")]:
        ax.text(x, y, label, ha="center", fontsize=10, color=INK_2)
    ax.set_xlim(-0.4, 3.4)
    ax.set_ylim(-0.36, 1.12)
    ax.axis("off")
    ax.set_title("Bailey Hall as a network (dot size = people starting there)")
    save(fig, "network.png")


# ---------------------------------------------------------------------------
# 2. People out over time: the three audiences (no event), over ALL runs.
#    Line = median run-to-run count at each time; band = fastest to slowest run.
# ---------------------------------------------------------------------------
def until_done(y):
    """Index just after the first point where y reaches TOTAL (everyone out),
    so a curve can be cut there instead of running flat along the top."""
    full = np.nonzero(y >= TOTAL)[0]
    return full[0] + 1 if len(full) else len(y)


def draw_evacuation(curves):
    grid = np.arange(0, max(max(c[-1] for c in curves[name(a, "no event")])
                            for a in AUDIENCES) + 10, 0.5)       # times to evaluate (s)
    fig, (ax, zoom) = plt.subplots(1, 2, figsize=(12, 5), width_ratios=[3, 2])
    for aud in AUDIENCES:
        runs_ = curves[name(aud, "no event")]
        # people out by time t, for every run: count of exit times <= t
        out = np.array([np.searchsorted(times, grid, side="right") for times in runs_])
        last = [times[-1] for times in runs_ if len(times) == TOTAL]   # 100% time (complete runs)
        color = AUDIENCE_COLOR[aud]
        med = np.median(out, axis=0)
        n_band = until_done(out.min(axis=0))     # band ends when the slowest run is done
        n_med = until_done(med)                  # line ends when the median run is done
        for a_ in (ax, zoom):                                    # same curves in both panels
            a_.fill_between(grid[:n_band], out.min(axis=0)[:n_band], out.max(axis=0)[:n_band],
                            color=color, alpha=0.2, lw=0)
            a_.plot(grid[:n_med], med[:n_med], color=color, lw=2.2,
                    label=f"{aud}: {np.mean(last):.0f} s",
                    solid_capstyle="round")

    # reference lines: everyone out (top) and the 180 s requirement
    ref = dict(color=MUTED, ls=(0, (4, 3)), lw=1, zorder=1)
    for a_ in (ax, zoom):
        a_.axhline(TOTAL, **ref)
        a_.axvline(LIMIT, **ref)
        a_.set_xlabel("Time since alarm (s)")
    ax.text(2, TOTAL + 12, f"all {TOTAL} people out", fontsize=9, color=INK_2, va="bottom")
    ax.text(LIMIT - 3, TOTAL * 0.04, f"{LIMIT} s requirement", ha="right",
            fontsize=9, color=INK_2)

    ax.set_xlim(0, grid[-1])
    ax.set_ylim(0, TOTAL * 1.08)
    ax.set_ylabel("People out of the building")
    ax.set_title(f"All {TOTAL} people, no event")
    ax.legend(loc="lower right", bbox_to_anchor=(1, 0.1), handlelength=1.8,
              title="everyone out (average)", title_fontsize=9, alignment="left",
              frameon=True, facecolor="white", edgecolor="none", framealpha=1)

    # zoom: the last 100 people, where the 180 s requirement is decided
    zoom.set_xlim(140, grid[-1])
    zoom.set_ylim(TOTAL - 100, TOTAL + 5)
    zoom.set_title("Zoom: the last 100 people")
    zoom.text(LIMIT + 1.5, TOTAL - 96, f"{LIMIT} s", fontsize=9, color=INK_2)

    fig.suptitle(f"Evacuation over {len(runs_)} runs: line = median, "
                 "band = fastest to slowest run", x=0.01, ha="left", fontsize=12, color=INK)
    save(fig, "evacuation.png")


# ---------------------------------------------------------------------------
# 2b. People out over time for every event: one panel per audience,
#     one line per event (median over the runs), "no event" in black as reference
# ---------------------------------------------------------------------------
# one colour per event (colourblind-safe); "no event" = black reference line
EVENT_PALETTE = ["#4c9be8", "#5cb88a", "#d65db1", "#e9b949", "#e76f51", "#9b72cf", "#8c5a3c"]
EVENT_COLOR = {}
for k, e in enumerate(e for e in EVENTS if e != "no event"):
    EVENT_COLOR[e] = EVENT_PALETTE[k % len(EVENT_PALETTE)]
EVENT_COLOR["no event"] = BLACK
EVENT_COLOR["LED"] = "#d65db1"       # pink
EVENT_COLOR["cameras"] = "#5cb88a"   # green


def draw_evacuation_events(curves):
    grid = np.arange(0, max(max(c[-1] for c in curves[s]) for s in SCENARIOS) + 10, 0.5)
    fig, axes = plt.subplots(1, len(AUDIENCES), figsize=(15, 4.8), sharex=True, sharey=True)
    for ax, aud in zip(axes, AUDIENCES):
        for ev in EVENTS:
            runs_ = curves[name(aud, ev)]
            out = np.array([np.searchsorted(times, grid, side="right") for times in runs_])
            med = np.median(out, axis=0)
            n = until_done(med)                  # stop the line once everyone is out
            ax.plot(grid[:n], med[:n], color=EVENT_COLOR[ev],
                    lw=1.5 if ev == "no event" else 2.4, label=ev, alpha=1 if ev == "no event" else 0.9,
                    solid_capstyle="round",
                    zorder=5 if ev == "no event" else 2)    # reference line on top
        ax.axhline(TOTAL, color=MUTED, ls=(0, (4, 3)), lw=1, zorder=1)
        ax.axvline(LIMIT, color=MUTED, ls=(0, (4, 3)), lw=1, zorder=1)
        ax.text(LIMIT + 4, TOTAL * 0.04, f"{LIMIT} s", fontsize=8, color=INK_2)
        ax.set_title(aud)
        ax.set_xlabel("Time since alarm (s)")
        ax.set_xlim(0, grid[-1])
        ax.set_ylim(0, TOTAL * 1.05)
    axes[0].set_ylabel("People out of the building")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(EVENTS), fontsize=9,
               bbox_to_anchor=(0.5, -0.07))
    fig.suptitle(f"Evacuation by event (median of {len(runs_)} runs per scenario)",
                 x=0.01, ha="left", fontsize=12, color=INK)
    save(fig, "evacuation_events.png")


# ---------------------------------------------------------------------------
# 2c. Students vs concert + CM (no event) vs students + cameras: people out over time,
#     line = median, band = fastest to slowest run (like evacuation.png)
# ---------------------------------------------------------------------------
GREEN = "#2e9e5b"
COMPARE = [("students", "no event", "students", BLUE),
           ("concert + CM", "no event", "concert + CM", BLACK),
           ("students", "cameras", "students + cameras", GREEN)]


def draw_compare(curves, results):
    grid = np.arange(0, max(max(c[-1] for c in curves[name(a, e)])
                            for a, e, _, _ in COMPARE) + 10, 0.5)
    fig, (ax, zoom) = plt.subplots(1, 2, figsize=(12, 5), width_ratios=[3, 2])
    for aud, ev, label, color in COMPARE:
        runs_ = curves[name(aud, ev)]
        out = np.array([np.searchsorted(times, grid, side="right") for times in runs_])
        med = np.median(out, axis=0)
        n_band = until_done(out.min(axis=0))
        n_med = until_done(med)
        t100, _ = mean_and_ci([r["t_last"] for r in results[name(aud, ev)]])
        t95, _ = mean_and_ci([r["t_95"] for r in results[name(aud, ev)]])
        for a_ in (ax, zoom):
            a_.fill_between(grid[:n_band], out.min(axis=0)[:n_band], out.max(axis=0)[:n_band],
                            color=color, alpha=0.2, lw=0)
            a_.plot(grid[:n_med], med[:n_med], color=color, lw=2.2, solid_capstyle="round",
                    label=f"{label}: {t100:.0f} s (95%: {t95:.0f} s)")
    ref = dict(color=MUTED, ls=(0, (4, 3)), lw=1, zorder=1)
    for a_ in (ax, zoom):
        a_.axhline(TOTAL, **ref)
        a_.axvline(LIMIT, **ref)
        a_.set_xlabel("Time since alarm (s)")
    ax.text(2, TOTAL + 12, f"all {TOTAL} people out", fontsize=9, color=INK_2, va="bottom")
    ax.text(LIMIT - 3, TOTAL * 0.04, f"{LIMIT} s requirement", ha="right",
            fontsize=9, color=INK_2)
    ax.set_xlim(0, grid[-1])
    ax.set_ylim(0, TOTAL * 1.08)
    ax.set_ylabel("People out of the building")
    ax.set_title(f"All {TOTAL} people")
    ax.legend(loc="lower right", bbox_to_anchor=(1, 0.1), handlelength=1.8,
              title="everyone out (average)", title_fontsize=9, alignment="left",
              frameon=True, facecolor="white", edgecolor="none", framealpha=1)
    zoom.set_xlim(140, grid[-1])
    zoom.set_ylim(TOTAL - 100, TOTAL + 5)
    zoom.set_title("Zoom: the last 100 people")
    zoom.text(LIMIT + 1.5, TOTAL - 96, f"{LIMIT} s", fontsize=9, color=INK_2)
    fig.suptitle(f"Students vs concert + Crowd Managers vs students + cameras ({len(runs_)} runs: "
                 "line = median, band = fastest to slowest run)", x=0.01, ha="left",
                 fontsize=12, color=INK)
    save(fig, "compare_cm_cameras.png")


# ---------------------------------------------------------------------------
# 3. All results in two grids: time until EVERYONE is out (100%) and until 95%
#    are out. Colored by distance from 180 s (green = under, red = over).
# ---------------------------------------------------------------------------
def draw_summary(results, runs):
    auds, evs = list(AUDIENCES), list(EVENTS)
    panels = [("t_last", "Everyone out (100%)"), ("t_95", "95% out")]
    stats = {}
    for key, _ in panels:
        stats[key] = [[mean_and_ci([r[key] for r in results[name(a, e)]]) for e in evs]
                      for a in auds]
    allv = [m for key, _ in panels for row in stats[key] for m, _ in row]
    norm = TwoSlopeNorm(vcenter=LIMIT, vmin=min(min(allv), LIMIT - 1),
                        vmax=max(max(allv), LIMIT + 1))       # same colors in both grids

    fig, axes = plt.subplots(2, 1, figsize=(12.5, 6.4))
    for ax, (key, title) in zip(axes, panels):
        mean = [[m for m, _ in row] for row in stats[key]]
        im = ax.imshow(mean, cmap=GREEN_RED, norm=norm, aspect="auto")
        for i in range(len(auds)):
            for j in range(len(evs)):
                m, ci = stats[key][i][j]
                dark = abs(norm(m) - 0.5) > 0.3
                ax.text(j, i, f"{m:.0f} s\n\u00b1{ci:.0f}", ha="center", va="center",
                        fontsize=9, color="white" if dark else INK)
        ax.set_xticks(range(len(evs)))
        ax.set_xticklabels(evs)
        ax.set_yticks(range(len(auds)))
        ax.set_yticklabels(auds)
        ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(title)
    cbar = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02)
    cbar.set_label("seconds; white = 180 s", color=INK_2)
    cbar.outline.set_visible(False)
    fig.suptitle(f"All {len(SCENARIOS)} scenarios (mean \u00b1 95% CI of {runs} runs)", x=0.01, ha="left",
                 fontsize=12, color=INK)
    save(fig, "summary.png")


# ---------------------------------------------------------------------------
# 4. Spread over runs: last-out time, one panel per audience, one box per event
# ---------------------------------------------------------------------------
# box fill per audience: concert + CM uses a mid grey instead of black,
# so its boxes read like the blue and pink ones (with a dark median line)
BOX_COLOR = {"students": BLUE, "concert": PINK, "concert + CM": "#8b8b96"}


def draw_spread(results, runs):
    fig, axes = plt.subplots(1, len(AUDIENCES), figsize=(14, 4.6), sharey=True)
    for ax, aud in zip(axes, AUDIENCES):
        data = [[r["t_last"] for r in results[name(aud, ev)] if r["t_last"] is not None]
                for ev in EVENTS]                     # incomplete runs left out
        box = ax.boxplot(data, patch_artist=True, widths=0.6,
                         medianprops=dict(color=INK, lw=1.4),
                         whiskerprops=dict(color=MUTED), capprops=dict(color=MUTED),
                         flierprops=dict(marker="o", markersize=4, markerfacecolor="none",
                                         markeredgecolor=MUTED))
        for patch in box["boxes"]:
            patch.set_facecolor(BOX_COLOR[aud])
            patch.set_alpha(0.85)
            patch.set_edgecolor(BOX_COLOR[aud])   # same as the fill: short boxes stay visible
        ax.set_xticks(range(1, len(EVENTS) + 1))
        ax.set_xticklabels(list(EVENTS), rotation=35, ha="right")
        ax.axhline(LIMIT, color=INK_2, ls=(0, (4, 3)), lw=1)
        ax.grid(axis="x", visible=False)
        ax.set_title(aud, color=AUDIENCE_COLOR[aud])
    axes[0].set_ylabel("Last person out (s)")
    fig.suptitle(f"Last-out time over {runs} runs (dashed line = {LIMIT} s)", x=0.01,
                 ha="left", fontsize=12, color=INK)
    save(fig, "spread.png")


# ---------------------------------------------------------------------------
# 5. People per exit A-H: the three audiences (no event), average over the runs
# ---------------------------------------------------------------------------
def draw_exits(results):
    exits = list("ABCDEFGH")
    auds = list(AUDIENCES)
    width = 0.8 / len(auds)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for k, aud in enumerate(auds):
        rs = results[name(aud, "no event")]
        avg = [sum(r["exit_use"].get(e, 0) for r in rs) / len(rs) for e in exits]
        x = [i + (k - (len(auds) - 1) / 2) * width for i in range(len(exits))]
        ax.bar(x, avg, width=width * 0.9, color=AUDIENCE_COLOR[aud], label=aud)
    ax.set_xticks(range(len(exits)))
    ax.set_xticklabels(exits)
    ax.grid(axis="x", visible=False)
    ax.set_xlabel("Exit")
    ax.set_ylabel("People (average over runs)")
    ax.set_title("People per exit, no event")
    ax.legend(loc="upper right")
    save(fig, "exits.png")


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else RUNS
    print(f"Running all {len(SCENARIOS)} scenarios, {runs} runs each ...")
    results, curves = run_all(runs)
    draw_network()
    draw_evacuation(curves)
    draw_evacuation_events(curves)
    draw_compare(curves, results)
    draw_summary(results, runs)
    draw_spread(results, runs)
    draw_exits(results)
