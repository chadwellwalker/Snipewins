# Chrome Prompt — Download NBA Price Lists (so the new Topps NBA cards VALUE)

Paste into Claude-in-Chrome. Be **logged into sportscardspro.com with Legendary**. Download
each set's **price-guide CSV** (the "Download Price Guide" button at the bottom of the set's
price table) into the Downloads folder. Skip anything that 404s or has no download button —
note it and move on.

Why this list: the scanner now *finds* these NBA cards, but the store can't *price* them
without their SportsCardsPro price lists. These are the gaps.

---

## PRIORITY 1 — New Topps NBA (the 2025-26 Fanatics license; this is the main gap)
1. **2025-26 Topps Chrome Basketball**
2. **2025-26 Topps Chrome Sapphire Basketball**
3. **2025-26 Topps Finest Basketball** (if released)
4. **2025-26 Topps Basketball** (flagship base)
5. **2025-26 Topps NBA Hoops**
6. **2025-26 Topps Chrome Black Basketball** (if it exists)

## PRIORITY 2 — Panini NBA high-end (for the stars' patch autos / RPAs / Logoman)
These carry the premium chase cards for the vet stars + rookies we just added:
7. **2023-24 Panini National Treasures Basketball**
8. **2023-24 Panini Immaculate Basketball**
9. **2023-24 Panini Flawless Basketball**
10. **2024-25 Panini National Treasures Basketball** (if not already loaded)
11. **2024-25 Panini Immaculate Basketball** (if not already loaded)

## PRIORITY 3 — Panini NBA liquid depth (older years for vet-star + legend cards)
The vintage legends (Magic, Bird, Shaq, Iverson, Duncan, Garnett) and vet stars appear in
modern Panini inserts across these years:
12. **2021-22 Panini Select Basketball**
13. **2021-22 Panini Mosaic Basketball**
14. **2021-22 Donruss Optic Basketball**
15. **2022-23 Panini Select Basketball**
16. **2022-23 Panini Mosaic Basketball**
17. **2022-23 Donruss Optic Basketball**
18. **2023-24 Panini Prizm Basketball** (if not already loaded)
19. **2023-24 Panini Select Basketball**
20. **2023-24 Panini Mosaic Basketball**

> Note: the site files NBA seasons WITHOUT the slash — "2021-22" shows as "2021 Panini Select",
> etc. That's fine; `scp_sync.py` reads the set name from inside the CSV, not the filename.

---

## Report back
Checklist: each set → ✓ downloaded / ✗ not found. Count CSVs in Downloads.

## ALREADY LOADED — skip (don't re-download)
2020-21 & 2024-25 Panini Prizm/Select/Mosaic/Optic Basketball; 2023 & 2024 Panini Prizm;
2024 Panini Court Kings/Hoops/Donruss/Donruss Optic/Origins/Revolution/National Treasures/
Immaculate Basketball; 2024-25 Flawless Basketball; 2024 Topps Chrome Basketball; 2023 Panini
Prizm/Select.

---

After downloading: the engineer runs `python scp_sync.py` → commits the CSVs → pushes, and the
new NBA sets go live on the next deploy (the rebuild now auto-triggers on CSV-count change).
Priority 1 is the big one — without it, the new Topps NBA cards discover but show NO COMPS.
