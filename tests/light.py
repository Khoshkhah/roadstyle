"""The light colour of a style's colour (a live style has a dark colour beside each: `["case", ["==", ["global-state", "rs_theme"], "dark"], dark, light]`,
rust/roadstyle-engine/src/dark.rs). `light(e)` is the expression with each of those cases replaced by its light colour."""


def light(e):
    if isinstance(e, list):
        if len(e) == 4 and e[0] == "case" and e[1] == ["==", ["global-state", "rs_theme"], "dark"]:
            return light(e[3])
        return [light(x) for x in e]
    if isinstance(e, dict):
        return {k: light(v) for k, v in e.items()}
    return e
