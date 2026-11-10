// The page script of examples/vehicles/dashboard.html: the example's own play bar (the dashboard parts of phase P5 replace it). The page
// loads the run itself, from its option `vehicles` (roadstyle page ... --vehicles '{"wasm": ..., "fcd": ..., "net": ...}').
rs.ready(async () => {
  const report = rs.vehicles.report() || await new Promise((r) => document.addEventListener("rs:vehicleload", (e) => r(e.detail), {once: true}));
  const bar = document.createElement("div");
  bar.style.cssText = "position:absolute;bottom:28px;transform:translateX(-50%);z-index:5;display:flex;gap:8px;" +
    "align-items:center;padding:6px 10px;border-radius:8px;background:var(--card);color:var(--ink);border:1px solid var(--line);font:13px system-ui,sans-serif";
  bar.innerHTML = '<button data-a="play">Play</button><input data-a="seek" type="range" step="0.5" style="width:260px">' +
    '<span data-a="clock">0:00</span><button data-s="1">1×</button><button data-s="4">4×</button><button data-s="16">16×</button><span data-a="n"></span>';
  bar.querySelectorAll("button").forEach((b) => b.style.cssText = "font:inherit;padding:3px 10px;cursor:pointer;background:var(--bg);" +
    "color:var(--ink);border:1px solid var(--line);border-radius:6px");
  document.body.appendChild(bar);
  // the bar in the middle of the free part of the map (not under the panel or the toolbar)
  const place = () => { const f = rs.freeArea(); bar.style.left = `${(f.lo + f.hi) / 2}px`; };
  place(); addEventListener("resize", place); map.on("resize", place);
  const $ = (a) => bar.querySelector(`[data-a="${a}"]`);
  const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
  $("seek").min = report.t0; $("seek").max = report.t1;
  $("play").onclick = () => { rs.vehicles.playing() ? rs.vehicles.pause() : rs.vehicles.play(); $("play").textContent = rs.vehicles.playing() ? "Pause" : "Play"; };
  $("seek").oninput = (e) => rs.vehicles.seek(+e.target.value);
  bar.querySelectorAll("[data-s]").forEach((b) => b.onclick = () => rs.vehicles.speed(+b.dataset.s));
  document.addEventListener("rs:vehicletime", (e) => {
    $("clock").textContent = fmt(e.detail.t); $("seek").value = e.detail.t; $("n").textContent = `${rs.vehicles.count()} vehicles`;
    if(!rs.vehicles.playing()) $("play").textContent = "Play";
  });
  rs.vehicles.seek(300);   // a time with many vehicles on the network
  // the page fits the roads first; the example's view after that
  await new Promise((r) => map.loaded() ? r() : map.once("idle", r));
  map.jumpTo({center: [7.4246, 43.7384], zoom: 16.5, pitch: 55, bearing: -20});
  place();
});
