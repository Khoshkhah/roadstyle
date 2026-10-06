"""Single-Source WebGL & MapLibre Style Compiler for roadstyle v2 Core Engine.

Translates the 5 universal primitives (Corridor, Channel, Demarcation, Patch, Glyph)
into high-performance 60 FPS WebGL vector maps with zero geometry duplication.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import tempfile
from typing import Any
import webbrowser

import shapely
from shapely.geometry import mapping

from .casing import split_casing_geometry
from .primitives import Channel, Corridor, Demarcation, Glyph, Patch, ViewPreset
from .solver import solve_stacking


# Default Basemap Tile Endpoints (Keyless, verified high-availability)
BASEMAPS: dict[str, dict[str, Any]] = {
    "carto-dark": {
        "type": "raster",
        "tiles": [
            "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        ],
        "tileSize": 256,
        "maxzoom": 20,
        "attribution": "© OpenStreetMap contributors © CARTO",
    },
    "carto-voyager": {
        "type": "raster",
        "tiles": [
            "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
            "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
            "https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        ],
        "tileSize": 256,
        "maxzoom": 20,
        "attribution": "© OpenStreetMap contributors © CARTO",
    },
    "carto-light": {
        "type": "raster",
        "tiles": [
            "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
            "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
            "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        ],
        "tileSize": 256,
        "maxzoom": 20,
        "attribution": "© OpenStreetMap contributors © CARTO",
    },
    "osm": {
        "type": "raster",
        "tiles": [
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        ],
        "tileSize": 256,
        "maxzoom": 19,
        "attribution": "© OpenStreetMap contributors",
    },
    "esri-dark": {
        "type": "raster",
        "tiles": [
            "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        ],
        "tileSize": 256,
        "maxzoom": 16,
        "attribution": "© Esri, HERE, Garmin, © OpenStreetMap",
    },
}


# Web-Mercator ground resolution for MapLibre (512px tiles) at the equator:
# metres per pixel at zoom z = _MPP_Z0 / 2**z
_MPP_Z0 = 2.0 * math.pi * 6378137.0 / 512.0  # 78271.517 m/px at z0

# Latitude used for the cos(lat) correction; set by compile_map() before layers are built.
_SCALE_LAT: float = 0.0


def _px_per_m(z: float, lat: float | None = None) -> float:
    """Exact screen pixels per ground metre at zoom ``z`` and latitude ``lat``."""
    lat = _SCALE_LAT if lat is None else lat
    return (2.0 ** z) / (_MPP_Z0 * max(math.cos(math.radians(lat)), 0.05))


def meter_to_pixel_width_expr(
    width_prop: str = "width_m",
    extra_prop: str | float | None = None,
    min_px: float = 0.75,
    extra_px: float = 0.0,
) -> list[Any]:
    """Build MapLibre exponential interpolation expression converting physical meters to screen pixels.

    Formula evaluated on GPU:
    W_px(z) = W_m * 2^z / (78271.517 * cos(lat)) + extra_px
    Clamped to min_px floor to prevent low-zoom network vanishing.
    """
    safe_w = ["coalesce", ["get", width_prop], 3.5]
    if extra_prop is not None:
        if isinstance(extra_prop, str):
            safe_extra = ["coalesce", ["get", extra_prop], 0.0]
            w_term: Any = ["+", safe_w, ["*", 2.0, safe_extra]]
        else:
            w_term = ["+", safe_w, 2.0 * float(extra_prop)]
    else:
        w_term = safe_w

    expr: list[Any] = ["interpolate", ["exponential", 2], ["zoom"]]
    # Cartographic boost: scales smoothly from visible road corridors at z10-15
    # to exact ground metres (b=1.0) at z18-22, strictly monotonic with zoom.
    boost = {
        10: 19.3,
        12: 7.7,
        14: 3.1,
        15: 2.3,
        16: 1.7,
        17: 1.15,
        18: 1.0,
        19: 1.0,
        20: 1.0,
        22: 1.0,
    }
    for z, b in boost.items():
        core: Any = ["max", min_px, ["*", w_term, round(_px_per_m(z) * b, 5)]]
        expr += [z, ["+", core, round(extra_px, 2)] if extra_px > 0.0 else core]
    return expr


def lateral_offset_expr(left_prop: str = "casing_left_m", right_prop: str = "casing_right_m") -> list[Any]:
    """MapLibre expression computing GPU lateral shift for asymmetric casings (c_left - c_right) / 2."""
    safe_left = ["coalesce", ["get", left_prop], 0.0]
    safe_right = ["coalesce", ["get", right_prop], 0.0]
    diff_term = ["-", safe_left, safe_right]
    expr: list[Any] = ["interpolate", ["exponential", 2], ["zoom"]]
    for z in (10, 14, 17, 20, 22):
        expr += [z, ["*", diff_term, round(_px_per_m(z) / 2.0, 5)]]
    return expr


_VENDOR_DIR = Path(__file__).resolve().parent.parent.parent / "vendor"


def _load_vendor_asset(fname: str) -> str:
    """Load vendored front-end asset (MapLibre JS/CSS) to inline into standalone HTML."""
    p = _VENDOR_DIR / fname
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


class WebMap:
    """An interactive MapLibre WebGL vector map created by the roadstyle v2 compiler."""

    def __init__(
        self,
        style: dict[str, Any],
        center: tuple[float, float],
        zoom: float,
        presets: list[ViewPreset] | None = None,
        background_color: str = "#0b0d14",
    ) -> None:
        self.style = style
        self.center = center
        self.zoom = zoom
        self.presets = presets or []
        self.background_color = background_color

    def to_dict(self) -> dict[str, Any]:
        """Return the complete MapLibre style JSON specification as a Python dict."""
        return self.style

    def to_style_json(self, indent: int = 2) -> str:
        """Return the serialized MapLibre style JSON specification."""
        return json.dumps(self.style, indent=indent)

    def to_html(self, standalone: bool = True) -> str:
        """Render self-contained HTML page embedding the interactive map."""
        style_json = self.to_style_json(indent=None)
        center_lon, center_lat = self.center
        presets_json = json.dumps([asdict(p) for p in self.presets])
        preset_display_style = "display: flex; flex-direction: column; gap: 8px;" if self.presets else "display: none;"
        basemap_tiles_json = json.dumps({
            "dark": "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "voyager": "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
            "esri": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        })
        has_bm = "basemap" in self.style.get("sources", {})
        active_dark = "active" if has_bm else ""
        active_none = "active" if not has_bm else ""
        blank_bg = self.background_color if not has_bm else "#efede8"
        target_bg = self.background_color if self.background_color.startswith("#") and len(self.background_color) == 7 else "#0b0d14"
        bg_r = int(target_bg[1:3], 16)
        bg_g = int(target_bg[3:5], 16)
        bg_b = int(target_bg[5:7], 16)

        if standalone:
            v_css = _load_vendor_asset("maplibre-gl.css")
            v_js = _load_vendor_asset("maplibre-gl.js").replace("</script>", "<\\/script>")
            if v_css and v_js:
                head_assets = f"<style>{v_css}</style>\n  <script>{v_js}</script>"
            else:
                head_assets = '<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">\n  <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>'
        else:
            head_assets = '<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">\n  <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>roadstyle v2 Interactive Map</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  {head_assets}
  <style>
    body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    #map {{ position: absolute; top: 0; right: 0; bottom: 0; left: 0; width: 100%; height: 100%; background: {self.background_color}; }}
    #map-loading {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 20; color: #38bdf8; font-size: 14px; font-weight: 600; background: rgba(18,20,29,0.9); padding: 10px 18px; border-radius: 8px; }}
    .preset-panel {{
      position: absolute;
      top: 16px;
      left: 16px;
      z-index: 10;
      background: rgba(18, 20, 29, 0.88);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 10px;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    }}
    .preset-title {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #38bdf8; }}
    .preset-btn-row {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .preset-btn {{
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #f1f5f9;
      padding: 5px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .preset-btn:hover {{ background: rgba(56, 189, 248, 0.2); border-color: #38bdf8; }}
    .preset-btn.active {{ background: #38bdf8; color: #0f172a; border-color: #38bdf8; }}
    .slider-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 11px;
      color: #94a3b8;
    }}
    .slider-row input[type=range] {{
      flex: 1;
      height: 4px;
      accent-color: #38bdf8;
      cursor: pointer;
    }}
    .slider-val {{
      font-weight: 700;
      color: #38bdf8;
      min-width: 32px;
      text-align: right;
    }}
    .info-tooltip {{
      position: absolute;
      z-index: 1000;
      background: rgba(15, 23, 42, 0.95);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(56, 189, 248, 0.4);
      border-radius: 10px;
      padding: 12px 16px;
      color: #f8fafc;
      font-size: 12px;
      line-height: 1.5;
      display: none;
      pointer-events: none;
      min-width: 260px;
      max-width: 360px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.1);
      transition: opacity 0.08s ease;
    }}
    .tt-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      padding-bottom: 6px;
      margin-bottom: 8px;
    }}
    .tt-title {{ font-weight: 700; font-size: 13px; color: #38bdf8; letter-spacing: 0.02em; }}
    .tt-tags {{ display: flex; gap: 6px; align-items: center; }}
    .tt-tag {{
      font-size: 10px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .tt-tag-bridge {{
      background: rgba(168, 85, 247, 0.25);
      color: #c084fc;
      border: 1px solid rgba(168, 85, 247, 0.4);
    }}
    .tt-tag-tunnel {{
      background: rgba(245, 158, 11, 0.25);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.4);
    }}
    .tt-tag-surface {{
      background: rgba(148, 163, 184, 0.15);
      color: #94a3b8;
    }}
    .tt-name {{ font-size: 13px; font-weight: 600; color: #ffffff; margin-bottom: 8px; }}
    .tt-row {{ display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 12px; }}
    .tt-lbl {{ color: #94a3b8; font-weight: 500; }}
    .tt-val {{ color: #f8fafc; font-weight: 600; }}
    .tt-box {{
      margin-top: 8px;
      padding: 8px 10px;
      background: rgba(0, 0, 0, 0.35);
      border-radius: 6px;
      border-left: 3px solid #f59e0b;
    }}
    .tt-box-title {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #f59e0b; margin-bottom: 4px; }}
    .tt-pills {{ display: flex; gap: 6px; }}
    .tt-pill {{
      flex: 1;
      text-align: center;
      background: rgba(255, 255, 255, 0.06);
      border-radius: 4px;
      padding: 4px 0;
      font-size: 11px;
    }}
    .tt-pill span {{ display: block; font-size: 9px; color: #94a3b8; text-transform: uppercase; }}
    .tt-pill b {{ font-size: 13px; color: #38bdf8; }}
    .badge {{
      font-size: 10px;
      color: #94a3b8;
      margin-top: 2px;
    }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="map-loading">Loading map…</div>
  <div id="map-error" style="display:none; position:absolute; top:20px; left:50%; transform:translateX(-50%); z-index:9999; background:rgba(220,38,38,0.92); color:#fff; padding:10px 18px; border-radius:8px; font-weight:600; font-size:13px; box-shadow:0 4px 16px rgba(0,0,0,0.5);"></div>

  <div class="preset-panel" id="preset-panel">
    <div class="preset-title">Basemap Layer</div>
    <div class="preset-btn-row" id="basemap-btn-row">
      <button class="preset-btn {active_dark}" id="bm-btn-dark" onclick="setBasemap('dark')">Dark Matter</button>
      <button class="preset-btn" id="bm-btn-voyager" onclick="setBasemap('voyager')">Voyager</button>
      <button class="preset-btn" id="bm-btn-esri" onclick="setBasemap('esri')">ESRI Dark</button>
      <button class="preset-btn {active_none}" id="bm-btn-none" onclick="setBasemap('none')">None</button>
    </div>
    <div style="{preset_display_style}">
      <div class="preset-title" style="margin-top: 4px;">Visual Presets</div>
      <div class="preset-btn-row" id="preset-btn-row"></div>
    </div>
    <div class="preset-title" style="margin-top: 8px;">🚇 Two-Color Tunnel Options (Bridge vs Tunnel)</div>
    <div class="preset-btn-row" id="twocolor-btn-row" style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px;">
      <button class="preset-btn active" id="btn-tc-portals" onclick="applyTwoColorPreset('portals')">Option 1: Portals + Tube</button>
      <button class="preset-btn" id="btn-tc-trench" onclick="applyTwoColorPreset('trench')">Option 2: 3D Dual-Stripe</button>
      <button class="preset-btn" id="btn-tc-bicolor" onclick="applyTwoColorPreset('bicolor')">Option 3: Bicolor Dashes</button>
      <button class="preset-btn" id="btn-tc-dark" onclick="applyTwoColorPreset('dark')">Option 4: Single Dark Slate</button>
    </div>
    <div style="font-size: 11px; color: #38bdf8; margin-top: 4px; font-weight: 500; line-height: 1.4; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; padding: 7px;" id="twocolor-desc">
      <b style="color: #f8fafc;">Option 1 Active:</b><br>
      • <span style="color:#f8fafc; font-weight:700;">Color 1 (Portal Heads):</span> Solid light stone collar (#f8fafc) marking mountain entrance/exit.<br>
      • <span style="color:#94a3b8; font-weight:700;">Color 2 (Tube Interior):</span> Recessed dark slate (#334155) dashed line along underground run.
    </div>

    <div style="margin-top: 6px; display: flex; flex-direction: column; gap: 5px; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 6px; border: 1px solid rgba(56, 189, 248, 0.25);">
      <div style="font-size: 11px; font-weight: 700; color: #38bdf8;">Junction Overlap Fix:</div>
      <div style="display: flex; gap: 4px;">
        <button class="preset-btn active" id="btn-mode-premix" style="flex: 1; font-size: 10px; padding: 4px 6px;" onclick="setTunnelBlendMode('premix', this)">✨ Method 1: Pre-Mix (Zero Seams)</button>
        <button class="preset-btn" id="btn-mode-alpha" style="flex: 1; font-size: 10px; padding: 4px 6px;" onclick="setTunnelBlendMode('alpha', this)">GPU Alpha (Shows Blotches)</button>
      </div>
      <div id="tunnel-mode-note" style="font-size: 10.5px; color: #38bdf8; line-height: 1.3;">
        ✨ <b>Method 1 Active:</b> 100% Solid Opacity with Pre-Mixed Color (Zero overlap blotches at joints!)
      </div>
      <div class="slider-row" style="margin-top: 4px;">
        <span>Fill Opacity:</span>
        <input type="range" id="tunnel-fill-opacity" min="20" max="100" value="65" oninput="onTunnelSliderChange()">
        <span class="slider-val" id="fill-val">65%</span>
      </div>
    </div>
    <div class="preset-btn-row" style="margin-top: 6px; display: flex; flex-direction: column; gap: 4px;">
      <button class="preset-btn" style="font-size: 10.5px; padding: 5px 8px; text-align: left;" onclick="map.flyTo({{ center: [7.423, 43.737], zoom: 17.5, duration: 1000 }})">📍 Larvotto (Bridge + Tunnel side-by-side)</button>
      <button class="preset-btn" style="font-size: 10.5px; padding: 5px 8px; text-align: left;" onclick="map.flyTo({{ center: [7.416, 43.732], zoom: 17.0, duration: 1000 }})">📍 Canton Roundabout (Underground Junction)</button>
      <button class="preset-btn" style="font-size: 10.5px; padding: 5px 8px; text-align: left;" onclick="map.flyTo({{ center: [7.425, 43.730], zoom: 16.8, duration: 1000 }})">📍 Monaco-Ville Tunnel</button>
    </div>
    <div class="badge">roadstyle v2 • 60 FPS Single-Source WebGL</div>
  </div>

  <div class="info-tooltip" id="tooltip"></div>

  <script>
    window.onerror = function(msg, url, line) {{
      console.error(msg, url, line);
      const b = document.getElementById('map-error');
      if (b) {{ b.style.display = 'block'; b.textContent = 'Script Error: ' + msg + ' (L' + line + ')'; }}
    }};

    const styleSpec = {style_json};
    const presets = {presets_json};

    function _dataBounds(spec) {{
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      function walk(c) {{
        if (!Array.isArray(c)) return;
        if (typeof c[0] === 'number' && typeof c[1] === 'number') {{
          if (c[0] < minX) minX = c[0]; if (c[0] > maxX) maxX = c[0];
          if (c[1] < minY) minY = c[1]; if (c[1] > maxY) maxY = c[1];
          return;
        }}
        c.forEach(walk);
      }}
      Object.values(spec.sources || {{}}).forEach(s => {{
        if (s.type === 'geojson' && s.data && s.data.features) {{
          s.data.features.forEach(f => f.geometry && walk(f.geometry.coordinates));
        }}
      }});
      return isFinite(minX) ? [[minX, minY], [maxX, maxY]] : null;
    }}

    if (styleSpec.sources && styleSpec.sources.network && styleSpec.sources.network.data) {{
      const netData = styleSpec.sources.network.data;
      if (Array.isArray(netData.features)) {{
        netData.features = netData.features.filter(f =>
          f && f.geometry &&
          f.geometry.type !== 'GeometryCollection' &&
          ['Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'].includes(f.geometry.type) &&
          Array.isArray(f.geometry.coordinates) && f.geometry.coordinates.length > 0
        );
      }}
    }}

    const map = new maplibregl.Map({{
      container: 'map',
      style: styleSpec,
      center: [{center_lon}, {center_lat}],
      zoom: {self.zoom},
      maxZoom: 24,
      pitch: 0,
      maxPitch: 85
    }});

    map.on('load', () => {{
      const l = document.getElementById('map-loading');
      if (l) l.remove();
      map.resize();
      const b = _dataBounds(styleSpec);
      if (b) map.fitBounds(b, {{ padding: 30, duration: 0 }});
    }});
    window.addEventListener('resize', () => map.resize());

    map.on('error', function(e) {{
      if (e && e.error) {{
        console.error('MapLibre error details:', e.error);
      }}
    }});

    map.addControl(new maplibregl.NavigationControl({{ showCompass: true }}), 'top-right');
    map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-right');

    const BASEMAP_TILES = {basemap_tiles_json};

    function setBasemap(type) {{
      document.querySelectorAll('#basemap-btn-row .preset-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.getElementById('bm-btn-' + type);
      if (activeBtn) activeBtn.classList.add('active');
      if (map.getLayer('basemap-tiles')) map.removeLayer('basemap-tiles');
      if (map.getSource('basemap')) map.removeSource('basemap');
      if (type === 'none') {{
        if (map.getLayer('background-solid')) {{
          map.setPaintProperty('background-solid', 'background-color', '{blank_bg}');
        }}
        document.getElementById('map').style.background = '{blank_bg}';
        return;
      }}
      const tiledBg = type === 'voyager' ? '#f8fafc' : '#0b0d14';
      if (map.getLayer('background-solid')) {{
        map.setPaintProperty('background-solid', 'background-color', tiledBg);
      }}
      document.getElementById('map').style.background = tiledBg;
      const url = BASEMAP_TILES[type];
      if (!url) return;
      map.addSource('basemap', {{ type: 'raster', tiles: [url], tileSize: 256, maxzoom: type === 'esri' ? 16 : 20,
                                  attribution: '© OpenStreetMap contributors' }});
      const layers = map.getStyle().layers;
      const before = layers.length > 1 ? layers[1].id : undefined;
      map.addLayer({{ id: 'basemap-tiles', type: 'raster', source: 'basemap',
                      paint: type === 'dark' ? {{ 'raster-brightness-min': 0.12, 'raster-contrast': 0.2 }} : {{}} }}, before);
    }}

    // Lane direction arrow icon, drawn on demand (no sprite sheet needed)
    map.on('styleimagemissing', (e) => {{
      if (e.id !== 'rs-arrow' || map.hasImage('rs-arrow')) return;
      const s = 48, c = document.createElement('canvas');
      c.width = s; c.height = s;
      const g = c.getContext('2d');
      g.fillStyle = '#ffffff';
      g.strokeStyle = 'rgba(0,0,0,0.55)';
      g.lineWidth = 2;
      g.beginPath();
      g.moveTo(4, 19); g.lineTo(26, 19); g.lineTo(26, 9); g.lineTo(44, 24);
      g.lineTo(26, 39); g.lineTo(26, 29); g.lineTo(4, 29); g.closePath();
      g.fill(); g.stroke();
      map.addImage('rs-arrow', g.getImageData(0, 0, s, s), {{ pixelRatio: 2 }});
    }});

    // Preset switcher (0ms GPU shader update)
    if (presets.length > 0) {{
      const row = document.getElementById('preset-btn-row');
      presets.forEach((p, idx) => {{
        const btn = document.createElement('button');
        btn.className = 'preset-btn' + (idx === 0 ? ' active' : '');
        btn.textContent = p.name;
        btn.onclick = () => {{
          document.querySelectorAll('#preset-btn-row .preset-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          applyPreset(p);
        }};
        row.appendChild(btn);
      }});
    }}

    function applyPreset(p) {{
      if (p.center && p.zoom) {{
        map.flyTo({{ center: p.center, zoom: p.zoom, duration: 1200 }});
      }}
      if (p.color_by) {{
        map.setPaintProperty('corridors-fill', 'line-color', ['get', p.color_by]);
      }}
      if (p.width_mode === 'flow' && p.width_by) {{
        map.setPaintProperty('corridors-fill', 'line-width', ['*', ['get', p.width_by], 0.005]);
      }}
    }}

    let currentCasingColor = '#94a3b8';
    let currentDashArray = [3.0, 3.0];
    let tunnelBlendMode = 'premix'; // 'premix' (Method 1) or 'alpha'
    const bgR = {bg_r}, bgG = {bg_g}, bgB = {bg_b};

    function setTunnelDash(dashArr, btn) {{
      currentDashArray = dashArr;
      document.querySelectorAll('[id^="btn-dash-"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      updateTunnelStyles();
    }}

    function setTunnelBlendMode(mode, btn) {{
      tunnelBlendMode = mode;
      document.querySelectorAll('[id^="btn-mode-"]').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      const note = document.getElementById('tunnel-mode-note');
      if (note) {{
        if (mode === 'premix') {{
          note.innerHTML = '✨ <b>Method 1 Active:</b> 100% Solid Opacity with Pre-Mixed Color (Zero overlap blotches at joints!)';
          note.style.color = '#38bdf8';
        }} else {{
          note.innerHTML = '⚠️ <b>Alpha Mode:</b> Translucent GPU alpha (Notice darker blotches at road connections)';
          note.style.color = '#f59e0b';
        }}
      }}
      updateTunnelStyles();
    }}

    function setTunnelCasingColor(color, btn) {{
      currentCasingColor = color;
      if (btn) {{
        document.querySelectorAll('[id^="btn-case-"]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      }}
      updateTunnelStyles();
    }}

    function onTunnelSliderChange() {{
      const fillVal = document.getElementById('tunnel-fill-opacity').value;
      const casingVal = document.getElementById('tunnel-casing-opacity').value;
      document.getElementById('fill-val').textContent = fillVal + '%';
      document.getElementById('casing-val').textContent = casingVal + '%';
      const cName = currentCasingColor === '#ffffff' ? 'White' : (currentCasingColor === '#94a3b8' ? 'Cool Slate' : 'Dark Slate');
      const lbl = document.getElementById('tunnel-status-label');
      if (lbl) lbl.textContent = 'Custom: Fill ' + fillVal + '%, Casing ' + casingVal + '% (' + cName + ')';
      document.querySelectorAll('#tunnel-btn-row .preset-btn').forEach(b => b.classList.remove('active'));
      updateTunnelStyles();
    }}

    function updateTunnelStyles() {{
      const fillOpacity = parseFloat(document.getElementById('tunnel-fill-opacity').value) / 100.0;
      const casingOpacity = parseFloat(document.getElementById('tunnel-casing-opacity').value) / 100.0;
      const style = map.getStyle();
      if (!style || !style.layers) return;

      // Method 1: Pre-mix color expression against dark background (at 100% solid opacity)
      const mixedColorExpr = [
        'rgb',
        ['+', ['*', ['at', 0, ['to-rgba', ['to-color', ['coalesce', ['get', 'fill_color'], '#38bdf8']]]], fillOpacity], Math.round((1.0 - fillOpacity) * bgR)],
        ['+', ['*', ['at', 1, ['to-rgba', ['to-color', ['coalesce', ['get', 'fill_color'], '#38bdf8']]]], fillOpacity], Math.round((1.0 - fillOpacity) * bgG)],
        ['+', ['*', ['at', 2, ['to-rgba', ['to-color', ['coalesce', ['get', 'fill_color'], '#38bdf8']]]], fillOpacity], Math.round((1.0 - fillOpacity) * bgB)]
      ];

      // Mixed casing color
      const hex = currentCasingColor.replace('#', '');
      const cR = parseInt(hex.substring(0, 2), 16);
      const cG = parseInt(hex.substring(2, 4), 16);
      const cB = parseInt(hex.substring(4, 6), 16);
      const mixedCaseHex = '#' + [
        Math.round(cR * casingOpacity + bgR * (1.0 - casingOpacity)),
        Math.round(cG * casingOpacity + bgG * (1.0 - casingOpacity)),
        Math.round(cB * casingOpacity + bgB * (1.0 - casingOpacity))
      ].map(x => Math.min(255, Math.max(0, x)).toString(16).padStart(2, '0')).join('');

      style.layers.forEach(l => {{
        const lid = l.id;
        if (lid.startsWith('tunnel-fill-')) {{
          if (tunnelBlendMode === 'premix') {{
            map.setPaintProperty(lid, 'line-color', mixedColorExpr);
            map.setPaintProperty(lid, 'line-opacity', 1.0);
          }} else {{
            map.setPaintProperty(lid, 'line-color', ['coalesce', ['get', 'fill_color'], '#38bdf8']);
            map.setPaintProperty(lid, 'line-opacity', fillOpacity);
          }}
        }}
        if (lid.startsWith('tunnel-casing-')) {{
          if (tunnelBlendMode === 'premix') {{
            map.setPaintProperty(lid, 'line-color', mixedCaseHex);
            map.setPaintProperty(lid, 'line-opacity', 1.0);
          }} else {{
            map.setPaintProperty(lid, 'line-color', currentCasingColor);
            map.setPaintProperty(lid, 'line-opacity', casingOpacity);
          }}
          map.setPaintProperty(lid, 'line-dasharray', currentDashArray);
        }}
      }});
    }}

    function applyTunnelPreset(name) {{
      document.querySelectorAll('#tunnel-btn-row .preset-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.getElementById('btn-tun-' + name);
      if (activeBtn) activeBtn.classList.add('active');

      const fillInput = document.getElementById('tunnel-fill-opacity');
      const casingInput = document.getElementById('tunnel-casing-opacity');
      const lbl = document.getElementById('tunnel-status-label');

      if (name === 'subtle') {{
        fillInput.value = 75;
        casingInput.value = 50;
        currentCasingColor = '#ffffff';
        document.querySelectorAll('[id^="btn-case-"]').forEach(b => b.classList.remove('active'));
        const btn = document.getElementById('btn-case-white');
        if (btn) btn.classList.add('active');
        if (lbl) lbl.textContent = 'Preset 1: Subtle Fade (Fill 75%, Soft White Casing 50%)';
      }} else if (name === 'balanced') {{
        fillInput.value = 65;
        casingInput.value = 60;
        currentCasingColor = '#94a3b8';
        document.querySelectorAll('[id^="btn-case-"]').forEach(b => b.classList.remove('active'));
        const btn = document.getElementById('btn-case-slate');
        if (btn) btn.classList.add('active');
        if (lbl) lbl.textContent = 'Preset 2: Balanced (Fill 65%, Slate Casing 60%)';
      }} else if (name === 'dark') {{
        fillInput.value = 60;
        casingInput.value = 75;
        currentCasingColor = '#334155';
        document.querySelectorAll('[id^="btn-case-"]').forEach(b => b.classList.remove('active'));
        const btn = document.getElementById('btn-case-dark');
        if (btn) btn.classList.add('active');
        if (lbl) lbl.textContent = 'Preset 3: Dark Inset (Fill 60%, Dark Slate Casing 75%)';
      }} else if (name === 'orig') {{
        fillInput.value = 95;
        casingInput.value = 100;
        currentCasingColor = '#ffffff';
        document.querySelectorAll('[id^="btn-case-"]').forEach(b => b.classList.remove('active'));
        const btn = document.getElementById('btn-case-white');
        if (btn) btn.classList.add('active');
        if (lbl) lbl.textContent = 'Baseline: Original 100% White Dash (Competes with bridge)';
      }}

      document.getElementById('fill-val').textContent = fillInput.value + '%';
      document.getElementById('casing-val').textContent = casingInput.value + '%';
      updateTunnelStyles();
    }}

    // Hover Tooltip & Dynamic Road Highlight
    // Hover Tooltip & Dynamic Road Highlight with Minimum Stop / Dwell Time
    const tooltip = document.getElementById('tooltip');
    let hoveredEdgeId = null;
    let pendingEvent = null;
    let rafId = null;
    let dwellTimer = null;
    const MIN_STOP_MS = 120; // Minimum stop time in ms before edge selecting & tooltip activation

    let roadFillLayers = [];
    function updateFillLayerCache() {{
      if (!map.getStyle() || !map.getStyle().layers) return;
      roadFillLayers = map.getStyle().layers
        .map(l => l.id)
        .filter(id => id.startsWith('corridors-fill-') || id.startsWith('channel-lv'));
    }}
    map.on('load', updateFillLayerCache);

    function findRoadAtPoint(point) {{
      if (roadFillLayers.length === 0) updateFillLayerCache();
      const pRadius = 3;
      const bbox = [[point.x - pRadius, point.y - pRadius], [point.x + pRadius, point.y + pRadius]];
      let candidateFeatures = [];
      if (roadFillLayers.length > 0) {{
        candidateFeatures = map.queryRenderedFeatures(bbox, {{ layers: roadFillLayers }});
      }}
      if (candidateFeatures.length === 0) {{
        const raw = map.queryRenderedFeatures(bbox);
        candidateFeatures = raw.filter(f => f.properties && f.properties.interactive !== false && (
          f.properties._type === 'corridor_fill' ||
          f.properties._type === 'channel' ||
          f.properties._type === 'corridor'
        ));
      }}
      if (candidateFeatures.length === 0) return null;
      if (hoveredEdgeId) {{
        const currentFeat = candidateFeatures.find(f => String(f.properties.edge_id) === String(hoveredEdgeId));
        if (currentFeat) {{
          const currentLvl = Number(currentFeat.properties.level ?? 0);
          const higherFeat = candidateFeatures.find(f => Number(f.properties.level ?? 0) > currentLvl);
          return higherFeat || currentFeat;
        }}
      }}
      return candidateFeatures[0];
    }}

    function positionTooltip(point) {{
      let tx = point.x + 16;
      let ty = point.y + 16;
      if (tx + 300 > window.innerWidth) tx = point.x - 310;
      if (ty + 240 > window.innerHeight) ty = point.y - 250;
      tooltip.style.left = Math.max(10, tx) + 'px';
      tooltip.style.top = Math.max(10, ty) + 'px';
    }}

    function activateRoad(feat, point) {{
      map.getCanvas().style.cursor = 'pointer';
      const p = feat.properties;
      const eid = String(p.edge_id || p.id || '');

      if (eid !== hoveredEdgeId) {{
        hoveredEdgeId = eid;
        const hSource = map.getSource('hover_source');
        if (hSource) {{
          hSource.setData({{
            type: 'FeatureCollection',
            features: [{{
              type: 'Feature',
              geometry: feat.geometry,
              properties: {{ width_m: p.width_m || 7.0 }}
            }}]
          }});
        }}
      }}

      // Build structure badge
      let structBadge = '';
      if (p.bridge === true || p.bridge === 'true' || p.band > 0) {{
        structBadge = '<span class="tt-tag tt-tag-bridge">🌉 BRIDGE (Band +' + (p.band || 1) + ')</span>';
      }} else if (p.tunnel === true || p.tunnel === 'true' || p.band < 0) {{
        structBadge = '<span class="tt-tag tt-tag-tunnel">🚇 TUNNEL (Band ' + (p.band || -1) + ')</span>';
      }} else {{
        structBadge = '<span class="tt-tag tt-tag-surface">SURFACE</span>';
      }}

      const hwTag = p.highway ? ('<span class="tt-tag">' + p.highway + '</span>') : '';
      const nameVal = p.name ? p.name : '<span style="color:#94a3b8;font-style:italic;">(unnamed road)</span>';
      const cs = (p.casing_start !== undefined && p.casing_start !== null) ? p.casing_start : '—';
      const cm = (p.casing_level !== undefined && p.casing_level !== null) ? p.casing_level : '—';
      const ce = (p.casing_end !== undefined && p.casing_end !== null) ? p.casing_end : '—';
      const fl = (p.fill_level !== undefined && p.fill_level !== null) ? p.fill_level : (p.level !== undefined ? p.level : 0);
      const w = p.width_m ? Number(p.width_m).toFixed(1) + ' m' : '—';
      const isBridgeStr = (p.bridge === true || p.bridge === 'true' || p.band > 0) ? '<span style="color:#c084fc;font-weight:700;">Yes</span>' : 'No';
      const isTunnelStr = (p.tunnel === true || p.tunnel === 'true' || p.band < 0) ? '<span style="color:#fbbf24;font-weight:700;">Yes</span>' : 'No';

      const refStr = p.edge_ref || p.ref || eid || 'N/A';

      tooltip.innerHTML = `
        <div class="tt-header">
          <span class="tt-title">Ref: ${{refStr}}</span>
          <div class="tt-tags">${{hwTag}}${{structBadge}}</div>
        </div>
        <div class="tt-name">${{nameVal}}</div>
        <div class="tt-row"><span class="tt-lbl">Edge Ref:</span><span class="tt-val" style="color:#38bdf8; font-family:monospace; font-size:12px; font-weight:700;">${{refStr}}</span></div>
        <div class="tt-row"><span class="tt-lbl">Highway Class:</span><span class="tt-val" style="color:#38bdf8; font-weight:700;">${{p.highway || '—'}}</span></div>
        <div class="tt-row"><span class="tt-lbl">Hovered Part:</span><span class="tt-val">${{p.part || p._type}}</span></div>
        <div class="tt-row"><span class="tt-lbl">Corridor Width:</span><span class="tt-val">${{w}}</span></div>
        <div class="tt-row"><span class="tt-lbl">Bridge Deck:</span><span class="tt-val">${{isBridgeStr}}</span></div>
        <div class="tt-row"><span class="tt-lbl">Subterranean Tunnel:</span><span class="tt-val">${{isTunnelStr}}</span></div>
        <div class="tt-row"><span class="tt-lbl">Fill Level (fl):</span><span class="tt-val" style="color:#38bdf8; font-size:13px; font-weight:700;">Level ${{fl}}</span></div>
        <div class="tt-box">
          <div class="tt-box-title">Casing Z-Levels (cs, cm, ce)</div>
          <div class="tt-pills">
            <div class="tt-pill"><span>Start (cs)</span><b>${{cs}}</b></div>
            <div class="tt-pill"><span>Main (cm)</span><b>${{cm}}</b></div>
            <div class="tt-pill"><span>End (ce)</span><b>${{ce}}</b></div>
          </div>
        </div>
      `;

      positionTooltip(point);
      tooltip.style.display = 'block';
    }}

    function clearHover() {{
      if (dwellTimer) {{
        clearTimeout(dwellTimer);
        dwellTimer = null;
      }}
      map.getCanvas().style.cursor = '';
      tooltip.style.display = 'none';
      if (hoveredEdgeId !== null) {{
        hoveredEdgeId = null;
        const hSource = map.getSource('hover_source');
        if (hSource) {{
          hSource.setData({{ type: 'FeatureCollection', features: [] }});
        }}
      }}
    }}

    function onMouseMoveAction(e) {{
      const candidate = findRoadAtPoint(e.point);

      if (!candidate) {{
        clearHover();
        return;
      }}

      const candidateEid = String(candidate.properties.edge_id || candidate.properties.id || '');

      // Case 1: Mouse is moving along the ALREADY active road
      if (hoveredEdgeId && candidateEid === hoveredEdgeId) {{
        if (dwellTimer) {{
          clearTimeout(dwellTimer);
          dwellTimer = null;
        }}
        positionTooltip(e.point);
        return;
      }}

      // Case 2: Mouse is moving over a NEW road candidate
      // Reset dwell timer so user must pause/stop for MIN_STOP_MS before activation
      if (dwellTimer) {{
        clearTimeout(dwellTimer);
      }}
      dwellTimer = setTimeout(() => {{
        dwellTimer = null;
        activateRoad(candidate, e.point);
      }}, MIN_STOP_MS);
    }}

    map.on('mousemove', (e) => {{
      pendingEvent = e;
      if (!rafId) {{
        rafId = requestAnimationFrame(() => {{
          rafId = null;
          if (pendingEvent) onMouseMoveAction(pendingEvent);
        }});
      }}
    }});

    map.on('mouseleave', () => {{
      pendingEvent = null;
      if (rafId) {{
        cancelAnimationFrame(rafId);
        rafId = null;
      }}
      clearHover();
    }});
  </script>
</body>
</html>"""
        return html

    def save(self, filepath: str | Path, standalone: bool = True) -> str:
        """Write map to standalone HTML file."""
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = self.to_html(standalone=standalone)
        p.write_text(content, encoding="utf-8")
        return str(p.resolve())

    def show(self) -> None:
        """Open interactive map in default web browser."""
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            f.write(self.to_html().encode("utf-8"))
            temp_path = f.name
        webbrowser.open(f"file://{temp_path}")

    def _repr_html_(self) -> str:
        """Display interactive iframe in Jupyter Notebook."""
        raw_html = self.to_html()
        escaped_html = raw_html.replace('"', '&quot;')
        return f'<iframe style="width: 100%; height: 500px; border: 1px solid #ddd; border-radius: 8px;" srcdoc="{escaped_html}"></iframe>'


