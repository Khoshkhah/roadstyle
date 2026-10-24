// The level editor of `roadstyle serve` (index.html): the module dashboard/editor/level_editor.js on the area that the server gives
// under /area/ and saves with a PUT (httpStore), on a map of its own.
import {levelEditor, httpStore} from "../dashboard/editor/level_editor.js";

await levelEditor({container: document.body, pkgUrl: new URL("./pkg/roadstyle_wasm.js", import.meta.url), store: httpStore("/area/")});
document.getElementById("lv-boot").remove();
