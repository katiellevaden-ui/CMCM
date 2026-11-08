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

from building import dynamic_time_to_exit, INFO, SEATS, NEXT, CM_NEXT, WALK_SPEED, STAIR_TIME, MERGE, crowd_speed, wall_options
from individuals import Person, choose_next, Power

DT = 0.25        # time step (s)
T_MAX = 700      # stop after this many seconds

# Reaction time: lognormal with mean 24.3 s, SD 19.83 s (Rafi et al. 2023 fire drill),
# converted to the lognormal's two parameters MU and SIGMA
REACT_MEAN, REACT_SD = 24.3, 19.83
SIGMA = math.sqrt(math.log(1 + (REACT_SD / REACT_MEAN) ** 2))
MU = math.log(REACT_MEAN) - SIGMA ** 2 / 2

def start_walking(p, queue, occupancy, rng, stair_time=STAIR_TIME, power=Power,
                  informed=False, heading=None, speed=WALK_SPEED, speed_factor=1.0, h=None):
    """Choose the next node and start walking."""
    scale = WALK_SPEED / (speed * speed_factor)   # NEXT / CM_NEXT times assume WALK_SPEED
    if p.node not in NEXT:
        return   # standing at a blocked door with no open door left anywhere
    if INFO[p.node]["kind"] == "stair":
        # going down a stair: land in a first-floor spot this stair reaches,
        # using the group's merge percentages (renormalised over those spots)
        spots = list(NEXT[p.node])
        weights = [MERGE[p.home].get(s, 0) for s in spots]
        if sum(weights) == 0:
            weights = [1] * len(spots)          # no percentage given: equally likely
        p.next_node = rng.choices(spots, weights=weights)[0]
        p.t_escape = stair_time
        p.state = "walking"
        return

    if informed and p.node in CM_NEXT:
        # Crowd Managers: any door is an option (via the wall), and the manager knows how
        # many people are already heading to each door, so overloaded doors look slow
        choices = CM_NEXT[p.node]
        target = choose_next(p.node, heading, p.known_blocked, power=power, rng=rng,
                             choices=choices, scale=scale)
    else:
        choices = NEXT[p.node]
        target = choose_next(p.node, queue, p.known_blocked, power=power, rng=rng,
                             scale=scale, h=h)
    if target is None:
        return
    walk_time = choices[target] * scale # seconds at this audience's free walking speed

    # In a crowded seating spot people walk slower, so the walk takes longer.
    # (Not on stairs: the stair time already includes normal stair crowding.)
    if INFO[p.node]["kind"] == "spot":
        v = speed_factor * crowd_speed(occupancy[p.node], INFO[p.node]["area"], v_max=speed)
        walk_time = choices[target] * WALK_SPEED / v     # = distance / speed

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
    stair_time = settings.get("stair_time", STAIR_TIME)  # seconds down one stair
    power = settings.get("power", Power)                 # how strongly people pick the faster option
    informed = settings.get("informed", False)           # True: Crowd Managers tell everyone
                                                         # which doors are blocked
    react_cap = settings.get("react_cap", None)          # Crowd Managers prompt anyone who
                                                         # hasn't moved by this time (s)
    react_mu = settings.get("react_mu", MU)              # reaction time ~ LogNormal(mu, sigma)
    react_sigma = settings.get("react_sigma", SIGMA)
    speed = settings.get("speed", WALK_SPEED)            # audience's free walking speed (m/s)
    speed_factor = settings.get("speed_factor", 1.0)     # LED strips: walk 7.7% faster
    hold = settings.get("hold", {})                      # {door: s}: door blocked for s seconds
                                                         # from when the first person reaches it
                                                         # (wheelchair in the doorway)
    hold_started = {}
    dynamic = settings.get("dynamic", False)             # True: recompute the time to exit
                                                         # every step, with queues included
    scale = WALK_SPEED / (speed * speed_factor)
    rng = random.Random(seed)
    people = []
    for spot in SEATS:
        for i in range(SEATS[spot]):
            reaction = rng.lognormvariate(react_mu, react_sigma)
            if react_cap is not None:
                reaction = min(reaction, react_cap)
            p = Person(len(people), spot, reaction)
            p.t_queue = None
            p.home = spot                     # their starting group (for MERGE)
            if informed:                      # nobody walks to a blocked door
                p.known_blocked = set(blocked)
            people.append(p)

    occupancy = {place: 0 for place in INFO}
    for p in people:
        occupancy[p.node] += 1

    # every stair entrance lets one person on every 1/flow seconds;
    # stair_free[x] = the time stair x's entrance is free again
    stair_free = {x: 0.0 for x in INFO if INFO[x]["kind"] == "stair"}
    # every exit has lanes; lane_free[e][i] = time lane i of exit e is free again
    lane_free = {e: [0.0] * INFO[e]["lanes"] for e in INFO if INFO[e]["kind"] == "exit"}
    t = 0.0
    inside = people[:]
    while inside and t<T_MAX:
        # count people queuing to define waiting time
        queue = {}
        for p in inside:
            if p.state == "queuing":
                queue[p.next_node] = queue.get(p.next_node, 0) + 1

        # people walking to or queuing at each exit (what a Crowd Manager can see)
        heading = {}
        for p in inside:
            if p.state in ("walking", "queuing") and p.next_node and p.next_node in INFO and INFO[p.next_node]["kind"] == "exit":
                heading[p.next_node] = heading.get(p.next_node, 0) + 1

        # dynamic time to exit (Managers see everyone heading to a door, others see lines)
        h = None
        if dynamic:
            h = dynamic_time_to_exit(heading if informed else queue, scale, stair_time)

        # Queuing people FIFO
        inside.sort(key=lambda p: p.t_queue if p.state == "queuing" else float("inf"))

        # updates
        for p in inside:
            if p.state == "waiting":
                if t >= p.t_ready:
                    start_walking(p, queue, occupancy, rng, stair_time, power, informed, heading,
                                  speed, speed_factor, h)
            elif p.state == "walking":
                p.t_escape -=DT
                if p.t_escape <=0:
                    if p.next_node is None: # nowhere left to go
                        start_walking(p, queue, occupancy, rng, stair_time, power, informed, heading,
                                  speed, speed_factor, h)
                    else:
                        p.state = "queuing"
                        p.t_queue = t
            elif p.state == "queuing":
                target = p.next_node
                if target in blocked:
                    # Found it blocked: remember it, then walk along the wall to the
                    # nearest door on the left or right, chosen by DISTANCE only
                    # (no queue term: you can't walk past the next door's line anyway).
                    p.known_blocked.add(target)
                    if p.node != target:            # leaving the seating area for the wall
                        occupancy[p.node] -= 1
                        occupancy[target] += 1
                        p.node = target
                    along_wall = {d: m / (speed * speed_factor) for d, m in
                                  wall_options(target, p.known_blocked).items()}
                    door = choose_next(target, {}, p.known_blocked, power=power, rng=rng,
                                       choices=along_wall)
                    p.next_node = door
                    p.t_escape = along_wall[door] if door else 0.0
                    p.state = "walking"
                elif INFO[target]["kind"] == "exit":
                    # wheelchair event: the first person to reach this door starts a hold;
                    # the whole doorway is blocked for hold[door] seconds from then
                    if target in hold and target not in hold_started:
                        hold_started[target] = t
                        lane_free[target] = [t + hold[target]] * len(lane_free[target])
                    # go through if one of the door's places is free; it is then busy for t_pass
                    lanes = lane_free[target]
                    i = min(range(len(lanes)), key=lambda k: lanes[k])   # earliest-free lane
                    if lanes[i] <= t:
                        # they step through when the lane frees up (or when they arrived,
                        # if later), not at the next tick: keeps the flow exactly lanes/t_pass
                        start = max(lanes[i], p.t_queue)
                        lanes[i] = start + INFO[target]["t_pass"]
                        occupancy[p.node] -=1
                        p.state = "exited"
                        p.t_exit = start
                else:
                    # a stair (step on if it has room and its entrance is free), or a
                    # first-floor spot at the bottom of a stair (step in if it has room)
                    has_room = occupancy[target] < INFO[target]["cap"]
                    is_stair = target in stair_free
                    has_turn = (not is_stair) or stair_free[target] <= t
                    if has_room and has_turn:
                        if is_stair:
                            # step on when the entrance frees up (or when they arrived, if
                            # later), not at this tick: keeps the flow exactly 1/flow per person
                            # whatever DT is. Never earlier than the previous tick.
                            start = max(stair_free[target], p.t_queue, t - DT)
                            stair_free[target] = start + 1 / INFO[target]["flow"]
                        occupancy[p.node] -= 1
                        occupancy[target] += 1
                        p.node = target
                        p.visited.add(target)
                        p.t_queue = None
                        start_walking(p, queue, occupancy, rng, stair_time, power, informed, heading,
                                  speed, speed_factor, h)
                        if is_stair:
                            p.t_escape -= t - start   # the stair walk began at start
            
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