// A Run button under each `javascript` block of the dashboard manual (docs/guides/dashboard-manual/javascript.md).
// It reloads the testbed map, runs the block in the map's window, and shows what the block logs.
(function () {
  const frame = document.getElementById("rs-testbed");
  if (!frame) return;
  let dirty = false;                                            // the map has run a block, or has failed to load: reload it before the next one
  const reload = () => new Promise(done => { frame.addEventListener("load", done, {once: true}); frame.contentWindow.location.reload(); });
  // the map's window when the page is ready; an error after 20 s (a missing file gives a page that is never ready)
  const ready = () => new Promise((done, fail) => {
    const t0 = Date.now(), t = setInterval(() => {
      let w = null;
      try { w = frame.contentWindow; if (w && w.rsReady) { clearInterval(t); done(w); return; } } catch (e) { /* another origin: not our map */ }
      if (Date.now() - t0 > 20000) { clearInterval(t); fail(new Error("the map did not load. Is " + frame.getAttribute("src") + " on the server?")); }
    }, 100);
  });
  const text = x => { try { return typeof x === "string" ? x : JSON.stringify(x); } catch (e) { return String(x); } };
  document.querySelectorAll(".md-typeset .language-javascript").forEach(block => {
    const code = block.querySelector("code").textContent;
    const bar = document.createElement("div"), btn = document.createElement("button"), out = document.createElement("pre");
    bar.className = "rs-run-bar"; btn.className = "md-button rs-run"; btn.textContent = "Run"; out.className = "rs-run-out"; out.hidden = true;
    bar.append(btn, out); block.after(bar);
    btn.onclick = async () => {
      btn.disabled = true; out.hidden = false; out.classList.remove("error"); out.textContent = "Loading the map...";
      const lines = [];
      try {
        if (dirty) await reload();
        dirty = true;                                           // a failure below leaves it set: the next push reloads the map
        const w = await ready();
        w.console.log = (...a) => lines.push(a.map(text).join(" "));
        await new w.Function("return (async () => {" + code + "\n})()")();                  // runs in the map's window: `rs` and `document` are the map's
        out.textContent = lines.join("\n") || "Done.";
      } catch (e) {
        out.classList.add("error"); out.textContent = lines.concat("Error: " + e.message).join("\n");
      }
      btn.disabled = false;
    };
  });
})();
