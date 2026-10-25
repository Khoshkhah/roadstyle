/* tslint:disable */
/* eslint-disable */

/**
 * A level area's files (makeArea): `roads` (roads.parquet's bytes, for new LevelArea), `pairs` and `edits` (pairs.csv and an empty
 * edits.csv), the numbers of roads and pairs, and the warnings.
 */
export class AreaFiles {
    private constructor();
    free(): void;
    [Symbol.dispose](): void;
    readonly edits: string;
    readonly pairCount: number;
    readonly pairs: string;
    readonly roadCount: number;
    readonly roads: Uint8Array;
    readonly warnings: string[];
}

/**
 * Stage 1's files for stage 2: each file's name and bytes (style.json and the files that it names).
 */
export class FileSet {
    free(): void;
    [Symbol.dispose](): void;
    add(name: string, bytes: Uint8Array): void;
    constructor();
}

/**
 * The level editor in the page (roadstyle::level_editor): new LevelArea(roads.parquet of the area, pairs.csv text). Each answer is JSON
 * text: the numbers of each road in the roads' order, the rules not kept (by road id) and the counts.
 */
export class LevelArea {
    free(): void;
    [Symbol.dispose](): void;
    /**
     * The check before rules are added (rows: CSV text with a header): [[index, why, [rule rows]]].
     */
    check(edits: string, rows: string): string;
    /**
     * The map's table (GeoParquet, one row for each edge) for makeStyle: 4 numbers for each road.
     */
    draw(levels: Int32Array, heads: string, caps: string): Uint8Array;
    /**
     * Each road end as drawn, a list in the roads' order: heads, caps, and yours (heads.csv, caps.csv).
     */
    ends(heads: string, caps: string): string;
    /**
     * What the panel shows of each road, a list in the roads' order.
     */
    facts(): string;
    /**
     * levels.csv: one row for each edge with its four numbers and its ends as drawn (4 numbers for each road).
     */
    levelsCsv(levels: Int32Array, heads: string, caps: string): string;
    constructor(roads: Uint8Array, pairs: string);
    /**
     * The solve after a change that names the roads of `changed` (edge ids): the roads around it, else the whole area.
     */
    solveLocal(edits: string, changed: string[]): string;
    /**
     * The whole solve with the edits (edits.csv text).
     */
    solve(edits: string): string;
    /**
     * The answer to start from (levels.csv, levels_info.json): 4 numbers for each road; the given-up parts as "upper|lower|part".
     */
    startFrom(levels: Int32Array, given_up_parts: string[], orders_not_kept: number, near: number): void;
}

/**
 * A resolved look (roadstyle-look), parsed one time: `resolveLook(options)` makes it, `Look.fromJson(text)` reads a saved look
 * (version 1, or version 0: today's look.json), `toJson()` gives its text (version 1). The calls below take it, not its text.
 */
export class Look {
    private constructor();
    free(): void;
    [Symbol.dispose](): void;
    /**
     * Look.fromJson(text): a saved look (version 1 or 0). An error is a thrown Error.
     */
    static fromJson(text: string): Look;
    /**
     * toJson(): the look's text (version 1).
     */
    toJson(): string;
}

export class Point {
    free(): void;
    [Symbol.dispose](): void;
    constructor(x: number, y: number, z: number);
    x: number;
    y: number;
    z: number;
}

export class Projection {
    free(): void;
    [Symbol.dispose](): void;
    constructor(defn: string);
    readonly axis: string;
    readonly isGeocentric: boolean;
    readonly isLatlon: boolean;
    readonly isNormalizedAxis: boolean;
    readonly projName: string;
    readonly to_meter: number;
    readonly units: string;
}

/**
 * Roads that a reader of a road file gave (roadstyle-io: a RoadTable, one row for each road): `readGeoJson(bytes)` makes them. `length`
 * and `columns()` describe them; `sources(look, features?, planner?, name?)` is stage 1 of them (makeSources' arguments after the roads).
 */
