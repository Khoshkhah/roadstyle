# roadstyle v2: Multi-View Architectural Blueprint

**Status:** Approved Reference  
**Audience:** Core Developers, Integrators, and Domain Adapter Authors  

This document provides a comprehensive visual reference of `roadstyle` v2 through **6 distinct architectural views**. Each view captures a different aspect of the system: pipeline flow, data model taxonomy, physical casing geometry, runtime WebGL memory, dynamic client-side presets, and domain adapter mapping.

---

## 1. System Pipeline View (End-to-End Compilation Flow)

This view traces the lifecycle of network data from raw input files down to GPU vertex buffers on the screen.

```mermaid
flowchart TD
    subgraph INGEST["1. Ingestion Layer"]
        RAW_OSM["Raw OSM / DuckOSM"]
        RAW_GMNS["GMNS CSVs (link, lane, node)"]
        RAW_ASAM["OpenDRIVE XML"]
        RAW_GIS["GeoPandas GeoDataFrame"]
    end

    subgraph ADAPT["2. Adapter Normalization"]
        A_OSM["OSMAdapter"]
        A_GMNS["GMNSAdapter"]
        A_ASAM["ASAMAdapter"]
        A_GIS["DirectTable"]
    end

    subgraph PRIM["3. The 5 Universal Primitives"]
        C_CORR["Corridors (LineString + Physical Width)"]
        C_CHAN["Channels (Travel Lanes / Tracks)"]
        C_DEM["Demarcations (Pavement Markings)"]
        C_PAT["Patches (2D Fillets / Islands)"]
        C_GLY["Glyphs (Arrows / Labels)"]
    end

    subgraph CORE["4. Core Engine Processing"]
        SOLV["Linear Programming Level Solver\n(Computes cs, cm, ce, fl from bands & priorities)"]
        SPLIT["2-Point Casing Splitter\n(Cuts polylines into start, main, and end heads)"]
        PACK["Single-Source GeoJSON Packager\n(sources['corridors'], sources['casings'])"]
    end

    subgraph SHADER["5. WebGL / MapLibre Style Compiler"]
        L_CAS["Casing Layers (roads-casing-lv*)"]
        L_FIL["Fill / Lane Layers (roads-fill-lv*)"]
        L_ORD["Sub-Level Ordered Passes (order_col)"]
        L_MRK["Marking & Symbol Layers"]
        L_HIT["Interactive Hit-Testing Target Layers"]
    end

    subgraph BROWSER["6. Client Browser Runtime (60 FPS)"]
        CANVAS["MapLibre WebGL Canvas"]
        PRESET["ViewPreset Switcher (0ms GPU Swap)"]
        SIDEBAR["Interactive Selection & Popups"]
    end

    RAW_OSM --> A_OSM
    RAW_GMNS --> A_GMNS
    RAW_ASAM --> A_ASAM
    RAW_GIS --> A_GIS

    A_OSM --> C_CORR
    A_GMNS --> C_CORR
    A_GMNS --> C_CHAN
    A_GMNS --> C_DEM
    A_GMNS --> C_PAT
    A_GMNS --> C_GLY
    A_ASAM --> C_CORR
    A_ASAM --> C_CHAN
    A_GIS --> C_CORR

    C_CORR --> SOLV
    SOLV --> SPLIT
    SPLIT --> PACK
    C_CHAN --> PACK
    C_DEM --> PACK
    C_PAT --> PACK
    C_GLY --> PACK

    PACK --> L_CAS
    PACK --> L_FIL
    PACK --> L_ORD
    PACK --> L_MRK
    PACK --> L_HIT

    L_CAS --> CANVAS
    L_FIL --> CANVAS
    L_ORD --> CANVAS
    L_MRK --> CANVAS
    L_HIT --> SIDEBAR
    PRESET -.-> CANVAS
```

---

## 2. Primitive Taxonomy View (The Universal Data Model)

This view details the object hierarchy, physical parameters, and interaction traits of the universal primitives.

