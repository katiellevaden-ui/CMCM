"""
Sensitivity and robustness tests for the Bailey Hall evacuation model. (Assisted by Claude)
(We wrote the prompt for this)
PART 1  SENSITIVITY (one input at a time, everything else at baseline)
    Baseline = "students | no event". Each test changes ONE input and reruns the
    same seeds, so the difference comes from the input, not from luck
    (common random numbers). Tests:
        power beta           0.05, 0.072 (-10%), 0.088 (+10%), 0.30      (baseline 0.08)
        reaction time        concert's lognormal instead of the students'
        reaction cap         20 s, -10%, +10%, 200 s, no cap            (baseline 26 s)
        stair descent        concert stair time 20.455 s                  (baseline 9.278 s)
        walking speed        -10%, +10%, concert speed 1.056              (baseline 1.321 m/s)
        door flow            -10%, +10% (SFPE coefficient 1.316)
        all distances        -10%, +10% (measurement error)
        wheelchair hold      7.42 s (-10%), 9.08 s (+10%)   vs "students | wheelchair at D" (8.25 s)
        LED speed-up         2.83% (-10%), 3.45% (+10%), 7.7% (old value)
                                                            vs "students | LED" (3.14%)
    -> results/sensitivity.csv, results/sensitivity_tornado.png
 
PART 2  ROBUSTNESS (do the conclusions survive?)
    a) number of runs : how the 95% CI of "everyone out" shrinks with more runs
    b) time step      : DT = 0.5, 0.25, 0.1 s give the same answer
    c) everything at once (Monte Carlo): draw N random combinations of the uncertain
       inputs (power, walking speed, reaction mean, cap +-10%, door flow, each distance)
       and rerun students / concert / concert + CM (no event) with each combination.
       Checks: share of combinations under 180 s, and whether concert + CM is still
       faster than concert.
    -> results/robustness.csv, results/robustness.png
 
Run:  python test.py          (full: about 1,240 runs; 5-20 min depending on cores)
      python test.py quick    (a few minutes, fewer runs; for checking the code)
"""
import copy
import csv
import math
import os
import random
import sys
from multiprocessing import Pool
 
import matplotlib
matplotlib.use("Agg")                     # save PNGs without opening windows
import matplotlib.pyplot as plt
 
import building
import simulate
from scenarios import SCENARIOS, AUDIENCES, mean_and_ci, incomplete
from building import STAIR_TIME_CONCERT
 
# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
QUICK = len(sys.argv) > 1 and sys.argv[1] == "quick"
RUNS = 5 if QUICK else 20          # seeds per sensitivity test
RUNS_CURVE = 20 if QUICK else 60   # seeds for the "number of runs" check
RUNS_DT = 3 if QUICK else 10       # seeds per time step
MC_DRAWS = 8 if QUICK else 30      # random input combinations (Monte Carlo)
MC_SEEDS = 3 if QUICK else 5       # seeds per combination
LIMIT = 180                        # required evacuation time (s)
RESULTS = "results"
os.makedirs(RESULTS, exist_ok=True)
 
BASE = "students | no event"
BASE_SET = SCENARIOS[BASE]
 
# ---------------------------------------------------------------------------
# Changing building inputs (door flow, distances) that are not scenario settings.
# simulate.py uses the SAME dictionaries as building.py, so we change the numbers
# inside them, run, and put the original numbers back afterwards.
# ---------------------------------------------------------------------------
ORIGINAL = {
    "NEXT": copy.deepcopy(building.NEXT),
    "CM_NEXT": copy.deepcopy(building.CM_NEXT),
    "CAMERA_NEXT": copy.deepcopy(building.CAMERA_NEXT),
    "WALL_DIST": copy.deepcopy(building.WALL_DIST),
    "INFO": copy.deepcopy(building.INFO),
}
WALK_NODES = list(building.SPOT_EXITS) + list(building.BALCONY_STAIRS)   # not stairs
 
 
def restore():
    """Put every changed number back to the value building.py computed."""
    for name in ("NEXT", "CM_NEXT", "CAMERA_NEXT", "WALL_DIST"):
        table = getattr(building, name)
        for key, value in ORIGINAL[name].items():
            if isinstance(value, dict):
                table[key].update(value)
            else:
                table[key] = value
    for node, info in ORIGINAL["INFO"].items():
        building.INFO[node].update(info)
 
 
