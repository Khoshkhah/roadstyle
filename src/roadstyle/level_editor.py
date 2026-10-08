"""The level editor (docs/design/level_input.md): a local page to write edits.csv, the overrides of the solver's pairs.

    roadstyle-levels edit AREA_DIR [--port 8780]

AREA_DIR holds roads.parquet and pairs.csv (roadstyle-levels make). Click two roads (or find them by edge id / edge_ref), see every pair between them (the found ones and
your edits), switch a found one off or add one (order / stack: the road you put on top over the other, a stack on one or more parts of its casing, one row each; meet: an end of each). Changes wait in a list until
you apply them: then they are solved together and the open page takes the new levels of the roads that changed, in place (the whole page
reloads when more than PARTIAL_MAX roads changed, and says so; levels.csv is written too); if the solver refuses
them, nothing is saved. The edits.csv before each
change is kept as edits.csv.bak.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import geopandas as gpd
import pandas as pd

import roadstyle as rs
from roadstyle import render_web

from .level_area import defaults, ends, own, solve, solve_local, write

COLS = ["relation", "a", "b", "a_end", "b_end", "enabled"]
DRAWN = ["casing_start", "casing_level", "casing_end", "fill_level", "head_start_m", "head_end_m", "cap_start", "cap_end"]   # what is drawn of a road
PARTIAL_MAX = 1500      # more roads changed by an Apply than this: the whole page again instead of an update in place


class Area:
    def __init__(self, folder):
        self.dir = Path(folder)
        self.roads = gpd.read_parquet(self.dir / "roads.parquet")
        self.pairs = pd.read_csv(self.dir / "pairs.csv", dtype=str, keep_default_na=False)
        self.edits_path = self.dir / "edits.csv"
        # each road end's head length and cap: solve_levels.defaults under yours in heads.csv / caps.csv ("" = the default)
        self.caps_path, self.heads_path = self.dir / "caps.csv", self.dir / "heads.csv"
        self.heads, self.caps = own(self.dir, self.roads)
        self.defaults = defaults(self.roads, self.pairs)                                  # 5 m heads; round caps, square at a two-way road's dead end
        self.auto_heads = self.defaults.set_index("road")
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
                                     "edge_ref": _txt(r.get("edge_ref")), "lanes": _txt(r.get("lanes")), "modes": _txt(r.get("modes")), "caps": ["", ""], "heads": [5.0, 5.0], "band": int(r["band"]), "priority": _num(r.get("priority")),
                                     "edges": len(r["edges"]) + len(r["reversed"]), "two_way": len(r["reversed"]) > 0, "length_m": float(m),
                                     "directions": _directions(r),
                                     "look": "tunnel" if _yes(r.get("tunnel")) else "bridge" if _yes(r.get("bridge")) else "ground",
                                     "width_px": _widths(_txt(r.get("highway")), len(r["reversed"]) > 0)}
        self.saved = len(self.edits())                          # the edits that were in edits.csv when the editor started
        self.drawn, self.update = None, None
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
            if len(r.edges):
                v = t.loc[str(r.edges[0]), cols].tolist()
            else:                                               # only the other way: its heads the other way round
                s, m, e, f = t.loc[str(r.reversed[0]), cols].tolist()
                v = [e, m, s, f]
            solved.iloc[i, [solved.columns.get_loc(c) for c in cols]] = v
        solved.attrs["levels_info"] = {k: v for k, v in json.loads(info.read_text()).items() if k not in ("given_up", "given_up_parts", "near", "orders_not_kept")}
        solved.attrs["levels_orders_not_kept"] = [tuple(p) for p in json.loads(info.read_text()).get("orders_not_kept", [])]
        solved.attrs["levels_near"] = [tuple(p) for p in json.loads(info.read_text()).get("near", [])]
        solved.attrs["levels_given_up_parts"] = [tuple(p) for p in json.loads(info.read_text()).get("given_up_parts", [])]
        solved.attrs["levels_given_up"] = [tuple(p) for p in json.loads(info.read_text()).get("given_up", [])]
        print(f"drawn from {lv} (not solved again)", flush=True)
        return solved

    def edits(self):
        return pd.read_csv(self.edits_path, dtype=str, keep_default_na=False).reindex(columns=COLS, fill_value="")

    def solve(self, edits, heads=None):
        return solve(self.roads, self.pairs, edits if len(edits) else None, self.heads if heads is None else heads, self.caps)[0]

    def build(self, edits, solved=None, save=False, in_place=False):
        """The map of ``solved`` (solved here if None): the automatic caps from its levels, yours on top; ``save``: levels.csv too.
        ``in_place``: the open page takes the change in place when at most PARTIAL_MAX roads are drawn differently (their levels, heads or
        caps): ``self.update`` holds what it needs (the new features of those roads, render_web.render(_edges=...), and their facts) and the
        whole page is built again only when it is asked for. Else ``self.update`` is None and ``self.reload`` says why the page reloads."""
        if solved is None:
            solved, save = self.solve(edits), True
        self.solved = solved
        auto = self.defaults
        drawn = ends(auto, self.heads, self.caps)
        if save:
            write(solved, self.dir, drawn)
        auto, drawn = auto.set_index("road").to_dict("index"), drawn.set_index("road").to_dict("index")      # dicts: .loc per road took a second
        self.stats = {**solved.attrs["levels_info"], "given_up": [list(p) for p in solved.attrs["levels_given_up"]], "area": self.dir.name}
        self.broken = solved.attrs.get("levels_given_up_parts", [])
        self.near = solved.attrs.get("levels_near", [])
        self.wishes = solved.attrs.get("levels_orders_not_kept", [])
        for r in solved.itertuples():
            a, d, own_h, own_c = auto[r.road], drawn[r.road], self.heads.get(r.road, ("", "")), self.caps.get(r.road, ("", ""))
            self.facts[r.road]["heads"] = [float(d["start_m"]), float(d["end_m"])]
            self.facts[r.road]["heads_auto"] = [float(a["start_m"]), float(a["end_m"])]       # what auto gives; heads_own: which ends you set
            self.facts[r.road]["heads_own"] = [bool(own_h[0]), bool(own_h[1])]
            self.facts[r.road]["caps"] = list(own_c)                                 # "" = auto
            self.facts[r.road]["caps_auto"] = [a["cap_start"], a["cap_end"]]
            self.facts[r.road]["levels"] = [int(r.casing_start), int(r.casing_level), int(r.casing_end), int(r.fill_level)]
        draw = solved.to_crs(4326)
        draw["head_start_m"], draw["head_end_m"] = ([self.facts[r]["heads"][k] for r in draw["road"]] for k in (0, 1))
        draw["cap_start"], draw["cap_end"] = ([drawn[r][c] for r in draw["road"]] for c in ("cap_start", "cap_end"))
        draw["oneway"] = [not f["two_way"] for f in (self.facts[r] for r in draw["road"])]      # a road with no other direction is one way
        tips = draw.geometry.apply(lambda ln: list(ln.coords[0][:2]) + list(ln.coords[-1][:2]))
        draw["s_lon"], draw["s_lat"], draw["e_lon"], draw["e_lat"] = zip(*tips, strict=True)    # the road's ends, on each of its edges
        draw = _edge_rows(draw)
        self.draw, before = draw, self.drawn
        self.drawn = list(zip(*(draw[c].tolist() for c in DRAWN), strict=True))           # an edge's row: what is drawn of it
        self.update, self.reload, self._page = None, None, None
        if not in_place:
            return
        changed = [i for i, (x, y) in enumerate(zip(before, self.drawn, strict=True)) if x != y]
        roads = list(dict.fromkeys(draw["road"].iat[i] for i in changed))
        if len(roads) > PARTIAL_MAX:
            self.reload = f"{len(roads)} roads changed, more than {PARTIAL_MAX}: the whole page again"
            return
        names = any(before[i][k] != self.drawn[i][k] for i in changed for k in (1, 3))   # a fill number (max of casing, fill) changed: the names and
        feats = self._render(_edges=changed, arrows=names, labels=names)                    # arrows again (their chains follow it); both directions of a road
        self.update = {"roads": roads, "features": feats, "pieces": render_web._PIECES, "facts": {r: self.facts[r] for r in roads}, "stats": self.stats}

    def _render(self, **kw):
        """The editor's map of ``self.draw`` (render_edges); with ``_edges``, the features of those roads instead (render_web.render)."""
        return rs.render_edges(self.draw, edge_id_col="edge", road_popup=False, name=f"Level editor · {self.dir.name}",
                               select_color="rgba(0,0,0,0)",               # the panel colours the picked roads (1 orange, 2 blue): no click glow over them
                               filter_control=False, tunnel_control=False,  # the panel is the only control: no class filter box, no Tunnels box
                               casing_start_col="casing_start", casing_level_col="casing_level", casing_end_col="casing_end",
                               fill_level_col="fill_level", cap_start_col="cap_start", cap_end_col="cap_end",
                               head_start_m_col="head_start_m", head_end_m_col="head_end_m", **kw)

    @property
    def page(self):
        """The whole page, built when asked for (after an update in place, only when the page is loaded again)."""
        if self._page is None:
            m = self._render()
            page = m.html if hasattr(m, "html") else str(m)
            self._page = page.replace("</body>", _EDITOR.replace("__STATS__", json.dumps(self.stats, default=str)) + "</body>", 1)
        return self._page

    def change(self, edits, saved=None, caps=None, heads=None):
        """Solve with ``edits``; save them (and the drawing's ``caps``, road -> (start, end) of "" / "square" / "flat", and ``heads``, road ->
        (start_m, end_m)) only if the solver takes them. Only caps or heads changed: no solve (the solver works from the tables only, 2026-10-08:
        which parts of a stack cross was decided when the area was made). The solve is local
        (level_area.solve_local: the roads around the change, the others as they were), or the whole area when the local result would not do;
        ``said`` tells which, and why."""
        if edits is None:                                    # only the ends' shapes changed: the levels as they are
            solved, self.full = self.solved, False
            self.said = "not solved again (only caps)" if heads is None or heads == self.heads else "not solved again (heads and caps are drawing only)"
        else:
            new, hd = self.edits() if edits is None else edits, self.heads if heads is None else heads
            solved = solve_local(self.roads, self.pairs, new if len(new) else None, hd, self.caps, self.solved,
                                 _changed(self.edits(), new, self.heads, hd, self.road_of))[0]                  # raises ValueError: nothing written
            r = solved.attrs["levels_info"]["resolve"]
            self.full = r["how"] == "full"
            self.said = (f"re-solved the {r['free']} roads around the change in {r['seconds']} s" if r["how"] == "local" else
                         f"solved the whole area in {r['seconds']} s: the local re-solve of {r['free']} roads did not do ({r['why']})")
            print(self.said, flush=True)
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
        if saved is not None:
            self.saved = saved
        self.build(edits, solved, save=True, in_place=True)    # levels.csv has the ends as drawn: written for a cap too

    def apply(self, ops):
        """Apply the changes the page collected, in one solve: ``{"op": "delete", "index": i, "row": row}`` (a row of edits.csv, as the page showed it) and ``{"op": "add",
        "body": row}`` and ``{"op": "cap", "road": id, "end": "start" / "end", "cap": "" (auto) / "round" / "square" / "flat"}`` (one end of a road, caps.csv) and
        ``{"op": "head", "road": id, "end": "start" / "end", "m": metres or ""}`` (a head's length, heads.csv; "" = auto). If any is wrong, or the solver refuses the result, nothing is saved (ValueError)."""
        if not ops:
            raise ValueError("nothing to apply")
        if any(o.get("op") not in ("add", "delete", "cap", "head") for o in ops):
            raise ValueError("a change is add, delete, cap or head")
        caps, heads = dict(self.caps), dict(self.heads)
        for o in ops:
            if o["op"] == "cap":
                r, c, k = self.road_of.get(str(o["road"])), o.get("cap", ""), {"start": 0, "end": 1}.get(o.get("end"))
                if r is None or c not in ("", "round", "square", "flat") or k is None:
                    raise ValueError(f"ends: {o['road']!r} is not a road, {o.get('end')!r} not start / end, or {c!r} not auto (empty), round, square or flat")
                v = list(caps.pop(r, ("", "")))
                v[k] = "" if c == self.defaults.set_index("road").loc[r, ("cap_start", "cap_end")[k]] else c    # the default shape: not stored
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
        for r in {self.road_of.get(str(o["road"])) for o in ops if o["op"] == "head"}:    # after all of them: the page sends both heads together
            v = heads.get(r, ("", ""))
            hs, he = (float(x) if x else float(self.auto_heads.loc[r, c]) for x, c in zip(v, ("start_m", "end_m"), strict=True))
            if all(v) and hs + he > self.facts[r]["length_m"] + 0.05:           # both set: they must fit the road
                raise ValueError(f"heads of {self.facts[r]['name'] or self.facts[r]['edge_ref'] or r}: {hs:g} + {he:g} m is more than the road's "
                                 f"{self.facts[r]['length_m']:g} m")
        e = self.edits()
        gone = sorted({int(o["index"]) for o in ops if o["op"] == "delete"}, reverse=True)
        for o in ops:                                           # a delete names its row as the page saw it: edits.csv may have changed since
            i = int(o["index"]) if o["op"] == "delete" else None
            if i is not None and not (0 <= i < len(e) and all(str(e.iat[i, e.columns.get_loc(c)]) == str(o["row"].get(c, "") or "") for c in COLS)):
                raise ValueError("an edit to delete is not in edits.csv as the page showed it (changed since): reload the page")
        new = pd.DataFrame([_row(o["body"]) for o in ops if o["op"] == "add"], columns=COLS)
        kept, seen = e.drop(index=gone), set()               # an exact copy of a rule already there is refused: a second copy kept the rule
        have = {tuple(str(x) for x in r) for r in kept[COLS].astype(str).itertuples(index=False)}    # working after one copy was deleted (2026-10-08)
        for r in new[COLS].astype(str).itertuples(index=False):
            if tuple(r) in have or tuple(r) in seen:
                raise ValueError(f"this rule is already in edits.csv: {self.say(dict(zip(COLS, r)))}: nothing saved")
            seen.add(tuple(r))
        edits = pd.concat([kept, new], ignore_index=True) if any(o["op"] in ("add", "delete") for o in ops) else None
        self.change(edits, saved=self.saved - sum(i < self.saved for i in gone), caps=caps, heads=heads)

    def given_up(self):
        """The stack pairs the solver could not keep (A over B), each with the parts of A's casing the solver could not put after B's fill
        and whether A's fill is under B's too: flaws on the map, to fix by hand."""
        def row(u, l, broken):
            lv, under = self.facts[u]["levels"], self.facts[l]["levels"][3]
            return {"a": u, "b": l, "levels": lv, "b_fill": under, "fill_under": lv[3] <= under, "parts": [h for a, b, h in broken if (a, b) == (u, l)]}
        rows = [row(u, l, self.broken) for u, l in self.stats["given_up"]]
        near = [row(u, l, self.near) for u, l in dict.fromkeys((a, b) for a, b, _ in self.near)]      # warnings: parts that only come near
        wishes = [{"a": x, "b": y, "fa": self.facts[x]["levels"][3], "fb": self.facts[y]["levels"][3]} for x, y in self.wishes]   # x's fill was to be after y's
        return {"rows": rows, "near": near, "wishes": wishes, "roads": {k: self.facts[k] for r in rows + near + wishes for k in (r["a"], r["b"])}}

    def check(self, rows, ops=()):
        """The guard before rules are added (levels.rule_conflicts): which of ``rows`` (the page's new rules) conflict with the enabled rules
        (found, edits.csv, and the changes waiting in the list, ``ops`` as apply takes them), in plain words."""
        from .levels import rule_conflicts
        e = self.edits()
        gone = sorted({int(o["index"]) for o in ops if o.get("op") == "delete"})
        edits = pd.concat([e.drop(index=gone), pd.DataFrame([_row(o["body"]) for o in ops if o.get("op") == "add"], columns=COLS)], ignore_index=True)
        found = rule_conflicts(self.roads, self.pairs, edits if len(edits) else None, [_row(r) for r in rows])
        return [{"rule": self.say(row), "why": why, "with": [self.say(r) for r in rules]} for row, why, rules in found]

    def say(self, r):
        """A rule in plain words, with whose it is (found / yours) when it is in the tables."""
        def nm(x):
            f = self.facts.get(self.road_of.get(str(x), str(x)), {})
            return (f.get("name") or f.get("highway") or "road") + (f" [{f['edge_ref']}]" if f.get("edge_ref") else f" [{x}]")
        part = {"start": "start head", "main": "main", "end": "end head"}
        txt = (f"{nm(r['a'])} ({r['a_end']}) joins {nm(r['b'])} ({r['b_end']})" if r["relation"] == "meet"
               else f"{nm(r['a'])}'s fill after {nm(r['b'])}'s" if r["relation"] == "order"
               else f"{nm(r['a'])}'s {part.get(r['a_end'], r['a_end'])} over {nm(r['b'])}" + (" (near only)" if r["relation"] == "near" else ""))
        return txt + (" · yours" if r.get("own") else " · found" if "enabled" not in r else "")

    def find(self, q, limit=20):
        """The roads for a search: an exact edge id (either direction of a road), else the edge_refs (of either direction) that hold ``q``
        (an exact one first)."""
        q = q.strip()
        if not q:
            return []
        if q in self.road_of:
            return [self.facts[self.road_of[q]]]
        low = q.lower()
        refs = lambda f: [x.lower() for x in [f["edge_ref"], *(d["edge_ref"] for d in f["directions"])] if x]     # noqa: E731
        hits = [f for f in self.facts.values() if any(low in x for x in refs(f))]
        return sorted(hits, key=lambda f: (low not in refs(f), f["edge_ref"] or ""))[:limit]

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