export class Roads {
    private constructor();
    free(): void;
    [Symbol.dispose](): void;
    /**
     * The names of the roads' columns (the file's properties), in order.
     */
    columns(): string[];
    /**
     * page(look, options, given?, features?): the page of these roads in one call, as makePage (its arguments after the roads).
     */
    page(look: Look, options: string, given?: string | null, features?: Uint8Array | null): string;
    /**
     * sources(look, features?, planner?, name?): stage 1 of these roads, as makeSources; `features` and `planner` are Parquet bytes.
     */
    sources(look: Look, features?: Uint8Array | null, planner?: Uint8Array | null, name?: string | null): Sources;
    /**
     * The number of roads (the file's features).
     */
    readonly length: number;
}

/**
 * Stage 1 (docs/rust/architecture.md, "The three stages and the one call"): the style and its sources in memory.
 */
export class Sources {
    private constructor();
    free(): void;
    [Symbol.dispose](): void;
    /**
     * fileNames(format): the names of stage 1's files (style.json, a file for each source, road_table.parquet).
     */
    fileNames(format: string): string[];
    /**
     * file(name, format, keep): one of stage 1's files ("geojson" or "geoparquet"; the roads' file has their drawing values and
     * `keep`, the road table every field of each road).
     */
    file(name: string, format: string, keep: string[]): Uint8Array;
    /**
     * roadTable(): the road table as the page loads it, JSON text (props, mids, bboxes, lines: one item for each road).
     */
    roadTable(): Uint8Array;
}

/**
 * A map with vector tiles: `new Tiler(roads, look, features?, name?, prefix, keep)`, then `style()` (the style's JSON text) and
 * `tile(source, z, x, y)` (a vector tile, empty when nothing is in it) for each request of the map, and `props(layer, id)` (the
 * tile layer, for example `roads`).
 */
export class Tiler {
    free(): void;
    [Symbol.dispose](): void;
    /**
     * archive(bounds, layers): a PMTiles archive of every tile in bounds [min lon, min lat, max lon, max lat] (one file of the map).
     */
    archive(bounds: Float64Array, layers: string[]): Uint8Array;
    constructor(parquet: Uint8Array, look: Look, features: Uint8Array | null | undefined, name: string | null | undefined, prefix: string, keep: string[]);
    /**
     * The properties of the feature `id` of a source, as JSON (`null` when there is none).
     */
    props(source: string, id: number): string;
    style(): string;
    /**
     * `source` is the style's one source, `roads`: the tile has a layer for each of the old sources.
     */
    tile(source: string, z: number, x: number, y: number): Uint8Array;
}

export function add_nadgrid(key: string, array: Uint8Array): void;

/**
 * duckosmFeaturesSelect(specs: number[], run: string) -> string | undefined: the base map's rows from the run's tables of the layers
 * `specs` that were made.
 */
export function duckosmFeaturesSelect(specs: Uint32Array, run: string): string | undefined;

/**
 * duckosmLevels(source?, nEdges?, edgeHash?) -> string: the look's keyword `levels` (JSON text) from the stored levels' metadata row
 * (none: the file has no such row); an error says what to do.
 */
export function duckosmLevels(source?: string | null, n_edges?: number | null, edge_hash?: string | null): string;

/**
 * duckosmPlan(catalog, mode, tags, specs, only?, run?) -> string: the SQL that reads a duckOSM file (roadstyle-io's duckosm.rs, the one copy that
 * Python runs too), as JSON text: {"catalog": the 2 queries of the catalog, "roads": 3 statements, "meta": the stored levels' query or
 * null, "select": the roads of `mode` ("roads" is null when the file has no network of `mode`: "roads_error" says why), "layers": [{spec, name, sql: the
 * queries in order}]}. `catalog`: the JSON text of {"name", "tables":
 * [[schema, table]], "columns": [[schema, table, column]]} (with no tables: only "catalog" is in the answer); `specs`: layers.yaml's
 * layers as JSON text. `only`: the map of `mode` alone; then "subset" has the queries of its roads with no stored levels and
 * of its edge_ids (for duckosmSubsetLevels). "level_edges": the edges of the file's level area (duckosm::level_edges_sql), for makeArea.
 * `run`: the id of this reading of the file: its tables have their own names (each layer's "table"; "drop" drops them), so two
 * readings at the same time on one connection do not meet. With no `run`, a new one; "run" gives it, for the next calls of the same
 * reading.
 */
