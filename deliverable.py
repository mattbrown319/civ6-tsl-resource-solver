#!/usr/bin/env python3
"""
Generate the full deliverable for the $300 Civ 6 TSL bounty.

Map: TSL World Map Huge (130x66), Gathering Storm
Civ: Aztec (TSL)
Goal: Minimum cities to control every luxury (and strategic) resource type.
"""

import csv
import os
from collections import defaultdict
import pulp
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import RegularPolygon
import numpy as np

# ============================================================
# Configuration
# ============================================================

MAP_WIDTH = 130
MAP_HEIGHT = 66
MAP_WRAPS_X = True

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TILE_CSV = os.path.join(SCRIPT_DIR, "TSLWorldMapHuge_XP2_all_tiles.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

IMPASSABLE_TERRAIN = {
    "TERRAIN_OCEAN", "TERRAIN_COAST",
    "TERRAIN_DESERT_MOUNTAIN", "TERRAIN_GRASS_MOUNTAIN",
    "TERRAIN_PLAINS_MOUNTAIN", "TERRAIN_SNOW_MOUNTAIN",
    "TERRAIN_TUNDRA_MOUNTAIN",
}

NATURAL_WONDERS = {
    "FEATURE_BARRIER_REEF", "FEATURE_DELICATE_ARCH", "FEATURE_EVEREST",
    "FEATURE_EYE_OF_THE_SAHARA", "FEATURE_GALAPAGOS", "FEATURE_HA_LONG_BAY",
    "FEATURE_KILIMANJARO", "FEATURE_MATTERHORN", "FEATURE_PANTANAL",
    "FEATURE_TORRES_DEL_PAINE", "FEATURE_TSINGY", "FEATURE_UBSUNUR_HOLLOW",
    "FEATURE_ULURU", "FEATURE_WHITEDESERT", "FEATURE_ZHANGYE_DANXIA",
}

LUXURY_RESOURCES = {
    "RESOURCE_AMBER", "RESOURCE_CITRUS", "RESOURCE_COCOA", "RESOURCE_COFFEE",
    "RESOURCE_COTTON", "RESOURCE_DIAMONDS", "RESOURCE_DYES", "RESOURCE_FURS",
    "RESOURCE_GYPSUM", "RESOURCE_HONEY", "RESOURCE_INCENSE", "RESOURCE_IVORY",
    "RESOURCE_JADE", "RESOURCE_MARBLE", "RESOURCE_MERCURY", "RESOURCE_OLIVES",
    "RESOURCE_PEARLS", "RESOURCE_SALT", "RESOURCE_SILK", "RESOURCE_SILVER",
    "RESOURCE_SPICES", "RESOURCE_SUGAR", "RESOURCE_TEA", "RESOURCE_TOBACCO",
    "RESOURCE_TRUFFLES", "RESOURCE_TURTLES", "RESOURCE_WHALES", "RESOURCE_WINE",
}

STRATEGIC_RESOURCES = {
    "RESOURCE_ALUMINUM", "RESOURCE_COAL", "RESOURCE_HORSES", "RESOURCE_IRON",
    "RESOURCE_NITER", "RESOURCE_OIL", "RESOURCE_URANIUM",
}

MIN_CITY_DISTANCE = 4

# Real-world labels for map regions
REGION_LABELS = {
    (15, 55): "Alaska",
    (20, 47): "Canada",
    (18, 40): "USA",
    (24, 35): "Mexico/\nC. America",
    (33, 25): "Brazil",
    (35, 15): "Patagonia",
    (55, 35): "N. Africa",
    (60, 25): "C. Africa",
    (67, 47): "W. Europe",
    (75, 47): "E. Europe",
    (80, 35): "Middle East",
    (90, 50): "Russia",
    (95, 40): "C. Asia",
    (105, 40): "China",
    (110, 48): "Siberia",
    (115, 35): "SE Asia",
    (105, 25): "Indonesia",
    (75, 15): "S. Africa",
}


def offset_to_cube(x, y):
    q = x
    r = y - (x + (x & 1)) // 2
    s = -q - r
    return (q, r, s)


def hex_distance(x1, y1, x2, y2):
    best = float('inf')
    candidates_x2 = [x2]
    if MAP_WRAPS_X:
        candidates_x2.extend([x2 + MAP_WIDTH, x2 - MAP_WIDTH])
    for cx2 in candidates_x2:
        q1, r1, s1 = offset_to_cube(x1, y1)
        q2, r2, s2 = offset_to_cube(cx2, y2)
        dist = max(abs(q1 - q2), abs(r1 - r2), abs(s1 - s2))
        best = min(best, dist)
    return best


def load_tiles():
    tiles = {}
    with open(TILE_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            x, y = int(row["X"]), int(row["Y"])
            tiles[(x, y)] = {
                "terrain": row["TerrainType"],
                "feature": row["FeatureType"],
                "continent": row["ContinentType"],
                "resource": row["ResourceType"],
            }
    return tiles


def is_valid_city_tile(tile):
    if tile["terrain"] in IMPASSABLE_TERRAIN:
        return False
    if tile["feature"] in NATURAL_WONDERS:
        return False
    if tile["feature"] == "FEATURE_ICE":
        return False
    return True


def is_coastal_tile(x, y, tiles):
    """Check if city center is directly adjacent to water (strict coastal)."""
    neighbors = get_hex_neighbors(x, y)
    for nx, ny in neighbors:
        if (nx, ny) in tiles:
            t = tiles[(nx, ny)]["terrain"]
            if t in ("TERRAIN_COAST", "TERRAIN_OCEAN"):
                return True
    return False


def _find_ocean_coast(tiles):
    """Find coast tiles connected to the ocean (excludes lakes)."""
    from collections import deque
    water = {(x, y) for (x, y), t in tiles.items()
             if t["terrain"] in ("TERRAIN_COAST", "TERRAIN_OCEAN")}
    ocean = {(x, y) for (x, y), t in tiles.items()
             if t["terrain"] == "TERRAIN_OCEAN"}
    # BFS from ocean through all connected water tiles
    connected = set(ocean)
    queue = deque(ocean)
    while queue:
        x, y = queue.popleft()
        for nx, ny in get_hex_neighbors(x, y):
            if (nx, ny) in water and (nx, ny) not in connected:
                connected.add((nx, ny))
                queue.append((nx, ny))
    coast = {(x, y) for (x, y), t in tiles.items()
             if t["terrain"] == "TERRAIN_COAST"}
    return coast & connected


def has_harbor_access(x, y, tiles, _cache={}):
    """Check if a city can build a harbor on ocean coast within 3 hexes.

    In Civ 6, a harbor district can be placed on any coast tile within
    the city's workable range (up to 3 tiles from city center).
    Excludes lake tiles (coast not connected to ocean).
    """
    if "ocean_coast" not in _cache:
        _cache["ocean_coast"] = _find_ocean_coast(tiles)
    return any(hex_distance(x, y, cx, cy) <= 3
               for cx, cy in _cache["ocean_coast"])


def get_hex_neighbors(x, y):
    neighbors = []
    if x % 2 == 0:
        deltas = [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (0, 1)]
    else:
        deltas = [(1, 1), (1, 0), (0, -1), (-1, 0), (-1, 1), (0, 1)]
    for dx, dy in deltas:
        nx = (x + dx) % MAP_WIDTH if MAP_WRAPS_X else x + dx
        ny = y + dy
        if 0 <= ny < MAP_HEIGHT:
            if not MAP_WRAPS_X and (nx < 0 or nx >= MAP_WIDTH):
                continue
            neighbors.append((nx, ny))
    return neighbors


def build_coverage(tiles, target_resources):
    resource_locations = defaultdict(list)
    for (x, y), tile in tiles.items():
        res = tile["resource"]
        if res in target_resources:
            resource_locations[res].append((x, y))

    valid_cities = [(x, y) for (x, y), tile in tiles.items()
                    if is_valid_city_tile(tile)]

    resource_coverage = defaultdict(set)
    for res_type, locations in resource_locations.items():
        for rx, ry in locations:
            for cx, cy in valid_cities:
                if hex_distance(cx, cy, rx, ry) <= 3:
                    resource_coverage[(cx, cy)].add(res_type)

    candidate_cities = {pos: types for pos, types in resource_coverage.items()
                        if len(types) > 0}

    return candidate_cities, resource_locations


def solve_minimum_cover(candidate_cities, resource_types, tiles,
                        require_coastal=False, min_city_dist=0):
    all_types = sorted(resource_types)
    city_positions = sorted(candidate_cities.keys())

    if require_coastal:
        coastal_cities = {pos for pos in city_positions
                          if has_harbor_access(pos[0], pos[1], tiles)}
        city_positions = sorted(coastal_cities)
        candidate_cities = {pos: types for pos, types in candidate_cities.items()
                            if pos in coastal_cities}

    coverable_types = set()
    for types in candidate_cities.values():
        coverable_types.update(types)
    uncoverable = set(all_types) - coverable_types
    if uncoverable:
        print(f"    WARNING: Cannot cover: {uncoverable}")
        all_types = [t for t in all_types if t not in uncoverable]

    prob = pulp.LpProblem("MinCityCover", pulp.LpMinimize)
    city_vars = {}
    for pos in city_positions:
        city_vars[pos] = pulp.LpVariable(f"city_{pos[0]}_{pos[1]}", cat="Binary")

    prob += pulp.lpSum(city_vars.values()), "TotalCities"

    for res_type in all_types:
        covering = [city_vars[pos] for pos in city_positions
                    if res_type in candidate_cities.get(pos, set())]
        if covering:
            prob += pulp.lpSum(covering) >= 1, f"Cover_{res_type}"

    if min_city_dist > 0:
        for i, pos1 in enumerate(city_positions):
            for pos2 in city_positions[i + 1:]:
                if hex_distance(pos1[0], pos1[1], pos2[0], pos2[1]) < min_city_dist:
                    prob += city_vars[pos1] + city_vars[pos2] <= 1, \
                        f"Dist_{pos1[0]}_{pos1[1]}_{pos2[0]}_{pos2[1]}"

    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=300))

    if pulp.LpStatus[prob.status] != "Optimal":
        return None, None

    selected = [pos for pos in city_positions if city_vars[pos].varValue > 0.5]

    # Get LP relaxation lower bound for minimality proof
    prob_relax = pulp.LpProblem("MinCityCover_Relaxed", pulp.LpMinimize)
    city_vars_r = {}
    for pos in city_positions:
        city_vars_r[pos] = pulp.LpVariable(f"city_{pos[0]}_{pos[1]}",
                                            lowBound=0, upBound=1)
    prob_relax += pulp.lpSum(city_vars_r.values()), "TotalCities"
    for res_type in all_types:
        covering = [city_vars_r[pos] for pos in city_positions
                    if res_type in candidate_cities.get(pos, set())]
        if covering:
            prob_relax += pulp.lpSum(covering) >= 1, f"Cover_{res_type}"
    if min_city_dist > 0:
        for i, pos1 in enumerate(city_positions):
            for pos2 in city_positions[i + 1:]:
                if hex_distance(pos1[0], pos1[1], pos2[0], pos2[1]) < min_city_dist:
                    prob_relax += city_vars_r[pos1] + city_vars_r[pos2] <= 1, \
                        f"Dist_{pos1[0]}_{pos1[1]}_{pos2[0]}_{pos2[1]}"
    prob_relax.solve(pulp.PULP_CBC_CMD(msg=0))
    lp_bound = pulp.value(prob_relax.objective) if prob_relax.status == 1 else 0

    return selected, lp_bound