def change_building(door_factor=1.0, dist_factor=None):
    """door_factor: multiply every exit's flow (and shorten its t_pass).
    dist_factor: one number (all distances) or a dict {(a, b): factor} per edge."""
    restore()
    if door_factor != 1.0:
        for node, info in building.INFO.items():
            if info["kind"] == "exit":
                info["flow"] = ORIGINAL["INFO"][node]["flow"] * door_factor
                info["t_pass"] = ORIGINAL["INFO"][node]["t_pass"] / door_factor
    if dist_factor is not None:
        def f(a, b):
            if isinstance(dist_factor, dict):
                return dist_factor.get((a, b), 1.0)
            return dist_factor
        for a in WALK_NODES:
            for b in building.NEXT[a]:
                building.NEXT[a][b] = ORIGINAL["NEXT"][a][b] * f(a, b)
        for table in ("CM_NEXT", "CAMERA_NEXT"):
            for a, row in getattr(building, table).items():
                for b in row:
                    row[b] = ORIGINAL[table][a][b] * f(a, b)
        for pair in building.WALL_DIST:
            building.WALL_DIST[pair] = ORIGINAL["WALL_DIST"][pair] * f(*pair)
 
 
# ---------------------------------------------------------------------------
# One job = one scenario with some changes, run for a list of seeds.
# Jobs are spread over the computer's cores (multiprocessing.Pool).
# ---------------------------------------------------------------------------
def run_job(job):
    """job = (key, settings, seeds, door_factor, dist_factor, dt).
    Returns (key, [summary of each seed])."""
    key, settings, seeds, door_factor, dist_factor, dt = job
    change_building(door_factor, dist_factor)
    simulate.DT = dt
    out = [simulate.summary(simulate.run(s, settings)) for s in seeds]
    simulate.DT = 0.25
    restore()
    return key, out
 
 
def job(key, settings, seeds, door=1.0, dist=None, dt=0.25):
    return (key, settings, list(seeds), door, dist, dt)
 
 
def paired(values, base):
    """Mean and 95% CI of the per-seed difference (same seeds in both lists).
    Seeds where either run is incomplete (None) are left out."""
    return mean_and_ci([v - b for v, b in zip(values, base)
                        if v is not None and b is not None])


def under(values):
    """Share of runs that got everyone out within LIMIT (incomplete runs count as no)."""
    return sum(v is not None and v <= LIMIT for v in values) / len(values)
 
 
