# roadstyle v2: Core Engine Specification

**Status:** Technical Specification  
**Package:** `roadstyle.v2.engine`  

---

## 1. Overview

The `roadstyle` v2 Core Engine is a pure, domain-agnostic cartographic compiler. It transforms 5 universal geometric primitives into an optimized, interactive MapLibre WebGL map.

The engine has no knowledge of road classifications (e.g. `highway="motorway"`), routing graphs, or vehicular rules. All semantics are expressed via physical dimensions, topological stacking ranks, and visual style properties.

---

## 2. The 5 Universal Primitives

All primitives inherit from `BasePrimitive` and can be supplied as Python dataclasses, lists of dictionaries, or GeoPandas `GeoDataFrame` rows.

### 2.1 `Corridor` (Carriageways, Links, Right-of-Way Hosts)
Represents a physical road corridor and its boundary casing:

```python
from dataclasses import dataclass, field
from shapely.geometry import LineString

@dataclass(slots=True)
class Corridor:
    geometry: LineString
    id: str | int | None = None
    
    # Physical Dimensions
    width_m: float = 8.0                     # Total corridor physical width
    casing_left_m: float = 0.20              # Thickness of left curb / barrier
    casing_right_m: float = 0.20             # Thickness of right curb / barrier
    
    # 2-Point Casing Split (Asymmetric Junction Setbacks or Stations)
    # Mode: "setbacks" (h_start, h_end) or "stations" (s_start, s_end)
    split_mode: str = "setbacks"
    split_start: float = 5.0                 # Setback from vertex 0 (m) or station
    split_end: float = 5.0                   # Setback from vertex -1 (m) or station
    
    # Stacking & Levels
    band: int = 0                            # Grade tier (-1 tunnel, 0 surface, +1 bridge)
    junction_priority: float = 0.0           # Relative draw rank at shared junctions
    casing_levels: tuple[int, int, int] | None = None  # (cs, cm, ce) if pre-solved
    fill_level: int | None = None            # fl if pre-solved
    
    # Visual Properties
    fill_visible: bool = True                # False when filled by child Channels
    fill_color: str = "#ffffff"
    casing_color: str = "#222222"
    bridge_deck: bool = False
    tunnel: bool = False
    
    # Interaction
    interactive: bool = True
    properties: dict = field(default_factory=dict)
```

---

### 2.2 `Channel` (Travel Lanes, Rails, Sidewalks, Cycle Tracks)
Represents an individual longitudinal flow channel inside or across corridors:

```python
@dataclass(slots=True)
class Channel:
    geometry: LineString
    id: str | int | None = None
    corridor_id: str | int | None = None     # Optional link to parent corridor
    
    # Physical Dimensions
    width_m: float = 3.50                    # Physical width of the track
    offset_m: float = 0.0                    # Lateral offset from reference line
    
    # Stacking
    order: int = 0                           # Relative draw order within elevation level
    band: int = 0
    
    # Styling
    fill_color: str = "#444444"
    opacity: float = 1.0
    dash_array: list[float] | None = None    # For painted channelization
    
    # Interaction
    interactive: bool = True
    properties: dict = field(default_factory=dict)
```

---

### 2.3 `Demarcation` (Pavement Markings, Divider Lines, Stop Bars)
Represents zero-area boundary markings:

```python
@dataclass(slots=True)
class Demarcation:
    geometry: LineString
    id: str | int | None = None
    corridor_id: str | int | None = None
    
    # Stroke properties
    stroke_px: float = 2.0                   # Screen width in pixels
    stroke_m: float | None = None            # Or physical width in meters (e.g. 0.15m)
    color: str = "#ffffff"
    opacity: float = 0.9
    dash_array: list[float] = field(default_factory=list) # e.g. [3, 9] for divider
    cap: str = "butt"                        # "butt", "round", "square"
    
    # Stacking
    order: int = 1                           # Placed above channel fills
    band: int = 0
    
    # Interaction (Default: False for pure decorative markings)
    interactive: bool = False
    properties: dict = field(default_factory=dict)
```

---

### 2.4 `Patch` (2D Planar Surfaces: Fillets, Islands, Wedges, Crosswalks)
Represents 2D planar polygons that cannot be modeled as constant-width line strokes:

```python
from shapely.geometry import Polygon, MultiPolygon

@dataclass(slots=True)
class Patch:
    geometry: Polygon | MultiPolygon
    id: str | int | None = None
    
    fill_color: str = "#333333"
    fill_opacity: float = 1.0
    outline_color: str | None = None
    outline_width_px: float = 0.0
    
    # Stacking
    order: int = -1                          # -1 for junction fillets, 2 for crosswalks
    band: int = 0
    
    # Interaction
    interactive: bool = False
    properties: dict = field(default_factory=dict)
```

---

