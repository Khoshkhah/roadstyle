// A Run button under each `javascript` block of the dashboard manual (docs/guides/dashboard-manual/javascript.md). Run opens a large window over the
// page with the testbed map (its desktop form, at any width of the docs page), runs the block in the map's window, and shows what the block logs under
// the map (2026-11-06: the map at the top of the page was 688 px wide, its phone form, and its bottom sheet hid the change). The panel shows only for a
// block that uses it; else the map's own hide button folds it, so that the map has the room.
(function () {
  const frame = document.getElementById("rs-testbed");
  if (!frame) return;
  const back = document.createElement("div"), win = document.createElement("div");
  back.id = "rs-tb-back"; win.id = "rs-tb-win"; win.setAttribute("role", "dialog"); win.setAttribute("aria-label", "The result on the map");
  win.innerHTML = '<div class="rs-tb-head"><b>Result</b><span class="rs-tb-what"></span><button type="button" class="rs-tb-x" aria-label="Close">✕</button></div>'
    + '<div class="rs-tb-map"></div><pre class="rs-tb-out"></pre>';
  document.body.append(back, win);
  win.querySelector(".rs-tb-map").append(frame);               // the map lives in the window: it loads once, at the window's size
  const close = () => document.documentElement.classList.remove("rs-tb-open");
  back.onclick = close; win.querySelector(".rs-tb-x").onclick = close;
  document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  let dirty = false;                                            // the map has run a block, or has failed to load: reload it before the next one
  const reload = () => new Promise(done => { frame.addEventListener("load", done, {once: true}); frame.contentWindow.location.reload(); });
  const ready = () => new Promise((done, fail) => {
    const t0 = Date.now(), t = setInterval(() => {
      let w = null;
      try { w = frame.contentWindow; if (w && w.rsReady) { clearInterval(t); done(w); return; } } catch (e) { /* another origin: not our map */ }
      if (Date.now() - t0 > 20000) { clearInterval(t); fail(new Error("the map did not load. Is " + frame.getAttribute("src") + " on the server?")); }
    }, 100);
  });
  const text = x => { try { return typeof x === "string" ? x : JSON.stringify(x); } catch (e) { return String(x); } };
  const PANEL = /rs\.(sections|help|kpi|tabs|frame)\b/;           // a block that puts something in the panel keeps it open
  const titleOf = block => { for (let h = block; h; h = h.previousElementSibling || h.parentElement) if (/^H[23]$/.test(h.tagName)) return h.textContent.replace("¶", "").trim(); return ""; };
  document.querySelectorAll(".md-typeset .language-javascript").forEach(block => {
    const code = block.querySelector("code").textContent;
    const bar = document.createElement("div"), btn = document.createElement("button");
    bar.className = "rs-run-bar"; btn.className = "md-button rs-run"; btn.textContent = "Run"; bar.append(btn); block.after(bar);
    btn.onclick = async () => {
      const out = win.querySelector(".rs-tb-out"), lines = [];
      win.querySelector(".rs-tb-what").textContent = titleOf(block);
      document.documentElement.classList.add("rs-tb-open"); out.classList.remove("error"); out.textContent = "Loading the map...";
      btn.disabled = true;
      try {
        if (dirty) await reload();
        dirty = true;
        const w = await ready();
        if (!w.__rsTbKey) { w.__rsTbKey = true; w.document.addEventListener("keydown", e => { if (e.key === "Escape") close(); }); }   // the keys go to the map's page after a click in it
        if (!PANEL.test(code)) w.document.getElementById("sb-hide")?.click();      // the map's own hide button: the "show panel" button stays
        w.console.log = (...a) => lines.push(a.map(text).join(" "));
        await new w.Function("return (async () => {" + code + "\n})()")();          // runs in the map's window: `rs` and `document` are the map's
        out.textContent = lines.join("\n") || "Done: see the map.";
      } catch (e) {
        out.classList.add("error"); out.textContent = lines.concat("Error: " + e.message).join("\n");
      }
      btn.disabled = false;
    };
  });
})();
