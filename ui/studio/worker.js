// The studio's engine, in a Web Worker so the page does not freeze: roadstyle's Rust engine (rust/roadstyle-wasm, `npm run build`). It keeps
// the roads (a GeoParquet file) and makes, for each set of knobs, the look and stage 1 (the style, its sources and the road table) and,
// with tiles, stage 2. Every call of the look is here (makeLook, and the look given to makeSources): the page sends only plain options.
// Messages: {type: "roads", bytes} -> {}; {type: "build", options, name, tiles, keep, gen} -> {style, table, files};
// {type: "tile", source, z, x, y} -> {bytes}. Every answer has the message's id, and ok or error.
import init, {makeLook, makeSources, tileSources} from "../../rust/roadstyle-wasm/pkg/roadstyle_wasm.js";

const ready = init();
let roads = null, tiler = null;
const text = (b) => new TextDecoder().decode(b);

onmessage = async (e) => {
  const m = e.data;
  try {
    await ready;
    if (m.type === "roads") {
      roads = new Uint8Array(m.bytes);
      postMessage({id: m.id, ok: true});
    } else if (m.type === "build") {
      const t0 = performance.now();
      const look = makeLook(JSON.stringify(m.options));
      const sources = makeSources(roads, look, undefined, undefined, m.name);
      const table = text(sources.roadTable());
      const files = {}, transfer = [];
      let style;
      if (m.tiles) {                                     // stage 2 from memory: the one vector source, its tiles asked for one by one
        tiler = tileSources(sources, `rs://${m.gen}/`, m.keep);
        style = JSON.parse(tiler.style());
      } else {                                           // the GeoJSON sources, as bytes: the page gives them to MapLibre as Blob URLs
        tiler = null;
        style = JSON.parse(text(sources.file("style.json", "geojson", [])));
        for (const src of Object.values(style.sources)) {
          if (typeof src.data !== "string") continue;
          const b = sources.file(src.data, "geojson", []);
          files[src.data] = b;
          transfer.push(b.buffer);
        }
      }
      postMessage({id: m.id, ok: true, style, table, files, ms: performance.now() - t0}, transfer);
    } else if (m.type === "tile") {
      const b = tiler ? tiler.tile(m.source, m.z, m.x, m.y) : new Uint8Array();
      postMessage({id: m.id, ok: true, bytes: b}, [b.buffer]);
    }
  } catch (err) {
    postMessage({id: m.id, ok: false, error: String((err && err.message) || err)});
  }
};