```mermaid
classDiagram
    class BasePrimitive {
        +id: str | int
        +band: int
        +interactive: bool
        +properties: dict
    }

    class Corridor {
        +geometry: LineString
        +width_m: float
        +casing_left_m: float
        +casing_right_m: float
        +split_mode: str
        +split_start: float
        +split_end: float
        +junction_priority: float
        +casing_levels: tuple[cs, cm, ce]
        +fill_level: int
        +fill_visible: bool
        +fill_color: str
        +casing_color: str
        +bridge_deck: bool
        +tunnel: bool
        +casing_m() float
    }

    class Channel {
        +geometry: LineString
        +corridor_id: str | int
        +width_m: float
        +offset_m: float
        +order: int
        +fill_color: str
        +opacity: float
        +dash_array: list[float]
    }

    class Demarcation {
        +geometry: LineString
        +corridor_id: str | int
        +stroke_px: float
        +stroke_m: float
        +color: str
        +opacity: float
        +dash_array: list[float]
        +cap: str
        +order: int
    }

    class Patch {
        +geometry: Polygon | MultiPolygon
        +fill_color: str
        +fill_opacity: float
        +outline_color: str
        +outline_width_px: float
        +order: int
    }

    class Glyph {
        +geometry: Point | LineString
        +symbol: str
        +text: str
        +size: float
        +color: str
        +alignment: str
        +order: int
    }

    class ViewPreset {
        +name: str
        +color_by: str
        +palette: str | dict
        +cmap: str
        +width_mode: str
        +width_by: str
        +width_scale: float
        +label_by: str
        +filter_expr: list
    }

    BasePrimitive <|-- Corridor
    BasePrimitive <|-- Channel
    BasePrimitive <|-- Demarcation
    BasePrimitive <|-- Patch
    BasePrimitive <|-- Glyph
    Corridor "1" o-- "0..*" Channel : contains
    Corridor "1" o-- "0..*" Demarcation : contains
```

---

## 3. Physical Casing & Geometry Anatomy View

This view illustrates how a single corridor polyline is geometrically sliced into three casing pieces using two cut numbers $(c_1, c_2)$.

```mermaid
flowchart LR
    subgraph NODE_U["Start Node u"]
        U_PT((Vertex 0))
    end

    subgraph PIECE_0["Piece 0: Start Head"]
        H_START["Casing Level: cs\nCap: round\nLength: cut_1 (h_start)"]
    end

    subgraph CUT_1["Cut Point 1"]
        C1["cut_1 = h_start"]
    end

    subgraph PIECE_1["Piece 1: Main Span"]
        MAIN["Casing Level: cm\nCap: butt (flat ends: __rs_cap=True)\nLength: cut_2 - cut_1"]
    end

    subgraph CUT_2["Cut Point 2"]
        C2["cut_2 = L - h_end"]
    end

    subgraph PIECE_2["Piece 2: End Head"]
        H_END["Casing Level: ce\nCap: round\nLength: L - cut_2 (h_end)"]
    end

    subgraph NODE_V["End Node v"]
        V_PT((Vertex -1))
    end

    U_PT --- H_START
    H_START --- C1
    C1 --- MAIN
    MAIN --- C2
    C2 --- H_END
    H_END --- V_PT

    subgraph SHORT["Short Road Handling (h_start + h_end >= L)"]
        SR_DESC["cut_1 = cut_2 = L * (h_start / (h_start + h_end))\nMain Span length = 0 (omitted)\nResult: Exactly 2 heads meeting at split point"]
    end
```

---

## 4. Single-Source Multi-Layer Runtime Architecture

This view contrasts the old v1 duplicate source architecture against the clean v2 Single-Source Multi-Layer pipeline.

