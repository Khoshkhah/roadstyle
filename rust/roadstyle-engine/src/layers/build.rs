use super::*;


/// The road layers of the style: what the page, the export and mapstyle's export make for simple mode with stored levels and
/// inline data (no base-map layers, no 3D decks, no metre widths, no items). `roads`, `simple`, `slots`: the features of the three sources.
/// What the page's controls read from the layers (contract.rs): the overlays' entries for the Layers box, each tunnel colour without the
/// tunnel look (_tunnel_look) and each fill layer's opacity without the road fill switch.
#[derive(Default)]
pub struct PageInfo {
    pub overlays: Vec<Value>,
    pub tunnel_layers: Map<String, Value>,
    pub tunnel_dash: Vec<String>,
    pub tunnel_casing: Map<String, Value>,
    pub fill_paint: Map<String, Value>,
    /// the dash patterns of the road layer's features (the pieces' and the items' `__rs_dash`), sorted: the page's simple-mode script
    pub dashes: Vec<String>,
}


/// The values that the layer builders share.
struct Ctx<'a> {
    look: &'a crate::Look,
    roads: &'a crate::road::Roads,
    /// the road layers read the class role's column by its own name in the table (the slots have their own "highway")
    hw: &'a str,
    /// render's width_m_col: metre widths from width_m_zoom on (docs/design/metre_widths.md)
    metres: bool,
    /// the roads have two-way pairs
    pairs: bool,
    any_tunnel: bool,
    any_dup: bool,
    /// audit N2: the pieces draw and pick, and the road table has the fields and the lines; only an export (an app with no road table)
    /// keeps the roads, with their pick and highlight layers, for its clicks
    export: bool,
    decks: bool,
    /// render's select_color / hover_color, else the theme's selection colours
    select: Value,
    hover: Value,
    /// the tests of a selected and a hovered road's feature state
    s_on: Value,
    h_on: Value,
    /// the minzoom of each class (the class filter)
    mz: Option<Map<String, Value>>,
    /// the road layer draws the class's fill and casing colours (by class index) of a piece that has none (`colors::Baked::class_only`)
    class_colours: bool,
    /// the road layer reads the fill and the casing colours of a piece as places in these tables (`colors::ColourTable`), bound as let variables
    places: Option<[Value; 2]>,
}

impl<'a> Ctx<'a> {
    fn new(look: &'a crate::Look, roads: &'a crate::road::Roads, decks: bool) -> Result<Self, crate::Error> {
        let s = &look.sections;
        let any_tunnel = roads.iter().any(|p| p.get(Mark::Tunnel.name()).is_some_and(crate::roads::yes));
        let tu = &s.tunnels;
        if any_tunnel && !tu.palettes.contains_key(&tu.palette) {        // render's check (the tunnel look)
            let names: Vec<String> = tu.palettes.keys().map(|k| format!("'{k}'")).collect();
            return Err(crate::error::options(format!("tunnel_palette '{}' is not in tunnel_palettes [{}]", tu.palette, names.join(", "))));
        }
        let pick = |c: &Option<roadstyle_look::color::Color>, theme: &roadstyle_look::color::Color| json!(c.as_ref().unwrap_or(theme).css());
        Ok(Ctx {
            look,
            roads,
            hw: roads.roles.name(&roads.table, roadstyle_model::Role::Class).unwrap_or(roadstyle_model::Role::Class.name()),
            metres: crate::roads::named(&look.map.columns.width_m).is_some(),
            pairs: roads.iter().any(|p| p.contains_key(Mark::Twin.name())),
            any_tunnel,
            any_dup: roads.iter().any(|p| p.get(Mark::Dup.name()).is_some_and(crate::roads::yes)),
            export: crate::export(look),
            decks,
            select: pick(&look.map.interaction.select_color, &s.selection.select),
            hover: pick(&look.map.interaction.hover_color, &s.selection.hover),
            s_on: json!(["boolean", ["feature-state", "select"], false]),
            h_on: json!(["boolean", ["feature-state", "hover"], false]),
            mz: class_minzoom(look),
            class_colours: false,
            places: None,
        })
    }

    fn fb_fill(&self) -> &Value {
        &self.look.sections.roads.fallback["fill"]
    }

    fn mz_filter(&self, col: &str) -> Option<Value> {
        self.mz.as_ref().map(|t| minzoom_filter(col, t))
    }

    fn casing_px(&self) -> Value {
        self.look.map.roads.casing_min_px.map_or_else(|| json!(self.look.sections.casing.min_px), crate::given)
    }
}

/// The test that a piece is of kind `n` (casing 0, fill 1, shadow 2, tunnel gap 3, tunnel dash 4, item 5).
fn piece_kind(n: i64) -> Value {
    json!(["==", ["get", Mark::PieceKind.name()], n])
}

/// The width and offset expressions of the road layers.
struct Widths {
    casing: Value,
    fill: Value,
    /// a bridge's casing: the width and two casings
    wings: Value,
    offset: Value,
    /// the offset of the road layer, with the items' own (metres)
    layer_offset: Value,
    /// the highlight's, as the full look made them
    fill0: Value,
    offset0: Value,
    /// the metre widths' first zoom, when the width is in metres
    metre_zoom: Option<f64>,
}