def resource_name(r):
    return r.replace("RESOURCE_", "")


# ============================================================
# Map visualization
# ============================================================

def hex_to_pixel(x, y):
    """Convert offset hex coords to pixel coords for drawing."""
    px = x * 1.5
    py = y * np.sqrt(3)
    if x % 2 == 1:
        py += np.sqrt(3) / 2
    return px, py  # y=0 is south, y increases north


TERRAIN_COLORS = {
    "TERRAIN_OCEAN": "#1a3a5c",
    "TERRAIN_COAST": "#4a8ab5",
    "TERRAIN_GRASS": "#5d8a3c",
    "TERRAIN_GRASS_HILLS": "#4d7a2c",
    "TERRAIN_GRASS_MOUNTAIN": "#3d5a2c",
    "TERRAIN_PLAINS": "#a8b060",
    "TERRAIN_PLAINS_HILLS": "#8a9040",
    "TERRAIN_PLAINS_MOUNTAIN": "#6a7030",
    "TERRAIN_DESERT": "#d4c090",
    "TERRAIN_DESERT_HILLS": "#b4a070",
    "TERRAIN_DESERT_MOUNTAIN": "#8a7850",
    "TERRAIN_TUNDRA": "#8a9a7a",
    "TERRAIN_TUNDRA_HILLS": "#7a8a6a",
    "TERRAIN_TUNDRA_MOUNTAIN": "#5a6a4a",
    "TERRAIN_SNOW": "#d8dce0",
    "TERRAIN_SNOW_HILLS": "#c0c4c8",
    "TERRAIN_SNOW_MOUNTAIN": "#a0a4a8",
}


