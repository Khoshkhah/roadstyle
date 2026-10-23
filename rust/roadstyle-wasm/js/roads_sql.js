// The only copy of this file (docs/design/rust_engine.md): geolibre-roadstyle and duckosm-rust take it from the same roadstyle commit as
// the engine, roadstyle-rs. Change it here, not in a copy.
//
// The option {levels: "tags"}: the drawing levels come from roadstyle's compute_levels(method="tags") in SQL, not from
// visualization.edge_levels; and the stored levels can also come from duckosm-rust (edge_levels_meta.source "tags" or "solve", no level
// area; duckosm-rust's docs/levels.md).
//
// Step 1 of the full port (geolibre-roadstyle's docs/design/rust-spike.md): the roads table that the Rust module reads, made by duckdb-wasm from a duckOSM file.
// The SQL of mapstyle.map (_roads_union, load_roads), the checks of roadstyle's load_area_levels and the columns that render_map adds
// (the stored levels, access, is_directed, has_arrows), for the map of a mode (render_map's mode: "all" or one network). The result is
// written as roads.parquet.

const MODES = ["driving", "walking", "cycling"];
const OPTIONAL_COLS = ["walk_type", "junction", "edge_ref", "lanes"];
const PATH_CLASSES = ["footway", "path", "cycleway", "steps", "pedestrian", "bridleway", "corridor"];
const COLS = "edge_id, source, target, osm_id, highway, name, bridge, tunnel, layer, oneway, geometry";

// _roads_union: every mode's edges and private_edges, NULL for an optional column a file does not have
async function roadsUnion(q, catalog) {
  const tables = await q(`SELECT table_schema AS s, table_name AS t FROM information_schema.tables WHERE table_catalog = '${catalog}'`);
  const has = new Set((await q(`SELECT table_schema AS s, table_name AS t, column_name AS c FROM information_schema.columns WHERE table_catalog = '${catalog}'`))
    .map((r) => `${r.s}.${r.t}.${r.c}`));
  const edges = new Set(tables.filter((r) => r.t === "edges").map((r) => r.s));
  const modes = MODES.filter((m) => edges.has(m));
  if (!modes.length) throw new Error(`no <mode>.edges table (modes: ${MODES.join(", ")})`);
  const priv = [...new Set(tables.filter((r) => r.t === "private_edges" && modes.includes(r.s)).map((r) => r.s))].sort();
  const optional = (m, t, skip = []) => OPTIONAL_COLS.map((c) =>
    `${has.has(`${m}.${t}.${c}`) && !skip.includes(c) ? c : (c === "edge_ref" ? "CAST(NULL AS VARCHAR)" : "NULL")} AS ${c}`).join(", ");
  return [
    ...modes.map((m) => `SELECT ${COLS}, ${optional(m, "edges")}, '${m}' AS mode, NULL AS pmode, NULL AS access FROM ${m}.edges`),
    ...priv.map((m) => `SELECT ${COLS}, ${optional(m, "private_edges", ["walk_type"])}, NULL AS mode, '${m}' AS pmode, access FROM ${m}.private_edges`),
  ].join(" UNION ALL ");
}

// load_area_levels' checks: the stored levels are from a level area (or from duckosm-rust: "tags", "solve") and were made for these edges
// (their number and the hash of their ids)
async function checkLevels(q) {
  let meta;
  try {
    meta = (await q("SELECT source, n_edges, edge_hash FROM visualization.edge_levels_meta"))[0];
  } catch (e) {
    throw new Error("no visualization.edge_levels_meta in this file: make and solve its level area (duckosm levels)");
  }
  if (!meta || !["area", "tags", "solve"].includes(meta.source)) throw new Error("the stored levels are not from a level area: make and solve its level area again");
  const ids = (await q("SELECT eid FROM r ORDER BY eid")).map((r) => BigInt(r.eid));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new BigInt64Array(ids).buffer));     // _hash: sha256 of the sorted int64 ids
  const hash = [...digest].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
  if (ids.length !== Number(meta.n_edges) || hash !== meta.edge_hash)
    throw new Error(`the edges are not the edges the stored levels were solved for (${ids.length} given, ${Number(meta.n_edges)} stored, or other edge_id values): run duckosm levels again`);
}