/// With `items` (the line items on the edges, `__rs_k` 5), every curve of the road layer is base-2 exponential, so theirs in metres is exact
/// at every zoom.
fn widths(cx: &Ctx, items: bool) -> Widths {
    let (m, s, mo) = (&cx.look.model, &cx.look.sections, &cx.look.map);
    let hw = cx.hw;
    let wmz = mo.width.m_zoom.map_or_else(|| json!(s.roads.width_m_zoom), crate::given);
    let wing = s.bridges.wing_scale.f();
    let offset = if cx.metres { m.offset_expr_m(hw, cx.pairs, &wmz) } else { m.offset_expr(hw, cx.pairs) };
    let (casing, fill, wings) = if cx.metres {
        let ml = MetreLook { wmz: wmz.clone(), bridge_m: json!(s.bridges.casing_m), bridge_px: json!(s.bridges.casing_px), casing_px: cx.casing_px(), wing_scale: wing };
        let mk = |k: &str| m.width_m_expr(hw, k, &ml);
        (mk("casing"), mk("fill"), mk("wings"))
    } else {
        (m.width_expr(hw, true, 1.0), m.width_expr(hw, false, 1.0), m.width_expr(hw, true, wing))
    };
    let (fill0, offset0) = (fill.clone(), offset.clone());
    let metre_zoom = if cx.metres { wmz.as_f64() } else { None };
    if !items {
        return Widths { casing, fill, wings, layer_offset: offset.clone(), offset, fill0, offset0, metre_zoom };
    }
    let exp = exp2(&offset);
    let layer_offset = by_feature(&[(piece_kind(5), metre_curve(&exp, Mark::ItemOffsetM.name()))], &exp);
    Widths { casing: exp2(&casing), fill: exp2(&fill), wings: exp2(&wings), offset, layer_offset, fill0, offset0, metre_zoom }
}

/// The filter of the road layer and the invisible roads-fill: the class minzoom, the casing drop, the seam, the decks' flat bridges and an
/// item's own minzoom.
fn road_filter(cx: &Ctx, items: &[&Props]) -> Value {
    let (m, s) = (&cx.look.model, &cx.look.sections);
    let mut flt = vec![json!("all")];
    flt.extend(cx.mz_filter(cx.hw));
    // casing.drop_below_px: the profile's 1.0 for a look made before the key (2026-10-25)
    let drop = s.casing.drop_below_px.as_ref().map_or(1.0, Num::f);
    flt.extend(casing_drop_filter(m, drop, cx.metres && cx.casing_px().as_f64().unwrap_or(0.0) >= drop));
    flt.push(seam_filter());
    // the 3D decks (view_3d): a bridge is the flat line below flat_below and the extruded deck from it up
    if cx.decks {
        flt.push(json!(["any", ["<", ["zoom"], cx.look.deck.flat_below], ["!", ["to-boolean", ["get", Mark::Bridge.name()]]]]));
    }
    if items.iter().any(|p| p.contains_key(Mark::ItemMinZoom.name())) {      // an item's own minzoom
        flt.push(json!(["any", ["!", ["has", Mark::ItemMinZoom.name()]], [">=", ["zoom"], ["get", Mark::ItemMinZoom.name()]]]));
    }
    Value::Array(flt)
}

/// The dash patterns of the road layer's features (the pieces' and the items'), sorted.
fn dash_patterns(cx: &Ctx, items: &[&Props]) -> Vec<String> {
    let roads = cx.roads.iter().filter_map(|p| p.get(Mark::Dash.name()).and_then(Cell::as_str));
    let items = items.iter().filter_map(|p| p.get(Mark::Dash.name()).and_then(Value::as_str));
    let mut dashes: Vec<String> = roads.chain(items).filter(|s| !s.is_empty()).map(String::from).collect();
    dashes.sort();
    dashes.dedup();
    dashes
}

/// The bridge ramp's two zooms and the position of a zoom on it (0 to 1).
fn bridge_ramp(cx: &Ctx) -> (Value, Value, impl Fn(&Value) -> f64) {
    let r = &cx.look.sections.bridges.ramp;
    let (r0, r1) = (r[0].f(), r[1].f());
    (json!(r[0]), json!(r[1]), move |z: &Value| ((z.as_f64().unwrap() - r0) / (r1 - r0)).clamp(0.0, 1.0))
}

