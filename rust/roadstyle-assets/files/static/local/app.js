// The page of `roadstyle local` (way D): the standard dashboard with the adapter of way D (dashboard/adapter.js, rsHttpAdapter). The program that serves
// this page answers the four requests at addresses on its own origin: the style and the tiles of the roads, the rows and the lines of a road, and the
// queries of the data dock. The page keeps no road table.
import {rsDashboard} from "../dashboard/index.js";
import {httpAdapter} from "../dashboard/adapter.js";
import {rsFirstPaint} from "../dashboard/template.js";
import {dataDock} from "../dashboard/data/data_dock.js";

const adapter = httpAdapter(location.origin);
const opts = await (await fetch("../host_options.json")).json();
rsFirstPaint(opts.first_paint);
const style = await adapter.style();
const [w, s, e, n] = style.metadata["roadstyle:bounds"];
const map = new maplibregl.Map({container: "map", style: opts.style, bounds: [[w, s], [e, n]], fitBoundsOptions: {padding: 40}, attributionControl: {compact: true}});
window.map = map;
const rs = rsDashboard(map, {style: null, prefix: "rs-", tiles: true, simple: "roads-simple", adapter, basemaps: opts.basemaps, ontop: opts.ontop,
                             dashboard: {...opts.dashboard, panel: null}});
await new Promise(done => map.loaded() ? done() : map.once("load", done));
await rs.roadLayers({prefix: "rs-"}).show(style);              // the roads, with the tile addresses of the program
window.data = dataDock({dashboard: rs, sql: "SELECT * FROM roads LIMIT 100"});     // the queries of the adapter
window.rsLocalReady = true;
