//! The MapLibre Tile encoding: a tile that `mvt.rs` made, made again as MLT by the crate mlt-core, so both formats have the same
//! features (ids, order, properties, geometry). The settings are the ones MapLibre GL JS 5.24 reads: no shared dictionary (GL JS
//! refuses the tile); no FSST and no FastPFOR (the `web` profile: they lose bytes after gzip); no triangles (GL JS ignores them).
//! A property's type is the one that mlt-core infers from all values of the column (an integer and a float together: a float).

use crate::Error;
use mlt_core::encoder::{EncoderConfig, Network, Profile};

/// The MLT bytes of the MVT tile `mvt` (empty when `mvt` is empty).
pub(crate) fn from_mvt(mvt: &[u8]) -> Result<Vec<u8>, Error> {
    if mvt.is_empty() {
        return Ok(Vec::new());
    }
    let config = EncoderConfig::from_profile(Profile::Web(Network::default())).with_shared_dict(false);
    let err = |e: mlt_core::MltError| Error::Mlt(e.to_string());
    let mut out = Vec::new();
    for layer in mlt_core::mvt::mvt_to_tile_layers(mvt).map_err(err)? {
        out.extend(layer.encode(config).map_err(err)?);      // a tile's layers are repeated records: their bytes join
    }
    Ok(out)
}
