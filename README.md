# Civ 6 TSL Huge Earth — Minimum Cities to Cover All Resources

Solves the minimum set cover problem for the TSL World Map Huge (Gathering Storm).

## Solutions

- **$200 (luxuries only):** 9 cities cover all 28 luxury types
- **$300 (full):** 10 cities cover all 28 luxuries + 7 strategics, all with ocean harbor access

Results are in `output/`.

## Verify

```
pip install -r requirements.txt
python deliverable.py
```

This regenerates all solutions and maps from scratch. Takes ~2 minutes.

## How it works

1. Reads tile data from `TSLWorldMapHuge_XP2_all_tiles.csv` (extracted from the game's `.Civ6Map` SQLite file)
2. For each valid city tile, computes which resource types fall within hex distance 3 (workable range)
3. Solves a Minimum Set Cover ILP (Integer Linear Program) with city spacing constraints
4. The CBC solver guarantees the solution is provably optimal
