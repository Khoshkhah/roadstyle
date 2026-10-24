"""The road table of a page (the page part static/page/side.html: one row for each road), as a FeatureCollection of the roads: each road's
properties and its line. A page in simple mode has no roads source; its fields and lines are in this table."""
import base64
import gzip
import json
import re


def roads_of(html):
    """The roads of the page's road table, or None when the page has no table."""
    m = re.search(r'id="rs-side" type="application/json">([A-Za-z0-9+/=]+)<', html)
    if not m:
        return None
    t = json.loads(gzip.decompress(base64.b64decode(m.group(1))))
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": p, "geometry": c and {"type": "LineString", "coordinates": c}}
                                                      for p, c in zip(t["props"], t["lines"], strict=True)]}
