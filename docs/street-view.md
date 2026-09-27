# Google Street View

Click a road and see it in Google Street View, looking the way the road runs. There are two
versions:

1. **[The floating window](#1-the-floating-window-every-map)**: every map has a Street View button;
   it opens a small window over the map. The default, nothing to switch on.
2. **[Side by side](#2-side-by-side)**: a page with the map and Street View next to each other,
   Street View **beside** the map or **below** it, with a divider you can drag.

No API key in either. Both show a **marker** on the map (a dot and a cone) where Street View stands
and which way it looks, and **◀ ▶** buttons that walk 15 m back or forward along the road.

!!! note "Serve the page to see Street View"
    Google's Street View only loads in a page served over http(s). Opened from disk (`file://`,
    a double-click) it stays grey, so the page says so and offers a link instead. Serve the
    folder: `python -m http.server`, then open `http://localhost:8000/map.html`.

## 1. The floating window (every map)

Press the **Street View** button (the person, under 3D) and click a road. The window follows each
new click; drag its title bar to move it and its corner to resize it; ◀ ▶ step along the road.
The road popup's *Street View* link opens it too. Nothing is loaded from Google while it is closed,
and the page remembers whether it was open, where and how big.

<iframe src="../maps/street_view_window.html" loading="lazy" title="A map with the Street View window open"
        style="width:100%;height:520px;border:0;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.18)"></iframe>

```python
rs.render_edges(edges)                      # street_view="window": the button and window (default)
rs.render_edges(edges, street_view=True)    # a plain Street View link in the popup instead (new tab)
rs.render_edges(edges, street_view=False)   # no Street View
```

It opens at the map's bottom-right corner, clear of any panel the host page adds; on a phone it is
a sheet at the bottom. From your own UI: `rsSetStreetView(true)` opens it, `rsStreetViewStep(15)`
steps (see the [JavaScript API](web-backend.md#the-javascript-api-windowrs)).

## 2. Side by side

A page of its own: the map and Street View share the screen, with a divider between them that you
can drag. Click a road and Street View shows it.

### Beside the map

<iframe src="../maps/street_view.html" loading="lazy" title="The map with Google Street View beside it"
        style="width:100%;height:520px;border:0;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.18)"></iframe>

```python
rs.render_street_view(edges).save("street_view.html")
```

```bash
roadstyle edges.gpkg --page street-view -o street_view.html
```

### Below the map

<iframe src="../maps/street_view_below.html" loading="lazy" title="The map with Google Street View below it"
        style="width:100%;height:640px;border:0;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.18)"></iframe>

```python
rs.render_street_view(edges, layout="below").save("street_view.html")
```

```bash
roadstyle edges.gpkg --page street-view --layout below
```

### Options

- `layout`: `"beside"` (default) or `"below"`.
- `panel_width`: Street View's share of the width (below: of the height), in percent, 20-80,
  default 42.
- `resizable`: `True` (default) gives the draggable divider; the viewer's choice is remembered in
  their browser. `False` fixes the size: `rs.render_street_view(edges, panel_width=60, resizable=False)`,
  CLI `--panel-width 60 --no-resize`.
- Every `render_edges` keyword passes through. On a phone, Street View sits under the map.

## Where Street View looks

The point is the spot on the clicked road's own line (its centre line) nearest the click, and the
heading is the road's direction there. A two-way road's two directions share one line, so each
steps 2.5 m to its right, into the middle of its own lane (right-hand traffic, the side the map
draws it on): its two directions stand 5 m apart, looking opposite ways. The marker sits in the
lane as the map draws it at the current zoom, so it stays on the road. `rsSelect(id)` stands at the
middle of the road instead of a click.

Google shows the panorama nearest that point. Where it has no car imagery, that can be a photo
someone uploaded, such as a shop interior; tunnels work where Google drove through them, but with no
height in the request, a street right above a tunnel can win.

## Street View in your own page

The Street View URL rides on the selection event (`null` with `street_view=False`):

```js
document.addEventListener("rs:select", e => {
  const url = e.detail.streetView;          // "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=59.31,18.07&heading=172"
  if (url) myPanel.innerHTML += `<a href="${url}" target="_blank">Street View</a>`;
});
```

Google won't show that page inside an iframe; to embed Street View, turn its point and heading into
Google's embeddable URL, as the side-by-side panel (`rs.sidebar_html("street_view")`) does:

```js
document.addEventListener("rs:select", e => {
  if (e.detail.overlay || !e.detail.streetView) return;   // roads only (overlays set .overlay)
  const u = new URL(e.detail.streetView);
  const [lat, lng] = u.searchParams.get("viewpoint").split(",");
  const h = u.searchParams.get("heading") || 0;
  frame.src = `https://www.google.com/maps/embed?pb=!6m7!1m6!2m2!1d${lat}!2d${lng}!3f${h}!4f0!5f1`;
});
```

That is the URL form Google's own *Share → Embed a map* produces. It needs no key, but building it
by hand is not a documented Google API, so it could stop working. The official embed needs a
Google **Maps Embed API** key:
`https://www.google.com/maps/embed/v1/streetview?key=KEY&location=${lat},${lng}&heading=${h}`.
Street View imagery is Google's, under Google's terms.
