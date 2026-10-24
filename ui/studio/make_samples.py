"""The studio's sample networks as GeoParquet (samples/sodermalm_*.parquet, not in git): the engine reads only GeoParquet until it has a
GeoJSON reader (then the studio reads the GeoJSON samples and this file goes). Run it in the repository's root:

    python ui/studio/make_samples.py
"""
from pathlib import Path

import geopandas as gpd

here = Path(__file__).parent / "samples"
for mode in ("driving", "walking", "cycling"):
    g = gpd.read_file(here / f"sodermalm_{mode}.geojson")
    g.to_parquet(here / f"sodermalm_{mode}.parquet", index=False)
    print(f"samples/sodermalm_{mode}.parquet: {len(g)} edges")