### 2.5 `Glyph` (Symbols, Directional Arrows, Shields, Text Labels)
Represents oriented symbols or text:

```python
from shapely.geometry import Point

@dataclass(slots=True)
class Glyph:
    geometry: Point | LineString
    id: str | int | None = None
    
    symbol: str | None = None                # Icon name (e.g. "turn-left", "bike")
    text: str | None = None                  # Label text (e.g. "Main St")
    size: float = 1.0
    color: str = "#ffffff"
    alignment: str = "line"                  # "line", "map", "viewport"
    
    order: int = 10                          # Overlays everything else
    band: int = 0
    
    interactive: bool = False
    properties: dict = field(default_factory=dict)
```

---

## 3. The 2-Point Casing Split Algorithm

Given a corridor polyline $C$ of length $L$ in meters, and two cut parameters $(c_1, c_2)$:

### Algorithm:
1. **Compute Polyline Station Lengths**:
   Project coordinates into local cartesian meters $(x \cdot k_x, y \cdot k_y)$ where $k_x = 111320 \cdot \cos(\text{lat}_0), k_y = 111320$.
   Compute cumulative distance array $\text{cum} = [d_0 = 0, d_1, \dots, d_m = L]$.

2. **Calculate Cut Points $(\text{cut}_1, \text{cut}_2)$**:
   * **If `split_mode == "setbacks"`**:
     $$\text{cut}_1 = \max(0.0, c_1)$$
     $$\text{cut}_2 = \min(L, L - c_2)$$
     *If $\text{cut}_1 \ge \text{cut}_2$ (Short Road)*:
     The road has no middle main part. The two heads meet at:
     $$\text{cut}_1 = \text{cut}_2 = L \cdot \frac{c_1}{c_1 + c_2}$$
   * **If `split_mode == "stations"`**:
     $$\text{cut}_1 = \min(L, \max(0.0, c_1))$$
     $$\text{cut}_2 = \min(L, \max(\text{cut}_1, c_2))$$

3. **Subdivide Geometry into 3 Pieces**:
   * **Piece 0 (Start Head)**: Segment from $[0, \text{cut}_1]$:
     - Level: `casing_levels[0]` (`cs`)
     - Cap: `round` (seals at intersection node $u$)
   * **Piece 1 (Main Span)**: Segment from $[\text{cut}_1, \text{cut}_2]$ (omitted if length $\le 0$):
     - Level: `casing_levels[1]` (`cm`)
     - Cap: `butt` (`__rs_cap = True`: prevents round cap bleeding into junction heads)
   * **Piece 2 (End Head)**: Segment from $[\text{cut}_2, L]$:
     - Level: `casing_levels[2]` (`ce`)
     - Cap: `round` (seals at intersection node $v$)

4. **Coordinate Rounding & Back-Projection**:
   Back-project to WGS84 coordinates rounded to 7 decimal places (~1.1 cm precision).

---

## 4. Single-Source Multi-Layer Architecture

MapLibre style compilation places all network primitives into a **single GeoJSON source** (`sources["network"]`):
* Contains split casing pieces, corridor fill envelopes, channel travel lanes, demarcations, patches, and glyphs.
* Zero geometry duplication across multiple source dictionaries.

Deterministic visual passes compiled per elevation level $L$:
1. `patch-under-lv<L>` $\to$ Underlay fillets and islands (`order < 0`).
2. `bridge-shadow-lv<L>` $\to$ Ambient blurred drop shadow (`line-blur: 4.0`) cast under bridge decks (`bridge == True`).
3. `casing-head-lv<L>` $\to$ Junction head collar with `line-cap: round`.
4. `casing-main-lv<L>` $\to$ Main span casing with `line-cap: butt` (dark `#0f172a` deck casing for bridges).
5. `tunnel-casing-dash-lv<L>` $\to$ Dashed casing overlay (`line-dasharray: [3.0, 3.0]`) for subterranean tunnels (`tunnel == True`).
6. `corridors-fill-lv<L>` $\to$ Base carriageway pavement fill (data-driven `line-opacity: 0.50` for tunnels).
7. `channel-lv<L>` $\to$ Dedicated sub-lanes and turn connectors.
8. `demarcation-solid-lv<L>` $\to$ Edge lines and median divides.
9. `demarcation-dashed-lv<L>` $\to$ Inter-lane divider lines (`line-dasharray: [4.0, 4.0]`).
10. `glyph-lv<L>` $\to$ Turn arrows, bike stencils, street labels.

**Result:** Zero duplicate geometry in the HTML/JSON payload, 60 FPS rendering on mobile and desktop WebGL runtimes.

---

## 5. Dynamic ViewPresets (Multi-Dimensional Client-Side Switching)

In `roadstyle` v1, client-side switching was strictly limited to recoloring (`color_options`).
In `roadstyle` v2, dynamic switching is generalized to **any visual channel** via `ViewPreset`.