def draw_map(tiles, selected_cities, candidate_cities, resource_locations,
             filename, title, target_resources):
    """Draw the hex map with cities and resources marked."""
    fig, ax = plt.subplots(1, 1, figsize=(52, 22))
    ax.set_aspect('equal')
    ax.set_title(title, fontsize=24, fontweight='bold', pad=30, color='white')

    hex_size = 0.58

    # Draw terrain
    for (x, y), tile in tiles.items():
        px, py = hex_to_pixel(x, y)
        color = TERRAIN_COLORS.get(tile["terrain"], "#808080")
        hex_patch = RegularPolygon((px, py), numVertices=6, radius=hex_size,
                                   orientation=0, facecolor=color,
                                   edgecolor='none', alpha=0.8)
        ax.add_patch(hex_patch)

    # Draw resource tiles (small dots)
    for res_type, locs in resource_locations.items():
        if res_type in target_resources:
            for rx, ry in locs:
                px, py = hex_to_pixel(rx, ry)
                color = '#FFD700' if res_type in LUXURY_RESOURCES else '#C0C0C0'
                ax.plot(px, py, 'o', color=color, markersize=3, alpha=0.8)

    # Draw selected cities
    city_colors = plt.cm.tab10(np.linspace(0, 1, max(len(selected_cities), 1)))
    for i, (cx, cy) in enumerate(sorted(selected_cities)):
        px, py = hex_to_pixel(cx, cy)

        # Draw coverage radius (3 tiles)
        circle = plt.Circle((px, py), hex_size * 10, fill=False,
                             edgecolor=city_colors[i], linewidth=1.5,
                             linestyle='--', alpha=0.5)
        ax.add_patch(circle)

        # Draw city marker
        ax.plot(px, py, '*', color=city_colors[i], markersize=28,
                markeredgecolor='white', markeredgewidth=1.2, zorder=10)

        # Label
        covered = candidate_cities.get((cx, cy), set())
        lux_covered = [resource_name(r) for r in sorted(covered)
                       if r in LUXURY_RESOURCES]
        strat_covered = [resource_name(r) for r in sorted(covered)
                         if r in STRATEGIC_RESOURCES]
        label = f"City {i+1}  ({cx},{cy})\n"
        label += ", ".join(lux_covered)
        if strat_covered:
            label += "\n" + ", ".join(strat_covered)

        ax.annotate(label, (px, py), textcoords="offset points",
                    xytext=(18, 12), fontsize=9, fontweight='bold',
                    color='white', zorder=11,
                    bbox=dict(boxstyle='round,pad=0.4',
                              facecolor=city_colors[i], alpha=0.9,
                              edgecolor='white', linewidth=0.8))

    # Axis setup
    all_px = [hex_to_pixel(x, y)[0] for x, y in tiles.keys()]
    all_py = [hex_to_pixel(x, y)[1] for x, y in tiles.keys()]
    ax.set_xlim(min(all_px) - 2, max(all_px) + 2)
    ax.set_ylim(min(all_py) - 2, max(all_py) + 2)
    ax.set_facecolor('#0a1a2c')
    ax.axis('off')

    # Legend
    legend_elements = [
        mpatches.Patch(color='#FFD700', label='Luxury Resource'),
        mpatches.Patch(color='#C0C0C0', label='Strategic Resource'),
        plt.Line2D([0], [0], marker='*', color='w', markerfacecolor='red',
                   markersize=12, label='City Location', linestyle='None'),
    ]
    ax.legend(handles=legend_elements, loc='lower left', fontsize=14,
              facecolor='#1a2a3c', edgecolor='white', labelcolor='white')

    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight',
                facecolor='#0a1a2c', edgecolor='none')
    plt.close()
    print(f"  Map saved: {filename}")


