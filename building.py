"""
We model Baily Hall first floor into 16 spots (S1-S16) with 8 exists (A-H),
and balcony into 6 spots (S17-S22) with 4 stairs (XYZW) connecting to first floor.

Nodes: the spots, stairs, and exits.
Edges: spot-> exit, spot(S17-S22)->stairs, staris->exits(X->A, Y->C,D,E, Z->C,D,E, W->G,H)

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
WALK_SPEED = 1.24 # m/s, (Seyfried et al. 2005)
MAX_DENSITY = 3.8     # people per m^2 at which a crowd stops moving (SFPE)
STAIR_TIME  = 20.0    # seconds to walk down one balcony stair (team estimate)
SQFT        = 0.0929  # 1 square foot in m^2

# Whole-floor areas printed on the floor plans (used only as a sanity check)
GROSS_AREA = {1: 18602 * SQFT,    # first floor  = 1728 m^2
              2: 7107 * SQFT}     # second floor =  660 m^2

# ==================================================================
# 2. First floor: which exits each spot can use, and how far (m)
# ==================================================================
SPOT_EXITS = {
    "S1":  {"A": 17},
    "S2":  {"A": 20, "B": 14},
    "S3":  {"B": 9,  "C": 12},
    "S4":  {"A": 23, "G": 24, "H": 28},
    "S5":  {"C": 20, "D": 22, "E": 20},
    "S6":  {"C": 13, "D": 15, "E": 13},
    "S7":  {"G": 16, "H": 22},
    "S8":  {"F": 15, "G": 15},
    "S9":  {"E": 13, "F": 9},
    "S10": {"G": 6,  "H": 19},
    "S11": {"F": 11, "G": 8},
    "S12": {"E": 12, "F": 5},
    "S13": {"C": 7,  "D": 4, "E": 7},
    "S14": {"B": 4,  "C": 11},
    "S15": {"A": 9,  "B": 15},
    "S16": {"A": 7},
}

# ==================================================================
# 3. Balcony: We split each route into two parts so a stair can be a shared bottleneck
#     BALCONY_STAIRS : seat -> top of stair (m)
#     STAIR_EXITS    : bottom of stair -> exit (m), plus STAIR_TIME on the stair
# ==================================================================
STAIR_EXITS = {
    "X": {"A": 7},
    "Y": {"C": 7, "D": 11, "E": 14},
    "Z": {"C": 14, "D": 11, "E": 7},
    "W": {"G": 6, "H": 9},
}
 
BALCONY_STAIRS = {
    "S17": {"X": 14},
    "S18": {"X": 22, "Y": 25},
    "S19": {"Y": 18, "Z": 31},
    "S20": {"Y": 13, "Z": 21},
    "S21": {"Y": 20, "Z": 14},
    "S22": {"W": 16},
}

MEASURED_ROUTES = {
    "S17": {("X", "A"): 21},
    "S18": {("X", "A"): 29, ("Y", "C"): 32, ("Y", "D"): 36, ("Y", "E"): 39},
    "S19": {("Y", "C"): 25, ("Y", "D"): 29, ("Y", "E"): 33,
            ("Z", "C"): 45, ("Z", "D"): 42, ("Z", "E"): 38},
    "S20": {("Y", "C"): 20, ("Y", "D"): 24, ("Y", "E"): 27,
            ("Z", "C"): 35, ("Z", "D"): 32, ("Z", "E"): 28},
    "S21": {("Y", "C"): 27, ("Y", "D"): 31, ("Y", "E"): 34,
            ("Z", "C"): 28, ("Z", "D"): 24, ("Z", "E"): 21},
    "S22": {("W", "G"): 22, ("W", "H"): 25},
}

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
STAIR_AREA  = 1.2 * 10    # PLACEHOLDER: stair 1.2 m wide x 10 m long
EXIT_WIDTH  = 1.5         # PLACEHOLDER: clear width of each exit door (m)
STAIR_WIDTH = 1.2         # PLACEHOLDER: width of each stair (m)

# ==================================================================
# 6. Formulas from the SFPE fire-engineering handbook
# ==================================================================
def door_flow(width, people_per_meter):
    """How many people per second can get through an opening.
    people_per_meter = 1.3 for doors, about 1.0 for stairs.
    0.3 m is subtracted because people keep ~15 cm away from each side."""
    return people_per_meter * (width - 0.3)
 
 
def crowd_speed(people, area):
    """Walking speed (m/s) when `people` share `area` m^2.
    The more crowded, the slower: v = 1.4 * (1 - 0.266 * density).
    Never faster than WALK_SPEED, never slower than 0.1 m/s."""
    density = people / area
    v = 1.4 * (1 - 0.266 * density)
    return max(0.1, min(WALK_SPEED, v))

# ==================================================================
# 7. Build INFO: facts about each node
# ==================================================================
INFO = {}

for exit_name in "ABCDEFGH":
    INFO[exit_name] = {
        "kind": "exit",
        "flow": door_flow(EXIT_WIDTH, 1.3) # people/sec through the door
    }

for stair in STAIR_EXITS:
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
 
for stair, exits in STAIR_EXITS.items(): # stair -> exit
    NEXT[stair] = {e: STAIR_TIME + meters / WALK_SPEED for e, meters in exits.items()}

# ==================================================================
# 9. Fastest time from each place to ANY exit (with nobody in the way)
#      Worked out from the outside in:
#      exits -> first-floor spots -> stairs -> balcony spots
# ==================================================================
TIME_TO_EXIT = {e: 0.0 for e in "ABCDEFGH"}
 
for spot in SPOT_EXITS: # first floor: the quickest of its exits
    TIME_TO_EXIT[spot] = min(NEXT[spot].values())
 
for stair in STAIR_EXITS: # stair: go down, then the quickest of its exits
    TIME_TO_EXIT[stair] = min(NEXT[stair].values())
 
for spot in BALCONY_STAIRS: # balcony: walk to a stair, then as above
    TIME_TO_EXIT[spot] = min(t + TIME_TO_EXIT[stair] for stair, t in NEXT[spot].items())

# =======
if __name__ == "__main__":
    print("people:", sum(SEATS.values()))
    for place in ["S13", "S20", "Y"]:
        print(place, "can go to", NEXT[place],
              "| fastest way out", round(TIME_TO_EXIT[place], 1), "s")