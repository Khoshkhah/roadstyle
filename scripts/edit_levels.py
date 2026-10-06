"""The level editor (docs/design/level_input.md): a local page to write edits.csv, the overrides of the solver's pairs.

    python scripts/edit_levels.py AREA_DIR [--port 8780]

AREA_DIR holds roads.parquet and pairs.csv (scripts/level_input.py). Click two roads (or find them by edge id / edge_ref), see every pair between them (the found ones and
your edits), switch a found one off or add one (order / stack: the road you put on top over the other, a stack on one part of it if you like; meet: an end of each). Changes wait in a list until
you apply them: then they are solved together and the page reloads with the new levels (levels.csv is written too); if the solver refuses
them, nothing is saved. The edits.csv before each
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
from roadstyle import render_web

sys.path.insert(0, str(Path(__file__).resolve().parent))
from solve_levels import write  # noqa: E402

COLS = ["relation", "a", "b", "a_end", "b_end", "enabled"]


class Area:
    def __init__(self, folder):
        self.dir = Path(folder)
        self.roads = gpd.read_parquet(self.dir / "roads.parquet")
        self.pairs = pd.read_csv(self.dir / "pairs.csv", dtype=str, keep_default_na=False)
        self.edits_path = self.dir / "edits.csv"
        self.caps_path = self.dir / "caps.csv"                 # road -> (start, end): "", "square" or "flat" (cap_start_col / cap_end_col): drawing only
        t = pd.read_csv(self.caps_path, dtype=str, keep_default_na=False) if self.caps_path.exists() else pd.DataFrame(columns=["road", "start", "end"])
        both = t["cap"] if "cap" in t else ["flat"] * len(t)   # an older file: one value (or none: flat) for both ends
        self.heads_path = self.dir / "heads.csv"               # road -> (start_m, end_m) as text, "" = the default 5 m: the drawing's, and which mains are empty
        t2 = pd.read_csv(self.heads_path, dtype=str, keep_default_na=False) if self.heads_path.exists() else pd.DataFrame(columns=["road", "start_m", "end_m"])
        self.heads = {r: (s, e) for r, s, e in zip(t2["road"], t2["start_m"], t2["end_m"], strict=True)}
        self.caps = {r: (s, e) for r, s, e in zip(t["road"], t["start"] if "start" in t else both, t["end"] if "end" in t else both, strict=True)}
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
                                     "edge_ref": _txt(r.get("edge_ref")), "lanes": _txt(r.get("lanes")), "caps": ["", ""], "heads": [5.0, 5.0], "band": int(r["band"]), "priority": _num(r.get("priority")),
                                     "edges": len(r["edges"]) + len(r["reversed"]), "two_way": len(r["reversed"]) > 0, "length_m": float(m),
                                     "look": "tunnel" if _yes(r.get("tunnel")) else "bridge" if _yes(r.get("bridge")) else "ground",
                                     "width_px": _widths(_txt(r.get("highway")))}
        self.saved = len(self.edits())                          # the edits that were in edits.csv when the editor started
        self.build(self.edits(), self.stored())

    def stored(self):
        """The levels of levels.csv (the map starts from the tables as they are), or None when it is missing or older than an input."""
        lv, info = self.dir / "levels.csv", self.dir / "levels_info.json"
        inputs = [self.dir / "roads.parquet", self.dir / "pairs.csv", self.edits_path] + ([self.heads_path] if self.heads_path.exists() else [])
        if not (lv.exists() and info.exists()) or lv.stat().st_mtime < max(p.stat().st_mtime for p in inputs):
            print("levels.csv is missing or older than roads.parquet / pairs.csv / edits.csv: solved again", flush=True)
            return None
        t = pd.read_csv(lv, dtype={"edge": str}).set_index("edge")
        if not t.index.is_unique or not set(self.road_of) <= set(t.index):             # every edge of the roads, once
            print("levels.csv does not match roads.parquet: solved again", flush=True)
            return None
        solved = self.roads.copy()
        cols = ["casing_start", "casing_level", "casing_end", "fill_level"]
        for c in cols:
            solved[c] = 0
        for i, r in enumerate(solved.itertuples()):
            if r.edges:
                v = t.loc[str(r.edges[0]), cols].tolist()
            else:                                               # only the other way: its heads the other way round
                s, m, e, f = t.loc[str(r.reversed[0]), cols].tolist()
                v = [e, m, s, f]
            solved.iloc[i, [solved.columns.get_loc(c) for c in cols]] = v
        solved.attrs["levels_info"] = {k: v for k, v in json.loads(info.read_text()).items() if k not in ("given_up", "given_up_parts")}
        solved.attrs["levels_given_up_parts"] = [tuple(p) for p in json.loads(info.read_text()).get("given_up_parts", [])]
        solved.attrs["levels_given_up"] = [tuple(p) for p in json.loads(info.read_text()).get("given_up", [])]
        print(f"drawn from {lv} (not solved again)", flush=True)
        return solved

    def edits(self):
        return pd.read_csv(self.edits_path, dtype=str, keep_default_na=False).reindex(columns=COLS, fill_value="")

    def solve(self, edits, heads=None):
        heads = self.heads if heads is None else heads
        t = pd.DataFrame([(r, *heads[r]) for r in sorted(heads)], columns=["road", "start_m", "end_m"])
        return rs.solve_levels(self.roads, self.pairs, edits=edits if len(edits) else None, empty_main=rs.empty_mains(self.roads, 5.0, t))

    def build(self, edits, solved=None):
        if solved is None:
            solved = self.solve(edits)
            write(solved, self.dir)
        self.solved = solved
        self.stats = {**solved.attrs["levels_info"], "given_up": [list(p) for p in solved.attrs["levels_given_up"]], "area": self.dir.name}
        self.broken = solved.attrs.get("levels_given_up_parts", [])
        for r in solved.itertuples():
            self.facts[r.road]["caps"] = list(self.caps.get(r.road, ("", "")))
            self.facts[r.road]["heads"] = [float(x) if x else 5.0 for x in self.heads.get(r.road, ("", ""))]
            self.facts[r.road]["levels"] = [int(r.casing_start), int(r.casing_level), int(r.casing_end), int(r.fill_level)]
        draw = solved.drop(columns=["edges", "reversed"]).to_crs(4326)
        draw["head_start_m"], draw["head_end_m"] = ([self.facts[r]["heads"][k] for r in draw["road"]] for k in (0, 1))
        draw["cap_start"], draw["cap_end"] = ([self.caps.get(r, ("", ""))[k] or "round" for r in draw["road"]] for k in (0, 1))
        draw["oneway"] = [not f["two_way"] for f in (self.facts[r] for r in draw["road"])]      # a road with no other direction is one way
        ends = draw.geometry.apply(lambda ln: list(ln.coords[0][:2]) + list(ln.coords[-1][:2]))
        draw["s_lon"], draw["s_lat"], draw["e_lon"], draw["e_lat"] = zip(*ends, strict=True)
        m = rs.render_edges(draw, edge_id_col="road", road_popup=False, name=f"Level editor · {self.dir.name}",
                            select_color="rgba(0,0,0,0)",               # the panel colours the picked roads (1 orange, 2 blue): no click glow over them
                            filter_control=False, tunnel_control=False,  # the panel is the only control (Kaveh): no class filter box, no Tunnels box
                            casing_start_col="casing_start", casing_level_col="casing_level", casing_end_col="casing_end",
                            fill_level_col="fill_level", cap_start_col="cap_start", cap_end_col="cap_end",
                            head_start_m_col="head_start_m", head_end_m_col="head_end_m")
        page = m.html if hasattr(m, "html") else str(m)
        self.page = page.replace("</body>", _EDITOR.replace("__STATS__", json.dumps(self.stats, default=str)) + "</body>", 1)

    def change(self, edits, saved=None, caps=None, heads=None):
        """Solve with ``edits``; save them (and the drawing's ``caps``, road -> (start, end) of "" / "square" / "flat", and ``heads``, road ->
        (start_m, end_m), which tell the solver the empty mains) only if the solver takes them. Only caps changed: no solve."""
        if edits is None and heads == self.heads:              # only the ends' shapes changed: the levels as they are
            solved = self.solved
        else:
            solved = self.solve(self.edits() if edits is None else edits, heads)          # raises ValueError: nothing written
        if heads is not None:
            pd.DataFrame([(r, *heads[r]) for r in sorted(heads)], columns=["road", "start_m", "end_m"]).to_csv(self.heads_path, index=False)
            self.heads = dict(heads)
        if caps is not None:
            pd.DataFrame([(r, *caps[r]) for r in sorted(caps)], columns=["road", "start", "end"]).to_csv(self.caps_path, index=False)
            self.caps = dict(caps)
        if edits is not None:
            self.edits_path.with_name("edits.csv.bak").write_text(self.edits_path.read_text())
            edits.to_csv(self.edits_path, index=False)
        else:
            edits = self.edits()
        if solved is not self.solved:
            write(solved, self.dir)
        if saved is not None:
            self.saved = saved
        self.build(edits, solved)

    def apply(self, ops):
        """Apply the changes the page collected, in one solve: ``{"op": "delete", "index": i, "row": row}`` (a row of edits.csv, as the page showed it) and ``{"op": "add",
        "body": row}`` and ``{"op": "cap", "road": id, "end": "start" / "end", "cap": "" / "square" / "flat"}`` (one end of a road, caps.csv) and
        ``{"op": "head", "road": id, "end": "start" / "end", "m": metres or ""}`` (a head's length, heads.csv; "" = 5 m). If any is wrong, or the solver refuses the result, nothing is saved (ValueError)."""
        if not ops:
            raise ValueError("nothing to apply")
        if any(o.get("op") not in ("add", "delete", "cap", "head") for o in ops):
            raise ValueError("a change is add, delete, cap or head")
        caps, heads = dict(self.caps), dict(self.heads)
        for o in ops:
            if o["op"] == "cap":
                r, c, k = self.road_of.get(str(o["road"])), o.get("cap", ""), {"start": 0, "end": 1}.get(o.get("end"))
                if r is None or c not in ("", "square", "flat") or k is None:
                    raise ValueError(f"ends: {o['road']!r} is not a road, {o.get('end')!r} not start / end, or {c!r} not round (empty), square or flat")
                v = list(caps.pop(r, ("", "")))
                v[k] = c
                if any(v):
                    caps[r] = tuple(v)
            elif o["op"] == "head":
                r, m, k = self.road_of.get(str(o["road"])), str(o.get("m", "") or "").strip(), {"start": 0, "end": 1}.get(o.get("end"))
                try:
                    ok = m == "" or float(m) > 0
                except ValueError:
                    ok = False
                if r is None or k is None or not ok:
                    raise ValueError(f"heads: {o['road']!r} is not a road, {o.get('end')!r} not start / end, or {m!r} not a positive number of metres")
                v = list(heads.pop(r, ("", "")))
                v[k] = m
                if any(v):
                    heads[r] = tuple(v)
        e = self.edits()
        gone = sorted({int(o["index"]) for o in ops if o["op"] == "delete"}, reverse=True)
        for o in ops:                                           # a delete names its row as the page saw it: edits.csv may have changed since
            i = int(o["index"]) if o["op"] == "delete" else None
            if i is not None and not (0 <= i < len(e) and all(str(e.iat[i, e.columns.get_loc(c)]) == str(o["row"].get(c, "") or "") for c in COLS)):
                raise ValueError("an edit to delete is not in edits.csv as the page showed it (changed since): reload the page")
        new = pd.DataFrame([_row(o["body"]) for o in ops if o["op"] == "add"], columns=COLS)
        edits = pd.concat([e.drop(index=gone), new], ignore_index=True) if any(o["op"] in ("add", "delete") for o in ops) else None
        self.change(edits, saved=self.saved - sum(i < self.saved for i in gone), caps=caps, heads=heads)

    def given_up(self):
        """The stack pairs the solver could not keep (A over B), each with the parts of A's casing the solver could not put after B's fill
        and whether A's fill is under B's too: flaws on the map, to fix by hand."""
        rows = []
        for u, l in self.stats["given_up"]:
            lv, under = self.facts[u]["levels"], self.facts[l]["levels"][3]
            rows.append({"a": u, "b": l, "levels": lv, "b_fill": under, "fill_under": lv[3] <= under,
                         "parts": [h for a, b, h in self.broken if (a, b) == (u, l)]})
        return {"rows": rows, "roads": {x: self.facts[x] for r in rows for x in (r["a"], r["b"])}}

    def find(self, q, limit=20):
        """The roads for a search: an exact edge id (either direction of a road), else the edge_refs that hold ``q`` (an exact one first)."""
        q = q.strip()
        if not q:
            return []
        if q in self.road_of:
            return [self.facts[self.road_of[q]]]
        low = q.lower()
        hits = [f for f in self.facts.values() if f["edge_ref"] and low in f["edge_ref"].lower()]
        return sorted(hits, key=lambda f: (f["edge_ref"].lower() != low, f["edge_ref"]))[:limit]

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


def _row(body):
    """One edit from the page's form, checked."""
    row = {c: str(body.get(c, "") or "") for c in COLS}
    if row["relation"] not in ("meet", "stack", "order"):
        raise ValueError("relation must be meet, stack or order")
    if row["relation"] == "meet" and not (row["a_end"] in ("start", "end") and row["b_end"] in ("start", "end")):
        raise ValueError("a meet needs an end of each road (start / end)")
    if row["relation"] == "stack" and row["a_end"] not in ("", "start", "main", "end"):
        raise ValueError("a stack's part of the upper road is start, main, end or empty (the whole road)")
    if row["relation"] != "meet":                               # a stack keeps its part of the upper road (a_end)
        row["b_end"] = ""
        if row["relation"] == "order":
            row["a_end"] = ""
    return row


def _widths(cls):
    """The page's width of a road of class ``cls`` in pixels, fill and casing, at the zoom stops of its width expression (linear between
    them, the end values outside): the panel shows it at the map's zoom. One line per road here, so no two-way narrowing."""
    out = {}
    for kind in ("fill", "casing"):
        e = render_web._width_expr("highway", casing=kind == "casing")         # ["interpolate", ["linear"], ["zoom"], z, match, z, match, ...]
        vals = []
        for m in e[4::2]:
            m = m[1] if m[0] == "*" else m                      # ["*", match, two-way case]: the match
            vals.append(dict(zip(m[2:-1:2], m[3:-1:2], strict=True)).get(cls, m[-1]))
        out[kind] = vals
    return {"z": e[3::2], **out}


def _txt(v):
    return None if v is None or (isinstance(v, float) and v != v) else str(v)


def _yes(v):
    return _txt(v) not in (None, "", "no", "false", "False", "0")


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
                if u.path == "/api/given_up":
                    return self._send(200, area.given_up())
                if u.path == "/api/find":
                    return self._send(200, area.find(q.get("q", "")))
                if u.path == "/api/relations":
                    return self._send(200, area.relations(q.get("a", ""), q.get("b") or None))
            except ValueError as err:
                return self._send(400, {"error": str(err)})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            try:
                if self.path != "/api/apply":
                    return self._send(404, {"error": "not found"})
                area.apply(body.get("ops", []))
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
    print(f"level editor: http://localhost:{a.port}/  ({a.area_dir}; Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), _handler(area)).serve_forever()


if __name__ == "__main__":
    main()