/// The width curve of the road layer, by piece: the bridge's shadow and casing, the tunnel dashes, the casing, an item, else the fill.
fn width_curve(cx: &Ctx, w: &Widths, items: bool) -> Value {
    let (m, s) = (&cx.look.model, &cx.look.sections);
    let (is_c, is_sh, is_b) = (piece_kind(0), piece_kind(2), json!(["to-boolean", ["get", Mark::Bridge.name()]]));
    let (blur, extra) = (s.bridges.shadow.blur.f(), s.bridges.casing_extra.f());
    let (_, _, ramp) = bridge_ramp(cx);
    let bwide = plus_px(&w.wings, |z| json!(2.0 * extra * ramp(z)), None);
    let mut wide = vec![(is_sh, plus_px(&w.wings, |z| json!(2.0 * (extra + blur) * ramp(z)), None)), (json!(["all", is_c, is_b]), bwide)];
    if cx.any_tunnel {
        let px = json!(s.tunnels.dash_extra_px);
        wide.push((json!(["any", piece_kind(3), piece_kind(4)]), plus_px(&w.casing, |_| px.clone(), None)));
    }
    wide.push((is_c, w.casing.clone()));
    if items {     // 1 px over: two lanes side by side show no antialiased seam
        let px = json!(s.overlays.item_overlap_px);
        wide.push((piece_kind(5), plus_px(&metre_curve(&w.fill, Mark::ItemWidthM.name()), |_| px.clone(), None)));
    }
    let width = by_feature(&wide, &w.fill);
    if cx.pairs { m.pair_width(cx.hw, &width, w.metre_zoom) } else { width }
}

/// The width of the road layer: `width_curve` as one lookup of a row table (width_table.rs), else (a width that a feature's own value sets:
/// metres, items) the curve with the live factor at each stop.
fn line_width(cx: &Ctx, w: &Widths, items: bool) -> Value {
    let (curve, live) = (width_curve(cx, w, items), json!(["coalesce", ["feature-state", LIVE_WIDTH], 1]));
    width_table::table_form(&curve, cx.hw, &cx.look.model.classes, &live).unwrap_or_else(|| times_each_stop(&curve, &live))
}

/// _simple_color, with the glow of lean mode. R22 and audit N8 (2026-10-24), in every style: a road's colour (rsColor, rsColorBase,
/// rs.setData: the dashboard writes the one that wins) is the feature state on its row, over the baked fill of the active option; an item has
/// its road's row. The glow of a selected or hovered road is its pieces' feature state, by its row (promoteId).
fn line_color(cx: &Ctx, fills: &[String]) -> Value {
    let (s, fb_fill) = (&cx.look.sections, cx.fb_fill());
    let (s_on, h_on) = (&cx.s_on, &cx.h_on);
    let class_colour = |i: usize, fallback: &Value| class_table(cx, i, fallback);
    let own_fill = if cx.places.is_some() { fill_place(fills, FILL_TABLE) } else if cx.class_colours { json!(["coalesce", ["get", fills[0]], class_colour(0, fb_fill)]) } else { fill_base(fills, fb_fill) };
    let mut fill = json!(["coalesce", ["feature-state", LIVE_COLOR], own_fill]);
    let mut item = json!(["coalesce", ["feature-state", LIVE_COLOR], ["coalesce", ["get", Mark::ItemColor.name()], fb_fill]]);
    let is_b = json!(["to-boolean", ["get", Mark::Bridge.name()]]);
    let mut cases = vec![piece_kind(2), json!(s.bridges.shadow.color), piece_kind(0),
                         json!(["case", is_b, s.bridges.casing_color, casing_colour(cx, class_colour)])];
    if cx.any_tunnel {
        fill = tun_mix(&fill);
        item = tun_mix(&item);
        cases.extend([piece_kind(3), tun_gap(), piece_kind(4), tun_dash()]);
    }
    item = json!(["case", s_on, cx.select, h_on, cx.hover, item]);
    // the fill, or the fill mixed with the select or hover colour by the selection's opacity (the fill once, not three times)
    fill = json!(["interpolate", ["linear"], ["case", ["any", s_on, h_on], s.selection.opacity, 0], 0, fill, 1, ["case", s_on, cx.select, cx.hover]]);
    let mut color = vec![json!("case")];
    color.extend(cases);
    color.extend([piece_kind(5), item, fill]);
    match &cx.places {
        Some([f, c]) => json!(["let", FILL_TABLE, ["literal", f], CASING_TABLE, ["literal", c], Value::Array(color)]),
        None => Value::Array(color),
    }
}

/// The names of the let variables that hold the colour tables.
const FILL_TABLE: &str = "fill_colours";
const CASING_TABLE: &str = "casing_colours";

/// The casing colour of a piece that is not a bridge: its own (a place in the table, or the colour of its class), else the theme's.
fn casing_colour(cx: &Ctx, class_colour: impl Fn(usize, &Value) -> Value) -> Value {
    let fallback = &cx.look.sections.roads.fallback["casing"];
    if cx.places.is_some() {
        return json!(["case", ["has", Mark::Casing.name()], place_colour(json!(["get", Mark::Casing.name()]), CASING_TABLE), fallback]);
    }
    json!(["coalesce", ["get", Mark::Casing.name()], if cx.class_colours { class_colour(1, fallback) } else { fallback.clone() }])
}

/// The colour of a class (0: its fill, 1: its casing) as a table over the classes (`class_index` makes it one lookup by class index).
fn class_table(cx: &Ctx, i: usize, fallback: &Value) -> Value {
    let colours = crate::colors::ClassColours::of(&cx.look.road, &cx.look.model.classes);
    let mut m = vec![json!("match"), json!(["get", cx.hw])];
    for c in &cx.look.model.classes {
        m.extend([c.as_str().into(), colours.of_class(Some(c))[i].clone()]);
    }
    m.push(fallback.clone());
    json!(["to-color", Value::Array(m)])          // a lookup of texts: MapLibre wants the colour type here
}

