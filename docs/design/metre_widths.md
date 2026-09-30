# Line widths in metres

**Status:** implemented 2026-09-30 on branch `metre-width` (approved by Kaveh the same day); not released. Agreed in outline on 2026-10-01 as the one roadstyle change
for lanestyle (see lanestyle's `docs/design/lanestyle_on_roadstyle.md`), to be released as 0.10.0.

## Problem

roadstyle sets widths in pixels per road class, at the zoom stops 12–20, blended linearly. That suits
roads. It doesn't suit lines that have a real width: GMNS lanes lie side by side, 3.25 m apart, so each
must be exactly its width in metres at every zoom, or neighbours overlap or leave gaps. The option is
general: any line data with a real width can use it (a road with a `width` tag, a canal, a runway).
Nothing about lanes goes into roadstyle.

## Proposal

Three new `render_edges` keywords (web backend):

| Keyword | Does | Default |
|---|---|---|
| `width_m_col` | a column with each line's width in metres; from `width_m_zoom` on, the line is drawn at that width | `None` (no change) |
| `width_m_zoom` | the zoom from which metre widths apply; below it, the class widths as today, so a lane doesn't vanish when zoomed out | `16` |
| `casing_m` | the casing's width on each side, in metres | `0.15` |

**The drawn line is exactly the column's width.** The casing is the whole width; the fill is
`width − 2·casing_m`, drawn on top. So nothing spills past the real edge, and two lanes side by side
show a line of `2·casing_m` (0.30 m) between them. (With the casing outside the width, as roads have
it, the neighbour's fill would cover it and no line would show.) The bridge's heavier casing
(the "wings") is `width + 2·casing_m`, so a bridge deck still reads as one.

**How:** MapLibre draws `512 · 2^z / 40,075,017` pixels per metre at the equator, and `1 / cos φ`
times that at latitude φ. In Python each feature gets `__rs_wm = width / cos φ`, with φ its own mean
latitude, so a large area (a county spanning 1.5° of latitude) is exact everywhere, not only at the
map's centre. The three width expressions `cw` / `fw` / `bcw` (`render_web.py`, next to the
`_width_expr` calls) become:

```
["interpolate", ["exponential", 2], ["zoom"],
   12, <class widths as now>, …, 15, <class widths>,
   16, ["case", <has __rs_wm>, ["*", ["get", "__rs_wm"], p0(16)], <class width at 16>],
   …  (every zoom stop from width_m_zoom on, then 22, MapLibre's max zoom)]
```

- **Exponential base 2**, so a metre width is exact between the stops too, not only at them (linear
  would make a lane about 6 % too wide at half zooms). Zoom stays the top-level input, as MapLibre
  requires.
- The class stops below `width_m_zoom` are blended exponentially too. That is a small change,
  and only in maps that pass `width_m_col`.
- **A null width is drawn at the class width**, at every zoom, as today.
- **Stop at 22:** the class widths stop at 20 and stay the same from there; metre lines keep growing
  to 22 so they stay exact.

**Every width roadstyle draws** goes through `cw` / `fw` / `bcw`: fill, casing, bridge wings, tunnel
casing and dashes, tunnel mouths. So one change covers all of them. **What stays the same:**

- the two-way lane offset: a lane has its own offset geometry and no reverse twin, so its offset is
  0 and it gets no end caps;
- arrows, labels and the Street View marker, which reads only `line-offset`;
- the 3D bridge decks: `view_3d` is off by default and the decks keep their class sizes.

## Checks

- Tests:
  - At zoom 22, a feature's fill width is `(w − 2·casing_m) · p0(22) / cos φ`, and its casing
    width is `w · p0(22) / cos φ`.
  - Below `width_m_zoom`, and for a null width, a line has its class width.
  - A map without `width_m_col` has the same style as before: every existing test passes, and
    `cw` / `fw` / `bcw` are unchanged.
- In a browser: two parallel lines 3.25 m apart, each 3.25 m wide, at zoom 16, 19 and 22. They touch,
  with a thin line between them and no gap or overlap. I'll send a screenshot for each zoom.
- Docs: `docs/reference/parameters.md`, `CHANGELOG.md` (0.10.0), `skills/roadstyle/SKILL.md` (one line).

## Open

- The `main` checkout has uncommitted work that isn't part of this change (`twoway_col`, fill-only
  end caps at tunnel mouths, in `twin_ends.md`). This branch is cut from the last commit, so the two
  may meet in `render()`'s keyword list when they merge. That is a small, mechanical conflict.