def _changed(old, new, heads_old, heads_new, road_of):
    """The roads a change names: those of the edit rows added or taken out (old -> new edits.csv) and those whose heads changed."""
    from collections import Counter
    rows = lambda t: Counter(map(tuple, t.reindex(columns=COLS, fill_value="").astype(str).to_numpy().tolist()))   # noqa: E731
    a, b = rows(old), rows(new)
    out = {road_of.get(x, x) for r in (a - b) + (b - a) for x in (r[1], r[2])}
    return out | {r for r in set(heads_old) | set(heads_new) if heads_old.get(r) != heads_new.get(r)}


def _row(body):
    """One edit from the page's form, checked."""
    row = {c: str(body.get(c, "") or "") for c in COLS}
    if row["relation"] not in ("meet", "stack", "order", "near"):
        raise ValueError("relation must be meet, stack or order (or near, to switch a found near row off)")
    if row["relation"] == "meet" and not (row["a_end"] in ("start", "end") and row["b_end"] in ("start", "end")):
        raise ValueError("a meet needs an end of each road (start / end)")
    if row["relation"] in ("stack", "near") and row["a_end"] not in ("start", "main", "end"):
        raise ValueError("a stack names one part of the upper road: start, main or end (one row per part)")
    if row["relation"] != "meet":                               # a stack (near) keeps its part of the upper road (a_end)
        row["b_end"] = ""
        if row["relation"] == "order":
            row["a_end"] = ""
    return row