# ---------------------------------------------------------------------------
# PART 1: the sensitivity tests
# ---------------------------------------------------------------------------
def sensitivity_tests():
    """(group, label, baseline scenario, changed settings, door, dist)"""
    s = BASE_SET
    concert = AUDIENCES["concert"]
    wheel = SCENARIOS["students | wheelchair at D"]
    led = SCENARIOS["students | LED"]
    h = wheel["hold"]["D"]
    sf = led["speed_factor"] - 1
    cap = s["react_cap"]                  # the students' own cap (scenarios.py)
    tests = [
        ("Power β (0.08)", "β = 0.05", BASE, {**s, "power": 0.05}),
        ("Power β (0.08)", "β = 0.072 (−10%)", BASE, {**s, "power": 0.072}),
        ("Power β (0.08)", "β = 0.088 (+10%)", BASE, {**s, "power": 0.088}),
        ("Power β (0.08)", "β = 0.30", BASE, {**s, "power": 0.30}),
        ("Reaction time", "concert lognormal (mean 32.5 s)", BASE,
         {**s, "react_mu": concert["react_mu"], "react_sigma": concert["react_sigma"]}),
        (f"Reaction cap ({cap:g} s)", "cap 20 s", BASE, {**s, "react_cap": 20}),
        (f"Reaction cap ({cap:g} s)", f"cap {cap * 0.9:.1f} s (−10%)", BASE,
         {**s, "react_cap": cap * 0.9}),
        (f"Reaction cap ({cap:g} s)", f"cap {cap * 1.1:.1f} s (+10%)", BASE,
         {**s, "react_cap": cap * 1.1}),
        (f"Reaction cap ({cap:g} s)", "cap 200 s", BASE, {**s, "react_cap": 200}),
        (f"Reaction cap ({cap:g} s)", "no cap", BASE, {**s, "react_cap": None}),
        (f"Stair descent ({s['stair_time']:.3f} s)", f"concert stair {STAIR_TIME_CONCERT:.3f} s", BASE,
         {**s, "stair_time": STAIR_TIME_CONCERT}),
        ("Walking speed (1.321 m/s)", "−10%", BASE, {**s, "speed": s["speed"] * 0.9}),
        ("Walking speed (1.321 m/s)", "+10%", BASE, {**s, "speed": s["speed"] * 1.1}),
        ("Walking speed (1.321 m/s)", "concert 1.056 m/s (−20%)", BASE,
         {**s, "speed": concert["speed"]}),
        ("Door flow (1.316 /s/m)", "−10%", BASE, s, 0.9, None),
        ("Door flow (1.316 /s/m)", "+10%", BASE, s, 1.1, None),
        ("All distances", "−10%", BASE, s, 1.0, 0.9),
        ("All distances", "+10%", BASE, s, 1.0, 1.1),
        (f"Wheelchair at D ({h} s)", f"{h * 0.9:.2f} s (−10%)", "students | wheelchair at D",
         {**wheel, "hold": {"D": h * 0.9}}),
        (f"Wheelchair at D ({h} s)", f"{h * 1.1:.2f} s (+10%)", "students | wheelchair at D",
         {**wheel, "hold": {"D": h * 1.1}}),
        (f"LED (+{sf:.2%})", f"+{sf * 0.9:.2%} (−10%)", "students | LED",
         {**led, "speed_factor": 1 + sf * 0.9}),
        (f"LED (+{sf:.2%})", f"+{sf * 1.1:.2%} (+10%)", "students | LED",
         {**led, "speed_factor": 1 + sf * 1.1}),
        (f"LED (+{sf:.2%})", "+7.7% (old value)", "students | LED",
         {**led, "speed_factor": 1.077}),
    ]
    # pad to (group, label, base, settings, door, dist)
    return [t + (1.0, None) if len(t) == 4 else t for t in tests]
 
 