def _round_coords(coords: Any, precision: int = 6) -> Any:
    """Recursively round coordinate tuples/lists to specified decimal precision."""
    if isinstance(coords, (list, tuple)):
        if coords and isinstance(coords[0], (int, float)):
            return [round(float(c), precision) for c in coords]
        return [_round_coords(c, precision) for c in coords]
    return coords


def smooth_coords(
    coords: list[Any], iterations: int = 2, corner_deg: float = 100.0
) -> list[tuple[float, ...]]:
    """Chaikin corner-cutting for display. Endpoints and turns sharper than ``corner_deg`` stay put."""
    import math

    pts = [tuple(c) for c in coords]
    if iterations <= 0 or len(pts) < 3:
        return pts
    cos_lat = math.cos(math.radians(pts[0][1]))

    def turn(a: Any, b: Any, c: Any) -> float:
        v1 = ((b[0] - a[0]) * cos_lat, b[1] - a[1])
        v2 = ((c[0] - b[0]) * cos_lat, c[1] - b[1])
        n = math.hypot(*v1) * math.hypot(*v2)
        if n == 0:
            return 0.0
        dot = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))
        return math.degrees(math.acos(dot))

    fixed = [i in (0, len(pts) - 1) or turn(pts[i - 1], pts[i], pts[i + 1]) > corner_deg
             for i in range(len(pts))]
    for _ in range(iterations):
        out: list[tuple[float, ...]] = []
        out_fixed: list[bool] = []
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if fixed[i]:
                out.append(a)
                out_fixed.append(True)
            else:
                out.append(tuple(0.75 * x + 0.25 * y for x, y in zip(a, b)))
                out_fixed.append(False)
            if fixed[i + 1]:
                if i + 1 == len(pts) - 1:
                    out.append(b)
                    out_fixed.append(True)
            else:
                out.append(tuple(0.25 * x + 0.75 * y for x, y in zip(a, b)))
                out_fixed.append(False)
        pts, fixed = out, out_fixed
    return pts


