//! The dark theme of a live style (docs/design/dark_theme.md). The style holds the light colour of each layer and its dark one, and the global state
//! `rs_theme` ("light" or "dark": the dashboard's theme switch sets it) picks one, so the theme changes with no new style and no new tile. The dark colour is
//! the light one turned by the look's `dark` bands (roadstyle_look::sections::DarkLook): its lightness and saturation, the hue stays.
//!
//! What goes dark: the colours of the base map's layers (fills and 3D buildings: `area`; lines and outlines: `line`; points: `point`), the casing of the
//! roads (`casing`; the fill of a road keeps its colour) and the names and arrows (`label`). The selection colours stay. The textures of the land and the
//! icons of the points get a twin image `<name>-dark`, made with the same bands, and the layers pick the image by the theme.

use crate::Error;
use roadstyle_look::sections::{DarkBand, DarkLook};
use serde_json::{json, Map, Value};

/// The global state that the theme switch sets.
pub const STATE: &str = "rs_theme";

fn is_dark() -> Value {
    json!(["==", ["global-state", STATE], "dark"])
}

/// A colour text as channels (0 to 1) and its alpha: "#rrggbb", "#rgb", "rgb(r,g,b)" or "rgba(r,g,b,a)". A colour name is not read: a name in a style is a
/// label (a kind of land, a class).
fn read(c: &str) -> Option<([f64; 3], Option<f64>)> {
    if c.starts_with('#') {
        return roadstyle_look::color::hex_rgb(c).map(|v| (v.map(|x| f64::from(x) / 255.0), None));
    }
    let inner = c.strip_prefix("rgba(").or_else(|| c.strip_prefix("rgb("))?.strip_suffix(')')?;
    let n: Vec<f64> = inner.split(',').map(|x| x.trim().parse().ok()).collect::<Option<_>>()?;
    match n[..] {
        [r, g, b] => Some(([r / 255.0, g / 255.0, b / 255.0], None)),
        [r, g, b, a] => Some(([r / 255.0, g / 255.0, b / 255.0], Some(a))),
        _ => None,
    }
}

/// The colour `c` in the band: the same text form, the same alpha. None: `c` is not a colour.
pub fn darken(c: &str, band: &DarkBand) -> Option<String> {
    let (rgb, alpha) = read(c)?;
    let (h, l, s) = roadstyle_look::basemap::rgb_to_hls(rgb[0], rgb[1], rgb[2]);
    let l = band.lightness[0] + (band.lightness[1] - band.lightness[0]) * l;
    let out = roadstyle_look::basemap::hls_to_rgb(h, l.clamp(0.0, 1.0), (s * band.saturation).clamp(0.0, 1.0)).map(|x| (x * 255.0).round() as u8);
    Some(match alpha {
        None => roadstyle_look::color::hex(out),
        Some(a) => format!("rgba({},{},{},{a})", out[0], out[1], out[2]),
    })
}

/// An expression with each colour of it chosen by the theme: a colour text becomes `["case", dark, its dark colour, itself]`, and a literal list of colours
/// (a table that the expression looks up) the same for the whole list. `keep`: the colours that do not change (the selection's).
fn themed(e: &Value, band: &DarkBand, keep: &[String]) -> Value {
    match e {
        Value::String(s) if !keep.contains(s) => match darken(s, band) {
            Some(d) => json!(["case", is_dark(), d, s]),
            None => e.clone(),
        },
        Value::Array(a) if a.first().is_some_and(|f| f == "literal") => match a.get(1).and_then(Value::as_array) {
            Some(list) if !list.is_empty() && list.iter().all(|c| c.as_str().is_some_and(|c| read(c).is_some())) => {
                let dark: Vec<Value> = list.iter().map(|c| darken(c.as_str().unwrap_or_default(), band).map_or(c.clone(), Value::from)).collect();
                json!(["case", is_dark(), ["literal", dark], e])
            }
            _ => e.clone(),
        },
        Value::Array(a) => Value::Array(a.iter().map(|x| themed(x, band, keep)).collect()),
        _ => e.clone(),
    }
}

/// An expression with each name of a twin image chosen by the theme: `ms-pat-forest` becomes `["case", dark, "ms-pat-forest-dark", "ms-pat-forest"]`.
fn themed_image(e: &Value) -> Value {
    match e {
        Value::String(s) if s.starts_with("ms-pat-") || s.starts_with("ms-icon-") => json!(["case", is_dark(), format!("{s}-dark"), s]),
        Value::Array(a) => Value::Array(a.iter().map(themed_image).collect()),
        _ => e.clone(),
    }
}

