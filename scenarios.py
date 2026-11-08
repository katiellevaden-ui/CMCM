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
REACT_CAP = 60   # s: everyone has started moving by then. PLACEHOLDER, needs a reason
                 # (cuts ~0.1% of students', ~7% of concert and ~2% of concert + CM reaction times)

DYNAMIC = True   # recompute the time to exit every step, with queues further along
                 # (dynamic Dijkstra / Bellman, see dynamic_time_to_exit in building.py)

AUDIENCES = {
    "students":     {"react_mu": 2.418, "react_sigma": 0.527, "speed": 1.321,
                     "stair_time": STAIR_TIME_LECTURE, "power": 0.08,
                     "react_cap": REACT_CAP, "dynamic": DYNAMIC},
    "concert":      {"react_mu": 3.358, "react_sigma": 0.497, "speed": 1.056,
                     "stair_time": STAIR_TIME_CONCERT, "power": 0.23,
                     "react_cap": REACT_CAP, "dynamic": DYNAMIC},
    "concert + CM": {"react_mu": 3.070, "react_sigma": 0.497, "speed": 1.056,
                     "stair_time": STAIR_TIME_CONCERT, "power": 0.23, "informed": True, "all_doors": True,
                     "react_cap": REACT_CAP, "dynamic": DYNAMIC},
}

# ------------------------------------------------------------------
# Layer 2: events ("no event" = baseline for comparison)
# ------------------------------------------------------------------
EVENTS = {
    "no event":        {},
    "wheelchair at E": {"hold": {"E": 11.7}},      # E blocked 11.7 s from when the first
                                                   # person reaches it
    "LED":             {"speed_factor": 1.077},    # everyone walks 7.7% faster (not stairs)
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
    R = len(values)
    mean = sum(values) / R
    sd = math.sqrt(sum((v - mean)** 2 for v in values)/ (R-1))
    return mean, 1.96*sd/math.sqrt(R)

if __name__ == "__main__":
    print(f"{'scenario':32s} {'last out (s)':>18s} {'95% out (s)':>18s} {'stuck':>6s}")
    for name, settings in SCENARIOS.items():
        results = run_scenario(settings)
        last, last_ci = mean_and_ci([r["t_last"] for r in results])
        p95, p95_ci = mean_and_ci([r["t_95"] for r in results])
        stuck = sum(r["stuck"] for r in results)
        print(f"{name:32s} {last:9.1f} +- {last_ci:4.1f} {p95:9.1f} +- {p95_ci:4.1f} {stuck:6d}")