def _to_geojson_geom(geom: Any, precision: int = 6) -> dict[str, Any]:
    """Safely convert geometry object (or dict) to GeoJSON geometry mapping."""
    if isinstance(geom, dict):
        d = geom
    elif hasattr(geom, "__geo_interface__"):
        d = geom.__geo_interface__
    else:
        d = mapping(geom)

    if precision is not None and "coordinates" in d:
        d = dict(d)
        d["coordinates"] = _round_coords(d["coordinates"], precision)
    return d


def compile_map(
    corridors: list[Corridor] | None = None,
    channels: list[Channel] | None = None,
    demarcations: list[Demarcation] | None = None,
    patches: list[Patch] | None = None,
    glyphs: list[Glyph] | None = None,
    *,
    presets: list[ViewPreset] | None = None,
    basemap: str | None = "carto-dark",
    background: str | None = None,
    center: tuple[float, float] | None = None,
    zoom: float | None = None,
    auto_solve: bool = True,
    theme: str = "dark",
    smooth: int = 0,
    smooth_corner_deg: float = 100.0,
) -> WebMap:
    """Compile network cartographic primitives into a self-contained WebMap instance.

    Parameters
    ----------
    corridors : list[Corridor], optional
        Right-of-way carrier corridors with casing split definitions.
    channels : list[Channel], optional
        Sub-lanes, cycle tracks, and turn connectors.
    demarcations : list[Demarcation], optional
        Paint markings (solid white edge lines, yellow centerlines, dashes).
    patches : list[Patch], optional
        Planar polygonal surfaces (intersection fillets, islands, crosswalks).
    glyphs : list[Glyph], optional
        Oriented symbols (turn arrows, bike symbols, street labels).
    presets : list[ViewPreset], optional
        Client-side dynamic view presets.
    basemap : str or None
        Basemap style token ("carto-dark", "carto-light", "osm", or None).
    center : tuple[float, float], optional
        Initial map center (lon, lat). Auto-computed from bounding box if None.
    zoom : float, optional
        Initial zoom level. Auto-computed from bounding box if None.
    auto_solve : bool
        If True and corridors lack casing_levels, solves LP stacking automatically.
    theme : str
        Default color theme ("dark" or "light").
    """
    cor_list = corridors or []
    chan_list = channels or []
    dem_list = demarcations or []
    patch_list = patches or []
    glyph_list = glyphs or []

    # 1. Automatic LP Stacking Solve
    if auto_solve and cor_list:
        needs_solve = any(c.casing_levels is None or c.fill_level is None for c in cor_list)
        if needs_solve:
            solve_stacking(cor_list, assign=True)

    # 2. Package into Single GeoJSON Source (Zero Geometry Duplication)
    features: list[dict[str, Any]] = []
    all_levels: set[int] = {0}
    all_geoms = []

    # Emit Corridors (Split casings + fill)
    for c in cor_list:
        all_geoms.append(c.geometry)
        fl = c.fill_level if c.fill_level is not None else 0
        all_levels.add(fl)

        # 2-Point Casing Split (using split_casing_geometry)
        coords = list(c.geometry.coords) if hasattr(c.geometry, "coords") else []
        if smooth > 0:
            coords = smooth_coords(coords, smooth, smooth_corner_deg)
        cs, cm, ce = c.casing_levels if c.casing_levels is not None else (fl, fl, fl)
        all_levels.update([cs, cm, ce])

        eid = str(c.id or c.properties.get("edge_id") or c.properties.get("id") or "")
        edge_ref = str(c.properties.get("edge_ref") or c.properties.get("ref") or eid)
        name = str(c.properties.get("name") or "")
        hw = str(c.properties.get("highway") or "")
        c_props = {
            "edge_id": eid,
            "edge_ref": edge_ref,
            "name": name,
            "highway": hw,
            "width_m": c.width_m,
            "casing_m": c.casing_m,
            "casing_left_m": c.casing_left_m,
            "casing_right_m": c.casing_right_m,
            "casing_color": c.casing_color,
            "fill_color": c.fill_color,
            "bridge": bool(c.bridge_deck or c.band > 0),
            "tunnel": bool(c.tunnel or c.band < 0),
            "interactive": True,
            "casing_start": cs,
            "casing_level": cm,
            "casing_end": ce,
            "fill_level": fl,
            "band": c.band,
        }

        if len(coords) >= 2:
            pieces = split_casing_geometry(
                coords=coords,
                split_start=c.split_start,
                split_end=c.split_end,
                split_mode=c.split_mode,
                casing_levels=(cs, cm, ce),
            )

            for i_p, p in enumerate(pieces):
                is_flat = p["properties"].get("__rs_cap", False)
                p_lvl = p["properties"].get("__rs_cl", fl)
                if is_flat:
                    part_title = "Casing Main"
                elif i_p == 0:
                    part_title = "Casing Head (Start)"
                else:
                    part_title = "Casing Head (End)"

                all_levels.add(p_lvl)
                features.append({
                    "type": "Feature",
                    "geometry": _to_geojson_geom(p["geometry"]),
                    "properties": {
                        **c_props,
                        "_type": "casing_main" if is_flat else "casing_head",
                        "part": part_title,
                        "level": p_lvl,
                    },
                })

        # Corridor Fill Surface
        if c.fill_visible:
            fill_props = dict(c.properties)
            fill_props.update({
                "_type": "corridor_fill",
                "part": "Road Fill",
                "level": fl,
                "width_m": c.width_m,
                "fill_color": c.fill_color,
                "bridge": bool(c.bridge_deck or c.band > 0),
                "tunnel": bool(c.tunnel or c.band < 0),
                "interactive": True,
                "edge_id": eid,
                "edge_ref": edge_ref,
                "name": name,
                "highway": hw,
                "casing_start": cs,
                "casing_level": cm,
                "casing_end": ce,
                "fill_level": fl,
                "band": c.band,
            })
            features.append({
                "type": "Feature",
                "geometry": _to_geojson_geom(
                    {"type": "LineString", "coordinates": coords} if smooth > 0 and len(coords) >= 2
                    else c.geometry
                ),
                "properties": fill_props,
            })

    # Emit Channels
    for ch in chan_list:
        all_geoms.append(ch.geometry)
        all_levels.add(ch.level)
        ch_props = dict(ch.properties)
        ch_props.update({
            "_type": "channel",
            "level": ch.level,
            "width_m": ch.width_m,
            "color": ch.color,
            "priority": ch.priority,
            "bridge": bool(ch.level > 0 or ch.properties.get("bridge")),
            "tunnel": bool(ch.level < 0 or ch.properties.get("tunnel")),
            "interactive": ch.interactive,
        })
        features.append({
            "type": "Feature",
            "geometry": _to_geojson_geom(ch.geometry),
            "properties": ch_props,
        })

    # Emit Demarcations
    for d in dem_list:
        all_geoms.append(d.geometry)
        all_levels.add(d.level)
        d_props = dict(d.properties)
        d_props.update({
            "_type": "demarcation",
            "level": d.level,
            "width_m": d.width_m,
            "color": d.color,
            "pattern": d.pattern,
            "bridge": bool(d.level > 0 or d.properties.get("bridge")),
            "tunnel": bool(d.level < 0 or d.properties.get("tunnel")),
            "interactive": d.interactive,
        })
        features.append({
            "type": "Feature",
            "geometry": _to_geojson_geom(d.geometry),
            "properties": d_props,
        })

    # Emit Patches
    for p in patch_list:
        all_geoms.append(p.geometry)
        all_levels.add(p.level)
        p_props = dict(p.properties)
        p_props.update({
            "_type": "patch",
            "level": p.level,
            "color": p.color,
            "opacity": p.opacity,
            "order": p.order,
            "interactive": p.interactive,
        })
        features.append({
            "type": "Feature",
            "geometry": _to_geojson_geom(p.geometry),
            "properties": p_props,
        })

    # Emit Glyphs
    for g in glyph_list:
        all_geoms.append(g.geometry)
        all_levels.add(g.level)
        g_props = dict(g.properties)
        g_props.update({
            "_type": "glyph",
            "level": g.level,
            "symbol": g.symbol,
            "text": g.text,
            "size": g.size,
            "color": g.color,
            "alignment": g.alignment,
            "interactive": g.interactive,
        })
        features.append({
            "type": "Feature",
            "geometry": _to_geojson_geom(g.geometry),
            "properties": g_props,
        })

    # Filter out null, empty, or unsupported geometry types before building GeoJSON source
    valid_features = []
    VALID_GEOMS = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}
    for f in features:
        geom = f.get("geometry")
        if not geom or not isinstance(geom, dict):
            continue
        gtype = geom.get("type")
        if gtype not in VALID_GEOMS:
            continue
        coords = geom.get("coordinates")
        if coords is None or len(coords) == 0:
            continue
        valid_features.append(f)

    single_source = {
        "type": "geojson",
        "maxzoom": 24,
        "tolerance": 0.0,
        "data": {
            "type": "FeatureCollection",
            "features": valid_features,
        },
    }

    # 3. Compute Map Center and Bounds
    if center is None or zoom is None:
        if all_geoms:
            bounds = shapely.total_bounds(shapely.GeometryCollection(all_geoms))
            minx, miny, maxx, maxy = bounds
            computed_center = ((minx + maxx) / 2.0, (miny + maxy) / 2.0)
            span_x = abs(maxx - minx)
            span_y = abs(maxy - miny)
            max_span = max(span_x, span_y, 0.001)
            # Web Mercator zoom estimation
            computed_zoom = max(1.0, min(19.0, round(math.log2(360.0 / max_span) - 1.0, 1)))
        else:
            computed_center = (0.0, 0.0)
            computed_zoom = 2.0
        center = center or computed_center
        zoom = zoom if zoom is not None else computed_zoom

    # 4. Build MapLibre Layers Stack
    global _SCALE_LAT
    _SCALE_LAT = float(center[1])
    sources: dict[str, Any] = {
        "network": single_source,
        "hover_source": {
            "type": "geojson",
            "data": {"type": "FeatureCollection", "features": []},
        },
    }
    layers: list[dict[str, Any]] = []

        # Solid bedrock canvas background (always present underneath everything)
    is_no_basemap = not basemap or str(basemap).strip().lower() in ("none", "blank", "false", "")
    if background is not None:
        bg_color = background
    elif is_no_basemap:
        # Non-black neutral drafting canvas so dark casings and road geometry are clearly visible
        bg_color = "#efede8" if theme != "dark" else "#e2e8f0"
    else:
        bg_color = "#0b0d14" if theme == "dark" else "#f8fafc"

    # Pre-calculated background RGB for Method 1 color mixing (zero alpha overlap blotches)
    target_bg = bg_color if bg_color.startswith("#") and len(bg_color) == 7 else ("#0b0d14" if theme == "dark" else "#f8fafc")
    bg_r = int(target_bg[1:3], 16)
    bg_g = int(target_bg[3:5], 16)
    bg_b = int(target_bg[5:7], 16)

    # Initial Method 1 pre-mixed color expression at 65% fade factor
    init_fade = 0.65
    tunnel_fill_color_expr = [
        "rgb",
        ["+", ["*", ["at", 0, ["to-rgba", ["to-color", ["coalesce", ["get", "fill_color"], "#38bdf8"]]]], init_fade], round((1.0 - init_fade) * bg_r, 2)],
        ["+", ["*", ["at", 1, ["to-rgba", ["to-color", ["coalesce", ["get", "fill_color"], "#38bdf8"]]]], init_fade], round((1.0 - init_fade) * bg_g, 2)],
        ["+", ["*", ["at", 2, ["to-rgba", ["to-color", ["coalesce", ["get", "fill_color"], "#38bdf8"]]]], init_fade], round((1.0 - init_fade) * bg_b, 2)],
    ]

    # Pre-mixed initial casing color at 60% fade factor
    c_fade = 0.60
    case_r, case_g, case_b = 0x94, 0xa3, 0xb8
    init_case_hex = f"#{round(case_r * c_fade + bg_r * (1.0 - c_fade)):02x}{round(case_g * c_fade + bg_g * (1.0 - c_fade)):02x}{round(case_b * c_fade + bg_b * (1.0 - c_fade)):02x}"

    layers.append({
        "id": "background-solid",
        "type": "background",
        "paint": {"background-color": bg_color},
    })

    # Basemap Raster Layer
    if basemap:
        bm_key = str(basemap).strip().lower().replace("_", "-")
        bm_spec = BASEMAPS.get(bm_key)
        if not bm_spec:
            if any(k in bm_key for k in ("light", "voyager", "positron")):
                bm_spec = BASEMAPS["carto-voyager"]
            elif "osm" in bm_key:
                bm_spec = BASEMAPS["osm"]
            elif "esri" in bm_key:
                bm_spec = BASEMAPS["esri-dark"]
            else:
                bm_spec = BASEMAPS["carto-dark"]
        sources["basemap"] = bm_spec
        layers.append({
            "id": "basemap-tiles",
            "type": "raster",
            "source": "basemap",
            "minzoom": 0,
            "maxzoom": 22,
            "paint": {"raster-brightness-min": 0.12, "raster-contrast": 0.2} if "dark" in bm_key else {},
        })

    # Visual Layer Hierarchy per Level L
    sorted_levels = sorted(all_levels)
    bridge_edge = "#f1f5f9" if theme == "dark" else "#0f172a"
    tunnel_edge = "#94a3b8" if theme == "dark" else "#64748b"

    for L in sorted_levels:
        lvl_tag = f"lv{L}" if L >= 0 else f"lvn{abs(L)}"

        # 1. Patches (order: -1 fillets & islands)
        layers.append({
            "id": f"patch-under-{lvl_tag}",
            "type": "fill",
            "source": "network",
            "filter": ["all", ["==", ["get", "_type"], "patch"], ["==", ["get", "level"], L], ["<", ["get", "order"], 0]],
            "paint": {
                "fill-color": ["coalesce", ["get", "color"], "#334155"],
                "fill-opacity": ["coalesce", ["get", "opacity"], 1.0],
            },
        })

        # 1b. Bridge Ambient Drop Shadow (projects soft shadow under bridge deck onto lower roads)
        layers.append({
            "id": f"bridge-shadow-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["==", ["get", "_type"], "casing_main"], ["==", ["get", "level"], L], ["==", ["get", "bridge"], True]],
            "layout": {
                "line-cap": "butt",
                "line-join": "round",
            },
            "paint": {
                "line-color": "rgba(0, 0, 0, 0.45)" if theme == "dark" else "rgba(15, 23, 42, 0.28)",
                "line-width": meter_to_pixel_width_expr("width_m", extra_prop="casing_m"),
                "line-blur": 1.5,
                "line-offset": lateral_offset_expr("casing_left_m", "casing_right_m"),
            },
        })

        # 2. Casing Start/End Heads (round caps)
        layers.append({
            "id": f"casing-head-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["==", ["get", "_type"], "casing_head"], ["==", ["get", "level"], L], ["!=", ["get", "tunnel"], True]],
            "layout": {
                "line-cap": "round",
                "line-join": "round",
            },
            "paint": {
                "line-color": [
                    "case",
                    ["==", ["get", "bridge"], True],
                    bridge_edge,
                    ["coalesce", ["get", "casing_color"], "#1e293b" if theme == "dark" else "#475569"],
                ],
                "line-width": meter_to_pixel_width_expr("width_m", extra_prop="casing_m", min_px=2.0, extra_px=3.0),
                "line-offset": lateral_offset_expr("casing_left_m", "casing_right_m"),
            },
        })

        # 3. Casing Main Span (flat butt caps) for Surface Roads
        layers.append({
            "id": f"casing-main-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["==", ["get", "_type"], "casing_main"], ["==", ["get", "level"], L], ["!=", ["get", "tunnel"], True]],
            "layout": {
                "line-cap": "butt",
                "line-join": "round",
            },
            "paint": {
                "line-color": [
                    "case",
                    ["==", ["get", "bridge"], True],
                    bridge_edge,
                    ["coalesce", ["get", "casing_color"], "#1e293b" if theme == "dark" else "#475569"],
                ],
                "line-width": meter_to_pixel_width_expr("width_m", extra_prop="casing_m", min_px=2.0, extra_px=3.0),
                "line-offset": lateral_offset_expr("casing_left_m", "casing_right_m"),
            },
        })

        # 3b. Tunnel Casing (Method 1: Pre-mixed Color with 100% Opacity)
        layers.append({
            "id": f"tunnel-casing-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["in", ["get", "_type"], ["literal", ["casing_main", "casing_head"]]], ["==", ["get", "level"], L], ["==", ["get", "tunnel"], True]],
            "layout": {
                "line-cap": "butt",
                "line-join": "round",
            },
            "paint": {
                "line-color": init_case_hex,
                "line-width": meter_to_pixel_width_expr("width_m", extra_prop="casing_m", min_px=2.0, extra_px=3.0),
                "line-dasharray": [3.0, 3.0],
                "line-offset": lateral_offset_expr("casing_left_m", "casing_right_m"),
                "line-opacity": 1.0,
            },
        })

        # 4. Corridor Fill Surface (Surface Roads - 100% Solid & Untouched)
        layers.append({
            "id": f"corridors-fill-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["in", ["get", "_type"], ["literal", ["corridor_fill", "corridor"]]], ["==", ["get", "level"], L], ["!=", ["get", "tunnel"], True]],
            "layout": {
                "line-cap": "round",
                "line-join": "round",
            },
            "paint": {
                "line-color": ["coalesce", ["get", "fill_color"], "#38bdf8"],
                "line-width": meter_to_pixel_width_expr("width_m", min_px=1.5),
                "line-opacity": 1.0,
            },
        })

        # 4b. Tunnel Fill Surface (Method 1: 100% Solid Opacity with Pre-Mixed Color -> Zero Overlap Blotches!)
        layers.append({
            "id": f"tunnel-fill-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["in", ["get", "_type"], ["literal", ["corridor_fill", "corridor"]]], ["==", ["get", "level"], L], ["==", ["get", "tunnel"], True]],
            "layout": {
                "line-cap": "round",
                "line-join": "round",
            },
            "paint": {
                "line-color": tunnel_fill_color_expr,
                "line-width": meter_to_pixel_width_expr("width_m", min_px=1.5),
                "line-opacity": 1.0,
            },
        })

        # 4b. Channel Pavement Deck & Outer Casing (frames the road corridor beneath the lanes)
        layers.append({
            "id": f"channel-casing-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["==", ["get", "_type"], "channel"], ["==", ["get", "level"], L]],
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {
                "line-color": [
                    "case",
                    ["==", ["get", "bridge"], True],
                    bridge_edge,
                    ["==", ["get", "tunnel"], True],
                    tunnel_edge,
                    "#1e293b" if theme == "dark" else "#64748b",
                ],
                "line-width": meter_to_pixel_width_expr("width_m", extra_prop=0.4, min_px=1.0, extra_px=2.0),
                "line-opacity": [
                    "case",
                    ["==", ["get", "tunnel"], True],
                    0.50,
                    1.0,
                ],
            },
        })

        # 5. Channel Sub-Lanes
        layers.append({
            "id": f"channel-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["==", ["get", "_type"], "channel"], ["==", ["get", "level"], L]],
            "layout": {
                "line-cap": "round",
                "line-join": "round",
            },
            "paint": {
                "line-color": ["coalesce", ["get", "color"], "#ffffff"],
                "line-width": meter_to_pixel_width_expr("width_m", min_px=1.0),
                "line-opacity": [
                    "case",
                    ["==", ["get", "tunnel"], True],
                    0.65,
                    1.0,
                ],
            },
        })

        # 6. Demarcations: Solid White/Yellow Stripes
        layers.append({
            "id": f"demarcation-solid-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["==", ["get", "_type"], "demarcation"], ["==", ["get", "pattern"], "solid"], ["==", ["get", "level"], L]],
            "layout": {
                "line-cap": "butt",
                "line-join": "round",
            },
            "paint": {
                "line-color": ["coalesce", ["get", "color"], "#ffffff"],
                "line-width": meter_to_pixel_width_expr("width_m", min_px=1.8),
                "line-opacity": [
                    "case",
                    ["==", ["get", "tunnel"], True],
                    0.65,
                    1.0,
                ],
            },
        })

        # 7. Demarcations: Dashed Lane Lines
        layers.append({
            "id": f"demarcation-dashed-{lvl_tag}",
            "type": "line",
            "source": "network",
            "filter": ["all", ["==", ["get", "_type"], "demarcation"], ["==", ["get", "pattern"], "dashed"], ["==", ["get", "level"], L]],
            "layout": {
                "line-cap": "butt",
                "line-join": "round",
            },
            "paint": {
                "line-color": ["coalesce", ["get", "color"], "#ffffff"],
                "line-width": meter_to_pixel_width_expr("width_m", min_px=1.8),
                "line-dasharray": [3.0, 4.0],
                "line-opacity": [
                    "case",
                    ["==", ["get", "tunnel"], True],
                    0.65,
                    1.0,
                ],
            },
        })

        # 8. Glyphs & Labels (only emit if custom glyph annotations are present)
        if glyph_list:
            layers.append({
                "id": f"glyph-{lvl_tag}",
                "type": "symbol",
                "source": "network",
                "filter": ["all", ["==", ["get", "_type"], "glyph"], ["==", ["get", "level"], L]],
                "layout": {
                    "text-field": ["coalesce", ["get", "text"], ""],
                    "text-size": 12,
                    "text-font": ["Noto Sans Regular"],
                    "symbol-placement": "point",
                },
                "paint": {
                    "text-color": ["coalesce", ["get", "color"], "#ffffff"],
                    "text-halo-color": "rgba(0,0,0,0.8)",
                    "text-halo-width": 1.5,
                },
            })

    # Direction arrows along one-way lanes (icon drawn at runtime, see to_html)
    layers.append({
        "id": "lane-arrows",
        "type": "symbol",
        "source": "network",
        "minzoom": 16,
        "filter": ["all", ["==", ["get", "_type"], "channel"], ["==", ["get", "oneway"], True]],
        "layout": {
            "symbol-placement": "line",
            "symbol-spacing": 90,
            "icon-image": "rs-arrow",
            "icon-size": ["interpolate", ["linear"], ["zoom"], 16, 0.35, 19, 0.8],
            "icon-rotation-alignment": "map",
            "icon-allow-overlap": True,
            "icon-ignore-placement": True,
        },
        "paint": {"icon-opacity": ["case", ["==", ["get", "tunnel"], True], 0.4, 0.9]},
    })

    # 9. Dynamic Interactive Road Hover Highlight (Dedicated Zero-Lag Source)
    layers.append({
        "id": "hover-road-casing",
        "type": "line",
        "source": "hover_source",
        "layout": {"line-cap": "round", "line-join": "round"},
        "paint": {
            "line-color": "#0284c7",
            "line-width": meter_to_pixel_width_expr("width_m", extra_px=6.0, min_px=5.0),
            "line-opacity": 0.95,
        },
    })
    layers.append({
        "id": "hover-road-glow",
        "type": "line",
        "source": "hover_source",
        "layout": {"line-cap": "round", "line-join": "round"},
        "paint": {
            "line-color": "#00f0ff",
            "line-width": meter_to_pixel_width_expr("width_m", extra_px=3.0, min_px=4.0),
            "line-opacity": 0.9,
            "line-blur": 1.5,
        },
    })
    layers.append({
        "id": "hover-road-fill",
        "type": "line",
        "source": "hover_source",
        "layout": {"line-cap": "round", "line-join": "round"},
        "paint": {
            "line-color": "#ffffff",
            "line-width": meter_to_pixel_width_expr("width_m", min_px=2.0),
            "line-opacity": 0.95,
        },
    })

    # Street names (line-placed, one label per named road)
    label_color = "#f1f5f9" if theme == "dark" else "#1e293b"
    label_halo = "rgba(11,13,20,0.9)" if theme == "dark" else "rgba(255,255,255,0.95)"
    layers.append({
        "id": "street-names",
        "type": "symbol",
        "source": "network",
        "minzoom": 15,
        "filter": [
            "all",
            ["in", ["get", "_type"], ["literal", ["corridor_fill", "channel"]]],
            ["!=", ["coalesce", ["get", "name"], ""], ""],
            ["!=", ["coalesce", ["get", "connector"], False], True],
            ["<=", ["coalesce", ["get", "lane_num"], 1], 1],
        ],
        "layout": {
            "symbol-placement": "line",
            "symbol-spacing": 350,
            "text-field": ["get", "name"],
            "text-font": ["Noto Sans Regular"],
            "text-size": ["interpolate", ["linear"], ["zoom"], 15, 10, 19, 14],
            "text-max-angle": 30,
            "text-padding": 4,
        },
        "paint": {
            "text-color": label_color,
            "text-halo-color": label_halo,
            "text-halo-width": 1.6,
        },
    })

    # Assemble Full MapLibre Style Dictionary
    style_dict: dict[str, Any] = {
        "version": 8,
        "name": "roadstyle-v2",
        "glyphs": "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
        "sources": sources,
        "layers": layers,
    }

    return WebMap(style=style_dict, center=center, zoom=zoom, presets=presets, background_color=bg_color)
