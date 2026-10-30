//! The dash layer of the road layer (docs/design/tile_speed.md, "Dash layers"). MapLibre looks up a dash pattern for each feature of a layer
//! that has `line-dasharray`, so only the dashed pieces have it, in a layer of their own.
//!
//! A road layer has no `minzoom` and no `maxzoom` (docs/design/tiling.md): the worker builds the buckets of a tile only for the layers of the
//! tile's zoom, and MapLibre keeps the tiles of the old zoom on the screen until the new ones come, so a layer with a zoom range leaves the
//! map empty while the new tiles load.

use super::*;

/// The pieces that the dash layer draws: a tunnel's gap and dashes (`__rs_k` 3 and 4) and a piece with its own pattern (`__rs_dash`).
fn dashed() -> Value {
    json!(["any", ["==", ["get", Mark::PieceKind.name()], 3], ["==", ["get", Mark::PieceKind.name()], 4], ["to-boolean", ["get", Mark::Dash.name()]]])
}

/// A layer with `line-dasharray` as two layers: a layer of the dashed pieces (`<id>-dash`) with the dash, and the layer of all other pieces
/// with none. MapLibre looks up a dash pattern for each feature of a layer that has the property, and the patterns of the solid pieces are the
/// cost. The dash layer is under the other layer: a tunnel is under the roads that cross it, and under its own fill, as its pieces are in
/// rank. A dashed piece is then under every piece of the other layer, not between them in rank.
pub(super) fn split_dash(layer: Value) -> Vec<Value> {
    if layer["paint"].get("line-dasharray").is_none() {
        return vec![layer];
    }
    let with = |flt: Value| json!(["all", layer["filter"].clone(), flt]);
    let (mut solid, mut dash) = (layer.clone(), layer.clone());
    solid["paint"].as_object_mut().unwrap().shift_remove("line-dasharray");
    solid["filter"] = with(json!(["!", dashed()]));
    dash["id"] = format!("{}-dash", layer["id"].as_str().unwrap()).into();
    dash["filter"] = with(dashed());
    vec![dash, solid]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::layers::eval::{ev, to_boolean, Ev};

    #[test]
    fn the_dash_is_in_a_layer_of_the_dashed_pieces() {
        let one = json!({"id": "roads-simple", "filter": ["all", true], "paint": {"line-width": 3, "line-dasharray": ["literal", [1, 1]]}});
        let two = split_dash(one.clone());
        assert_eq!(two.iter().map(|l| l["id"].as_str().unwrap()).collect::<Vec<_>>(), ["roads-simple-dash", "roads-simple"], "the dash layer is under");
        assert!(two[1]["paint"].get("line-dasharray").is_none() && two[0]["paint"].get("line-dasharray").is_some());
        let shows = |l: &Value, p: Value| matches!(ev(&l["filter"], p.as_object().unwrap()), Ev::V(v) if to_boolean(&v));
        let (k, dash) = (Mark::PieceKind.name(), Mark::Dash.name());
        let pieces = [json!({k: 0}), json!({k: 1}), json!({k: 3}), json!({k: 4}), json!({k: 1, dash: "2,2"}), json!({k: 0, dash: ""})];
        let in_dash: Vec<bool> = pieces.iter().map(|p| shows(&two[0], p.clone())).collect();
        assert_eq!(in_dash, [false, false, true, true, true, false], "the tunnel gaps and dashes and the pieces with a pattern");
        assert!(pieces.iter().all(|p| shows(&two[0], p.clone()) != shows(&two[1], p.clone())), "each piece is in one layer");
        assert_eq!(split_dash(json!({"id": "a", "paint": {}})).len(), 1);
    }
}
