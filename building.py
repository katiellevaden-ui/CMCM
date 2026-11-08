"""
We model Baily Hall first floor into 16 spots (S1-S16) with 8 exists (A-H),
and balcony into 6 spots (S17-S22) with 4 stairs (XYZW) connecting to first floor.

Nodes: the spots, stairs, and exits.
Edges: spot -> exit, balcony spot (S17-S22) -> stair,
       stair -> first-floor spot it lands in (X->S16, Y->S14/S13, Z->S13/S12, W->S10)

Every node that holds people has an AREA (m^2):
capacity = D_MAX * area
crowd_speed = v(D), D = people/area 
(SFPE: v = 1.4 (1 - 0.266 D), D = people per m^2, never below 0.2 m/s)

We build two dictionaries the other files use:
    INFO[place] -> facts about a place (kind, capacity, area, flow, seats)
    NEXT[place] -> {place you can walk to next: seconds it takes}
"""
# ==================================================================
# 1. Basic constants
# ==================================================================
WALK_SPEED = 1.61 # m/s, (Seyfried et al. 2005)
MAX_DENSITY = 3.8     # people per m^2 at which a crowd stops moving (SFPE)
# Time to walk down one balcony stair = stair length / stair descent speed
STAIR_TIME_LECTURE = 9 / 0.97   # 9.28 s  (0.97 m/s, Rafi et al. 2023 university drill)
STAIR_TIME_CONCERT = 9 / 0.44   # 20.45 s (0.44 m/s, Peacock et al., NIST)
STAIR_TIME = STAIR_TIME_LECTURE # default; each scenario sets its own "stair_time"
SQFT        = 0.0929  # 1 square foot in m^2

# Whole-floor areas printed on the floor plans (used only as a sanity check)
GROSS_AREA = {1: 18602 * SQFT,    # first floor  = 1728 m^2
              2: 7107 * SQFT}     # second floor =  660 m^2

# ==================================================================
# 2. First floor: which exits each spot can use, and how far (m)
# ==================================================================
SPOT_EXITS = {
    "S1":  {"A": 17, "B": 30},
    "S2":  {"A": 18, "B": 26},
    "S3":  {"B": 21, "C": 18},
    "S4":  {"A": 22, "G": 21, "H": 31},
    "S5":  {"C": 26, "D": 28, "E": 25},
    "S6":  {"C": 19, "D": 20, "E": 17},
    "S7":  {"G": 16, "H": 24},
    "S8":  {"F": 27, "G": 19},
    "S9":  {"E": 19, "F": 24},
    "S10": {"G": 9,  "H": 20},
    "S11": {"F": 15, "G": 10},
    "S12": {"E": 15, "F": 17},
    "S13": {"C": 18, "D": 19, "E": 16},
    "S14": {"B": 19, "C": 16},
    "S15": {"A": 11, "B": 17},
    "S16": {"A": 9,  "B": 23},
}

# ==================================================================
# 3. Balcony, in two layers:
#     layer 1  BALCONY_STAIRS : balcony spot -> top of a stair (m), chosen by distance (logit)
#     layer 2  STAIR_LANDS_IN : after walking down (STAIR_TIME), people join one of
#                               these first-floor spots, equally likely, and leave
#                               through that spot's exits with everyone else
# ==================================================================
BALCONY_STAIRS = {            # team's measurements (m)
    "S17": {"X": 8.2},
    "S18": {"X": 20.1, "Y": 6.9},
    "S19": {"Y": 7.6, "Z": 18.9},
    "S20": {"Y": 18.9, "Z": 7.6},
    "S21": {"W": 19.1, "Z": 7.1},
    "S22": {"W": 7.5},
}

# Where each balcony group merges on the first floor (team's percentages).
# After going down stair w, a person lands in spot s with probability
#   MERGE[group][s] restricted to the spots that stair reaches, renormalised.
MERGE = {
    "S17": {"S16": 100},
    "S18": {"S16": 50, "S14": 50},
    "S19": {"S14": 40, "S13": 40, "S12": 20},
    "S20": {"S14": 20, "S13": 40, "S12": 40},
    "S21": {"S10": 50, "S12": 50},
    "S22": {"S10": 100},
}

STAIR_LANDS_IN = {
    "X": ["S16"],
    "Y": ["S14", "S13"],
    "Z": ["S13", "S12"],
    "W": ["S10"],
}