```mermaid
flowchart TD
    subgraph V1["roadstyle v1 (Duplicate Data Problem)"]
        SRC_ROADS["Source: 'roads' (Contains road geometries)"]
        SRC_OV0["Source: 'ov0' (DUPLICATE copy of road geometries)"]
        L_CAS_V1["Layer: roads-casing"] --> SRC_ROADS
        L_FIL_V1["Layer: roads-fill (line-opacity: 0 phantom)"] --> SRC_ROADS
        L_OV_V1["Layer: overlay-fill"] --> SRC_OV0
    end

    subgraph V2["roadstyle v2 (Single-Source Architecture)"]
        SRC_CORR["Source: 'corridors' (Packaged ONCE)"]
        SRC_CAS["Source: 'casings' (Subdivided casing pieces)"]

        L_CAS_V2["Layer: casing-lv*"] --> SRC_CAS
        L_CAS_SQ["Layer: casing-lv*-sq (butt caps)"] --> SRC_CAS
        L_FIL_V2["Layer: fill-lv* (carriageway body)"] --> SRC_CORR
        L_ORD_V2["Layer: ordered-fill-lv*-o* (sub-level order)"] --> SRC_CORR
        L_HL["Layer: highlight (interactive selection)"] --> SRC_CORR
        L_LBL["Layer: labels (street names)"] --> SRC_CORR
    end

    style V1 fill:#ffebee,stroke:#c62828
    style V2 fill:#e8f5e9,stroke:#2e7d32
```

---

## 5. Client-Side Thematic Switching View (`ViewPreset`)

This view shows how multi-dimensional presets (Color, Width, Labels, Filters) are executed directly on the GPU in 0 milliseconds without re-requesting or re-parsing data.

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Dashboard
    participant UI as Preset Dropdown
    participant JS as Engine Runtime (applyPreset)
    participant GPU as MapLibre WebGL Shader

    User->>UI: Selects "Traffic Congestion"
    UI->>JS: Triggers applyPreset(preset)
    
    rect rgb(240, 248, 255)
        note over JS,GPU: 0ms GPU Shader Property Swaps (No Network Transfer)
        JS->>GPU: setPaintProperty("fill", "line-color", ["get", "_col_congestion"])
        JS->>GPU: setPaintProperty("fill", "line-width", ["get", "_width_aadt_flow"])
        JS->>GPU: setLayoutProperty("labels", "text-field", ["get", "speed_kmh"])
        JS->>GPU: setFilter("fill", ["<=", ["get", "v_over_c"], 1.5])
    end

    GPU-->>User: Immediate 60 FPS Visual Re-render
```

---

## 6. Multi-Domain Adapter Architecture

This view illustrates how diverse transport data standards map seamlessly into the universal primitives without requiring core engine changes.

```mermaid
flowchart LR
    subgraph OSM_IN["OpenStreetMap / DuckOSM"]
        OSM_WAY["highway=primary\nbridge=yes\nlayer=1\nlanes=4"]
    end

    subgraph GMNS_IN["GMNS / lanestyle"]
        GMNS_LINK["link.csv (Carriageway)\nlanes=3, width=10.5m"]
        GMNS_LANE["lane.csv (Individual Lanes)\nwidth=3.5m, is_connector=False"]
        GMNS_FILLET["Junction Corner Fillet Polygon"]
        GMNS_ARROW["Lane Movement Turn Arrows"]
    end

    subgraph ASAM_IN["OpenDRIVE / ASAM"]
        ASAM_REF["Reference Line & Elevation"]
        ASAM_SECTION["Lane Section Boundaries"]
        ASAM_ROADMARK["RoadMark Markings & Dashes"]
    end

    subgraph ENGINE["roadstyle v2 Core Primitives"]
        P_CORR["Corridor\n(LineString, width_m, casing_left/right)"]
        P_CHAN["Channel\n(LineString, width_m, order)"]
        P_DEM["Demarcation\n(LineString, stroke_px, dashes)"]
        P_PAT["Patch\n(Polygon, fillet fill)"]
        P_GLY["Glyph\n(Point, turn arrow symbol)"]
    end

    OSM_WAY ==>|"OSMAdapter"| P_CORR

    GMNS_LINK ==>|"GMNSAdapter"| P_CORR
    GMNS_LANE ==>|"GMNSAdapter"| P_CHAN
    GMNS_FILLET ==>|"GMNSAdapter"| P_PAT
    GMNS_ARROW ==>|"GMNSAdapter"| P_GLY

    ASAM_REF ==>|"ASAMAdapter"| P_CORR
    ASAM_SECTION ==>|"ASAMAdapter"| P_CHAN
    ASAM_ROADMARK ==>|"ASAMAdapter"| P_DEM
```