export function duckosmPlan(catalog: string, mode: string, tags: boolean, specs: string, only?: boolean | null, run?: string | null): string;

/**
 * duckosmSubsetLevels(source?, nEdges?, edgeHash?, missing, example?, ids) -> string: the look's keyword `levels` (JSON text) for a map
 * of one mode: the stored levels' metadata row, the row of the plan's "subset" query, and the map's edge_ids (a BigInt64Array).
 */
export function duckosmSubsetLevels(source: string | null | undefined, n_edges: number | null | undefined, edge_hash: string | null | undefined, missing: number, example: bigint | null | undefined, ids: BigInt64Array): string;

/**
 * exportLook(look: Look, cols: string[] (highway, oneway, tunnel, bridge, id), positions: number[]) -> string: the simple look
 * for another app's data layer (roadstyle's export_look) from a resolved look.
 */
export function exportLook(look: Look, cols: string[], positions: Int32Array): string;

export function main(): void;

/**
 * makeArea(edges: Uint8Array, options?: string) -> AreaFiles: a level area's files in memory (roadstyle::level_area::make_files), for
 * a page with no server: `edges` is GeoParquet of the area's edges (the line in `geometry`, longitude and latitude; a duckOSM file's:
 * duckosmPlan's "level_edges"); `options` the JSON text of {"id_col", "highway_col", "layer_col", "bridge_col", "tunnel_col",
 * "junction_col", "band_col", "order" ("priority", "class", a column, or null), "band_dist", "head_m", "near_rules", "heads" (heads.csv
 * text)}, each optional (make_area's defaults).
 */
export function makeArea(edges: Uint8Array, options?: string | null): AreaFiles;

/**
 * makePage(roads: Uint8Array, look: Look, options: string, given?: string) -> string: the page of the roads (GeoParquet) in one
 * call, as render_edges(backend="web") (roadstyle::page_options::page_from; MapLibre stays a placeholder). `look`: resolveLook's of
 * `options` (its JSON text, which a view's palette resolves again), with "state": "live" in its args; `given`: the caller's values
 * over the look's args (JSON text: api_key, street_view_key, resolved_basemaps); `features`: a duckOSM map's base map (Parquet bytes).
 */
export function makePage(roads: Uint8Array, look: Look, options: string, given?: string | null, features?: Uint8Array | null): string;

/**
 * makeSources(parquet, look, features, planner, name): stage 1, with makeStyle's arguments.
 */
export function makeSources(parquet: Uint8Array, look: Look, features?: Uint8Array | null, planner?: Uint8Array | null, name?: string | null): Sources;

/**
 * makeStyle(roads: Uint8Array, look: Look, features?: Uint8Array, planner?: Uint8Array, name?: string) -> string; an error is a thrown Error.
 */
export function makeStyle(parquet: Uint8Array, look: Look, features?: Uint8Array | null, planner?: Uint8Array | null, name?: string | null): string;

/**
 * The size of the module's memory, in bytes.
 */
export function memoryBytes(): number;

/**
 * rampStops(cmap: string, n: number) -> string[]: `n` colours ("#rrggbb") at even steps along a ramp (render_edges' cmap: a branca
 * scheme or a matplotlib colormap name, or the JSON text of a list of colours), from the first colour to the last (at least 2), as
 * roadstyle's ColorRamp.stops: for example a colour for each category of a column. An error is a thrown Error.
 */
export function rampStops(cmap: string, n: number): string[];

/**
 * readGeoJson(bytes: Uint8Array) -> Roads: the roads of a GeoJSON file (a FeatureCollection in EPSG:4326; roadstyle-io's geojson.rs
 * says how each property becomes a column). An error is a thrown Error.
 */
export function readGeoJson(bytes: Uint8Array): Roads;

/**
 * readGeoParquet(bytes: Uint8Array) -> Roads: the roads of a GeoParquet file (the geometry in the column `geometry`, as makeSources
 * reads it). An error is a thrown Error.
 */
export function readGeoParquet(bytes: Uint8Array): Roads;