### 5.1 `ViewPreset` Data Model

```python
@dataclass(slots=True)
class ViewPreset:
    name: str                                # Display name in UI dropdown (e.g. "Traffic Flow")
    
    # 1. Color Dimension
    color_by: str | None = None              # Column name or property key
    palette: str | dict | None = None        # Discrete category palette
    cmap: str | None = None                  # Continuous colormap ("viridis", "plasma", etc.)
    vmin: float | None = None
    vmax: float | None = None
    legend_title: str | None = None
    
    # 2. Width Dimension
    width_mode: str = "physical"             # "physical" (meters), "flow" (bandwidth), "schematic" (px)
    width_by: str | None = None              # Column for flow bandwidth (e.g. "aadt", "truck_volume")
    width_scale: float = 1.0                 # Scaling factor for flow width
    min_width_px: float = 2.0                # Minimum screen width
    max_width_px: float = 30.0               # Maximum screen width clamp
    
    # 3. Label / Annotation Dimension
    label_by: str | None = None              # "name", "ref", "link_id", "speed_kmh", or None
    
    # 4. Filter / Sub-Network Isolation
    filter_expr: list | None = None          # MapLibre filter expression (e.g. ["==", ["get", "mode"], "bus"])
    opacity_unselected: float = 0.10         # Dimming opacity for roads outside filter
```

### 5.2 How ViewPresets Compile into WebGL (0ms Latency)

1. **Python Pre-computation**:
   - The engine iterates through defined `ViewPreset` instances.
   - For each preset, resolved color hexes are baked into `_preset_col_{i}`.
   - If `width_mode == "flow"`, normalized bandwidth widths are baked into `_preset_w_{i}`.
   - Metadata is packaged into `web_map.spec["presets"]`.

2. **Client-Side Runtime Switching**:
   When the user picks a preset from the UI dropdown:
   ```javascript
   function applyPreset(p) {
     // 1. Swap Color
     map.setPaintProperty("corridors-fill", "line-color", ["get", p.color_prop]);
     
     // 2. Swap Width
     if (p.width_mode === "flow") {
       map.setPaintProperty("corridors-fill", "line-width", ["get", p.width_prop]);
     } else if (p.width_mode === "schematic") {
       map.setPaintProperty("corridors-fill", "line-width", p.fixed_px || 2);
     } else {
       map.setPaintProperty("corridors-fill", "line-width", DEFAULT_METER_WIDTH_EXPR);
     }
     
     // 3. Swap Labels
     if (p.label_prop) {
       map.setLayoutProperty("corridors-labels", "text-field", ["get", p.label_prop]);
       map.setLayoutProperty("corridors-labels", "visibility", "visible");
     } else {
       map.setLayoutProperty("corridors-labels", "visibility", "none");
     }
     
     // 4. Swap Filter / Dimming
     if (p.filter) {
       map.setFilter("corridors-fill", p.filter);
     } else {
       map.setFilter("corridors-fill", null);
     }
   }
   ```
   **All transitions occur on the GPU in 0 milliseconds without re-requesting or re-parsing GeoJSON.**

---

## 5. Boundary & Junction Topologies: Dead Ends & Roundabouts

### 5.1 Dead-End Twins & Cul-de-Sacs
For road segments terminating at degree-1 dead-end nodes:
1. **Corridor Envelope**: Rather than fanning two opposite twin edges into distinct lines that produce an "ω" notch, the parent `Corridor` envelope terminates with `line-cap: round`, encompassing both internal `Channel`s.
2. **Cul-de-Sac Bulbs**: Where an expanded turnaround bulb exists:
   $$\text{Geometry} = \text{Buffer}(P_{\text{end}}, R_{\text{bulb}})$$
   Represented as a planar `Patch` with `order: -1` and `interactive: False`.

### 5.2 Roundabout Topological Invariant
A roundabout consists of a closed loop or sequence of edges $E_{\text{ring}} = \{e_1, e_2, \dots, e_k\}$ intersected by approach arms $E_{\text{arms}}$.

1. **LP Solver Stacking Constraint**:
   To prevent entering arms' round caps or colors from bleeding across the circulating roadway:
   $$\forall e_r \in E_{\text{ring}}, \forall e_a \in E_{\text{arms}} \text{ meeting at node } u: \quad \text{fill\_level}(e_r) - \text{fill\_level}(e_a) \ge 1$$
2. **Approach Corridor Setback**:
   The approach corridor $e_a$ receives an asymmetric split cut at the entry node:
   $$s_{\text{entry}} = \frac{W_{\text{ring}}}{2} + \delta_{\text{curb\_return}}$$
   ensuring the arm's curb casing terminates cleanly at the outer perimeter of the circulating carriageway.
3. **Central Island**:
   The interior of the ring is closed as a 2D `Patch` polygon ($order = -1$), providing the central island curb and landscape fill.