/// The paint of the road layer, and the dash patterns of its features.
fn line_paint(cx: &Ctx, w: &Widths, items: &[&Props], fills: &[String]) -> (Value, Vec<String>) {
    let (m, s) = (&cx.look.model, &cx.look.sections);
    let dashes = dash_patterns(cx, items);
    let (is_sh, factor) = (piece_kind(2), json!(["coalesce", ["feature-state", LIVE_WIDTH], 1]));
    let op = json!(["case", ["all", ["!", gs("rs_fill_on")], piece_kind(1)], 0, 1]);
    let (r0v, r1v, _) = bridge_ramp(cx);
    let mut paint = Map::new();
    if !dashes.is_empty() || cx.any_tunnel {
        paint.insert("line-dasharray".into(), simple_dasharray(&dashes));
    }
    paint.insert("line-color".into(), line_color(cx, fills));
    paint.insert("line-width".into(), line_width(cx, w, !items.is_empty()));
    paint.insert("line-offset".into(), times_each_stop(&w.layer_offset, &factor));
    paint.insert("line-blur".into(), json!(["interpolate", ["linear"], ["zoom"], r0v, 0, r1v, ["case", is_sh, s.bridges.shadow.blur.f(), 0]]));
    paint.insert("line-opacity".into(), json!(["interpolate", ["linear"], ["zoom"], r0v, ["case", is_sh, 0, op], r1v, op]));
    let mut paint = Value::Object(paint);
    class_index(&mut paint, cx.hw, &m.classes);
    (paint, dashes)
}

/// roads-simple, the invisible roads-fill (the export's pick layer) and roads-highlight.
fn road_pick_highlight(cx: &Ctx, w: &Widths, flt: &Value, paint: Value) -> (Value, Value, Value) {
    let (s, fb_fill) = (&cx.look.sections, cx.fb_fill());
    let lay = json!({"line-cap": s.roads.cap, "line-join": s.roads.join, "line-sort-key": 0});
    let mut simple_layout = lay.as_object().unwrap().clone();
    simple_layout.insert("line-cap".into(), simple_cap());
    simple_layout.insert("line-sort-key".into(), json!(["+", ["*", ["get", Mark::Rank.name()], crate::simple::RANK_SHIFT as i64], ["id"]]));
    let road = json!({"id": "roads-simple", "type": "line", "source": "simple", "layout": simple_layout, "filter": flt, "paint": paint});
    let pick = json!({"id": "roads-fill", "type": "line", "source": "roads", "layout": lay, "filter": flt,
                      "paint": {"line-color": ["coalesce", ["get", Mark::Fill.name()], fb_fill], "line-width": w.fill, "line-offset": w.offset, "line-opacity": 0}});
    let mut highlight = json!({"id": "roads-highlight", "type": "line", "source": "roads", "layout": lay,
                               "paint": {"line-color": ["case", cx.s_on, cx.select, cx.hover],
                                         "line-opacity": ["case", ["any", cx.h_on, cx.s_on], s.selection.opacity, 0], "line-width": w.fill0, "line-offset": w.offset0}});
    if cx.decks {        // a bridge glows on its deck from flat_below up; in position mode the flat bridge layers do not exist
        highlight["filter"] = json!(["!", ["!", ["to-boolean", 1]]]);
    }
    (road, pick, highlight)
}

/// The base map's overlays, by where they go.
struct Overlays {
    under: Vec<Value>,
    over: Vec<Value>,
    /// the overlays on a street: fill number, order, overlay, layers
    edge: Vec<(i64, i64, usize, Vec<Value>)>,
    /// the layer ids of each overlay
    ids: Vec<Vec<String>>,
}

/// An overlay on edges: a copy of its layers for each (fill number, order), each with its own filter (position and order), which rsFilter keeps.
fn edge_layers(cx: &Ctx, ov: &mut Overlay, sid: &str, by_id: &HashMap<String, crate::road::Road>) -> Result<Vec<(i64, i64, Value, Vec<Value>)>, crate::Error> {
    let mut out = Vec::new();
    for (pos, order) in edge_overlay(ov, by_id)? {
        let flt = json!(["all", ["==", ["get", Mark::FillLevel.name()], pos], ["==", ["get", Mark::ItemOrder.name()], order]]);
        let drawn = crate::overlays::metre_items(ov);
        let mine = overlay_layers(sid, ov, cx.look).into_iter().map(|mut l| {
            l["id"] = format!("{}-lv{pos}-o{order}", l["id"].as_str().unwrap()).into();
            l["filter"] = flt.clone();
            if drawn {
                drawn_by_road_layer(cx, &mut l);
            }
            l
        }).collect();
        out.push((pos, order, flt, mine));
    }
    Ok(out)
}

