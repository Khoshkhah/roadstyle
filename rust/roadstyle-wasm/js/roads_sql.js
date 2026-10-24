// The only copy of this file (docs/design/rust_engine.md): geolibre-roadstyle and duckosm-rust take it from the same roadstyle commit as
// the engine, roadstyle-rs. Change it here, not in a copy.
//
// The option {levels: "tags"}: the engine computes the drawing levels with roadstyle's compute_levels(method="tags"), not from
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

// The stored levels' metadata: they are from a level area (or from duckosm-rust: "tags", "solve"). The engine checks that they were made
// for these edges (their number and the hash of their ids: roadstyle-levels' edge_hash).
async function levelsMeta(q) {
  let meta;
  try {
    meta = (await q("SELECT source, n_edges, edge_hash FROM visualization.edge_levels_meta"))[0];
  } catch (e) {
    throw new Error("no visualization.edge_levels_meta in this file: make and solve its level area (duckosm levels)");
  }
  if (!meta || !["area", "tags", "solve"].includes(meta.source)) throw new Error("the stored levels are not from a level area: make and solve its level area again");
  return { edge_hash: meta.edge_hash, n_edges: Number(meta.n_edges) };
}

const NO_LEVELS = `CAST(NULL AS INTEGER) AS casing_start, CAST(NULL AS INTEGER) AS casing_level, CAST(NULL AS INTEGER) AS casing_end,
  CAST(NULL AS INTEGER) AS fill_level, CAST(NULL AS DOUBLE) AS head_start_m, CAST(NULL AS DOUBLE) AS head_end_m,
  CAST(NULL AS VARCHAR) AS cap_start, CAST(NULL AS VARCHAR) AS cap_end`;

// Once for each file: the temp table r, one row for each edge with its stored levels. q(sql) -> rows as plain objects. opts.levels:
// "stored" (visualization.edge_levels of a solved level area) or "tags" (no levels: the engine computes them with the tags rule).
// Returns the keyword `levels` of the engine's look: "tags", or the stored levels' {edge_hash, n_edges}, which the engine checks.
export async function makeRoads(q, catalog, opts = {}) {
  const tags = opts.levels === "tags";
  const union = await roadsUnion(q, catalog);
  const first = (c) => `first(${c} ORDER BY mode IS NULL, mode, pmode)`;
  await q(`CREATE OR REPLACE TEMP TABLE e AS
    SELECT edge_id, any_value(source) AS source, any_value(target) AS target,
           ${first("osm_id")} AS osm_id, ${first("highway")} AS highway, COALESCE(${first("name")}, '') AS name,
           ${first("bridge")} AS bridge, ${first("tunnel")} AS tunnel, ${first("layer")} AS layer, bool_or(oneway) AS oneway,
           any_value(walk_type) AS walk_type,
           ${OPTIONAL_COLS.slice(1).map((c) => `${first(c)} AS ${c}`).join(", ")},
           ${MODES.map((m) => `COALESCE(bool_or(mode = '${m}'), false) AS ${m}`).join(", ")},
           ${MODES.map((m) => `max(CASE WHEN pmode = '${m}' THEN access END) AS access_${m}`).join(", ")},
           ${first("geometry")} AS geom
    FROM (${union}) GROUP BY edge_id`);
  const levels = tags ? "tags" : await levelsMeta(q);
  const path = `coalesce(highway IN (${PATH_CLASSES.map((c) => `'${c}'`).join(", ")}), false)`;
  await q(`CREATE OR REPLACE TEMP TABLE r AS
    SELECT e.* EXCLUDE (geom), ST_AsWKB(e.geom) AS geometry,
           -- load_roads: an undirected edge (a one-way street's walking-only reverse) on the street's own directed edge goes first
           NOT driving AND NOT cycling AND NOT ${path} AND osm_id IN (SELECT osm_id FROM e WHERE driving OR cycling) AS und,
           ${path} AS path,
           ${tags ? NO_LEVELS : "lv.casing_start, lv.casing_level, lv.casing_end, lv.fill_level, lv.head_start_m, lv.head_end_m, lv.cap_start, lv.cap_end"}
    FROM e ${tags ? "" : "LEFT JOIN visualization.edge_levels lv ON lv.edge_id = e.edge_id"}`);
  await q("DROP TABLE e");
  return levels;
}

// For each mode, after makeRoads: roads.parquet in duckdb-wasm's file system. mode: "all", "driving", "walking" or "cycling".
export async function writeRoads(q, mode = "all") {
  if (mode !== "all" && !MODES.includes(mode)) throw new Error(`unknown mode ${mode}`);
  // _access: in one mode, its restriction where that mode can't use the road; mode "all": bus for a bus road or lane for cars, else the
  // first restriction where no mode can use the road
  const access = mode !== "all" ? `CASE WHEN NOT ${mode} THEN access_${mode} END` : `CASE WHEN access_driving = 'bus' THEN access_driving
    WHEN NOT (driving OR walking OR cycling) AND (access_driving IS NOT NULL OR access_walking IS NOT NULL OR access_cycling IS NOT NULL)
    THEN coalesce(access_driving, access_walking, access_cycling) END`;
  const restricted = "coalesce(access IN ('private', 'bus'), false)";
  await q(`COPY (
    WITH a AS (SELECT *, ${access} AS access FROM r)
    SELECT a.* EXCLUDE (und, path, access_driving, access_walking, access_cycling),
           (driving OR cycling OR ${restricted}) AND NOT path AS is_directed,     -- _is_directed
           driving OR ${restricted} AS has_arrows
    FROM a ORDER BY NOT und, edge_id) TO 'roads.parquet' (FORMAT parquet)`);
}
