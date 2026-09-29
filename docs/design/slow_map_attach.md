# Roads never appear when the map starts slowly

Status: **implemented** 2026-09-29 (unreleased). The cause below was corrected while implementing.

## Problem

With the default inline data (`compress=True`, not `tiles=True`), the road data is decompressed by a
separate script (`_INFLATE_JS` in `render_web.py`), which then waits for the map to exist and hands
the data over. It checks every 100 ms and **gives up after 600 checks (60 s)**. If the map's
sources appear later than that, the page has a working map with no roads, forever. When the map does load, the amber self-check
banner reports `{"ok":false,"stage":"attach","error":"map never appeared"}`.

## Data

- Seen 2026-09-29 in a VS Code notebook: the amber banner with exactly that `attach` error, while the
  same saved output reopened later worked.
- **Not** a slow MapLibre download, as first assumed: in both the saved page and the notebook version
  the loader script comes after `window.map = map`, and the MapLibre `<script>` blocks parsing, so
  the loader never runs before the map object exists.
- **The cause:** MapLibre builds the style (and so the `roads` source) on the next animation frame,
  and browsers pause animation frames for anything not visible: background tabs, and notebook outputs
  that are off screen. Checked in Chromium with animation frames withheld: `window.map` is a real Map,
  `map.getSource("roads")` stays undefined. A map rendered off screen and looked at more than 60 s
  later got no roads.
- The tiled path (`tiles=True`) has no such limit, and nothing else in the page polls with a cap.
- The self-check banner fires 2.5 s after the map's `load` event. If the roads attach after that,
  the banner stays on screen, showing a failure that has since recovered.

## Approach

The smallest change that removes the failure:

1. **Never stop waiting.** Check every 100 ms for the first 60 s, as today, then every second for as
   long as the page is open. The waiting costs nothing measurable.
2. **Say that it is still waiting.** After 60 s set `window.__rs_gz = {ok:false, stage:"attach",
   waiting:true, ...}`, so the banner reads "still waiting for the map" instead of a final
   "never appeared".
3. **Clear the banner on success.** Give the banner an id, and remove it when the data attaches.

## Rejected

- **An event from the map script ("map ready") instead of polling.** Cleaner, but the data needs
  the map's sources to exist, which happens on a later animation frame, not at `new maplibregl.Map`. So the handoff
  would still need a check on the other side, in the template and in every page variant that
  includes `_INFLATE_JS`. It's more code for no visible difference.
- **A longer cap (e.g. 5 minutes).** Still fails on a slower start, just later.

## Impact

- `render_web.py` `_INFLATE_JS`: about 5 lines. The template's banner: an id and one removal line.
- Test: Playwright with a fake clock (`page.clock`) and animation frames withheld: run 61 s of
  timers, release the frames, and check the roads attach and no banner is left.
- No API change.
