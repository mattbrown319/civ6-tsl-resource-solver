# $300 Bounty Solution — Minimum Aztec Cities to Control Every Resource (TSL World Map Huge, Gathering Storm)

## TL;DR

- **$200 answer: 9 cities** — covers all 28 luxury types
- **$300 answer: 10 cities** — covers all 28 luxuries + all 7 strategics, every city has harbor access
- **Provably optimal** — solved via Integer Linear Programming (ILP)

---

## Method

1. Extracted the complete tile and resource data from the game file `TSLWorldMapHuge_XP2.Civ6Map` (it's a SQLite database). Map is 130x66 = 8,580 tiles with 931 pre-placed resources.
2. Resources on this premade map are **fixed** — identical every game (no procedural generation runs on premade maps).
3. Formulated as a **Minimum Set Cover** problem: for each valid city tile, computed which resource types fall within hex distance 3 (the workable range). Then used an ILP solver to find the minimum number of cities such that every resource type is covered, subject to the Civ 6 minimum 4-tile city spacing constraint.
4. The ILP solver (CBC via PuLP) returns a **provably optimal** solution with a certificate of minimality.

---

## $200 Solution — 9 Cities (All 28 Luxury Types)

| # | Coordinates | Region | Luxury Resources Covered |
|---|-------------|--------|--------------------------|
| 1 | (24, 35) | Central America | Amber, Jade, Marble, Sugar, Tobacco |
| 2 | (35, 16) | Patagonia | Honey, Silver |
| 3 | (46, 24) | West Africa coast | Cocoa, Coffee, Honey |
| 4 | (59, 34) | North Africa | Diamonds, Incense, Ivory |
| 5 | (66, 44) | Western Europe | Amber, Citrus, Olives, Truffles, Wine |
| 6 | (84, 53) | Central Asia | Furs, Mercury |
| 7 | (103, 19) | Australia (NW) | Gypsum, Pearls, Salt |
| 8 | (103, 29) | Indonesia | Dyes, Spices, Turtles |
| 9 | (108, 43) | Eastern China | Cotton, Silk, Tea, Whales |

**LP relaxation lower bound: 8.50 → ceil(8.50) = 9 = solution. Proven optimal.**

---

## $300 Solution — 10 Cities (All 28 Luxuries + All 7 Strategics + Harbor Access)

| # | Coordinates | Region | Harbor | Luxury Resources | Strategic Resources |
|---|-------------|--------|--------|------------------|---------------------|
| 1 | (24, 35) | Central America | On coast | Amber, Jade, Marble, Sugar, Tobacco | Aluminum, Coal, Iron, Oil |
| 2 | (38, 20) | South America | Coast in range | Honey, Silver | Horses, Iron |
| 3 | (47, 25) | West Africa | On coast | Cocoa, Coffee, Honey | Niter |
| 4 | (60, 40) | NW Africa coast | On coast | Citrus, Olives | Iron, Niter, Oil |
| 5 | (63, 49) | Western Europe | On coast | Mercury, Truffles, Wine | Coal, Horses, Niter, Oil, Uranium |
| 6 | (77, 29) | Central Africa | On coast | Diamonds, Incense, Ivory | Horses |
| 7 | (89, 36) | Central Asia | On coast | Cotton, Silk, Tea | Coal, Horses, Iron, Oil |
| 8 | (104, 18) | Australia (NW) | Coast in range | Gypsum, Pearls, Salt | Horses, Iron, Oil |
| 9 | (104, 29) | Indonesia | On coast | Dyes, Spices, Turtles | Coal, Oil |
| 10 | (109, 47) | NE Asia | Coast in range | Furs, Whales | Iron, Oil |

All 10 cities can build a harbor on ocean coast (not lakes). Minimum inter-city distance: 9 tiles.

**LP relaxation lower bound: 9.50 → ceil(9.50) = 10 = solution. Proven optimal.**

---

## Proof of Minimality

The problem is formulated as an Integer Linear Program:

- **Variables**: Binary x_i ∈ {0,1} for each valid harbor-accessible city tile
- **Objective**: Minimize Σ x_i (total cities)
- **Coverage constraints**: For each of the 35 resource types t: Σ{x_i : city i covers type t} ≥ 1
- **Spacing constraints**: For each pair (i,j) with hex_distance < 4: x_i + x_j ≤ 1

The LP relaxation (allowing fractional 0 ≤ x_i ≤ 1) gives a lower bound of 9.50, meaning no integer solution can have fewer than ⌈9.50⌉ = 10 cities. Our solution achieves exactly 10, so it is **mathematically optimal**.

For the luxury-only problem (no harbor/strategic requirements), the LP bound is 8.50, and the solution is 9 cities.

Note: "harbor access" means an ocean-connected coast tile exists within the city's 3-tile workable range, so a harbor district can be built there. Lake tiles are excluded.

---

## Data Source

Resource positions extracted directly from:
```
Sid Meier's Civilization VI/DLC/Expansion2/Maps/EarthMaps/TSLWorldMapHuge_XP2.Civ6Map
```
This is a SQLite database containing the pre-placed tile data. The map script (`Continents.lua`) is referenced but does NOT call `ResourceGenerator.Create()` for premade maps — confirmed by starting 3 separate games and verifying identical resource layouts via save file parsing.

28 luxury types on map: Amber (12), Citrus (5), Cocoa (5), Coffee (6), Cotton (13), Diamonds (10), Dyes (2), Furs (22), Gypsum (2), Honey (6), Incense (10), Ivory (11), Jade (13), Marble (6), Mercury (5), Olives (7), Pearls (12), Salt (2), Silk (10), Silver (6), Spices (2), Sugar (6), Tea (12), Tobacco (7), Truffles (10), Turtles (12), Whales (14), Wine (6)

7 strategic types on map: Aluminum (19), Coal (32), Horses (25), Iron (36), Niter (22), Oil (58), Uranium (18)
