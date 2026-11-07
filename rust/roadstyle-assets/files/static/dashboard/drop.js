// The file drop zone of a page (docs/design/dashboard_parts_2.md): a dashed box that takes a file by drag and drop or by a click (the browser's file
// window), and then shows the file's name and size with a button that takes it away.
//   const f = rs.drop(el, {accept: ".pbf,.osm", text: "Drop an .osm.pbf file here", hint: "Up to 2 GB", onFiles: files => load(files[0])});
// `multiple: true` takes more files. It returns {files(), clear()}. `onClear()` comes when the person takes the file away.
const _drIcon = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V4m0 0L7.5 8.5M12 4l4.5 4.5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>';
const _drFile = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>';
export const rsBytes = n => n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : n < 1073741824 ? (n / 1048576).toFixed(1) + " MB" : (n / 1073741824).toFixed(2) + " GB";
export function rsDrop(el, opts = {}){
  if(!(el instanceof Element)) throw new Error("rs.drop: give the element that the drop zone goes in");
  el.classList.add("rs-drop");
  el.innerHTML = '<button type="button" class="rs-drop-zone">' + _drIcon + '<span class="rs-drop-t"></span><span class="rs-drop-h"></span></button>' +
    '<div class="rs-drop-files" hidden></div><input type="file" hidden>';
  const zone = el.querySelector(".rs-drop-zone"), shown = el.querySelector(".rs-drop-files"), inp = el.querySelector("input");
  el.querySelector(".rs-drop-t").innerHTML = opts.text || (opts.multiple ? "Drop files here, or <u>choose files</u>" : "Drop a file here, or <u>choose a file</u>");
  el.querySelector(".rs-drop-h").textContent = opts.hint || "";
  if(opts.accept) inp.accept = opts.accept;
  inp.multiple = !!opts.multiple;
  let files = [];
  function take(list){
    files = [...list]; if(!opts.multiple) files = files.slice(0, 1);
    if(!files.length) return;
    shown.innerHTML = files.map((f, i) => '<div class="rs-drop-file">' + _drFile + '<b></b><span></span>' +
      (i === 0 ? '<button type="button" class="rs-drop-x" aria-label="Take the file away">×</button>' : "") + "</div>").join("");
    files.forEach((f, i) => { const r = shown.children[i]; r.querySelector("b").textContent = f.name; r.querySelector("span").textContent = rsBytes(f.size); });
    shown.hidden = false; el.classList.add("rs-drop-has");
    opts.onFiles?.(files);
  }
  function clear(){ files = []; inp.value = ""; shown.hidden = true; shown.innerHTML = ""; el.classList.remove("rs-drop-has"); }
  zone.addEventListener("click", () => inp.click());
  inp.addEventListener("change", () => take(inp.files));
  shown.addEventListener("click", e => { if(e.target.closest(".rs-drop-x")){ clear(); zone.focus(); opts.onClear?.(); } });
  let depth = 0;                                      // dragenter and dragleave come for each child: count them
  el.addEventListener("dragenter", e => { e.preventDefault(); depth++; el.classList.add("rs-drop-over"); });
  el.addEventListener("dragleave", () => { if(--depth <= 0){ depth = 0; el.classList.remove("rs-drop-over"); } });
  el.addEventListener("dragover", e => e.preventDefault());
  el.addEventListener("drop", e => { e.preventDefault(); depth = 0; el.classList.remove("rs-drop-over"); take(e.dataTransfer.files); });
  return {files: () => files, clear};
}
