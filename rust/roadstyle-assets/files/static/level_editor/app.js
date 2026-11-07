// The level editor of `roadstyle serve` (index.html): the module dashboard/editor/level_editor.js on the area that the server gives
// under /area/ and saves with a PUT (httpStore), on a map of its own. The area folder is beside this page's folder (a relative address: the
// docs site has it under live/area/, docs/copy_parts.py). With ?store=page (the docs' live editor, on a site that saves nothing) the page
// reads the area from there and keeps each change in the page only, until a reload. The page is a host of the standard dashboard: its template
// (host_options.json), its panel (#sb with .sb-card, .sb-top and .sb-body) that the editor draws into, and the hide and show buttons.
import {levelEditor, httpStore} from "../dashboard/editor/level_editor.js";

const area = httpStore(new URL("../area/", location.href).href);
const kept = new Map();                                          // ?store=page: the files that the page changed
const store = new URLSearchParams(location.search).get("store") === "page"
  ? {...area, load: async (n, bytes) => kept.has(n) ? {body: kept.get(n), mtime: Date.now() / 1000} : area.load(n, bytes), save: async (n, data) => { kept.set(n, data); }}
  : area;
import {rsFirstPaint} from "../dashboard/template.js";

const opts = await (await fetch("../host_options.json")).json();
opts.dashboard.panel.hide = [];                                  // none of roadstyle's own panel sections (the editor's panel has none of them)
rsFirstPaint(opts.first_paint);
const sb = document.getElementById("sb"), show = document.getElementById("sb-show");
document.getElementById("sb-hide").onclick = () => { sb.classList.add("hidden"); show.style.display = "flex"; };
show.onclick = () => { sb.classList.remove("hidden"); show.style.display = ""; };

// backLabel null: this page has no steps to go back to, so no "back" button
await levelEditor({container: document.body, panel: sb, backLabel: null, template: opts.dashboard, basemaps: opts,
  pkgUrl: new URL("./pkg/roadstyle_wasm.js", import.meta.url), store});
document.getElementById("lv-boot").remove();
