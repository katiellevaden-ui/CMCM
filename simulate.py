"""
Runs one evacuation of Bailey Hall.

For each person:
  waiting  -> reaction time t_ready passes -> choose next_node -> walking
  walking  -> t_escape counts down to 0 -> queuing
  queuing  -> next_node is an exit : go out if the door has room this step -> exited
           -> next_node is a stair : step onto it if it has room -> choose again
           -> next_node is blocked : remember it, walk back -> choose again
"""
import math
import random
from collections import Counter

from building import INFO, SEATS, NEXT, WALK_SPEED, crowd_speed
from individuals import Person, choose_next

DT = 0.25        # time step (s)
T_MAX = 700      # stop after this many seconds

# Reaction time: lognormal with mean 24.3 s, SD 19.83 s (Rafi et al. 2023 fire drill),
# converted to the lognormal's two parameters MU and SIGMA
REACT_MEAN, REACT_SD = 24.3, 19.83
SIGMA = math.sqrt(math.log(1 + (REACT_SD / REACT_MEAN) ** 2))
MU = math.log(REACT_MEAN) - SIGMA ** 2 / 2

def start_walking(p, queue, occupancy, rng):
    """Choose the next node and start walking."""
    target= choose_next(p.node, queue, p.known_blocked, rng=rng)
    if target is None:
        return
    walk_time = NEXT[p.node][target] # seconds at free walking speed

    # In a crowded seating spot people walk slower, so the walk takes longer.
    # (Not on stairs: the 20 s stair time already includes normal stair crowding.)
    if INFO[p.node]["kind"] == "spot":
        speed = crowd_speed(occupancy[p.node], INFO[p.node]["area"])
        walk_time = walk_time * WALK_SPEED/speed

    p.next_node = target
    p.t_escape = walk_time
    p.state = "walking"

def run(seed=0, settings = None):
    """
    One evacuation with settings from scenarios.py
    """
    if settings is None:
        settings = {}
    blocked = settings.get("blocked", set())
    rng = random.Random(seed)
    people = []
    for spot in SEATS:
        for i in range(SEATS[spot]):
            reaction = rng.lognormvariate(MU, SIGMA)
            p = Person(len(people), spot, reaction)
            p.t_queue = None
            people.append(p)

    occupancy = {place: 0 for place in INFO}
    for p in people:
        occupancy[p.node] += 1

    # every bottleneck(exists and stairs) has a budget
    budget = {place: 0.0 for place in INFO if INFO[place]["flow"]}
    t = 0.0
    inside = people[:]
    while inside and t<T_MAX:
        # refill the budget
        for place in budget:
            per_step = INFO[place]["flow"] * DT #people per step
            budget[place] = min(budget[place] + per_step, max(1.0, per_step))
        # count people queuing to define waiting time
        queue = {}
        for p in inside:
            if p.state == "queuing":
                queue[p.next_node] = queue.get(p.next_node, 0) + 1

        # Queuing people FIFO
        inside.sort(key=lambda p: p.t_queue if p.state == "queuing" else float("inf"))

        # updates
        for p in inside:
            if p.state == "waiting":
                if t >= p.t_ready:
                    start_walking(p, queue, occupancy, rng)
            elif p.state == "walking":
                p.t_escape -=DT
                if p.t_escape <=0:
                    if p.next_node is None: # walking back from a blocked door
                        start_walking(p, queue, occupancy, rng)
                    else:
                        p.state = "queuing"
                        p.t_queue = t
            elif p.state == "queuing":
                target = p.next_node
                if target in blocked:
                    p.known_blocked.add(target)
                    p.t_escape = NEXT[p.node][target]
                    p.next_node = None
                    p.state = "walking"
                elif INFO[target]["kind"] == "exit":
                    if budget[target]>=1:
                        budget[target] -= 1
                        occupancy[p.node] -=1
                        p.state = "exited"
                        p.t_exit = t
                else:
                    # for stairs, step on if budget allows
                    if occupancy[target] < INFO[target]["cap"] and budget[target]>=1:
                        budget[target] -= 1
                        occupancy[p.node] -= 1
                        occupancy[target] += 1
                        p.node = target
                        p.visited.add(target)
                        p.t_queue = None
                        start_walking(p, queue, occupancy, rng)
            
        # remove people who got out, move the clock.
        inside = [p for p in inside if p.state != "exited"]
        t += DT

    return people

        
def summary(people):
    times = sorted(p.t_exit for p in people if p.t_exit is not None)
    exit_use = {}
    for p in people:
        if p.state == "exited":
            exit_use[p.next_node] = exit_use.get(p.next_node, 0) +1
    return {
        "stuck": len(people) - len(times), 
        "t_last": times[-1],
        "t_95":times[int(0.95 * len(times)) - 1], # 95% of people out(s)
        "exit_use": dict(sorted(exit_use.items())),
    }

# Test
if __name__ == "__main__":
    scenarios = {
        "normal": set(),
        "exit D blocked": {"D"},
        "stair Y blocked": {"Y"},
    }
    runs = 20

    print(f"{'scenario':16s} {'last out (s)':>13s} {'95% out (s)':>12s} {'stuck':>6s}")
    for name, blocked in scenarios.items():
        results = [summary(run(seed, {"blocked": blocked})) for seed in range(runs)]
        last = sum(r["t_last"] for r in results) / runs
        p95 = sum(r["t_95"] for r in results) / runs
        stuck = sum(r["stuck"] for r in results)
        print(f"{name:16s} {last:13.1f} {p95:12.1f} {stuck:6d}")

    print("\npeople per exit (one normal run):", summary(run(0))["exit_use"])