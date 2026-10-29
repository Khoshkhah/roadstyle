# Live data: a new day

<p class="lead">Build the page once. For each new day, give the roads their numbers and colours from the browser. There is no new style and no reload.</p>

## The idea

1. Build the page with `live_data=True`.
2. In the page, call `rs.setData(rows, options)` with the numbers of a day.
3. A call for the next day **replaces** the values of the day before. The legend (in the toolbox box *Colour by and legend*) and the colours follow.

```javascript
await rs.setData([{edge_id: 17, flow: 840}, {edge_id: 18, flow: 120}],
                 {colorBy: "flow", widthBy: "flow", legend: {title: "Flow, 2026-10-29"}});
rs.clearData();                      // take the data away
```

`rows` is an array of objects, an Arrow table, or **the URL of a JSON file** with such an array (`rs.setData("flow-2026-10-29.json", ...)`).
Each row has an `edge_id` and the columns that you name in the options. **Write `edge_id` as text** (`"edge_id": "7203945719283746"`).
The ids of duckOSM are 64-bit numbers, and a JSON number above 2^53 is not exact in a browser: the road is not found, and `matched` is small. The call gives a Promise with `{rows, matched, ms}`, and the event
`rs:datachange` fires.

| Option | Meaning |
|---|---|
| `colorBy` | the column that gives the colour: a number goes on the ramp from `vmin` to `vmax` (the range of the data when you leave them out), a text gets one colour for each value |
| `widthBy`, `widthRange` | the column that gives the width, as a factor of the drawn width, from `widthRange[0]` at the smallest value to `widthRange[1]` at the largest (default `[1, 3]`) |
| `ramp`, `stepped` | your own list of colours; `stepped: true` takes the nearest colour, with hard edges |
| `nodata` | the colour of a road with no row (default: the page's no-data colour) |
| `key` | the column that names the road (default `edge_id`; `"row"` for the number of the road's row) |
| `legend` | `false`: no legend; `{title: "..."}`: change the legend |

## A day picker

The picker is a section of the panel (it follows both themes). Its code is the page's own script: `page_script=` adds it, with no edit of the HTML.

```python
days = ["2026-10-27", "2026-10-28", "2026-10-29"]
picker = "<select id='day'>" + "".join(f"<option>{d}</option>" for d in days) + "</select>"

m = rs.render_dashboard(
    edges, live_data=True, name="Flow by day",
    dashboard={"panel": {"sections": [{"id": "day", "label": "Day", "html": picker, "before": "query"}]}},
    page_script="""
      function start() {
        const pick = document.getElementById("day");
        const show = day => rs.setData(`flow-${day}.json`, {colorBy: "flow", widthBy: "flow", legend: {title: "Flow, " + day}});
        pick.onchange = () => show(pick.value);
        show(pick.value);
      }
      window.rsReady ? start() : document.addEventListener("rs:ready", start, {once: true});
    """,
)
m.save("flow.html")
```

Serve the page and the JSON files from one folder (`python -m http.server`): a page opened from disk cannot load files.
To add a new day, write its `flow-<day>.json` and add the day to `days`. The page does not change.

## Good to know

- The call gives `{rows, matched}`. When `matched` is much smaller than `rows`, the ids do not match: check that `edge_id` is text.
- A click on a road shows the joined values in the popup and in the panel.
- The event `rs:ready` fires when `window.rs` is there and the panel's sections (your picker) are in place. `window.rsReady` is true from then on.
  A `page_script` waits for the event, as in the example.
