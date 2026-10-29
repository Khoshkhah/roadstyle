// the tunnel look, v2's slider (docs/design/tunnel_look.md): TUNNEL.strength 0-100 moves a tunnel's colours toward TUNNEL.to.fill.
// The expressions that do it are made in Python and read the state (rs_tun_*); rsSetTunnelStyle only sets it.
import {map, O, _emit} from "./core.js";
import {_tlHost} from "./panel.js";
export let TUNNEL = {layers:{}};
export let _tunOn = false;
// window.rsSetTunnelStyle({strength, palette, ratio, toward}) moves the tunnel look (strength 0-100; palette a name of RS_TUNNEL_PALETTES;
// ratio [dash, gap] in line widths); the Tunnels box is UI over it. The casing follows the slider like everything on a tunnel: its
// two colours, each moved toward slate by the strength, are two layers with MapLibre's own dash (crisp, and only paint changes: no image,
// no tile reload): the position's casing layer draws the gap colour (transparent for "One colour"), the dash layer the dashes on top.
export function rsSetTunnelStyle(o){
  if(!_tunOn) return;
  o = o || {};
  if(o.strength != null) TUNNEL.strength = Math.max(0, Math.min(100, +o.strength));
  if(o.palette != null && o.palette in TUNNEL.palettes) TUNNEL.palette = o.palette;
  if(o.ratio != null) TUNNEL.ratio = o.ratio.map(Number);
  if(o.toward != null){                          // a name of RS_TUNNEL_TOWARDS or a "#rrggbb"
    const c = o.toward in TUNNEL.towards ? TUNNEL.towards[o.toward] : (/^#[0-9a-f]{6}$/i.test(o.toward) ? o.toward : null);
    if(!c) throw new Error("rsSetTunnelStyle: toward must be one of "+Object.keys(TUNNEL.towards).join(", ")+" or '#rrggbb', got "+JSON.stringify(o.toward));
    TUNNEL.toward = o.toward; TUNNEL.to.fill = c; }
  const pair = TUNNEL.palettes[TUNNEL.palette];   // the casing's two colours ("One colour": none, empty gaps)
  const st = {rs_tun_strength: TUNNEL.strength, rs_tun_toward: TUNNEL.to.fill, rs_tun_two: !!pair,
              rs_tun_c0: pair ? pair[0] : TUNNEL.to.dash, rs_tun_c1: pair ? pair[1] : TUNNEL.to.dash, rs_tun_ratio: TUNNEL.ratio.map(Number)};
  for(const k in st) map.setGlobalStateProperty(k, st[k]);
  const r=document.getElementById("tn-str"), v=document.getElementById("tn-val"), s=document.getElementById("tn-pal"),
        q=document.getElementById("tn-ratio"), tw=document.getElementById("tn-toward"), pr=document.getElementById("tn-pre");
  if(r) r.value = _tnStep(TUNNEL.strength); if(v) v.textContent = Math.round(TUNNEL.strength)+"%"; if(s) s.value = TUNNEL.palette;
  if(tw) tw.value = TUNNEL.toward;
  if(q) q.value = TUNNEL.ratio.join(":"); if(pr) pr.value = String(TUNNEL.strength);
  _emit("rs:tunnelchange", {strength:TUNNEL.strength, palette:TUNNEL.palette, ratio:TUNNEL.ratio, toward:TUNNEL.toward});
}
let _TN_STEPS = [];       // one slider for every colour (the profile's tunnels.steps)
const _tnStep = v => _TN_STEPS.reduce((b, [x], i)=> Math.abs(x - v) < Math.abs(_TN_STEPS[b][0] - v) ? i : b, 0);   // the nearest step
let _tnBox = null;
// the tunnel look of the style of the moment: at the start, and again for a new style (rs.setStyle). The look that the person chose stays
export function initTunnel(){
  const old = _tunOn && TUNNEL;
  TUNNEL = O.tunnel; _tunOn = Object.keys(TUNNEL.layers).length > 0;
  if(_tnBox){ _tnBox.remove(); _tnBox = null; }
  window.rsSetTunnelStyle = rsSetTunnelStyle;
  window.RS_TUNNEL_PALETTES = TUNNEL.palettes;
  window.RS_TUNNEL_TOWARDS = TUNNEL.towards;
  _TN_STEPS = TUNNEL.steps.map(v=>[v, String(v)]);
  if(TUNNEL.control){
    const w=document.createElement("div"); w.className="tn-ctrl";
    const sel=(id, opts, val, on)=>{ const e=document.createElement("select"); e.id=id;
      opts.forEach(([v, t])=>{ const op=document.createElement("option"); op.value=v; op.textContent=t; e.appendChild(op); });
      e.value=val; e.onchange=()=>on(e.value); return e; };
    const row=()=>{ const d=document.createElement("div"); d.className="tn-row"; w.appendChild(d); return d; };
    const r1=row(); r1.appendChild(document.createTextNode("Tunnels"));
    r1.appendChild(sel("tn-pre", _TN_STEPS.map(([v, t])=>[String(v), t]), String(TUNNEL.strength),
                       v=>rsSetTunnelStyle({strength:+v})));
    const r2=row();
    // five steps, the presets (2026-10-06: the smooth slider did not work well); its value is the step's index
    const r=document.createElement("input"); r.type="range"; r.id="tn-str"; r.min=0; r.max=_TN_STEPS.length-1; r.step=1; r.value=_tnStep(TUNNEL.strength);
    r.title="Tunnel style: Normal colors keeps the normal colours, Full applies the tunnel colours";
    r.oninput=()=>rsSetTunnelStyle({strength: _TN_STEPS[+r.value][0]});
    const val=document.createElement("span"); val.id="tn-val"; val.textContent=Math.round(TUNNEL.strength)+"%";
    r2.appendChild(r); r2.appendChild(val);
    r1.appendChild(sel("tn-toward", [...Object.keys(TUNNEL.towards), ...(TUNNEL.toward in TUNNEL.towards ? [] : [TUNNEL.toward])].map(n=>[n, n]), TUNNEL.toward, v=>rsSetTunnelStyle({toward:v})));
    const r3=row();
    r3.appendChild(sel("tn-pal", Object.keys(TUNNEL.palettes).map(n=>[n, n]), TUNNEL.palette, v=>rsSetTunnelStyle({palette:v})));
    r3.appendChild(sel("tn-ratio", TUNNEL.ratios.map(r=>[r.join(":"), r.join(":")]), TUNNEL.ratio.join(":"),
                       v=>rsSetTunnelStyle({ratio:v.split(":")})));
    _tlHost().appendChild(w);
    _tnBox = w;
  }
  if(old && _tunOn) rsSetTunnelStyle({strength: old.strength, palette: old.palette, ratio: old.ratio, toward: old.toward});
}
