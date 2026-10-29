# Move a dashboard to the new version

<p class="lead">Use this page when a script calls `render_dashboard` or `render_report` from an older version. Each old keyword has one new place.</p>

## What changed

| Before | Now |
|---|---|
| `render_report(...)`, `--page report` | Removed. Use `render_dashboard(...)` |
| `template="classic"` | `render_dashboard(..., layout="dock")` |
| `layout="overlay"` | The default. You can leave it out |
| `toolbar="right"` | `dashboard={"toolbar": {"position": "right"}}` |
| `edit=function` | Removed. Use `dashboard={"panel": {"sections": [...]}}` ([Add to the panel](dashboard-panel.md)) |
| panel width (a string replace in the HTML) | `dashboard={"panel": {"width_px": 400}}` |
| `window.rsG3dSelectionStyle = {...}` | `dashboard={"google_3d": {"selection_style": {...}}}` |
| `window.rsG3dMeshAltitude = 1.5` | `dashboard={"google_3d": {"mesh_altitude_m": 1.5}}` |
| `window.rsToolbarHold = true` | `dashboard={"toolbar": {"hold": True}}`, then `rs.tools.ready()` |
| `google_3d_layers=[...]` | The same keyword. A wrong key is now an error |

An old keyword that no longer exists stops with an error that says where it went.

## One call

```python
m = rs.render_dashboard(
    edges, name="My review", basemap="ofm_liberty", google_3d=True,
    dashboard={
        "windows": {"restore_open": False},                       # the windows start closed
        "google_3d": {"fov_deg": 25.4, "selection_style": {"width": 10}},
        "toolbar": {"hold": True},                                # the bar waits for your tools
        "panel": {"width_px": 400},
    },
)
```

`dashboard=` is a partial option. It is merged over the template's defaults. A wrong key or value is an error.
All fields are in the [design](../design/dashboard_templates.md) (section 3.1).

## Your own tools

```javascript
rs.tools.add({id: "export", title: "Export", icon: "&#8681;", onClick: () => save()});
rs.tools.ready();          // with toolbar.hold: show the bar now
```

## Your own panel content

There is no edit hook, and you do not need one. Add blocks to the panel, hide the panel's own, and add rows to the legend: see
[Add to the panel](dashboard-panel.md). Your HTML follows the light and the dark theme when it uses the panel's variables.

If you must change the template's text, build the page and change `m.html`. The panel is `<div id="sb">`. These ids stay stable, and the
page script uses them: `sb-hide`, `sb-show`, `sb-th`, `bm`, `co`, `sb-legend`, `q`, `tbl`, `count`, `detail`. Keep them, or hide them.