# ==================================================================
# 3b. Doors along the semicircle wall (team estimates, m).
#     A blocked door sends people along the wall to the next door.
# ==================================================================
WALL_ORDER = ["A", "B", "C", "D", "E", "F", "G", "H"]
WALL_DIST = {("A", "B"): 19.2, ("B", "C"): 16.4, ("C", "D"): 7.7, ("D", "E"): 8.1,
             ("E", "F"): 18.2, ("F", "G"): 16.9, ("G", "H"): 21.2}


def wall_options(door, known_blocked):
    """From a blocked `door`, the nearest door in each direction along the wall that
    is not known to be blocked, with the walking distance (m) to it.
    Example: from D with C known blocked -> {"B": 7.7 + 16.4, "E": 8.1}"""
    options = {}
    k = WALL_ORDER.index(door)
    for step in (-1, +1):                       # left, then right
        dist, i = 0.0, k
        while 0 <= i + step < len(WALL_ORDER):
            a, b = sorted((WALL_ORDER[i], WALL_ORDER[i + step]))
            dist += WALL_DIST[(a, b)]
            i += step
            if WALL_ORDER[i] not in known_blocked:
                options[WALL_ORDER[i]] = dist
                break
    return options

# ==================================================================
# 4. People per spot
#      PLACEHOLDER: only the totals are real (first floor 1010, balcony 316).
# ==================================================================
SEATS = {
    "S1": 30, "S2": 65, "S3": 40, "S4": 55, "S5": 140, "S6": 60, "S7": 30,
    "S8": 65, "S9": 39, "S10": 40, "S11": 60, "S12": 95, "S13": 96,
    "S14": 95, "S15": 60, "S16": 40,
    "S17": 55, "S18": 52, "S19": 52, "S20": 52, "S21": 50, "S22": 55,
}

# ==================================================================
# 5. Sizes
# ==================================================================
SEAT_AREA   = 7 * SQFT    # 0.65 m^2 per seated person (building-code value)
AISLE_EXTRA = 15          # PLACEHOLDER: m^2 of aisle in each spot
STAIR_AREA  = 1.2 * 9     # PLACEHOLDER: stair 1.2 m wide x 9 m long
# Exits: how many people can go through each door side by side (team's measurement),
# and how long one person occupies a lane before the next can follow
EXIT_LANES = {"A": 2, "B": 2, "C": 3, "D": 3, "E": 3, "F": 2, "G": 2, "H": 2}
# Measured clear widths (m); SFPE flow = 1.316 * (width - 0.3) people/s
EXIT_WIDTH = {"A": 1.1, "B": 1.1, "C": 1.7, "D": 1.7, "E": 1.7, "F": 1.1, "G": 1.1, "H": 1.1}
SPECIFIC_FLOW = 1.316   # people / s / m of effective width (SFPE hydraulic model)
STAIR_WIDTH = 1.2         # PLACEHOLDER: width of each stair (m)

# ==================================================================
# 6. Formulas from the SFPE fire-engineering handbook
# ==================================================================
def door_flow(width, people_per_meter):
    """How many people per second can get through an opening.
    people_per_meter = 1.3 for doors, about 1.0 for stairs.
    0.3 m is subtracted because people keep ~15 cm away from each side."""
    return people_per_meter * (width - 0.3)
 
 
def crowd_speed(people, area, v_max=WALK_SPEED):
    """Walking speed (m/s) when `people` share `area` m^2.
    The more crowded, the slower: v = 1.4 * (1 - 0.266 * density).
    Never faster than v_max (the audience's free speed), never slower than 0.1 m/s."""
    density = people / area
    v = 1.4 * (1 - 0.266 * density)
    return max(0.1, min(v_max, v))

# ==================================================================
# 7. Build INFO: facts about each node
# ==================================================================
INFO = {}

for exit_name in "ABCDEFGH":
    INFO[exit_name] = {
        "kind": "exit",
        "lanes": EXIT_LANES[exit_name],                          # people through at once
        "flow": door_flow(EXIT_WIDTH[exit_name], SPECIFIC_FLOW), # people/s (SFPE)
        # each person occupies a lane for t_pass = lanes / flow, so the door passes exactly
        # its SFPE flow: C, D, E 3 / 1.84 = 1.63 s;  others 2 / 1.05 = 1.90 s
        "t_pass": EXIT_LANES[exit_name] / door_flow(EXIT_WIDTH[exit_name], SPECIFIC_FLOW),
    }

for stair in STAIR_LANDS_IN:
    INFO[stair] = {
        "kind": "stair",
        "flow": door_flow(STAIR_WIDTH, 1.0), # people/sec onto the stair
        "cap": int(MAX_DENSITY * STAIR_AREA), # most people on the stair at once
        "area": STAIR_AREA,
    }

