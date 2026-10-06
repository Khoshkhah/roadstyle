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
        self.build(self.edits())

    def edits(self):
        return pd.read_csv(self.edits_path, dtype=str, keep_default_na=False).reindex(columns=COLS, fill_value="")

    def solve(self, edits):
        return rs.solve_levels(self.roads, self.pairs, edits=edits if len(edits) else None)

    def build(self, edits, solved=None):
        solved = self.solve(edits) if solved is None else solved
        edge_levels(solved).to_csv(self.dir / "levels.csv", index=False)
        self.info = {**solved.attrs["levels_info"], "given_up": [list(p) for p in solved.attrs["levels_given_up"]]}
        draw = solved.drop(columns=["edges", "reversed"]).to_crs(4326)
        ends = draw.geometry.apply(lambda ln: list(ln.coords[0][:2]) + list(ln.coords[-1][:2]))
        draw["s_lon"], draw["s_lat"], draw["e_lon"], draw["e_lat"] = zip(*ends, strict=True)
        shown = [c for c in ("name", "highway", "edge_ref", "road", "band", "priority", "casing_start", "casing_level", "casing_end", "fill_level")
                 if c in draw.columns]
        m = rs.render_edges(draw, edge_id_col="road", arrows=False, name=f"Level edits · {self.dir.name}", road_popup=shown,
                            casing_start_col="casing_start", casing_level_col="casing_level", casing_end_col="casing_end",
                            fill_level_col="fill_level")
        page = m.html if hasattr(m, "html") else str(m)
        tail = _EDITOR.replace("__INFO__", json.dumps(self.info, default=str))
        self.page = page.replace("</body>", tail + "</body>", 1)

    def change(self, edits):
        """Solve with ``edits``; save them only if the solver takes them."""
        solved = self.solve(edits)                              # raises ValueError: nothing written
        self.edits_path.with_name("edits.csv.bak").write_text(self.edits_path.read_text())
        edits.to_csv(self.edits_path, index=False)
        self.build(edits, solved)

    def between(self, a, b):
        ra, rb = self.road_of.get(a), self.road_of.get(b)
        if ra is None or rb is None:
            raise ValueError("pick two roads")
        same = lambda t: ((t["a"] == ra) & (t["b"] == rb)) | ((t["a"] == rb) & (t["b"] == ra))          # noqa: E731
        found = self.pairs[same(self.pairs)].to_dict("records")
        e = self.edits()
        e["index"] = range(len(e))
        mapped = e.assign(a=[self.road_of.get(v, v) for v in e["a"]], b=[self.road_of.get(v, v) for v in e["b"]])
        return {"a": ra, "b": rb, "found": found, "edits": e[same(mapped)].to_dict("records")}


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
                    e = area.edits()
                    return self._send(200, [{**r, "index": i} for i, r in enumerate(e.to_dict("records"))])
                if u.path == "/api/pairs":
                    return self._send(200, area.between(q.get("a", ""), q.get("b", "")))
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
                    area.change(e.drop(index=int(body["index"])).reset_index(drop=True))
                else:
                    return self._send(404, {"error": "not found"})
            except (ValueError, KeyError) as err:
                return self._send(400, {"error": str(err)})
            self._send(200, {"ok": True, "info": area.info})
    return H