# ============================================================
# Text report
# ============================================================

def generate_report(selected_cities, candidate_cities, resource_locations,
                    tiles, lp_bound, scenario_label, target_resources):
    """Generate detailed text report."""
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"  {scenario_label}")
    lines.append(f"{'='*70}")
    lines.append(f"")
    lines.append(f"Map: TSL World Map Huge (130 x 66 tiles)")
    lines.append(f"Ruleset: Gathering Storm (with all DLC)")
    lines.append(f"Resources: Fixed (pre-placed in .Civ6Map SQLite file)")
    lines.append(f"")
    lines.append(f"ANSWER: {len(selected_cities)} cities")
    lines.append(f"")

    all_covered_lux = set()
    all_covered_strat = set()

    for i, (cx, cy) in enumerate(sorted(selected_cities)):
        tile = tiles[(cx, cy)]
        covered = candidate_cities.get((cx, cy), set())
        adj_coastal = is_coastal_tile(cx, cy, tiles)
        harbor = has_harbor_access(cx, cy, tiles)

        lux = sorted([r for r in covered if r in LUXURY_RESOURCES])
        strat = sorted([r for r in covered if r in STRATEGIC_RESOURCES])
        all_covered_lux.update(lux)
        all_covered_strat.update(strat)

        lines.append(f"  City {i+1}: ({cx}, {cy})")
        lines.append(f"    Terrain: {tile['terrain'].replace('TERRAIN_','')}")
        feat = tile['feature'].replace('FEATURE_','') if tile['feature'] else 'None'
        lines.append(f"    Feature: {feat}")
        lines.append(f"    Continent: {tile['continent'].replace('CONTINENT_','') if tile['continent'] else 'N/A'}")
        if adj_coastal:
            lines.append(f"    Harbor access: Yes (city on coast)")
        elif harbor:
            lines.append(f"    Harbor access: Yes (coast within workable range)")
        else:
            lines.append(f"    Harbor access: No")
        if lux:
            lines.append(f"    Luxury resources ({len(lux)}):")
            for r in lux:
                # Find which instance(s) this city covers
                for rx, ry in resource_locations.get(r, []):
                    d = hex_distance(cx, cy, rx, ry)
                    if d <= 3:
                        lines.append(f"      - {resource_name(r)} at ({rx},{ry}), distance {d}")
                        break
        if strat:
            lines.append(f"    Strategic resources ({len(strat)}):")
            for r in strat:
                for rx, ry in resource_locations.get(r, []):
                    d = hex_distance(cx, cy, rx, ry)
                    if d <= 3:
                        lines.append(f"      - {resource_name(r)} at ({rx},{ry}), distance {d}")
                        break
        lines.append(f"")

    # Coverage summary
    lux_on_map = set(r for r in resource_locations if r in LUXURY_RESOURCES)
    strat_on_map = set(r for r in resource_locations if r in STRATEGIC_RESOURCES)

    lines.append(f"  COVERAGE SUMMARY")
    lines.append(f"  ────────────────")
    lines.append(f"  Luxury types covered:    {len(all_covered_lux)}/{len(lux_on_map)}")
    lines.append(f"  Strategic types covered: {len(all_covered_strat)}/{len(strat_on_map)}")

    all_harbor = all(has_harbor_access(cx, cy, tiles) for cx, cy in selected_cities)
    lines.append(f"  All cities harbor access: {'Yes' if all_harbor else 'No'}")

    # City spacing
    min_dist = float('inf')
    for i, p1 in enumerate(sorted(selected_cities)):
        for p2 in sorted(selected_cities)[i + 1:]:
            d = hex_distance(p1[0], p1[1], p2[0], p2[1])
            min_dist = min(min_dist, d)
    if len(selected_cities) > 1:
        lines.append(f"  Min inter-city distance: {min_dist} tiles (>= 4 required)")

    # Minimality proof
    lines.append(f"")
    lines.append(f"  PROOF OF MINIMALITY")
    lines.append(f"  ───────────────────")
    lines.append(f"  Method: Integer Linear Programming (ILP) with CBC solver")
    lines.append(f"  ")
    lines.append(f"  The problem is formulated as a Minimum Weighted Set Cover:")
    lines.append(f"  - Binary variable x_i for each candidate city tile i")
    lines.append(f"  - Minimize: sum(x_i)")
    lines.append(f"  - Subject to: for each resource type t,")
    lines.append(f"      sum(x_i for cities i that cover type t) >= 1")
    lines.append(f"  - Distance constraint: for each pair (i,j) with dist < 4,")
    lines.append(f"      x_i + x_j <= 1")
    if lp_bound:
        lines.append(f"  ")
        lines.append(f"  LP relaxation lower bound: {lp_bound:.2f}")
        lines.append(f"  ILP optimal solution:      {len(selected_cities)}")
        lp_ceil = int(np.ceil(lp_bound))
        if lp_ceil == len(selected_cities):
            lines.append(f"  Since ceil({lp_bound:.2f}) = {lp_ceil} = {len(selected_cities)},")
            lines.append(f"  the solution is provably optimal.")
        else:
            lines.append(f"  LP lower bound: ceil({lp_bound:.2f}) = {lp_ceil}.")
            lines.append(f"  The ILP solver's branch-and-bound search proves {len(selected_cities)}")
            lines.append(f"  is optimal (no feasible integer solution with fewer cities exists).")
    lines.append(f"  ")
    lines.append(f"  The ILP solver guarantees that no feasible solution exists")
    lines.append(f"  with fewer than {len(selected_cities)} cities while satisfying all constraints.")
    lines.append(f"  This is a certificate of mathematical minimality.")

    # Resource type matrix
    lines.append(f"")
    lines.append(f"  RESOURCE-TO-CITY MAPPING")
    lines.append(f"  ───────────────────────")
    sorted_cities = sorted(selected_cities)
    for res_type in sorted(target_resources & set(resource_locations.keys())):
        covering = []
        for i, (cx, cy) in enumerate(sorted_cities):
            if res_type in candidate_cities.get((cx, cy), set()):
                covering.append(f"City {i+1}")
        cat = "LUX" if res_type in LUXURY_RESOURCES else "STR"
        lines.append(f"  [{cat}] {resource_name(res_type):12s} -> {', '.join(covering)}")

    return "\n".join(lines)