/// A layer of items that the road layer draws: this layer is the pick and shows the hover / select highlight.
fn drawn_by_road_layer(cx: &Ctx, l: &mut Value) {
    let metres = |prop: &str| json!(["interpolate", ["exponential", 2], ["zoom"],
        0, ["*", ["get", prop], round_to(512.0 / 40075016.686, 6)], 22, ["*", ["get", prop], round_to(512.0 * 2f64.powi(22) / 40075016.686, 6)]]);
    l["layout"]["line-cap"] = json!("butt");
    let p = l["paint"].as_object_mut().unwrap();
    p.shift_remove("line-dasharray");
    p.insert("line-opacity".into(), json!(["case", ["any", cx.s_on, cx.h_on], 1, 0]));
    p.insert("line-width".into(), metres(Mark::ItemWidthM.name()));
    p.insert("line-offset".into(), metres(Mark::ItemOffsetM.name()));
}

/// _build_overlays' entry for the page (the Layers box, the popups, the hover and the select).
fn overlay_entry(ov: &Overlay, i: usize, sid: &str, ids: &[String], base: Map<String, Value>) -> Value {
    let u = ov.user.as_deref();
    let label = match u {
        None => ov.name.clone(),
        Some(u) => u.label.as_deref().filter(|l| !l.is_empty()).map_or_else(|| format!("Layer {}", i + 1), String::from),
    };
    let popup = u.and_then(|u| u.popup.as_ref());
    let list = |v: Option<&Vec<String>>| v.filter(|a| !a.is_empty()).map_or(Value::Null, |a| json!(a));
    let mut entry = json!({"label": label, "source": sid, "layers": ids, "hit": ids.first(), "visible": ov.visible, "color": ov.color,
        "popup": popup.map_or(Value::Null, |p| json!(p)),
        // render_map's interaction: a base-map layer's start popup and tooltip (the tooltip on: the popup's fields, else every field,
        // as the dashboard's rsSetInteraction)
        "popup_window": ov.popup_on.unwrap_or(u.is_none_or(|u| u.popup_window)),
        "tooltip": match ov.tooltip_on { Some(true) => Some(list(popup)).filter(|p| !p.is_null()).unwrap_or(json!(true)), Some(false) => Value::Null,
                                         None => list(u.and_then(|u| u.tooltip.as_ref())) }, "under": ov.under && !ov.edge,
        "base": if ov.edge { Value::Object(base) } else { Value::Null },
        "select": if u.is_some_and(|u| u.select == roadstyle_look::options::Select::Item) { "item" } else { "road" },
        "interactive": ov.clickable.unwrap_or(popup.is_none() || list(popup) != Value::Null)});
    if !ov.kinds.is_empty() {          // a base-map layer's kinds with their counts, most first (the page's kind filter)
        entry["kinds"] = json!(ov.kinds);
    }
    if crate::roads::yes(&ov.l["extrude"]) {    // its 3D layer (the dashboard's 3D button; a page's layers have no metadata)
        entry["extrude"] = ov_3d(i).into();
    }
    entry
}

/// The base map's overlays (_build_overlays): under the roads, over them, or on a street (_edge_overlay: one copy per fill number).
/// The page's entry of each goes into `info`.
fn base_overlays(cx: &Ctx, ovs: &mut [Overlay], info: &mut PageInfo) -> Result<Overlays, crate::Error> {
    let by_id: HashMap<String, crate::road::Road> = cx.roads.iter().filter_map(|p| p.role(roadstyle_model::Role::EdgeId).map(|e| (crate::overlays::eid(e), p))).collect();
    let mut out = Overlays { under: Vec::new(), over: Vec::new(), edge: Vec::new(), ids: Vec::new() };
    let layer_id = |l: &Value| l["id"].as_str().unwrap().to_string();
    for (i, ov) in ovs.iter_mut().enumerate() {
        let sid = format!("ov{i}");
        let mut ids: Vec<String> = Vec::new();
        let mut base = Map::new();
        if ov.edge {
            for (pos, order, flt, mine) in edge_layers(cx, ov, &sid, &by_id)? {
                ids.extend(mine.iter().map(layer_id));
                base.extend(mine.iter().map(|l| (layer_id(l), flt.clone())));
                out.edge.push((pos, order, i, mine));
            }
        } else {
            let ls = overlay_layers(&sid, ov, cx.look);
            ids.extend(ls.iter().map(layer_id));
            if ov.under { out.under.extend(ls) } else { out.over.extend(ls) }
        }
        info.overlays.push(overlay_entry(ov, i, &sid, &ids, base));
        out.ids.push(ids);
    }
    Ok(out)
}