def draw_tornado(rows, base_vals):
    """Two panels: change in 'everyone out' and in '95% out' vs the baseline,
    one bar per test (with the 95% CI of the paired difference)."""
    labels = [f"{r['group']}: {r['label']}" for r in rows]
    y = list(range(len(rows)))[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(14, 0.38 * len(rows) + 1.6), sharey=True)
    for ax, key, title in [(axes[0], "d100", "Change in everyone out (100%)"),
                           (axes[1], "d95", "Change in 95% out")]:
        vals = [r[key] for r in rows]
        cis = [r[key + "_ci"] for r in rows]
        colors = ["#d6457f" if v > 0 else "#2a78d6" for v in vals]   # slower / faster
        ax.barh(y, vals, xerr=cis, color=colors, alpha=0.85, height=0.62,
                error_kw=dict(ecolor="#52514e", lw=1, capsize=2))
        ax.axvline(0, color="#0b0b0b", lw=0.8)
        ax.set_title(title, loc="left", fontsize=11)
        ax.set_xlabel("seconds (positive = slower)")
        ax.grid(axis="x", color="#e1e0d9", lw=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        # thin lines between groups
        for i in range(1, len(rows)):
            if rows[i]["group"] != rows[i - 1]["group"]:
                ax.axhline(y[i] + 0.5, color="#c3c2b7", lw=0.6)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(labels, fontsize=8.5)
    fig.suptitle(f"Sensitivity, one input at a time ({RUNS} paired runs each). Baseline "
                 f"students, no event: everyone out {base_vals[0]:.1f} s, 95% out "
                 f"{base_vals[1]:.1f} s", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    path = os.path.join(RESULTS, "sensitivity_tornado.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("saved", path)
 
 
# ---------------------------------------------------------------------------
# PART 2c: random combinations of the uncertain inputs (Monte Carlo)
# ---------------------------------------------------------------------------
NO_EVENT = ["students | no event", "concert | no event", "concert + CM | no event"]
 
 
def draw_inputs(rng):
    """One random combination. The same combination is used for all three
    audiences, so their comparison stays fair."""
    pairs = {}
    for a in WALK_NODES:
        for b in building.NEXT[a]:
            pairs[(a, b)] = rng.uniform(0.95, 1.05)        # each distance +-5%
    for a, row in building.CM_NEXT.items():
        for b in row:
            pairs.setdefault((a, b), rng.uniform(0.95, 1.05))
    for pair in building.WALL_DIST:
        pairs[pair] = rng.uniform(0.95, 1.05)
    return {
        "power": rng.uniform(0.8, 1.2),        # power x 0.8 .. 1.2
        "speed": rng.uniform(0.9, 1.1),        # walking speed x 0.9 .. 1.1
        "react": rng.uniform(0.9, 1.1),        # reaction mean x 0.9 .. 1.1
        "cap": rng.uniform(0.9, 1.1),          # each audience's own cap x 0.9 .. 1.1
        "door": rng.uniform(0.9, 1.1),         # door flow x 0.9 .. 1.1
        "dist": pairs,
    }
 
 
def apply_inputs(settings, d):
    out = dict(settings)
    out["power"] = settings["power"] * d["power"]
    out["speed"] = settings["speed"] * d["speed"]
    out["react_mu"] = settings["react_mu"] + math.log(d["react"])   # scales the mean
    out["react_cap"] = settings["react_cap"] * d["cap"]
    return out
 
 
def draw_robustness(curve, dts, mc):
    colors = {"students | no event": "#2a78d6", "concert | no event": "#d6457f",
              "concert + CM | no event": "#1f1f24"}
    names = {n: n.split(" | ")[0] for n in NO_EVENT}
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
 
    # a) CI half-width vs number of runs
    ax = axes[0]
    for n in NO_EVENT:
        vals = [r["t_last"] for r in curve[n]]
        Rs = list(range(5, len(vals) + 1, 5))
        ax.plot(Rs, [mean_and_ci(vals[:R])[1] for R in Rs], marker="o", ms=3,
                color=colors[n], label=names[n])
    ax.set_title("a) 95% CI of everyone out vs number of runs", loc="left", fontsize=11)
    ax.set_xlabel("runs (seeds)")
    ax.set_ylabel("± seconds")
    ax.legend(frameon=False)
 
    # b) time step
    ax = axes[1]
    for k, n in enumerate(NO_EVENT):
        xs = [i + (k - 1) * 0.12 for i in range(len(dts))]
        stats = [mean_and_ci([r["t_last"] for r in dts_res]) for dts_res in dts[n]]
        ax.errorbar(xs, [m for m, _ in stats], yerr=[c for _, c in stats], fmt="o",
                    color=colors[n], capsize=3, label=names[n])
    ax.set_xticks(range(len(DT_LIST)))
    ax.set_xticklabels([f"Δt = {d} s" for d in DT_LIST])
    ax.axhline(LIMIT, color="#898781", ls=(0, (4, 3)), lw=1)
    ax.set_title(f"b) Time step ({RUNS_DT} runs each)", loc="left", fontsize=11)
    ax.set_ylabel("everyone out (s)")
 
    # c) Monte Carlo
    ax = axes[2]
    data = [[m for m in mc[n]] for n in NO_EVENT]
    box = ax.boxplot(data, patch_artist=True, widths=0.55,
                     medianprops=dict(color="#0b0b0b", lw=1.4))
    for patch, n in zip(box["boxes"], NO_EVENT):
        patch.set_facecolor(colors[n] if n != "concert + CM | no event" else "#8b8b96")
        patch.set_alpha(0.85)
    for i, n in enumerate(NO_EVENT, 1):
        share = sum(m <= LIMIT for m in mc[n]) / len(mc[n])
        ax.text(i, max(mc[n]) + 1.5, f"{share:.0%} ≤ {LIMIT} s", ha="center", fontsize=9)
    ax.axhline(LIMIT, color="#898781", ls=(0, (4, 3)), lw=1)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels([names[n] for n in NO_EVENT])
    ax.set_ylabel(f"everyone out, mean of {MC_SEEDS} runs (s)")
    ax.set_title(f"c) {MC_DRAWS} random input combinations", loc="left", fontsize=11)
 
    for ax in axes:
        ax.grid(color="#e1e0d9", lw=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle("Robustness checks (no event)", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    path = os.path.join(RESULTS, "robustness.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("saved", path)
 
 
DT_LIST = [0.5, 0.25, 0.1]
 
 
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    seeds = range(RUNS)
    tests = sensitivity_tests()
    rng = random.Random(2026)
    draws = [draw_inputs(rng) for _ in range(MC_DRAWS)]
 
    # ---- all jobs in one list, run in parallel ----
    jobs = []
    for base in sorted({t[2] for t in tests}):                      # the baselines
        jobs.append(job(("base", base), SCENARIOS[base], seeds))
    for i, (group, label, base, settings, door, dist) in enumerate(tests):
        jobs.append(job(("sens", i), settings, seeds, door, dist))
    for n in NO_EVENT:
        jobs.append(job(("curve", n), SCENARIOS[n], range(RUNS_CURVE)))
        for dt in DT_LIST:
            jobs.append(job(("dt", n, dt), SCENARIOS[n], range(RUNS_DT), dt=dt))
        for k, d in enumerate(draws):
            jobs.append(job(("mc", n, k), apply_inputs(SCENARIOS[n], d),
                            range(MC_SEEDS), door=d["door"], dist=d["dist"]))
    total = sum(len(j[2]) for j in jobs)
    print(f"{'QUICK' if QUICK else 'FULL'} run: {len(jobs)} jobs, {total} simulations ...")
 
    res = {}
    with Pool() as pool:
        for k, (key, out) in enumerate(pool.imap_unordered(run_job, jobs), 1):
            res[key] = out
            if k % 10 == 0 or k == len(jobs):
                print(f"  {k}/{len(jobs)} jobs done")
 
    # ---- PART 1: sensitivity table + tornado ----
    rows = []
    for i, (group, label, base, settings, door, dist) in enumerate(tests):
        new, old = res[("sens", i)], res[("base", base)]
        t100 = [r["t_last"] for r in new]
        t95 = [r["t_95"] for r in new]
        d100, d100_ci = paired(t100, [r["t_last"] for r in old])
        d95, d95_ci = paired(t95, [r["t_95"] for r in old])
        rows.append({"group": group, "label": label, "baseline": base,
                     "t100": mean_and_ci(t100)[0], "t95": mean_and_ci(t95)[0],
                     "d100": d100, "d100_ci": d100_ci, "d95": d95, "d95_ci": d95_ci,
                     "under180": under(t100),
                     "stuck": sum(r["stuck"] for r in new),
                     "incomplete": incomplete(t100)})
    base_vals = (mean_and_ci([r["t_last"] for r in res[("base", BASE)]])[0],
                 mean_and_ci([r["t_95"] for r in res[("base", BASE)]])[0])
    with open(os.path.join(RESULTS, "sensitivity.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "test", "baseline scenario", "everyone out (s)",
                    "change (s)", "change 95% CI (s)", "95% out (s)", "change (s)",
                    "change 95% CI (s)", "share of runs <= 180 s", "people stuck",
                    "incomplete runs"])
        for r in rows:
            w.writerow([r["group"], r["label"], r["baseline"], f"{r['t100']:.1f}",
                        f"{r['d100']:+.1f}", f"{r['d100_ci']:.1f}", f"{r['t95']:.1f}",
                        f"{r['d95']:+.1f}", f"{r['d95_ci']:.1f}", f"{r['under180']:.0%}",
                        r["stuck"], r["incomplete"]])
    print("saved", os.path.join(RESULTS, "sensitivity.csv"))
    draw_tornado(rows, base_vals)
 
    print(f"\nBaseline {BASE}: everyone out {base_vals[0]:.1f} s, 95% out {base_vals[1]:.1f} s")
    print(f"{'test':52s} {'Δ100%':>8s} {'Δ95%':>8s} {'≤180':>6s}")
    for r in rows:
        print(f"{r['group'] + ': ' + r['label']:52s} {r['d100']:+7.1f}s {r['d95']:+7.1f}s "
              f"{r['under180']:6.0%}")
 
    # ---- PART 2: robustness ----
    curve = {n: res[("curve", n)] for n in NO_EVENT}
    dts = {n: [res[("dt", n, dt)] for dt in DT_LIST] for n in NO_EVENT}
    mc = {n: [mean_and_ci([r["t_last"] for r in res[("mc", n, k)]])[0]
              for k in range(MC_DRAWS)] for n in NO_EVENT}
    cm_faster = sum(mc["concert + CM | no event"][k] < mc["concert | no event"][k]
                    for k in range(MC_DRAWS)) / MC_DRAWS
    with open(os.path.join(RESULTS, "robustness.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["check", "scenario", "value"])
        for n in NO_EVENT:
            vals = [r["t_last"] for r in curve[n]]
            for R in (10, 20, len(vals)):
                m, ci = mean_and_ci(vals[:R])
                w.writerow([f"runs = {R}", n, f"{m:.1f} ± {ci:.1f} s"])
            for dt, out in zip(DT_LIST, dts[n]):
                m, ci = mean_and_ci([r["t_last"] for r in out])
                w.writerow([f"DT = {dt} s", n, f"{m:.1f} ± {ci:.1f} s"])
            share = sum(m <= LIMIT for m in mc[n]) / MC_DRAWS
            w.writerow(["Monte Carlo: combinations <= 180 s", n, f"{share:.0%}"])
            w.writerow(["Monte Carlo: range of means", n,
                        f"{min(mc[n]):.1f} - {max(mc[n]):.1f} s"])
            w.writerow(["Monte Carlo: incomplete runs", n,
                        sum(incomplete([r["t_last"] for r in res[("mc", n, k)]])
                            for k in range(MC_DRAWS))])
        w.writerow(["Monte Carlo: concert + CM faster than concert", "", f"{cm_faster:.0%}"])
    print("saved", os.path.join(RESULTS, "robustness.csv"))
    draw_robustness(curve, dts, mc)
 
    print("\nRobustness (Monte Carlo, no event):")
    for n in NO_EVENT:
        share = sum(m <= LIMIT for m in mc[n]) / MC_DRAWS
        print(f"  {n:26s} {min(mc[n]):6.1f}-{max(mc[n]):6.1f} s, {share:.0%} of combinations ≤ {LIMIT} s")
    print(f"  concert + CM faster than concert in {cm_faster:.0%} of combinations")