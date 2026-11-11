"""Makes docs/samples/bridge-profile/granville_bridge_profile_today.json: the complete bridge profile that the engine itself writes for the roads of the Granville Bridge
(`rs.bridge_profile`, the curve `smooth`). It is real output of the engine, and the maker reads it again and makes the same pieces (tests/test_bridge_profile.py). Run it again after a change:

    python docs/img/bridge-height/granville_engine_profile.py

Compare it with granville_input_profile.json, the profile of the planned design (the heights are chosen, and the curve is `design`)."""
import sys
from pathlib import Path

import geopandas as gpd

import roadstyle as rs

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parents[1] / "samples" / "bridge-profile"
sys.path.insert(0, str(HERE))
from granville_input_profile import dump  # noqa: E402


def engine_profile():
    """The profile that the engine writes for the roads of docs/samples/bridge-profile/granville_bridge_edges.parquet."""
    return rs.bridge_profile(gpd.read_parquet(SAMPLES / "granville_bridge_edges.parquet"))


def main():
    profile = engine_profile()
    (SAMPLES / "granville_bridge_profile_today.json").write_text(dump(profile))
    g = profile["groups"][0]
    print(f"{len(profile['groups'])} group, {len(g['nodes'])} nodes ({sum(1 for n in g['nodes'] if n['kind'] == 'junction')} junctions), {len(g['chains'])} chains, top {g['chains'][0]['top_m']} m")


if __name__ == "__main__":
    main()
