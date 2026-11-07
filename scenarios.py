"""
A scenario is just a set of settings passed to run() in simulate.py.
"""
import math
from simulate import run, summary

SCENARIOS = {
    "normal": {"blocked": set()},
    "exit A blocked": {"blocked" : {"A"}},
    "stair Y bloced": {"blocked" : {"Y"}}
    # "concert + crowd managers": {"blocked": set(), "managers": {...}, "p_comply": 0.8},
}
RUNS = 20

def run_scenario(settings, runs = RUNS):
    return [summary(run(seed, settings)) for seed in range(runs)]

def mean_and_ci(values):
    R = len(values)
    mean = sum(values) / R
    sd = math.sqrt(sum((v - mean)** 2 for v in values)/ (R-1))
    return mean, 1.96*sd/math.sqrt(R)

if __name__ == "__main__":
    print(f"{'scenario':16s} {'last out (s)':>18s} {'95% out (s)':>18s} {'stuck':>6s}")
    for name, settings in SCENARIOS.items():
        results = run_scenario(settings)
        last, last_ci = mean_and_ci([r["t_last"] for r in results])
        p95, p95_ci = mean_and_ci([r["t_95"] for r in results])
        stuck = sum(r["stuck"] for r in results)
        print(f"{name:16s} {last:9.1f} +- {last_ci:4.1f} {p95:9.1f} +- {p95_ci:4.1f} {stuck:6d}")