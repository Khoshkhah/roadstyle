//! The look's colours (review D4): one reader for every colour of the look, and the mixes. A colour is "#rrggbb", "#rgb" (the CSS
//! short form) or a CSS colour name; any other text is an error that names it.

use crate::Error;

/// The channels of a hex colour, "#rrggbb" or "#rgb" (any case); None for any other text. A theme's values are read with this one (a
/// font's name could be a colour name).
pub fn hex_rgb(c: &str) -> Option<[u8; 3]> {
    let h = c.strip_prefix('#').filter(|h| h.bytes().all(|b| b.is_ascii_hexdigit()))?;
    let at = |s: &str| u8::from_str_radix(s, 16).ok();
    match h.len() {
        6 => Some([at(&h[0..2])?, at(&h[2..4])?, at(&h[4..6])?]),
        3 => Some([0, 1, 2].map(|i| at(&h[i..i + 1]).map_or(0, |d| d * 17))),
        _ => None,
    }
}

/// The channels of a colour: a hex colour or a CSS colour name (any case, data/cmaps.json's names); None for any other text.
pub fn rgb(c: &str) -> Option<[u8; 3]> {
    hex_rgb(c).or_else(|| crate::ramp::css(&c.to_lowercase()).and_then(hex_rgb))
}

/// As `rgb`, with an error that names the colour.
pub fn parse(c: &str) -> Result<[u8; 3], Error> {
    rgb(c).ok_or_else(|| Error::Unknown(format!("{c:?} is not a colour: give \"#rrggbb\", \"#rgb\" or a colour name")))
}

/// "#rrggbb" of the channels.
pub fn hex(c: [u8; 3]) -> String {
    format!("#{:02x}{:02x}{:02x}", c[0], c[1], c[2])
}

/// A colour of the options or the look: the channels of "#rrggbb", "#rgb" or a CSS colour name (written "#rrggbb"), or a colour that
/// MapLibre reads and this type does not (`rgb(...)`, `rgba(...)`, `hsl(...)`, `hsla(...)`), kept as its text so that no value is lost.
/// Any other text is an error that names it.
/// It keeps its text as given (a look of version 1 that goes to version 2 and back gives the same text); two colours with channels are
/// the same when their channels are.
#[derive(Clone, Debug)]
pub struct Color {
    text: String,
    rgb: Option<[u8; 3]>,
}

impl Color {
    /// The colour of a text, or an error that names it.
    pub fn parse(c: &str) -> Result<Color, Error> {
        if ["rgb(", "rgba(", "hsl(", "hsla("].iter().any(|f| c.trim_start().to_lowercase().starts_with(f)) {
            return Ok(Color { text: c.to_string(), rgb: None });
        }
        Ok(Color { text: c.to_string(), rgb: Some(parse(c)?) })
    }

    /// The colour as MapLibre reads it: the text as given.
    pub fn css(&self) -> &str {
        &self.text
    }

    /// The channels; none for a MapLibre colour text (`rgba(...)`).
    pub fn rgb(&self) -> Option<[u8; 3]> {
        self.rgb
    }
}

impl PartialEq for Color {
    fn eq(&self, o: &Color) -> bool {
        match (self.rgb, o.rgb) {
            (Some(a), Some(b)) => a == b,
            _ => self.text == o.text,
        }
    }
}

impl serde::Serialize for Color {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.text)
    }
}

impl schemars::JsonSchema for Color {
    fn schema_name() -> std::borrow::Cow<'static, str> {
        "Color".into()
    }
    fn json_schema(_: &mut schemars::SchemaGenerator) -> schemars::Schema {
        schemars::json_schema!({"type": "string", "description": "\"#rrggbb\", \"#rgb\", a CSS colour name, or rgb(...), rgba(...), hsl(...), hsla(...)"})
    }
}

impl<'de> serde::Deserialize<'de> for Color {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Color, D::Error> {
        let t = String::deserialize(d)?;
        Color::parse(&t).map_err(serde::de::Error::custom)
    }
}

/// `a` moved `t` of the way to `b` (0: a, 1: b), each channel rounded half up.
pub fn mix(a: [u8; 3], b: [u8; 3], t: f64) -> [u8; 3] {
    [0, 1, 2].map(|i| (a[i] as f64 * (1.0 - t) + b[i] as f64 * t + 0.5).clamp(0.0, 255.0) as u8)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_forms_of_a_colour() {
        assert_eq!(rgb("#ffffff"), Some([255, 255, 255]));
        assert_eq!(rgb("#fff"), Some([255, 255, 255]), "the short form");
        assert_eq!(rgb("#FfA500"), Some([255, 165, 0]), "any case");
        assert_eq!(rgb("red"), Some([255, 0, 0]), "a colour name");
        assert_eq!(hex_rgb("red"), None, "a theme value: hex only");
        for bad in ["#zzz", "", "#ffff", "fff", "#ff ff f"] {
            assert_eq!(rgb(bad), None, "{bad:?}");
        }
        assert_eq!(parse("#zzz").unwrap_err().to_string(), "\"#zzz\" is not a colour: give \"#rrggbb\", \"#rgb\" or a colour name");
        assert_eq!(hex(mix([0, 0, 0], [255, 255, 255], 0.5)), "#808080", "127.5: half up");
        assert_eq!(hex(mix(rgb("#e892a2").unwrap(), [255; 3], 0.3)), "#efb3be");
    }

    #[test]
    fn a_colour_value() {
        assert_eq!(serde_json::from_str::<Color>("\"Red\"").unwrap().rgb(), Some([255, 0, 0]));
        assert_eq!(serde_json::to_string(&Color::parse("#abc").unwrap()).unwrap(), "\"#abc\"", "the text as given");
        assert_eq!(Color::parse("#abc").unwrap(), Color::parse("#AABBCC").unwrap(), "the same channels");
        let t = Color::parse("rgba(0, 0, 0, 0.5)").unwrap();
        assert_eq!((t.css(), t.rgb(), serde_json::to_string(&t).unwrap()), ("rgba(0, 0, 0, 0.5)", None, "\"rgba(0, 0, 0, 0.5)\"".into()));
        assert!(serde_json::from_str::<Color>("\"#zzz\"").unwrap_err().to_string().starts_with("\"#zzz\" is not a colour"));
    }
}