/// The arrows and the names (simple mode: one layer each, above all roads, under the highlight).
fn slot_layers(cx: &Ctx) -> Vec<Value> {
    let (m, s) = (&cx.look.model, &cx.look.sections);
    let (arw, lbl) = (&s.arrows, &s.labels);
    let sort = json!(["*", -1, m.sort_key("highway")]);
    let minor = s.roads.flagged("minor");
    let minor_or = |mz: &Value| json!(["any", ["!", ["match", ["get", "highway"], minor, true, false]], [">=", ["zoom"], mz]]);
    let mut layers = Vec::new();
    if cx.look.map.arrows.on {
        let size = &arw.size;
        let mut icon = vec![json!("interpolate"), json!(["exponential", size["base"]]), json!(["zoom"])];
        for zb in size["stops"].as_array().into_iter().flatten() {
            icon.push(zb[0].clone());
            icon.push(json!(["*", zb[1], ["match", ["get", "highway"], minor, size["minor"], 1.0]]));
        }
        let mut spacing = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
        for zp in arw.spacing.as_array().into_iter().flatten() {
            spacing.extend(zp.as_array().unwrap().iter().cloned());
        }
        // the arrows along the slots; stage 3 chooses another kind (the inline page's points: Styled::page_arrows; the export's
        // line-center, below)
        let layout = json!({"symbol-placement": "line", "symbol-spacing": spacing, "icon-image": "oneway", "icon-rotation-alignment": "map",
                            "symbol-sort-key": sort, "icon-size": icon});
        layers.push(json!({"id": "roads-arrows", "type": "symbol", "source": "slots", "minzoom": arw.minzoom,
            "filter": with_minzoom(json!(["all", ["==", ["get", "oneway"], 1], true, minor_or(&json!(arw.minor_minzoom))]), cx.mz_filter("highway")),
            "layout": layout, "paint": {"icon-opacity": arw.opacity}}));
    }
    if cx.look.map.labels.on {
        let mut lf = vec![json!("all"), json!(["==", ["%", ["get", "slot"], 2], 0]), json!(["to-boolean", ["get", "name"]]), minor_or(&json!(lbl.minor_minzoom))];
        lf.extend(cx.mz_filter("highway"));      // a hidden class must not keep its street name floating either
        let fixed = lbl.size.as_ref().filter(|v| crate::roads::yes(v));
        if fixed.is_none() {
            lf.push(label_readable_filter(m, lbl));
        }
        let mut lpaint = json!({"text-color": lbl.color, "text-opacity": arw.opacity});
        if let Some(halo) = lbl.halo_color.as_ref().filter(|_| lbl.halo_width.f() != 0.0) {
            lpaint["text-halo-color"] = json!(halo);
            lpaint["text-halo-width"] = json!(lbl.halo_width);
        }
        layers.push(json!({"id": "roads-labels", "type": "symbol", "source": "slots", "minzoom": lbl.minzoom, "filter": Value::Array(lf),
            "layout": {"symbol-placement": "line-center", "text-field": ["get", "name"], "text-font": lbl.font,
                       "text-size": label_size_expr(m, lbl, fixed), "text-max-angle": lbl.max_angle, "text-padding": lbl.padding,
                       "symbol-sort-key": sort},
            "paint": lpaint}));
    }
    layers
}

/// The 3D decks' layers (view_3d): the casing slabs and the bridge decks.
fn deck_layers(cx: &Ctx) -> Vec<Value> {
    let (s, dk) = (&cx.look.sections, &cx.look.deck);
    let deck = |id: &str, flt: Value, color: Value| json!({"id": id, "type": "fill-extrusion", "source": "decks",
        "minzoom": dk.flat_below, "filter": flt, "paint": {"fill-extrusion-color": color, "fill-extrusion-base": ["get", Mark::DeckBase.name()],
        "fill-extrusion-height": ["get", Mark::DeckHeight.name()], "fill-extrusion-opacity": dk.opacity}});
    vec![
        deck("roads-deck-casing", json!(["has", Mark::CasingSlab.name()]), json!(s.bridges.casing_color)),
        deck("roads-bridge-decks", json!(["!", ["has", Mark::CasingSlab.name()]]),
             json!(["case", cx.s_on, cx.select, cx.h_on, cx.hover, ["coalesce", ["get", Mark::Fill.name()], cx.fb_fill()]])),
    ]
}

/// The passes: a reverse pair's second edge draws nowhere; the layers no feature can draw go.
fn prune(cx: &Ctx, simple: &crate::simple::SimpleSource, slots: &[Value], mut layers: Vec<Value>) -> Vec<Value> {
    if cx.any_dup {
        let nd = json!(["!", ["to-boolean", ["get", Mark::Dup.name()]]]);
        for l in layers.iter_mut().filter(|l| l["source"] == "roads") {
            l["filter"] = match l.get("filter") { Some(f) => json!(["all", f, nd]), None => nd.clone() };
        }
    }
    let empty = Map::new();
    let road_views: Vec<crate::road::Road> = cx.roads.iter().collect();
    let rd: Vec<&dyn Get> = road_views.iter().map(|p| p as &dyn Get).collect();
    let simple_feats = simple.gets(cx.roads);
    let sd: Vec<&dyn Get> = simple_feats.iter().map(|p| p as &dyn Get).collect();
    let ld: Vec<&dyn Get> = props_of(slots, &empty).iter().map(|p| *p as &dyn Get).collect();
    let feats: HashMap<&str, Vec<&dyn Get>> = [("roads", rd), ("slots", ld.clone()), ("arrows", ld), ("simple", sd)].into();
    drop_empty_layers(layers, &feats)
}