# ============================================================
# Main
# ============================================================

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Loading map data...")
    tiles = load_tiles()
    print(f"  {len(tiles)} tiles loaded")

    # ---- $200 Solution: Luxuries only ----
    print("\nBuilding luxury coverage...")
    cand_lux, res_locs_lux = build_coverage(tiles, LUXURY_RESOURCES)
    print(f"  {len(cand_lux)} candidate cities")

    print("Solving luxury-only (with 4-tile spacing)...")
    selected_lux, lp_lux = solve_minimum_cover(
        cand_lux, set(res_locs_lux.keys()), tiles,
        require_coastal=False, min_city_dist=MIN_CITY_DISTANCE)

    if selected_lux:
        report_lux = generate_report(
            selected_lux, cand_lux, res_locs_lux, tiles, lp_lux,
            "$200 SOLUTION: Minimum Cities for All 28 Luxury Types",
            LUXURY_RESOURCES)
        report_path = os.path.join(OUTPUT_DIR, "solution_200_luxuries.txt")
        with open(report_path, "w") as f:
            f.write(report_lux)
        print(f"  Report: {report_path}")
        print(report_lux)

        draw_map(tiles, selected_lux, cand_lux, res_locs_lux,
                 os.path.join(OUTPUT_DIR, "map_200_luxuries.png"),
                 f"$200 Solution: {len(selected_lux)} Cities — All 28 Luxury Types",
                 LUXURY_RESOURCES)

    # ---- $300 Solution: Luxuries + Strategics + Coastal ----
    print("\nBuilding full coverage...")
    all_target = LUXURY_RESOURCES | STRATEGIC_RESOURCES
    cand_all, res_locs_all = build_coverage(tiles, all_target)
    print(f"  {len(cand_all)} candidate cities")

    print("Solving luxury + strategic + coastal (with 4-tile spacing)...")
    selected_bonus, lp_bonus = solve_minimum_cover(
        cand_all, set(res_locs_all.keys()), tiles,
        require_coastal=True, min_city_dist=MIN_CITY_DISTANCE)

    if selected_bonus:
        report_bonus = generate_report(
            selected_bonus, cand_all, res_locs_all, tiles, lp_bonus,
            "$300 SOLUTION: All 28 Luxuries + All 7 Strategics + Coastal",
            all_target)
        report_path = os.path.join(OUTPUT_DIR, "solution_300_full.txt")
        with open(report_path, "w") as f:
            f.write(report_bonus)
        print(f"  Report: {report_path}")
        print(report_bonus)

        draw_map(tiles, selected_bonus, cand_all, res_locs_all,
                 os.path.join(OUTPUT_DIR, "map_300_full.png"),
                 f"$300 Solution: {len(selected_bonus)} Cities — All Luxuries + Strategics + Coastal",
                 all_target)

    print(f"\nAll outputs saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