_EDITOR = r"""
<style>
#lv-ed{position:fixed;top:10px;right:60px;z-index:5;width:330px;max-height:calc(100vh - 20px);overflow:auto;background:#fff;border-radius:8px;
  box-shadow:0 2px 12px rgba(0,0,0,.18);font:13px system-ui,sans-serif;color:#222;padding:10px 12px}
#lv-ed h3{margin:0 0 6px;font-size:14px} #lv-ed h4{margin:10px 0 4px;font-size:12px;color:#555;text-transform:uppercase;letter-spacing:.04em}
#lv-ed .road{display:flex;gap:6px;align-items:center;margin:3px 0} #lv-ed .sw{width:10px;height:10px;border-radius:50%;flex:none}
#lv-ed .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap} #lv-ed button{font:12px system-ui;cursor:pointer}
#lv-ed .row{display:flex;gap:6px;align-items:center;justify-content:space-between;border-top:1px solid #eee;padding:3px 0}
#lv-ed .msg{color:#c92a2a;margin:4px 0;min-height:1em} #lv-ed .ok{color:#2b8a3e} #lv-ed small{color:#666}
#lv-ed ol{margin:0;padding-left:18px} #lv-ed li{cursor:pointer} #lv-ed li:hover{background:#f1f3f5}
</style>
<div id="lv-ed">
  <h3>Level edits</h3>
  <small id="lv-info"></small>
  <div class="road"><span class="sw" style="background:#e8590c"></span><span class="nm" id="lv-n1">click road 1</span>
    <label><input type="radio" name="lv-e1" value="start" checked>start</label><label><input type="radio" name="lv-e1" value="end">end</label></div>
  <div class="road"><span class="sw" style="background:#1971c2"></span><span class="nm" id="lv-n2">click road 2</span>
    <label><input type="radio" name="lv-e2" value="start" checked>start</label><label><input type="radio" name="lv-e2" value="end">end</label></div>
  <small>● start &nbsp;○ end of each picked road (for a meet)</small>
  <div style="margin:6px 0;display:flex;gap:6px;flex-wrap:wrap">
    <select id="lv-rel"><option value="order">order: road 1's fill after road 2's</option><option value="stack">stack: road 1 over road 2</option>
      <option value="meet">meet: the chosen ends join</option></select>
    <button id="lv-add">Add</button><button id="lv-swap" title="swap road 1 and road 2">⇄</button><button id="lv-clear">Clear</button>
  </div>
  <div class="msg" id="lv-msg"></div>
  <h4>Pairs between them</h4><div id="lv-pairs"><small>pick two roads</small></div>
  <h4>Your edits (edits.csv)</h4><ol id="lv-list"></ol>
</div>
<script>
(function(){
  const INFO = __INFO__;
  const sel = [null, null], C = ["#e8590c", "#1971c2"];          // [{id, road, props}]
  const $ = id => document.getElementById(id);
  $("lv-info").textContent = `${INFO.roads} roads · ${INFO.given_up.length} stack pair(s) given up · ${INFO.order_violations || 0} order wish(es) not kept`;
  const label = p => (p.name || p.highway || "road") + " · " + (p.edge_ref || p.road);
  function msg(t, ok){ const m = $("lv-msg"); m.textContent = t || ""; m.className = "msg" + (ok ? " ok" : ""); }
  function ends(){
    const f = [];
    sel.forEach((s, k) => { if(!s) return; const p = s.props;
      f.push({type:"Feature", properties:{c:C[k], open:0}, geometry:{type:"Point", coordinates:[p.s_lon, p.s_lat]}});
      f.push({type:"Feature", properties:{c:C[k], open:1}, geometry:{type:"Point", coordinates:[p.e_lon, p.e_lat]}}); });
    const src = map.getSource("lv-ends"), fc = {type:"FeatureCollection", features:f};
    if(src) src.setData(fc);
    else { map.addSource("lv-ends", {type:"geojson", data:fc});
      map.addLayer({id:"lv-ends", type:"circle", source:"lv-ends", paint:{"circle-radius":6, "circle-stroke-width":2.5,
        "circle-stroke-color":["get","c"], "circle-color":["case",["==",["get","open"],1],"#ffffff",["get","c"]]}}); }
  }
  function show(){
    $("lv-n1").textContent = sel[0] ? label(sel[0].props) : "click road 1";
    $("lv-n2").textContent = sel[1] ? label(sel[1].props) : "click road 2";
    const g = sel.map((s, k) => s && [[s.id], C[k]]).filter(Boolean);
    rsColor(g.length ? g : null); ends(); pairs();
  }
  function pick(ids){ return ids.length ? {id: ids[0], road: String(rsGetProps([ids[0]])[0].road), props: rsGetProps([ids[0]])[0]} : null; }
  document.addEventListener("rs:select", e => {
    if(e.detail.overlay || e.detail.id == null) return;
    const s = {id: e.detail.id, road: String(e.detail.properties.road), props: e.detail.properties};
    if(sel[0] && sel[0].road === s.road) return;
    if(!sel[0] || (sel[0] && sel[1])) { sel[0] = s; sel[1] = null; } else sel[1] = s;
    show();
  });
  async function api(path, body){
    const r = await fetch(path, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {});
    const j = await r.json(); if(!r.ok) throw new Error(j.error || r.statusText); return j;
  }
  function reload(){                                              // keep the camera and the picked roads over the reload
    sessionStorage.setItem("lv-view", JSON.stringify({c: map.getCenter(), z: map.getZoom(), b: map.getBearing(), p: map.getPitch(),
                                                     sel: sel.map(s => s && s.road)}));
    location.reload();
  }
  async function change(path, body){ msg("solving …", true); try { await api(path, body); reload(); } catch(err){ msg(err.message); } }
  async function pairs(){
    const box = $("lv-pairs");
    if(!(sel[0] && sel[1])) { box.innerHTML = "<small>pick two roads</small>"; return; }
    try {
      const j = await api(`/api/pairs?a=${encodeURIComponent(sel[0].road)}&b=${encodeURIComponent(sel[1].road)}`);
      const who = r => r === sel[0].road ? "1" : "2";
      const txt = r => r.relation === "meet" ? `meet: ${who(r.a)} ${r.a_end} = ${who(r.b)} ${r.b_end}` : `${r.relation}: ${who(r.a)} over ${who(r.b)}`;
      box.innerHTML = "";
      j.found.forEach(r => { const d = document.createElement("div"); d.className = "row";
        d.innerHTML = `<span>${txt(r)} <small>found</small></span>`; const b = document.createElement("button"); b.textContent = "switch off";
        b.onclick = () => change("/api/add", {...r, enabled: "false"}); d.appendChild(b); box.appendChild(d); });
      j.edits.forEach(r => { const d = document.createElement("div"); d.className = "row";
        d.innerHTML = `<span>${r.enabled === "false" ? "off: " : ""}${txt(r)} <small>edit #${r.index + 1}</small></span>`;
        const b = document.createElement("button"); b.textContent = "delete"; b.onclick = () => change("/api/delete", {index: r.index});
        d.appendChild(b); box.appendChild(d); });
      if(!j.found.length && !j.edits.length) box.innerHTML = "<small>none: they neither meet nor stack</small>";
    } catch(err){ box.innerHTML = `<small>${err.message}</small>`; }
  }
  async function list(){
    const ol = $("lv-list"); ol.innerHTML = "";
    const rows = await api("/api/edits");
    if(!rows.length){ ol.innerHTML = "<small>none yet</small>"; return; }
    rows.forEach(r => { const li = document.createElement("li");
      li.textContent = `${r.enabled === "false" ? "switch off " : ""}${r.relation} ${r.a} ${r.a_end || ""} · ${r.b} ${r.b_end || ""}`;
      li.title = "show these two roads";
      li.onclick = () => { const a = rsQuery(p => String(p.road) === r.a || (p.edge_ref && p.edge_ref === r.a));
        const b = rsQuery(p => String(p.road) === r.b || (p.edge_ref && p.edge_ref === r.b));
        sel[0] = pick(a); sel[1] = pick(b); show(); rsFocus([...a, ...b]); };
      ol.appendChild(li); });
  }
  $("lv-add").onclick = () => {
    if(!(sel[0] && sel[1])) return msg("pick two roads first");
    const rel = $("lv-rel").value, e1 = document.querySelector("input[name=lv-e1]:checked").value, e2 = document.querySelector("input[name=lv-e2]:checked").value;
    change("/api/add", {relation: rel, a: sel[0].road, b: sel[1].road, a_end: rel === "meet" ? e1 : "", b_end: rel === "meet" ? e2 : "", enabled: "true"});
  };
  $("lv-swap").onclick = () => { sel.reverse(); show(); };
  $("lv-clear").onclick = () => { sel[0] = sel[1] = null; show(); msg(""); };
  function start(){
    const v = JSON.parse(sessionStorage.getItem("lv-view") || "null");
    if(v){ map.jumpTo({center: v.c, zoom: v.z, bearing: v.b, pitch: v.p});
      v.sel.forEach((r, k) => { if(r) sel[k] = pick(rsQuery(p => String(p.road) === r)); }); sessionStorage.removeItem("lv-view"); }
    show(); list();
  }
  if(map.loaded()) start(); else map.once("load", start);
})();
</script>
"""


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
