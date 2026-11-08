"""
A scenario is just a set of settings passed to run() in simulate.py.
"""
import math
from simulate import run, summary
from building import STAIR_TIME_LECTURE, STAIR_TIME_CONCERT

# ------------------------------------------------------------------
# Layer 1: three audiences
#   reaction time ~ LogNormal(react_mu, react_sigma^2)   (seconds)
#     means: students 12.9 s, concert 32.5 s, concert + CM 24.4 s
#   speed = free walking speed (m/s), stair_time = seconds down one stair,
#   power = how strongly people pick the faster option (beta)
# ------------------------------------------------------------------
# s: everyone has started moving by then (one cap per audience)
# (cuts ~5.5% of students' and ~0.002% of concert / concert + CM reaction times)
REACT_CAP = {"students": 26, "concert": 224, "concert + CM": 168}

DYNAMIC = True   # recompute the time to exit every step, with queues further along
                 # (dynamic Dijkstra / Bellman, see dynamic_time_to_exit in building.py)

AUDIENCES = {
    "students":     {"react_mu": 2.418, "react_sigma": 0.527, "speed": 1.321,
                     "stair_time": STAIR_TIME_LECTURE, "power": 0.08,
                     "react_cap": REACT_CAP["students"], "dynamic": DYNAMIC},
    "concert":      {"react_mu": 3.358, "react_sigma": 0.497, "speed": 1.056,
                     "stair_time": STAIR_TIME_CONCERT, "power": 0.23,
                     "react_cap": REACT_CAP["concert"], "dynamic": DYNAMIC},
    "concert + CM": {"react_mu": 3.070, "react_sigma": 0.497, "speed": 1.056,
                     "stair_time": STAIR_TIME_CONCERT, "power": 0.23, "informed": True, "all_doors": True,
                     "react_cap": REACT_CAP["concert + CM"], "dynamic": DYNAMIC},
}

# ------------------------------------------------------------------
# Layer 2: events ("no event" = baseline for comparison)
# ------------------------------------------------------------------
EVENTS = {
    "no event":        {},
    "wheelchair at D": {"hold": {"D": 8.25}},      # D blocked 8.25 s (wheelchair crossing
                                                   # 6 m at 0.727 m/s) from when the first
                                                   # person reaches it
    "LED":             {"speed_factor": 1.0314},   # everyone walks 3.14% faster (not stairs)
    "cameras":         {"informed": True, "all_doors": True},
                                                   # same information as Crowd Managers:
                                                   # blocked doors, crowd heading to each door,
                                                   # direct routes to every door (ALL_DOORS);
                                                   # reaction time NOT changed
    "A+B blocked":     {"blocked": {"A", "B"}},
    "C+D+E blocked":   {"blocked": {"C", "D", "E"}},
    "F+G blocked":     {"blocked": {"F", "G"}},
    "H blocked":       {"blocked": {"H"}},
}

# every audience x every event: 3 x 8 = 24 scenarios
SCENARIOS = {f"{a} | {e}": {**AUDIENCES[a], **EVENTS[e]}
             for a in AUDIENCES for e in EVENTS}
RUNS = 20

def run_scenario(settings, runs = RUNS):
    return [summary(run(seed, settings)) for seed in range(runs)]

def mean_and_ci(values):
    """Mean and 95% CI half-width. Runs that never reached the time (None) are left
    out; count them with incomplete(values). Returns (nan, nan) if fewer than 2 remain."""
    values = [v for v in values if v is not None]
    R = len(values)
    if R < 2:
        return (values[0] if R else float("nan")), float("nan")
    mean = sum(values) / R
    sd = math.sqrt(sum((v - mean)** 2 for v in values)/ (R-1))
    return mean, 1.96*sd/math.sqrt(R)


def incomplete(values):
    """How many runs never reached the time (still people inside at T_MAX)."""
    return sum(v is None for v in values)

if __name__ == "__main__":
    print(f"{'scenario':32s} {'last out (s)':>18s} {'95% out (s)':>18s} {'stuck':>6s} {'incomplete runs':>16s}")
    for name, settings in SCENARIOS.items():
        results = run_scenario(settings)
        last, last_ci = mean_and_ci([r["t_last"] for r in results])
        p95, p95_ci = mean_and_ci([r["t_95"] for r in results])
        stuck = sum(r["stuck"] for r in results)
        bad = incomplete([r["t_last"] for r in results])
        print(f"{name:32s} {last:9.1f} +- {last_ci:4.1f} {p95:9.1f} +- {p95_ci:4.1f} {stuck:6d} {bad:16d}")