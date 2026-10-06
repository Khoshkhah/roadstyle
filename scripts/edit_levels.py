"""The level editor (docs/design/level_input.md): a local page to write edits.csv, the overrides of the solver's pairs.

    python scripts/edit_levels.py AREA_DIR [--port 8780]

AREA_DIR holds roads.parquet and pairs.csv (scripts/level_input.py). Click two roads, see every pair between them (the found ones and
your edits), switch a found one off or add one (order / stack: road 1 over road 2; meet: an end of each). Every change is solved at once
and the page reloads with the new levels (levels.csv is written too); an edit the solver refuses is not saved. The edits.csv before each
change is kept as edits.csv.bak.
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import geopandas as gpd
import pandas as pd

import roadstyle as rs

sys.path.insert(0, str(Path(__file__).resolve().parent))
from solve_levels import edge_levels  # noqa: E402

COLS = ["relation", "a", "b", "a_end", "b_end", "enabled"]


class Area:
    def __init__(self, folder):
        self.dir = Path(folder)
        self.roads = gpd.read_parquet(self.dir / "roads.parquet")
        self.pairs = pd.read_csv(self.dir / "pairs.csv", dtype=str, keep_default_na=False)
        self.edits_path = self.dir / "edits.csv"
        if not self.edits_path.exists():
            self.edits_path.write_text(",".join(COLS) + "\n")
        self.road_of = {}                                       # any edge id -> its road id
        for r in self.roads.itertuples():
            for e in [r.road, *list(r.edges), *list(r.reversed)]:
                self.road_of[str(e)] = r.road
        length = _metres(self.roads.geometry).length.round(1)
        self.facts = {}                                         # road id -> what the panel shows about it
        for (_, r), m in zip(self.roads.iterrows(), length, strict=True):
            self.facts[r["road"]] = {"road": r["road"], "name": _txt(r.get("name")), "highway": _txt(r.get("highway")),
                                     "edge_ref": _txt(r.get("edge_ref")), "band": int(r["band"]), "priority": _num(r.get("priority")),
                                     "edges": len(r["edges"]) + len(r["reversed"]), "two_way": len(r["reversed"]) > 0, "length_m": float(m)}
        self.saved = len(self.edits())                          # the edits that were in edits.csv when the editor started
        self.build(self.edits())

    def edits(self):
        return pd.read_csv(self.edits_path, dtype=str, keep_default_na=False).reindex(columns=COLS, fill_value="")

    def solve(self, edits):
        return rs.solve_levels(self.roads, self.pairs, edits=edits if len(edits) else None)

    def build(self, edits, solved=None):
        solved = self.solve(edits) if solved is None else solved
        edge_levels(solved).to_csv(self.dir / "levels.csv", index=False)
        self.stats = {**solved.attrs["levels_info"], "given_up": [list(p) for p in solved.attrs["levels_given_up"]], "area": self.dir.name}
        for r in solved.itertuples():
            self.facts[r.road]["levels"] = [int(r.casing_start), int(r.casing_level), int(r.casing_end), int(r.fill_level)]
        draw = solved.drop(columns=["edges", "reversed"]).to_crs(4326)
        draw["oneway"] = [not f["two_way"] for f in (self.facts[r] for r in draw["road"])]      # a road with no other direction is one way
        ends = draw.geometry.apply(lambda ln: list(ln.coords[0][:2]) + list(ln.coords[-1][:2]))
        draw["s_lon"], draw["s_lat"], draw["e_lon"], draw["e_lat"] = zip(*ends, strict=True)
        m = rs.render_edges(draw, edge_id_col="road", road_popup=False, name=f"Level editor · {self.dir.name}",
                            casing_start_col="casing_start", casing_level_col="casing_level", casing_end_col="casing_end",
                            fill_level_col="fill_level")
        page = m.html if hasattr(m, "html") else str(m)
        self.page = page.replace("</body>", _EDITOR.replace("__STATS__", json.dumps(self.stats, default=str)) + "</body>", 1)

    def change(self, edits, saved=None):
        """Solve with ``edits``; save them only if the solver takes them."""
        solved = self.solve(edits)                              # raises ValueError: nothing written
        self.edits_path.with_name("edits.csv.bak").write_text(self.edits_path.read_text())
        edits.to_csv(self.edits_path, index=False)
        if saved is not None:
            self.saved = saved
        self.build(edits, solved)

    def rows(self):
        """Every edit, with its index, its section (saved before this session / added now) and its two roads."""
        out = []
        for i, r in enumerate(self.edits().to_dict("records")):
            ra, rb = self.road_of.get(r["a"], r["a"]), self.road_of.get(r["b"], r["b"])
            out.append({**r, "index": i, "section": "saved" if i < self.saved else "new", "ra": ra, "rb": rb})
        return out

    def relations(self, a, b=None):
        """What the two tables have about road ``a`` (and ``b``): the found pairs and the edits, each with its two roads."""
        ra, rb = self.road_of.get(a), self.road_of.get(b) if b else None
        if ra is None or (b and rb is None):
            raise ValueError("unknown road")
        mine = lambda x, y: (x == ra and (rb is None or y == rb)) or (y == ra and (rb is None or x == rb))   # noqa: E731
        found = [{**r, "section": "found", "ra": r["a"], "rb": r["b"]} for r in self.pairs.to_dict("records") if mine(r["a"], r["b"])]
        edits = [r for r in self.rows() if mine(r["ra"], r["rb"])]
        roads = {x for r in found + edits for x in (r["ra"], r["rb"])} | {ra} | ({rb} if rb else set())
        return {"a": ra, "b": rb, "rows": found + edits, "roads": {x: self.facts.get(x, {"road": x}) for x in roads}}


def _txt(v):
    return None if v is None or (isinstance(v, float) and v != v) else str(v)


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v != v else round(v, 2)


def _metres(geoseries):
    return geoseries.to_crs(geoseries.estimate_utm_crs()) if geoseries.crs is not None and geoseries.crs.is_geographic else geoseries


def _handler(area):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, kind="application/json"):
            data = body.encode() if isinstance(body, str) else json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path == "/":
                    return self._send(200, area.page, "text/html; charset=utf-8")
                if u.path == "/api/edits":
                    rows = area.rows()
                    return self._send(200, {"rows": rows, "roads": {x: area.facts.get(x, {"road": x}) for r in rows for x in (r["ra"], r["rb"])}})
                if u.path == "/api/relations":
                    return self._send(200, area.relations(q.get("a", ""), q.get("b") or None))
            except ValueError as err:
                return self._send(400, {"error": str(err)})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            e = area.edits()
            try:
                if self.path == "/api/add":
                    row = {c: str(body.get(c, "") or "") for c in COLS}
                    if row["relation"] not in ("meet", "stack", "order"):
                        raise ValueError("relation must be meet, stack or order")
                    if row["relation"] == "meet" and not (row["a_end"] in ("start", "end") and row["b_end"] in ("start", "end")):
                        raise ValueError("a meet needs an end of each road (start / end)")
                    if row["relation"] != "meet":
                        row["a_end"] = row["b_end"] = ""
                    area.change(pd.concat([e, pd.DataFrame([row])], ignore_index=True))
                elif self.path == "/api/delete":
                    i = int(body["index"])
                    area.change(e.drop(index=i).reset_index(drop=True), saved=area.saved - (i < area.saved))
                else:
                    return self._send(404, {"error": "not found"})
            except (ValueError, KeyError) as err:
                return self._send(400, {"error": str(err)})
            self._send(200, {"ok": True})
    return H


_EDITOR = (Path(__file__).resolve().parent / "edit_levels.html").read_text()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("area_dir", type=Path)
    ap.add_argument("--port", type=int, default=8780)
    a = ap.parse_args(argv)
    area = Area(a.area_dir)
    print(f"level editor: http://localhost:{a.port}/  ({a.area_dir}; Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", a.port), _handler(area)).serve_forever()


if __name__ == "__main__":
    main()