/**
 * readShp(shp: Uint8Array, dbf: Uint8Array, prj?: string, name?: string) -> Roads: the roads of a Shapefile, in EPSG:4326 (roadstyle-io's
 * shp.rs; no prj: no CRS, an error). A GeoPackage is not read here: SQLite is C (the native programs read it). An error is a thrown Error.
 */
export function readShp(shp: Uint8Array, dbf: Uint8Array, prj?: string | null, name?: string | null): Roads;

/**
 * resolveLook(options: string) -> Look: the look of render_edges' palette, profile and settings; options: {"palette", "profile",
 * "settings", "args", "features", "files"} as JSON text. An error is a thrown Error.
 */
export function resolveLook(options: string): Look;

/**
 * tileFiles(files, prefix, keep): stage 2 from stage 1's files (GeoJSON or GeoParquet, as style.json names them); the Tiler's
 * style is the saved style with the one vector source (roadstyle::tiled_style).
 */
export function tileFiles(files: FileSet, prefix: string, keep: string[]): Tiler;

/**
 * tileSources(sources, prefix, keep): stage 2 from memory (the typed pieces, no GeoJSON text; the sources stay as they are). The
 * Tiler's style has the one vector source `<prefix>roads/{z}/{x}/{y}`, with the pieces' promoteId (roadstyle::tile_stage).
 */
export function tileSources(sources: Sources, prefix: string, keep: string[]): Tiler;

export function toProjstring(src: string): string;

export function transform(src: Projection, dst: Projection, point: Point): void;

export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