/// The road fill switch: each fill layer's opacity (the end caps' fills too) goes to 0 when it is off. `info` keeps the opacity without it.
fn fill_switch(layers: &mut [Value], info: &mut PageInfo) {
    for l in layers.iter_mut() {
        let lid = l["id"].as_str().unwrap_or("").to_string();
        let keys: &[&str] = if lid.starts_with("roads-fill") && !lid.ends_with("-pat") { &["line-opacity"] }
                            else if lid.starts_with("roads-ends-fill") { &["circle-opacity", "circle-stroke-opacity"] } else { continue };
        let mut rec = Map::new();
        for k in keys {
            let v = l["paint"].get(*k).cloned().unwrap_or(Value::Null);
            rec.insert(k.to_string(), v.clone());
            l["paint"][*k] = json!(["case", gs("rs_fill_on"), if v.is_null() { json!(1) } else { v }, 0]);
        }
        info.fill_paint.insert(lid, Value::Object(rec));
    }
}

/// The overlays on a street go between the road layer and the arrows, by fill number, order and overlay; the ones over the roads go on top.
/// The ids of the street ones are returned.
fn place_overlays(layers: &mut Vec<Value>, mut edge: Vec<(i64, i64, usize, Vec<Value>)>, over: Vec<Value>) -> HashSet<String> {
    edge.sort_by_key(|e| (e.0, e.1, e.2));
    let edge_ids: HashSet<String> = edge.iter().flat_map(|e| e.3.iter().map(|l| l["id"].as_str().unwrap().to_string())).collect();
    if !edge.is_empty() {
        let at = layers.iter().position(|l| matches!(l["id"].as_str(), Some("roads-arrows" | "roads-labels" | "roads-highlight"))).unwrap_or(layers.len());
        let items: Vec<Value> = edge.into_iter().flat_map(|e| e.3).collect();
        layers.splice(at..at, items);
    }
    layers.extend(over);
    edge_ids
}

/// _state_expressions (audit N8): the pick layer's colour is the active option's; a painted road sorts on top by the ids that rsColor
/// painted (the state rs_top: layout reads no feature state).
fn state_expressions(cx: &Ctx, layers: &mut [Value], fills: &[String]) {
    let fb_fill = cx.fb_fill();
    let base = json!(["coalesce", ["get", Mark::Fill.name()], fb_fill]);
    let top = json!(["in", ["id"], gs("rs_top")]);
    // the road fill layers (_fill_layer_ids: in simple mode the export's pick layer roads-fill) and their dashed fills
    const FILLS: [&str; 6] = ["roads-fill", "roads-fill-sq", "roads-fill-sx", "roads-fill-h", "roads-fill-hsq", "roads-fill-hsx"];
    let is_fill = |lid: &str| FILLS.contains(&lid) || FILLS.iter().any(|b| lid.starts_with(&format!("{b}-dash")));
    for l in layers.iter_mut() {
        if l["id"].as_str().is_some_and(is_fill) {
            l["paint"]["line-color"] = swap(&l["paint"]["line-color"], &base, &fill_base(fills, fb_fill));
        } else if l["id"] == "roads-bridge-decks" {
            l["paint"]["fill-extrusion-color"] = swap(&l["paint"]["fill-extrusion-color"], &base, &fill_base(fills, fb_fill));
        }
        if l["type"] == "line" && l["layout"].get("line-sort-key").is_some_and(|v| !v.is_null()) {
            let key = l["layout"]["line-sort-key"].clone();
            if l["source"] == "roads" {
                l["layout"]["line-sort-key"] = json!(["+", key, ["case", top, 500, 0]]);
            } else if l["id"] == "roads-simple" {
                l["layout"]["line-sort-key"] = json!(["+", key, ["case", ["all", ["any", piece_kind(1), piece_kind(5)], top], (0.5 * crate::simple::RANK_UNIT * crate::simple::RANK_SHIFT) as i64, 0]]);
            }
        }
    }
}

/// An overlay's colours set by rsColor (state rs_ov_<i>).
fn overlay_colours(layers: &mut [Value], ov_ids: &[Vec<String>]) {
    for (i, ids) in ov_ids.iter().enumerate() {
        for l in layers.iter_mut().filter(|l| l["id"].as_str().is_some_and(|x| ids.iter().any(|y| y == x))) {
            let t = l["type"].as_str().unwrap_or("").to_string();
            if matches!(t.as_str(), "line" | "fill" | "circle") {
                let k = format!("{t}-color");
                if let Some(c) = l["paint"].get(&k).cloned() {
                    l["paint"][&k] = json!(["coalesce", ["get", ["to-string", ["id"]], gs(&format!("rs_ov_{i}"))], c]);
                }
            }
        }
    }
}