def _directions(r):
    """A road's directions for the panel: each edge id with its edge_ref (``edge_refs`` / ``reversed_refs`` of roads.parquet: an area
    made before 2026-10-08 has only the road's own ``edge_ref``, the one of its first edge, the road's id; the others' are None) and ``way``:
    "along" the road or "against"."""
    out = []
    for way, ids, refs in (("along", r["edges"], r.get("edge_refs")), ("against", r["reversed"], r.get("reversed_refs"))):
        if refs is None or (isinstance(refs, float) and refs != refs):
            refs = [r.get("edge_ref") if str(e) == str(r["road"]) else None for e in ids]
        out += [{"edge": str(e), "edge_ref": _txt(x), "way": way} for e, x in zip(ids, refs, strict=True)]
    return out


def _widths(cls, two_way=False):
    """The page's width of a road of class ``cls`` in pixels, fill and casing, at the zoom stops of its width expression (linear between
    them, the end values outside): the panel shows it at the map's zoom. A ``two_way`` road: the fill of one direction (narrowed as the
    page draws it) and the outer width of the pair's one casing (both directions together, render_web._pair_width)."""
    out = {}
    for kind in ("fill", "casing"):
        e = render_web._width_expr("highway", casing=kind == "casing")         # ["interpolate", ["linear"], ["zoom"], z, match, z, match, ...]
        vals = []
        for z, m in zip(e[3::2], e[4::2], strict=True):
            f = m[2][2] if m[0] == "*" and two_way else 1       # ["*", match, ["case", two-way?, factor, 1]]
            m = m[1] if m[0] == "*" else m
            v = dict(zip(m[2:-1:2], m[3:-1:2], strict=True)).get(cls, m[-1]) * f
            if two_way and kind == "casing":
                o = render_web._offset_match("highway", z)
                v += 2 * dict(zip(o[2:-1:2], o[3:-1:2], strict=True)).get(cls, o[-1])
            vals.append(round(v, 2))
        out[kind] = vals
    return {"z": e[3::2], **out}