/// The colour properties of a layer, with the kind of colour of each: by the layer's type, else the name's.
fn band_of<'a>(d: &'a DarkLook, ty: &str, prop: &str) -> Option<&'a DarkBand> {
    match prop {
        "text-color" | "text-halo-color" | "icon-color" | "icon-halo-color" => Some(&d.label),
        "fill-color" | "fill-outline-color" | "fill-extrusion-color" => Some(&d.area),
        "line-color" => Some(&d.line),
        "circle-color" | "circle-stroke-color" => Some(&d.point),
        _ => {
            let _ = ty;
            None
        }
    }
}

/// The road layer's colour: the casing goes dark, the fill of a road does not. The expression is `["let", "fill_colours", ..., "casing_colours", ..., body]`
/// (or the body alone): the casing table, and the branch of the body for the pieces of kind 0 (the casing), are themed.
fn road_colour(e: &Value, band: &DarkBand, keep: &[String]) -> Value {
    let (bindings, body) = match e.as_array() {
        Some(a) if a.first().is_some_and(|f| f == "let") && a.len() >= 3 => (&a[1..a.len() - 1], &a[a.len() - 1]),
        _ => (&[][..], e),
    };
    let casing = json!(["==", ["get", "__rs_k"], 0]);
    let body = match body.as_array() {
        Some(a) if a.first().is_some_and(|f| f == "case") => {
            let mut out = a.clone();
            let mut i = 1;
            while i + 1 < out.len() {
                if out[i] == casing {
                    out[i + 1] = themed(&out[i + 1], band, keep);
                }
                i += 2;
            }
            Value::Array(out)
        }
        _ => body.clone(),
    };
    if bindings.is_empty() {
        return body;
    }
    let mut out = vec![json!("let")];
    for pair in bindings.chunks(2) {
        out.push(pair[0].clone());
        out.push(if pair[0] == "casing_colours" { themed(&pair[1], band, keep) } else { pair[1].clone() });
    }
    out.push(body);
    Value::Array(out)
}

/// The dark colours of the layers of a style. `keep`: the colours that stay (the selection's).
pub fn layers(layers: &mut [Value], d: &DarkLook, keep: &[String]) {
    for l in layers.iter_mut() {
        let (id, ty) = (l["id"].as_str().unwrap_or_default().to_string(), l["type"].as_str().unwrap_or_default().to_string());
        if id.starts_with("roads-simple") && ty == "line" {
            if let Some(c) = l["paint"].get("line-color").cloned() {
                l["paint"]["line-color"] = road_colour(&c, &d.casing, keep);
            }
            continue;
        }
        if id.starts_with("roads-") && ty != "symbol" {
            continue;                                   // the other road layers (the glow, the pick layer, the decks) keep their colours
        }
        if let Some(paint) = l["paint"].as_object_mut() {
            for (prop, v) in paint.iter_mut() {
                if let Some(band) = band_of(d, &ty, prop) {
                    *v = themed(v, band, keep);
                } else if prop == "fill-pattern" {
                    *v = themed_image(v);
                }
            }
        }
        if let Some(icon) = l["layout"].get("icon-image").cloned() {
            l["layout"]["icon-image"] = themed_image(&icon);
        }
    }
}