// roadstyle's compute_levels(method="tags"): L = a non-zero layer, else bridge 1, tunnel -1, else 0 (_level); N(v) = the value of
// [min L, max L] of the edges at node v nearest 0; casing_start = casing_level = casing_end = min(N(s), N(t), L), fill_level = the max
// (_tag_intervals). The heads and caps stay NULL, as in roadstyle.
const TRUTHY = (c) => `(${c} IS NOT NULL AND CAST(${c} AS VARCHAR) NOT IN ('', 'no', 'false', '0'))`;
const TAG_LEVELS = `CREATE OR REPLACE TEMP TABLE lv AS
  WITH e AS (SELECT eid, s, t, CASE WHEN coalesce(CAST(trunc(TRY_CAST(layer AS DOUBLE)) AS INTEGER), 0) <> 0
                                    THEN CAST(trunc(TRY_CAST(layer AS DOUBLE)) AS INTEGER)
                                    WHEN ${TRUTHY("bridge")} THEN 1 WHEN ${TRUTHY("tunnel")} THEN -1 ELSE 0 END AS l FROM r),
       n AS (SELECT v, least(greatest(0, min(l)), max(l)) AS nv FROM (SELECT s AS v, l FROM e UNION ALL SELECT t, l FROM e) GROUP BY v)
  SELECT e.eid AS edge_id, least(ns.nv, nt.nv, e.l) AS casing_start, least(ns.nv, nt.nv, e.l) AS casing_level,
         least(ns.nv, nt.nv, e.l) AS casing_end, greatest(ns.nv, nt.nv, e.l) AS fill_level,
         CAST(NULL AS DOUBLE) AS head_start_m, CAST(NULL AS DOUBLE) AS head_end_m, CAST(NULL AS BOOLEAN) AS cap_start, CAST(NULL AS BOOLEAN) AS cap_end
  FROM e JOIN n ns ON ns.v = e.s JOIN n nt ON nt.v = e.t`;

// q(sql) -> rows as plain objects; mode: "all", "driving", "walking" or "cycling". Writes roads.parquet in duckdb-wasm's file system.
// opts.levels: "stored" (visualization.edge_levels of a solved level area, checked) or "tags" (the tags rule above).
export async function writeRoads(q, catalog, mode = "all", opts = {}) {
  const tags = opts.levels === "tags";
  if (mode !== "all" && !MODES.includes(mode)) throw new Error(`unknown mode ${mode}`);
  const union = await roadsUnion(q, catalog);
  const first = (c) => `first(${c} ORDER BY mode IS NULL, mode, pmode)`;
  await q(`CREATE OR REPLACE TEMP TABLE r AS
    SELECT CAST(edge_id AS VARCHAR) AS edge_id, edge_id AS eid, any_value(source) AS s, any_value(target) AS t,
           CAST(${first("osm_id")} AS VARCHAR) AS osm_id, ${first("highway")} AS highway, COALESCE(${first("name")}, '') AS name,
           ${first("bridge")} AS bridge, ${first("tunnel")} AS tunnel, ${first("layer")} AS layer, bool_or(oneway) AS oneway,
           any_value(walk_type) AS walk_type,
           ${OPTIONAL_COLS.slice(1).map((c) => `${first(c)} AS ${c}`).join(", ")},
           ${MODES.map((m) => `COALESCE(bool_or(mode = '${m}'), false) AS ${m}`).join(", ")},
           ${MODES.map((m) => `max(CASE WHEN pmode = '${m}' THEN access END) AS access_${m}`).join(", ")},
           ${first("geometry")} AS geom
    FROM (${union}) GROUP BY edge_id`);
  if (tags) await q(TAG_LEVELS);
  else await checkLevels(q);
  const path = `coalesce(highway IN (${PATH_CLASSES.map((c) => `'${c}'`).join(", ")}), false)`;
  const restricted = "coalesce(access IN ('private', 'bus'), false)";
  await q(`COPY (
    WITH x AS (SELECT r.* EXCLUDE (s, t, geom), ST_AsWKB(r.geom) AS geometry FROM r),
    -- load_roads: an undirected edge (a one-way street's walking-only reverse) on the street's own directed edge goes first
    u AS (SELECT *, NOT driving AND NOT cycling AND NOT ${path} AND osm_id IN (SELECT osm_id FROM x WHERE driving OR cycling) AS und FROM x),
    -- _access: in one mode, its restriction where that mode can't use the road; mode "all": bus for a bus road or lane for cars, else the
    -- first restriction where no mode can use the road
    a AS (SELECT u.*, ${mode !== "all" ? `CASE WHEN NOT ${mode} THEN access_${mode} END` : `CASE WHEN access_driving = 'bus' THEN access_driving
                           WHEN NOT (driving OR walking OR cycling) AND (access_driving IS NOT NULL OR access_walking IS NOT NULL OR access_cycling IS NOT NULL)
                           THEN coalesce(access_driving, access_walking, access_cycling) END`} AS access FROM u)
    SELECT a.* EXCLUDE (eid, und, access_driving, access_walking, access_cycling),
           lv.casing_start, lv.casing_level, lv.casing_end, lv.fill_level, lv.head_start_m, lv.head_end_m, lv.cap_start, lv.cap_end,
           (driving OR cycling OR ${restricted}) AND NOT ${path} AS is_directed,     -- _is_directed
           driving OR ${restricted} AS has_arrows
    FROM a LEFT JOIN ${tags ? "lv" : "visualization.edge_levels"} lv ON lv.edge_id = a.eid
    ORDER BY NOT und, a.eid) TO 'roads.parquet' (FORMAT parquet)`);
}
