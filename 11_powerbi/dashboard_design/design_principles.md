# Dashboard Design — "Charcoal & Coral"

## Palette

| Role | Colour | Use |
|---|---|---|
| Header band | `#25242A` warm charcoal + 4 px amber-gold line `#C2851A` | page title + one-line definition; data-date pill `#36343C` |
| Canvas / card | `#F2F4F8` / `#FFFFFF` | cool-grey page, white cards, 1 px border `#E2E6EF`, radius 12 |
| Ink | `#1B2233` · `#4A5367` · `#8A92A6` | values · axis/labels · captions |
| **Segment: At Risk** | `#D9653B` terracotta coral | valuable but slipping away |
| **Segment: Hibernating** | `#C266C0` orchid | dormant |
| **Segment: New Customers** | `#139C85` teal | fresh |
| **Segment: Loyal Customers** | `#3558D4` royal indigo | proven repeaters |
| Single series | `#3A5BA0` denim | any non-segment chart (months, categories, hours…) |
| Second series | `#C2851A` amber-gold | returning customers, reactivation |
| Sequential (cohort heatmap) | `#EEF1FA → #C7D2F0 → #8DA2E0 → #4D6BC6 → #26408F` | one hue, light → dark |
| Status | `#C8423B` | only for churn (never a segment) |

Every data colour was checked for lightness band, chroma, contrast against the background and colour-vision-
deficiency separation (OKLab ΔE, protanopia/deuteranopia simulation, light mode):
- segments, all pairs (scatter-safe): lightness, chroma and ≥ 3:1 contrast PASS; normal-vision worst pair ΔE 18.7;
  colour-blind worst pair ΔE 7.9 (floor band) → segments are always direct-labelled (axis labels, bubble labels);
- denim + amber, adjacent: all checks PASS (ΔE 30.9 normal, 27.0 CVD).

Colour follows the segment **name** (`custseg.viz.SEGMENT_PALETTE` → `mart.segment_profile.color` →
`[Segment Color]` / `[Profile Color]` measures), so Python figures and Power BI always agree and a filter never
repaints a segment.

## Layout

- Canvas 1280 × 800. Header 64 px (charcoal, no blue) + 4 px amber-gold line.
- Row 1 **filter bar**: one rounded white card, amber "FILTER" caption, borderless dropdown slicers with their own
  small header, evenly spaced · Row 2 KPI cards (amber accent bar each) ·
  Rows 3–4 charts in white rounded cards.
- Filter pane collapsed by default; trends use a continuous monthly date axis (no scrollbars).
- Bars: value axis hidden, data labels on; lines 2 px; no dual axes; short titles that name measure and unit.
- Ordered categories (CLV bands, inactivity bands, CLV tiers) are sorted by hidden order columns, not by value.

## Currency & number format (Bahasa Indonesia)

- The analysis is in BRL (source currency). The dashboard shows **Rupiah** at one fixed rate
  (Rp 4.026/BRL = ValutaFX annual averages 2017 & 2018 weighted by each year's revenue; `custseg.fx`), applied in the
  `pbi` views, so every ratio, share and growth rate is unchanged.
- Model culture `id-ID`. KPI cards use text measures `"<measure> (label)"` built with `FORMAT`, so they always read
  the Indonesian way: `93.104`, `Rp 643.296`, `Rp 61,9 miliar`, `3,00%`, `80 hari`.
- Money charts are scaled and say the unit in the title (`Rp miliar`, `Rp ribu`); no English K/M/bn suffixes.
- Numbers inside charts and tables follow the **viewer's Power BI regional setting** (Power BI does not let a file
  force it). To see `1.242` instead of `1,242` everywhere: Power BI Desktop → File → Options and settings → Options →
  Global → Regional settings → choose Bahasa Indonesia.
