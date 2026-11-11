"""The two JSON Schemas of the bridge profile (docs/reference/formats.md, "The bridge profile (planned)"). One source makes both files in docs/samples/bridge-profile/:

    bridge_profile_input.schema.json      the input profile: every value is optional (an empty profile is valid)
    bridge_profile_complete.schema.json   the complete input profile that Part 1 writes and Part 2 reads: every value that Part 2 needs is required

A schema checks the form. It cannot check the rules that need the roads (a node must be within 5 m of exactly one node of the group, a grade between two heights, the order of the points): the reference
lists them, and the engine checks them. Run it again after a change of the format:

    python docs/img/bridge-height/bridge_profile_schema.py"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parents[1] / "samples" / "bridge-profile"
SITE = "https://khoshkhah.github.io/roadstyle/samples/bridge-profile/"
FORMAT = "roadstyle.bridge_profile/1"


def _defs(complete):
    """The definitions. In the complete form, the keys that Part 2 needs are required."""
    def obj(properties, required=(), any_of=None):
        out = {"type": "object", "additionalProperties": False, "properties": properties}
        if required:
            out["required"] = list(required)
        if any_of:
            out["anyOf"] = any_of
        return out

    mark = {"source": {"type": "string", "description": "Where the value comes from: data, rule, given, example, a survey..."},
            "method": {"enum": ["mapped", "measured", "derived", "chosen"], "description": "How it was found"}}
    node = {"id": {"type": "string", "pattern": "^n[0-9]+$", "description": "The id of the node in a complete profile"},
            "lonlat": {"$ref": "#/$defs/lonlat", "description": "The position of the node. In a partial input it names the node: the node of the group within 5 m"},
            "kind": {"enum": ["ground", "junction"], "description": "ground: one chain ends here, height 0. junction: chains meet here"},
            "chains": {"type": "array", "items": {"type": "string", "pattern": "^c[0-9]+$"}, "description": "The chains that meet at the node"},
            "z_m": {"type": "number", "minimum": 0, "description": "The height of the node above the ground, in metres"}, **mark}
    chain = {"id": {"type": "string", "pattern": "^c[0-9]+$"},
             "osm_ways": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "description": "The OSM ways of the chain. In a partial input they name the chain"},
             "length_m": {"type": "number", "exclusiveMinimum": 0},
             "from": {"type": "string", "pattern": "^n[0-9]+$", "description": "The node at the first end of the chain"},
             "to": {"type": "string", "pattern": "^n[0-9]+$", "description": "The node at the last end of the chain"},
             "points": {"type": "array", "items": {"$ref": "#/$defs/point"}, "description": "Interior control points, in order of s"},
             "width_m": {"type": "number", "exclusiveMinimum": 0, "description": "The width of the deck, in metres"},
             "width_source": {"type": "string"}}
    return {
        "lonlat": {"type": "array", "prefixItems": [{"type": "number", "minimum": -180, "maximum": 180}, {"type": "number", "minimum": -90, "maximum": 90}], "items": False, "minItems": 2},
        "point": obj({"s": {"type": "number", "minimum": 0, "description": "Metres from the first end of the chain"},
                      "z_m": {"type": "number", "minimum": 0}, **mark}, required=("s", "z_m")),
        "parameters": obj({"design_speed_kmh": {"type": "number", "exclusiveMinimum": 0, "maximum": 200}, "design_grade": {"type": "number", "exclusiveMinimum": 0, "maximum": 0.3},
                           "curve": {"enum": ["smooth", "design"], "description": "smooth: the curve of today. design: straight grades and vertical curves"}},
                          required=("design_speed_kmh", "design_grade") if complete else ()),
        "node": obj(node, required=("id", "lonlat", "kind", "chains", "z_m", "source", "method") if complete else (), any_of=None if complete else [{"required": ["lonlat"]}, {"required": ["id"]}]),
        "chain": obj(chain, required=("id", "osm_ways", "length_m", "from", "to", "points", "width_m", "width_source") if complete else (), any_of=None if complete else [{"required": ["osm_ways"]}, {"required": ["id"]}]),
        "group": obj({"name": {"type": "string"}, "nodes": {"type": "array", "items": {"$ref": "#/$defs/node"}}, "chains": {"type": "array", "items": {"$ref": "#/$defs/chain"}}},
                     required=("name", "nodes", "chains") if complete else ()),
    }


def schema(complete):
    """The schema of the complete profile (`complete`) or of the input profile (every value optional)."""
    name = "bridge_profile_complete" if complete else "bridge_profile_input"
    props = {"format": {"const": FORMAT}, "parameters": {"$ref": "#/$defs/parameters"}, "groups": {"type": "array", "items": {"$ref": "#/$defs/group"}, **({"minItems": 1} if complete else {})}}
    out = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"{SITE}{name}.schema.json",
           "title": ("The complete input profile of a group of 3D bridges: what Part 1 writes and Part 2 reads (planned)" if complete
                     else "The input profile of a group of 3D bridges: every value is optional (planned)"),
           "type": "object", "additionalProperties": False, "properties": props, "$defs": _defs(complete)}
    if complete:
        out["required"] = ["format", "parameters", "groups"]
    return out


def main():
    for complete in (False, True):
        name = "bridge_profile_complete" if complete else "bridge_profile_input"
        (SAMPLES / f"{name}.schema.json").write_text(json.dumps(schema(complete), indent=1) + "\n")
        print("wrote", SAMPLES / f"{name}.schema.json")


if __name__ == "__main__":
    main()