/// The twin of an image of the style, in the dark bands: a texture (a PNG of one colour and its alpha) in the `area` band, an icon (an SVG with a `fill`) in
/// the `point` band. The twin is named `<name>-dark`.
fn twin(name: &str, v: &Value, d: &DarkLook) -> Result<Option<Value>, Error> {
    use base64::Engine;
    let b64 = base64::engine::general_purpose::STANDARD;
    let url = v.get("url").unwrap_or(v).as_str().unwrap_or_default();
    let Some((head, data)) = url.split_once(";base64,") else { return Ok(None) };
    let bytes = b64.decode(data).map_err(|e| Error::Data(format!("image {name}: {e}")))?;
    let dark = if name.starts_with("ms-pat-") {
        let (w, h, ch, px) = roadstyle_look::png_pixels(&bytes).map_err(|e| Error::Data(format!("image {name}: {e}")))?;
        let mut last: Option<([u8; 3], [u8; 3])> = None;
        let rgba: Vec<u8> = px.chunks(ch).flat_map(|p| {
            let c = if ch >= 3 { [p[0], p[1], p[2]] } else { [p[0]; 3] };
            let to = match last { Some((from, to)) if from == c => to, _ => {
                let out = darken(&roadstyle_look::color::hex(c), &d.area).and_then(|t| roadstyle_look::color::hex_rgb(&t)).unwrap_or(c);
                last = Some((c, out));
                out
            } };
            [to[0], to[1], to[2], p[ch - 1]]
        }).collect();
        b64.encode(roadstyle_look::png_rgba(w, h, &rgba))
    } else if name.starts_with("ms-icon-") {
        let svg = String::from_utf8(bytes).map_err(|e| Error::Data(format!("image {name}: {e}")))?;
        let Some(at) = svg.find("fill=\"").map(|i| i + 6) else { return Ok(None) };
        let end = at + svg[at..].find('"').unwrap_or(0);
        let Some(c) = darken(&svg[at..end], &d.point) else { return Ok(None) };
        b64.encode(format!("{}{c}{}", &svg[..at], &svg[end..]))
    } else {
        return Ok(None);
    };
    let url = format!("{head};base64,{dark}");
    Ok(Some(match v.as_object() {
        Some(o) => { let mut o = o.clone(); o.insert("url".into(), url.into()); Value::Object(o) }
        None => url.into(),
    }))
}

/// The twin of each texture and icon in `images`.
pub fn images(images: &mut Map<String, Value>, d: &DarkLook) -> Result<(), Error> {
    let mut twins = Vec::new();
    for (name, v) in images.iter() {
        if let Some(t) = twin(name, v, d)? {
            twins.push((format!("{name}-dark"), t));
        }
    }
    images.extend(twins);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn band(l0: f64, l1: f64, s: f64) -> DarkBand {
        DarkBand { lightness: [l0, l1], saturation: s }
    }

    #[test]
    fn a_light_colour_goes_dark_with_its_hue_and_a_label_turns_over() {
        let d = darken("#cdebb0", &band(0.10, 0.30, 0.85)).unwrap();
        let (_, l, _) = { let (c, _) = read(&d).unwrap(); roadstyle_look::basemap::rgb_to_hls(c[0], c[1], c[2]) };
        assert!(l < 0.31 && l > 0.2, "{d} {l}");
        assert_eq!(darken("rgba(0,0,0,0.25)", &band(0.9, 0.3, 1.0)).unwrap(), "rgba(230,230,230,0.25)");
        assert_eq!(darken("grass", &band(0.1, 0.3, 1.0)), None, "a name is not a colour");
    }

    #[test]
    fn an_expression_has_each_colour_chosen_by_the_theme_and_the_selection_stays() {
        let e = json!(["case", ["boolean", ["feature-state", "select"], false], "#7c4dff", "#aad3df"]);
        let t = themed(&e, &band(0.1, 0.3, 1.0), &["#7c4dff".to_string()]);
        assert_eq!(t[2], "#7c4dff");
        assert_eq!(t[3][0], "case");
        assert_eq!(t[3][3], "#aad3df");
        let table = themed(&json!(["literal", ["#ffffff", "#000000"]]), &band(0.1, 0.3, 1.0), &[]);
        assert_eq!(table[0], "case");
        assert_eq!(table[3], json!(["literal", ["#ffffff", "#000000"]]));
    }

    #[test]
    fn a_road_keeps_its_fill_and_its_casing_table_and_branch_go_dark() {
        let e = json!(["let", "fill_colours", ["literal", ["#ffffff"]], "casing_colours", ["literal", ["#bbbbbb"]],
                       ["case", ["==", ["get", "__rs_k"], 2], "rgba(0,0,0,0.25)", ["==", ["get", "__rs_k"], 0], "#64748b", "#ffffff"]]);
        let t = road_colour(&e, &band(0.12, 0.42, 0.85), &[]);
        assert_eq!(t[2], json!(["literal", ["#ffffff"]]), "the fills stay");
        assert_eq!(t[4][0], "case", "the casing table has a dark twin");
        let body = &t[5];
        assert_eq!(body[2], "rgba(0,0,0,0.25)");
        assert_eq!(body[4][0], "case");
        assert_eq!(body[5], "#ffffff", "the default (the fill) stays");
    }
}