def _edge_rows(draw):
    """One row per edge from one row per road (``edges`` / ``reversed``), as the final map has them: an edge of the other direction runs
    the road's line backwards, with its two heads, casing numbers and caps swapped (level_area.edge_levels); ``edge`` is its id."""
    import shapely
    refs = "edge_refs" in draw.columns                          # each edge's own edge_ref (an area made since 2026-10-08)
    def one(ids, rs, w):
        t = draw.assign(edge=draw[ids], _o=range(len(draw)), _w=w, **({"edge_ref": draw[rs]} if refs else {}))
        return pd.DataFrame.explode(t, ["edge", "edge_ref"] if refs else "edge").dropna(subset=["edge"])     # geopandas' explode is of geometries
    fw, bw = one("edges", "edge_refs", 0), one("reversed", "reversed_refs", 1)
    for a, b in (("casing_start", "casing_end"), ("head_start_m", "head_end_m"), ("cap_start", "cap_end")):
        bw[a], bw[b] = bw[b].to_numpy(), bw[a].to_numpy()
    bw = bw.set_geometry(shapely.reverse(bw.geometry.to_numpy()), crs=draw.crs)
    out = pd.concat([fw, bw]).sort_values(["_o", "_w"], kind="stable").drop(columns=["edges", "reversed", "_o", "_w", "edge_refs", "reversed_refs"], errors="ignore")
    out["edge"] = out["edge"].astype(str)
    return out.reset_index(drop=True)


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
            if code >= 400:                                    # every error the page shows is in this log too
                print(f"error {code} on {self.path}: {body.get('error') if isinstance(body, dict) else body}", flush=True)
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
                if self.path == "/api/check":
                    return self._send(200, {"conflicts": area.check(body.get("rows", []), body.get("ops", []))})
                if self.path == "/api/new_session":                # what is in edits.csv now counts as saved before: "added now" starts empty
                    area.saved = len(area.edits())
                    return self._send(200, {"ok": True, "saved": area.saved})
                if self.path != "/api/apply":
                    return self._send(404, {"error": "not found"})
                area.apply(body.get("ops", []))
            except (ValueError, KeyError) as err:
                return self._send(400, {"error": str(err)})
            self._send(200, {"ok": True, "said": area.said, "full": area.full, "update": area.update, "reload": area.reload})
    return H


_EDITOR = (Path(__file__).resolve().parent / "static" / "level_editor.html").read_text()


def serve(folder, port=8780):
    """The editor of the area in ``folder`` at http://localhost:``port``/ until Ctrl+C."""
    area = Area(folder)
    print(f"level editor: http://localhost:{port}/  ({folder}; Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), _handler(area)).serve_forever()
