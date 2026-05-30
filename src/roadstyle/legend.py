"""Map legends for data-driven styling.

Two kinds, both rendered as a small floating panel on a folium map:
- **categorical** — a list of colour swatches + labels (e.g. congestion levels);
- **continuous** — a gradient bar with min/max (and optional mid) ticks (e.g. traffic volume),
  built from a :class:`roadstyle.colors.ColorRamp`'s hex stops.

The legend spec comes from a styler's ``ResolvedFrame.legend`` dict, so callers never build it by
hand. Categorical legends are a self-contained ``MacroElement``; the continuous gradient is also a
``MacroElement`` (a CSS linear-gradient bar) to keep one consistent look.
"""
from __future__ import annotations

from branca.element import MacroElement
from jinja2 import Template

_BASE_CSS = """
.rs-legend{position:absolute;z-index:9999;background:rgba(20,24,30,.82);
  backdrop-filter:blur(6px);border-radius:12px;padding:9px 11px;
  box-shadow:0 3px 14px rgba(0,0,0,.45);font:600 11px/1.4 system-ui,sans-serif;color:#cfd6dd;}
.rs-legend h4{margin:0 0 6px;font-size:10px;letter-spacing:.4px;color:#9fb0bf;
  text-transform:uppercase;}
.rs-legend .rs-row{display:flex;align-items:center;gap:7px;padding:1px 0;white-space:nowrap;}
.rs-legend .rs-sw{width:16px;height:6px;border-radius:2px;display:inline-block;flex:none;}
.rs-legend .rs-bar{height:10px;border-radius:3px;margin:2px 0 3px;}
.rs-legend .rs-ends{display:flex;justify-content:space-between;font-weight:500;color:#aeb8c2;}
"""

_CAT = Template("""
{% macro header(this, kwargs) %}<style>{{ this.css }}</style>{% endmacro %}
{% macro html(this, kwargs) %}
<div class="rs-legend" style="{{ this.pos }}">
  {% if this.title %}<h4>{{ this.title }}</h4>{% endif %}
  {% for label, color in this.entries %}
  <div class="rs-row"><span class="rs-sw" style="background:{{ color }}"></span>{{ label }}</div>
  {% endfor %}
</div>
{% endmacro %}
""")

_CONT = Template("""
{% macro header(this, kwargs) %}<style>{{ this.css }}</style>{% endmacro %}
{% macro html(this, kwargs) %}
<div class="rs-legend" style="{{ this.pos }}min-width:150px;">
  {% if this.title %}<h4>{{ this.title }}</h4>{% endif %}
  <div class="rs-bar" style="background:linear-gradient(90deg,{{ this.stops }});"></div>
  <div class="rs-ends"><span>{{ this.vmin }}</span><span>{{ this.vmax }}</span></div>
</div>
{% endmacro %}
""")

_POS = {
    "bottomleft": "left:14px;bottom:22px;",
    "bottomright": "right:14px;bottom:22px;",
    "topleft": "left:14px;top:14px;",
    "topright": "right:14px;top:14px;",
}


def _fmt(v) -> str:
    """Short number formatting for legend ticks (e.g. 25000 -> '25,000', 3.5 -> '3.5')."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return f"{int(f):,}"
    return f"{f:,.2f}".rstrip("0").rstrip(".")


class CategoricalLegend(MacroElement):
    def __init__(self, entries, title="", position="bottomleft"):
        super().__init__()
        self._name = "RoadStyleLegend"
        self.entries = list(entries)
        self.title = title or ""
        self.css = _BASE_CSS
        self.pos = _POS.get(position, _POS["bottomleft"])
        self._template = _CAT


class ContinuousLegend(MacroElement):
    def __init__(self, stops, vmin, vmax, title="", position="bottomleft"):
        super().__init__()
        self._name = "RoadStyleLegend"
        self.stops = ",".join(stops)
        self.vmin = _fmt(vmin)
        self.vmax = _fmt(vmax)
        self.title = title or ""
        self.css = _BASE_CSS
        self.pos = _POS.get(position, _POS["bottomleft"])
        self._template = _CONT


def make_legend(spec: dict, position: str = "bottomleft"):
    """Build a folium legend MacroElement from a ``ResolvedFrame.legend`` spec, or None."""
    if not spec:
        return None
    kind = spec.get("kind")
    title = spec.get("title", "")
    if kind == "categorical":
        entries = spec.get("entries") or []
        return CategoricalLegend(entries, title=title, position=position) if entries else None
    if kind == "continuous":
        stops = spec.get("ramp") or []
        if not stops:
            return None
        return ContinuousLegend(stops, spec.get("vmin"), spec.get("vmax"),
                                title=title, position=position)
    return None