for spot, people in SEATS.items():
    area = SEAT_AREA * people + AISLE_EXTRA
    INFO[spot] = {
        "kind": "spot",
        "flow": None,  # a spot has no door of its own
        "cap": int(MAX_DENSITY * area), # most people that fit (standing included)
        "area": area,
        "seats": people, # people who start here
    }

# ==================================================================
# 8. Build NEXT: where you can go from each place, and the walk time (s)
# ==================================================================
NEXT = {}

for spot, exits in SPOT_EXITS.items():  # spot -> exit
    NEXT[spot] = {e: meters / WALK_SPEED for e, meters in exits.items()}
 
for spot, stairs in BALCONY_STAIRS.items(): # balcony spot -> stair
    NEXT[spot] = {t: meters / WALK_SPEED for t, meters in stairs.items()}
 
for stair, spots in STAIR_LANDS_IN.items(): # stair -> first-floor spot it lands in
    NEXT[stair] = {s: STAIR_TIME for s in spots}

# Crowd Managers know every door. From a first-floor spot, any door d can be reached by
# walking to one of the spot's own exits e, then along the wall from e to d:
#     distance = min over e of ( l_se + wall distance(e, d) )
def wall_distance(a, b):
    """Walking distance (m) along the wall between doors a and b."""
    i, j = sorted((WALL_ORDER.index(a), WALL_ORDER.index(b)))
    return sum(WALL_DIST[(WALL_ORDER[k], WALL_ORDER[k + 1])] for k in range(i, j))

CM_NEXT = {}   # spot -> {any door: seconds to walk there}, used only with Crowd Managers
for spot, exits in SPOT_EXITS.items():
    CM_NEXT[spot] = {d: min(m + wall_distance(e, d) for e, m in exits.items()) / WALK_SPEED
                     for d in WALL_ORDER}

# ==================================================================
# 9. Fastest time from each place to ANY exit (with nobody in the way)
#      Worked out from the outside in:
#      exits -> first-floor spots -> stairs -> balcony spots
# ==================================================================
TIME_TO_EXIT = {e: 0.0 for e in "ABCDEFGH"}
 
for spot in SPOT_EXITS: # first floor: the quickest of its exits
    TIME_TO_EXIT[spot] = min(NEXT[spot].values())
 
for stair in STAIR_LANDS_IN: # stair: go down, land in one of its spots (equally likely)
    spots = STAIR_LANDS_IN[stair]
    TIME_TO_EXIT[stair] = STAIR_TIME + sum(TIME_TO_EXIT[s] for s in spots) / len(spots)
 
for spot in BALCONY_STAIRS: # balcony: walk to a stair, then as above
    TIME_TO_EXIT[spot] = min(t + TIME_TO_EXIT[stair] for stair, t in NEXT[spot].items())


# ==================================================================
# Dynamic time to exit: like TIME_TO_EXIT, but recomputed every time step
# and including the waiting time Q/f at every door and stair further along.
#     h_e = 0                                            (exit)
#     h_s = min_e [ s*c_se + Q_e/f_e ]                   (first-floor spot)
#     h_x = tau + mean of h_s over its landing spots     (stair)
#     h_b = min_x [ s*c_bx + Q_x/f_x + h_x ]             (balcony spot)
# s = walking-time scale of this audience, tau = this scenario's stair time.
# ==================================================================
def dynamic_time_to_exit(queue, scale=1.0, stair_time=STAIR_TIME):
    def wait(n):                         # expected wait at a bottleneck
        return queue.get(n, 0) / INFO[n]["flow"]

    h = {e: 0.0 for e in "ABCDEFGH"}
    for spot in SPOT_EXITS:
        h[spot] = min(scale * t + wait(e) for e, t in NEXT[spot].items())
    for stair in STAIR_LANDS_IN:
        spots = STAIR_LANDS_IN[stair]
        h[stair] = stair_time + sum(h[s] for s in spots) / len(spots)
    for spot in BALCONY_STAIRS:
        h[spot] = min(scale * t + wait(x) + h[x] for x, t in NEXT[spot].items())
    return h

# =======
if __name__ == "__main__":
    print("people:", sum(SEATS.values()))
    for place in ["S13", "S20", "Y"]:
        print(place, "can go to", NEXT[place],
              "| fastest way out", round(TIME_TO_EXIT[place], 1), "s")