/// _tunnel_look: everything on a tunnel moves toward the tunnel colour. `info` keeps the colours without it (the page's record:
/// [paint property, its colour without the look, "fill"]).
fn tunnel_look(cx: &Ctx, layers: &mut [Value], edge_ids: &HashSet<String>, info: &mut PageInfo) {
    let arw = &cx.look.sections.arrows;
    for l in layers.iter_mut().filter(|l| matches!(l["source"].as_str(), Some("roads" | "slots" | "arrows"))
                                        || l["id"].as_str().is_some_and(|i| edge_ids.contains(i))) {
        let id = l["id"].as_str().unwrap_or("").to_string();
        let mut mix = |l: &mut Value, k: &str, base: Value| {
            l["paint"][k] = tun_mix(&base);
            info.tunnel_layers.entry(id.clone()).or_insert_with(|| json!([])).as_array_mut().unwrap().push(json!([k, base, "fill"]));
        };
        if id.starts_with("roads-fill") && !id.ends_with("-pat") {
            let b = l["paint"]["line-color"].clone();
            mix(l, "line-color", b);
        } else if id.starts_with("roads-labels") {
            let b = l["paint"]["text-color"].clone();
            mix(l, "text-color", b);
        } else if id.starts_with("roads-arrows") {
            mix(l, "icon-color", json!(arw.color));
        } else if edge_ids.contains(&id) {
            for k in ["fill-color", "line-color", "circle-color", "text-color"] {
                if let Some(c) = l["paint"].get(k).cloned() {
                    mix(l, k, c);
                }
            }
        }
    }
}

/// The export: the state baked (a live page keeps it); fewer arrows, one in the middle of its slot; each layer's group (_tag_groups: its
/// overlay's label, else "roads").
fn finish(cx: &Ctx, layers: Vec<Value>, state: &Map<String, Value>, ovs: &[Overlay]) -> Vec<Value> {
    let arw = &cx.look.sections.arrows;
    let live = cx.look.map.output.state == roadstyle_look::options::State::Live;
    let main: Vec<String> = arw.main.iter().flat_map(|h| [h.to_string(), format!("{h}_link")]).collect();
    let mut out = Vec::new();
    for l in layers {
        let mut l = l.as_object().unwrap().clone();
        for k in ["paint", "layout", "filter"].into_iter().filter(|_| !live) {
            if let Some(v) = l.get(k) {
                let b = bake(v, state);
                l.insert(k.into(), b);
            }
        }
        if cx.export && l["id"].as_str().is_some_and(|i| i.starts_with("roads-arrows")) {
            if l["paint"].get("icon-color").is_none() {
                l["paint"]["icon-color"] = json!(arw.color);
            }
            l["filter"] = json!(["all", l["filter"], ["has", Mark::SlotArrow.name()], ["any", ["match", ["get", "highway"], main, true, false], [">=", ["zoom"], arw.main_below]],
                                 ["==", ["%", ["get", Mark::SlotArrow.name()], ["step", ["zoom"], 4, 16, 2, 17, 1]], 0]]);
            let lay = l["layout"].as_object_mut().unwrap();
            lay.shift_remove("symbol-spacing");
            lay.insert("symbol-placement".into(), "line-center".into());
        }
        let group = l["source"].as_str().and_then(|s| s.strip_prefix("ov")).and_then(|n| n.parse::<usize>().ok())
            .and_then(|i| ovs.get(i)).map_or("roads".to_string(), |ov| ov.name.clone());
        let meta = l.entry("metadata").or_insert_with(|| json!({}));
        meta["roadstyle:group"] = group.into();
        out.push(Value::Object(l));
    }
    out
}

#[allow(clippy::too_many_arguments)] // the sources of the style, as make_parts has them
pub fn road_layers(look: &crate::Look, roads: &crate::road::Roads, simple: &crate::simple::SimpleSource, slots: &[Value], decks: bool, ovs: &mut [Overlay], fills: &[String], active: usize)
                   -> Result<(Vec<Value>, PageInfo), crate::Error> {
    let mut info = PageInfo::default();
    let mut cx = Ctx::new(look, roads, decks)?;
    cx.class_colours = simple.class_colours.is_some() && fills.len() == 1;
    cx.places = simple.colours.as_ref().map(|t| [json!(t.fill.list), json!(t.casing.list)]);
    let items: Vec<&Props> = simple.items.iter().map(|(_, it)| &it.props).filter(|p| p.get(Mark::PieceKind.name()) == Some(&json!(5))).collect();
    let w = widths(&cx, !items.is_empty());
    let flt = road_filter(&cx, &items);
    let (paint, dashes) = line_paint(&cx, &w, &items, fills);
    info.dashes = dashes;
    let (road, pick, highlight) = road_pick_highlight(&cx, &w, &flt, paint);
    let ov = base_overlays(&cx, ovs, &mut info)?;
    let mut layers = ov.under;
    layers.push(road);
    if cx.export {
        layers.push(pick);
    }
    if !slots.is_empty() {
        layers.extend(slot_layers(&cx));
    }
    if cx.export {
        layers.push(highlight);
    }
    if decks {
        layers.extend(deck_layers(&cx));
    }
    let mut layers = prune(&cx, simple, slots, layers);
    fill_switch(&mut layers, &mut info);
    let edge_ids = place_overlays(&mut layers, ov.edge, ov.over);
    state_expressions(&cx, &mut layers, fills);
    overlay_colours(&mut layers, &ov.ids);
    if cx.any_tunnel {
        tunnel_look(&cx, &mut layers, &edge_ids, &mut info);
    }
    let state = crate::contract::page_state(look, active, ovs.len());       // the page's start values, baked in `finish`
    let out = finish(&cx, layers, &state, ovs);
    Ok((if ovs.is_empty() { out } else { restyle(out, ovs) }, info))
}

#[cfg(test)]
#[path = "width_tests.rs"]
mod width_tests;