export interface InitOutput {
    readonly memory: WebAssembly.Memory;
    readonly __wbg_areafiles_free: (a: number, b: number) => void;
    readonly __wbg_fileset_free: (a: number, b: number) => void;
    readonly __wbg_get_point_x: (a: number) => number;
    readonly __wbg_get_point_y: (a: number) => number;
    readonly __wbg_get_point_z: (a: number) => number;
    readonly __wbg_levelarea_free: (a: number, b: number) => void;
    readonly __wbg_look_free: (a: number, b: number) => void;
    readonly __wbg_point_free: (a: number, b: number) => void;
    readonly __wbg_projection_free: (a: number, b: number) => void;
    readonly __wbg_roads_free: (a: number, b: number) => void;
    readonly __wbg_set_point_x: (a: number, b: number) => void;
    readonly __wbg_set_point_y: (a: number, b: number) => void;
    readonly __wbg_set_point_z: (a: number, b: number) => void;
    readonly __wbg_sources_free: (a: number, b: number) => void;
    readonly __wbg_tiler_free: (a: number, b: number) => void;
    readonly add_nadgrid: (a: number, b: number, c: any) => [number, number];
    readonly areafiles_edits: (a: number) => [number, number];
    readonly areafiles_pairCount: (a: number) => number;
    readonly areafiles_pairs: (a: number) => [number, number];
    readonly areafiles_roadCount: (a: number) => number;
    readonly areafiles_roads: (a: number) => [number, number];
    readonly areafiles_warnings: (a: number) => [number, number];
    readonly duckosmFeaturesSelect: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly duckosmLevels: (a: number, b: number, c: number, d: number, e: number, f: number) => [number, number, number, number];
    readonly duckosmPlan: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number, j: number) => [number, number, number, number];
    readonly duckosmSubsetLevels: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: bigint, j: number, k: number) => [number, number, number, number];
    readonly exportLook: (a: number, b: number, c: number, d: number, e: number) => [number, number, number, number];
    readonly fileset_add: (a: number, b: number, c: number, d: number, e: number) => void;
    readonly fileset_new: () => number;
    readonly levelarea_check: (a: number, b: number, c: number, d: number, e: number) => [number, number, number, number];
    readonly levelarea_draw: (a: number, b: number, c: number, d: number, e: number, f: number, g: number) => [number, number, number, number];
    readonly levelarea_ends: (a: number, b: number, c: number, d: number, e: number) => [number, number, number, number];
    readonly levelarea_facts: (a: number) => [number, number];
    readonly levelarea_levelsCsv: (a: number, b: number, c: number, d: number, e: number, f: number, g: number) => [number, number, number, number];
    readonly levelarea_new: (a: number, b: number, c: number, d: number) => [number, number, number];
    readonly levelarea_solve: (a: number, b: number, c: number) => [number, number, number, number];
    readonly levelarea_solveLocal: (a: number, b: number, c: number, d: number, e: number) => [number, number, number, number];
    readonly levelarea_startFrom: (a: number, b: number, c: number, d: number, e: number, f: number, g: number) => [number, number];
    readonly look_fromJson: (a: number, b: number) => [number, number, number];
    readonly look_toJson: (a: number) => [number, number];
    readonly main: () => void;
    readonly makeArea: (a: number, b: number, c: number, d: number) => [number, number, number];
    readonly makePage: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number) => [number, number, number, number];
    readonly makeSources: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number) => [number, number, number];
    readonly makeStyle: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number) => [number, number, number, number];
    readonly memoryBytes: () => number;
    readonly point_new: (a: number, b: number, c: number) => number;
    readonly projection_axis: (a: number) => [number, number];
    readonly projection_isGeocentric: (a: number) => number;
    readonly projection_isLatlon: (a: number) => number;
    readonly projection_isNormalizedAxis: (a: number) => number;
    readonly projection_new: (a: number, b: number) => [number, number, number];
    readonly projection_projName: (a: number) => [number, number];
    readonly projection_to_meter: (a: number) => number;
    readonly projection_units: (a: number) => [number, number];
    readonly rampStops: (a: number, b: number, c: number) => [number, number, number, number];
    readonly readGeoJson: (a: number, b: number) => [number, number, number];
    readonly readGeoParquet: (a: number, b: number) => [number, number, number];
    readonly readShp: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number) => [number, number, number];
    readonly resolveLook: (a: number, b: number) => [number, number, number];
    readonly roads_columns: (a: number) => [number, number];
    readonly roads_length: (a: number) => number;
    readonly roads_page: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number) => [number, number, number, number];
    readonly roads_sources: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number) => [number, number, number];
    readonly sources_file: (a: number, b: number, c: number, d: number, e: number, f: number, g: number) => [number, number, number, number];
    readonly sources_fileNames: (a: number, b: number, c: number) => [number, number, number, number];
    readonly sources_roadTable: (a: number) => [number, number];
    readonly tileFiles: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly tileSources: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly tiler_archive: (a: number, b: number, c: number, d: number, e: number) => [number, number, number, number];
    readonly tiler_new: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number, j: number, k: number) => [number, number, number];
    readonly tiler_props: (a: number, b: number, c: number, d: number) => [number, number];
    readonly tiler_style: (a: number) => [number, number];
    readonly tiler_tile: (a: number, b: number, c: number, d: number, e: number, f: number) => [number, number];
    readonly toProjstring: (a: number, b: number) => [number, number, number, number];
    readonly transform: (a: number, b: number, c: number) => [number, number];
    readonly __wbindgen_malloc: (a: number, b: number) => number;
    readonly __wbindgen_realloc: (a: number, b: number, c: number, d: number) => number;
    readonly __wbindgen_externrefs: WebAssembly.Table;
    readonly __externref_table_dealloc: (a: number) => void;
    readonly __wbindgen_free: (a: number, b: number, c: number) => void;
    readonly __externref_drop_slice: (a: number, b: number) => void;
    readonly __externref_table_alloc: () => number;
    readonly __wbindgen_start: () => void;
}

export type SyncInitInput = BufferSource | WebAssembly.Module;

/**
 * Instantiates the given `module`, which can either be bytes or
 * a precompiled `WebAssembly.Module`.
 *
 * @param {{ module: SyncInitInput }} module - Passing `SyncInitInput` directly is deprecated.
 *
 * @returns {InitOutput}
 */
export function initSync(module: { module: SyncInitInput } | SyncInitInput): InitOutput;

/**
 * If `module_or_path` is {RequestInfo} or {URL}, makes a request and
 * for everything else, calls `WebAssembly.instantiate` directly.
 *
 * @param {{ module_or_path: InitInput | Promise<InitInput> }} module_or_path - Passing `InitInput` directly is deprecated.
 *
 * @returns {Promise<InitOutput>}
 */
export default function __wbg_init (module_or_path?: { module_or_path: InitInput | Promise<InitInput> } | InitInput | Promise<InitInput>): Promise<InitOutput>;
