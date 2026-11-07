"""
Each person stores:
    node: where they are (S1-S22, WXYZ, A-H)
    next_node: where they are heading next (None = not decided)
    state: "waiting" (still reacting on the seat), "walking", "queuing" (at a bottleneck), "exited"
    known_blocked: exits they have found blocked
    visited: places they have been (their path)
    t_ready: the time (s) they stop waiting and start moving
    t_escape: seconds of walking left before reaching next_node
    t_exit: the time they got out (None until then)

How they choose path (logit model):
for every node n they could go:
    T(n) = walk time to n + fastest time from n to an exit + waiting time at n
waiting time = people queued at n / flow of n
weight(n) = exp(-Power * T(n)) where faster options has bigger weight
P(n) = weight(n) / sum of all weights

node: the area they are in now 
    Floor 1: S1 ~ S16
    Stairs: X->A, Y->C,D,E, Z->C,D,E, W->G,H
    Exist: A ~ H
"""
import math
import random

from building import INFO, NEXT, TIME_TO_EXIT

Power = 0.2 # per second: how strongly people prefer the faster option
            #   0    -> choose at random
            #   0.2  -> baseline
            #   1+   -> nearly everyone takes the fastest option

class Person:
    def __init__(self, pid, node, t_ready):
        self.id = pid
        self.node = node
        self.next_node = None
        self.state = "waiting"
        self.known_blocked = set()
        self.visited = {node}
        self.t_ready = t_ready
        self.t_escape = 0.0
        self.t_exit = None

    def head_for(self, next_node, walk_time):
        self.next_node = next_node
        self.t_escape = walk_time
        self.state = "walking"
    
    def enter(self, node):
        """Called when the next area accepts them."""
        self.node = node
        self.next_node = None
        self.visited.add(node)

    def found_blocked(self, G):
        """Reached next_node and it is blocked: remember it, walk back,
        and return the seconds that takes. """
        door = self.next_node
        self.known_blocked.add(door)
        self.next_node = None
        self.state = "walking"
        return NEXT[self.node][door]
    
    def leave(self, t):
        self.state = "exited"
        self.t_exit = t

    def __repr__(self):
        return f"Person({self.id}, {self.state}, in {self.node}, -> {self.next_node})"

def choose_next(node, queue, blocked = (), power = Power, rng = random):
    """Pick the next node with probability proportional to exp(-Power * T(n)).
    Nodes in `blocked` are not considered. Returns None if there is nowhere to go."""
    options, times = [], []
    for n in NEXT[node]:
        if n in blocked:
            continue
        T = NEXT[node][n] + TIME_TO_EXIT[n]
        flow = INFO[n]["flow"]
        if flow is not None:
            T += queue.get(n, 0)/ flow # waiting time at n, use 0 if there is no queue
        options.append(n)
        times.append(T)

    if not options:
        return None
    fastest = min(times)
    wights = [math.exp(-power * (T - fastest)) for T in times]
    return rng.choices(options, weights=wights)[0]
    
if __name__ == "__main__":
    picks = [choose_next("S13", {}) for _ in range(4000)]
    print("empty:", {e: picks.count(e) / 4000 for e in "CDE"})
    picks = [choose_next("S13", {"D": 30}) for _ in range(4000)]
    print("30 queued at D:", {e: picks.count(e) / 4000 for e in "CDE"})

