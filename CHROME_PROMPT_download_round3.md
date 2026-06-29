# Chrome Prompt — Download Round 3 (fill the audit's NO-COMPS gaps)

Paste into Claude-in-Chrome. You must be **logged into sportscardspro.com with Legendary**.
Download each set's **price-guide CSV** (the "Download Price Guide" button at the bottom of
the set's price table) into the Downloads folder. We already have 119 sets loaded — only the
sets below are missing and showed up as NO COMPS in today's audit. Skip anything that 404s
or has no download button; note it and move on.

---

## BASEBALL — specific NO-COMPS cards from today's board
1. **2018 Topps Chrome Update** — (Juan Soto RC auto, Ronald Acuna RC auto kept showing NO COMPS)
2. **2019 Bowman Draft Chrome** — (Gunnar Henderson Purple Refractor /250)
3. **2013 Bowman Draft** (a.k.a. 2013 Bowman Chrome Draft) — (Aaron Judge Draft Picks / dual auto)
4. **2021 Topps Gypsy Queen** — (Juan Soto Chrome Refractor Auto /25)
5. **2026 Bowman Chrome** (the base/flagship set — we only have "2026 Bowman Chrome Prospect")
6. **2023 Bowman Draft Chrome** — (if not already present; Holliday/Wood draft autos)
7. **2017 Topps Chrome** — (Aaron Judge #169 RC)

## BASKETBALL — the NBA gap (this is the priority — NBA is starved)
These older NBA years carry the rookie-era cards (Anthony Edwards, LaMelo, etc.) that came up
NO COMPS, and they'll feed the 3-sport rebalance:
8. **2020-21 Panini Prizm Basketball**
9. **2021-22 Panini Prizm Basketball**
10. **2022-23 Panini Prizm Basketball**
11. **2020-21 Panini Mosaic Basketball**
12. **2020-21 Donruss Optic Basketball**
13. **2020-21 Panini Select Basketball**
14. **2025-26 Panini Prizm Basketball** (if released — newest rookies)
15. **2024-25 Panini Flawless Basketball** (RPAs/patches for the patch-auto fix)

## FOOTBALL — high-end for the patch/RPA cards
These carry the patch autos / RPAs that now correctly show NO COMPS (so they'll fill in as exact):
16. **2024 Panini Flawless Football**
17. **2023 Panini National Treasures Football**
18. **2023 Panini Immaculate Football**
19. **2024 Panini Spectra Football** (if not already present)
20. **2025 Panini Phoenix Football** (if not already present)

---

## Report back
A simple checklist: each set → ✓ downloaded / ✗ not found. Count CSVs that landed in Downloads.

## ALREADY LOADED — do NOT re-download (119 sets), key ones:
All Bowman Chrome 2013/2014/2016/2018/2019/2020/2021/2022/2023/2024/2025; Bowman Chrome Prospects
2024/2026; Bowman Draft Chrome 2022/2024/2025; Topps Chrome 2020/2021/2022/2023/2024/2025; Topps
Chrome Black 2021/2022/2024/2025/2026; Topps Chrome Update 2021/2022/2024/2025; Topps Chrome
Platinum 2025; Topps Cosmic Chrome 2024/2025; Pristine 2024/2025; Finest; Heritage; Allen & Ginter;
Stadium Club; Panini Prizm BB 2020/2021; Panini Prizm/Select/Mosaic/Optic/Donruss/Contenders/
Spectra/Phoenix/Absolute/Certified/Zenith/Illusions/Luminance/Obsidian/Origins/Chronicles/
National Treasures/Immaculate Football 2024/2025; Panini Prizm/Select/Mosaic/Optic/Donruss/Hoops/
Court Kings/Revolution/Origins/Immaculate/National Treasures Basketball 2023/2024; Topps Chrome
Basketball 2024.

---

After you finish, the engineer runs `python scp_sync.py` → commits the CSVs → pushes, and the
new sets go live on the next deploy. The basketball ones (8–14) are the most important — they're
what unlocks real NBA coverage.
