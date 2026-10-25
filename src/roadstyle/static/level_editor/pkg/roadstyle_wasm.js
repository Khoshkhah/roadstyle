/* @ts-self-types="./roadstyle_wasm.d.ts" */

/**
 * A level area's files (makeArea): `roads` (roads.parquet's bytes, for new LevelArea), `pairs` and `edits` (pairs.csv and an empty
 * edits.csv), the numbers of roads and pairs, and the warnings.
 */
export class AreaFiles {
    static __wrap(ptr) {
        const obj = Object.create(AreaFiles.prototype);
        obj.__wbg_ptr = ptr;
        AreaFilesFinalization.register(obj, obj.__wbg_ptr, obj);
        return obj;
    }
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        AreaFilesFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_areafiles_free(ptr, 0);
    }
    /**
     * @returns {string}
     */
    get edits() {
        let deferred1_0;
        let deferred1_1;
        try {
            const ret = wasm.areafiles_edits(this.__wbg_ptr);
            deferred1_0 = ret[0];
            deferred1_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
        }
    }
    /**
     * @returns {number}
     */
    get pairCount() {
        const ret = wasm.areafiles_pairCount(this.__wbg_ptr);
        return ret >>> 0;
    }
    /**
     * @returns {string}
     */
    get pairs() {
        let deferred1_0;
        let deferred1_1;
        try {
            const ret = wasm.areafiles_pairs(this.__wbg_ptr);
            deferred1_0 = ret[0];
            deferred1_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
        }
    }
    /**
     * @returns {number}
     */
    get roadCount() {
        const ret = wasm.areafiles_roadCount(this.__wbg_ptr);
        return ret >>> 0;
    }
    /**
     * @returns {Uint8Array}
     */
    get roads() {
        const ret = wasm.areafiles_roads(this.__wbg_ptr);
        var v1 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
        return v1;
    }
    /**
     * @returns {string[]}
     */
    get warnings() {
        const ret = wasm.areafiles_warnings(this.__wbg_ptr);
        var v1 = getArrayJsValueFromWasm0(ret[0], ret[1]);
        wasm.__wbindgen_free(ret[0], ret[1] * 4, 4);
        return v1;
    }
}
if (Symbol.dispose) AreaFiles.prototype[Symbol.dispose] = AreaFiles.prototype.free;

/**
 * Stage 1's files for stage 2: each file's name and bytes (style.json and the files that it names).
 */
export class FileSet {
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        FileSetFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_fileset_free(ptr, 0);
    }
    /**
     * @param {string} name
     * @param {Uint8Array} bytes
     */
    add(name, bytes) {
        const ptr0 = passStringToWasm0(name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passArray8ToWasm0(bytes, wasm.__wbindgen_malloc);
        const len1 = WASM_VECTOR_LEN;
        wasm.fileset_add(this.__wbg_ptr, ptr0, len0, ptr1, len1);
    }
    constructor() {
        const ret = wasm.fileset_new();
        this.__wbg_ptr = ret;
        FileSetFinalization.register(this, this.__wbg_ptr, this);
        return this;
    }
}
if (Symbol.dispose) FileSet.prototype[Symbol.dispose] = FileSet.prototype.free;

/**
 * The level editor in the page (roadstyle::level_editor): new LevelArea(roads.parquet of the area, pairs.csv text). Each answer is JSON
 * text: the numbers of each road in the roads' order, the rules not kept (by road id) and the counts.
 */
export class LevelArea {
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        LevelAreaFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_levelarea_free(ptr, 0);
    }
    /**
     * The check before rules are added (rows: CSV text with a header): [[index, why, [rule rows]]].
     * @param {string} edits
     * @param {string} rows
     * @returns {string}
     */
    check(edits, rows) {
        let deferred4_0;
        let deferred4_1;
        try {
            const ptr0 = passStringToWasm0(edits, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len0 = WASM_VECTOR_LEN;
            const ptr1 = passStringToWasm0(rows, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len1 = WASM_VECTOR_LEN;
            const ret = wasm.levelarea_check(this.__wbg_ptr, ptr0, len0, ptr1, len1);
            var ptr3 = ret[0];
            var len3 = ret[1];
            if (ret[3]) {
                ptr3 = 0; len3 = 0;
                throw takeFromExternrefTable0(ret[2]);
            }
            deferred4_0 = ptr3;
            deferred4_1 = len3;
            return getStringFromWasm0(ptr3, len3);
        } finally {
            wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
        }
    }
    /**
     * The map's table (GeoParquet, one row for each edge) for makeStyle: 4 numbers for each road.
     * @param {Int32Array} levels
     * @param {string} heads
     * @param {string} caps
     * @returns {Uint8Array}
     */
    draw(levels, heads, caps) {
        const ptr0 = passArray32ToWasm0(levels, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(heads, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ptr2 = passStringToWasm0(caps, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len2 = WASM_VECTOR_LEN;
        const ret = wasm.levelarea_draw(this.__wbg_ptr, ptr0, len0, ptr1, len1, ptr2, len2);
        if (ret[3]) {
            throw takeFromExternrefTable0(ret[2]);
        }
        var v4 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
        return v4;
    }
    /**
     * Each road end as drawn, a list in the roads' order: heads, caps, and yours (heads.csv, caps.csv).
     * @param {string} heads
     * @param {string} caps
     * @returns {string}
     */
    ends(heads, caps) {
        let deferred4_0;
        let deferred4_1;
        try {
            const ptr0 = passStringToWasm0(heads, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len0 = WASM_VECTOR_LEN;
            const ptr1 = passStringToWasm0(caps, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len1 = WASM_VECTOR_LEN;
            const ret = wasm.levelarea_ends(this.__wbg_ptr, ptr0, len0, ptr1, len1);
            var ptr3 = ret[0];
            var len3 = ret[1];
            if (ret[3]) {
                ptr3 = 0; len3 = 0;
                throw takeFromExternrefTable0(ret[2]);
            }
            deferred4_0 = ptr3;
            deferred4_1 = len3;
            return getStringFromWasm0(ptr3, len3);
        } finally {
            wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
        }
    }
    /**
     * What the panel shows of each road, a list in the roads' order.
     * @returns {string}
     */
    facts() {
        let deferred1_0;
        let deferred1_1;
        try {
            const ret = wasm.levelarea_facts(this.__wbg_ptr);
            deferred1_0 = ret[0];
            deferred1_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
        }
    }
    /**
     * levels.csv: one row for each edge with its four numbers and its ends as drawn (4 numbers for each road).
     * @param {Int32Array} levels
     * @param {string} heads
     * @param {string} caps
     * @returns {string}
     */
    levelsCsv(levels, heads, caps) {
        let deferred5_0;
        let deferred5_1;
        try {
            const ptr0 = passArray32ToWasm0(levels, wasm.__wbindgen_malloc);
            const len0 = WASM_VECTOR_LEN;
            const ptr1 = passStringToWasm0(heads, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len1 = WASM_VECTOR_LEN;
            const ptr2 = passStringToWasm0(caps, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len2 = WASM_VECTOR_LEN;
            const ret = wasm.levelarea_levelsCsv(this.__wbg_ptr, ptr0, len0, ptr1, len1, ptr2, len2);
            var ptr4 = ret[0];
            var len4 = ret[1];
            if (ret[3]) {
                ptr4 = 0; len4 = 0;
                throw takeFromExternrefTable0(ret[2]);
            }
            deferred5_0 = ptr4;
            deferred5_1 = len4;
            return getStringFromWasm0(ptr4, len4);
        } finally {
            wasm.__wbindgen_free(deferred5_0, deferred5_1, 1);
        }
    }
    /**
     * @param {Uint8Array} roads
     * @param {string} pairs
     */
    constructor(roads, pairs) {
        const ptr0 = passArray8ToWasm0(roads, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(pairs, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.levelarea_new(ptr0, len0, ptr1, len1);
        if (ret[2]) {
            throw takeFromExternrefTable0(ret[1]);
        }
        this.__wbg_ptr = ret[0];
        LevelAreaFinalization.register(this, this.__wbg_ptr, this);
        return this;
    }
    /**
     * The solve after a change that names the roads of `changed` (edge ids): the roads around it, else the whole area.
     * @param {string} edits
     * @param {string[]} changed
     * @returns {string}
     */
    solveLocal(edits, changed) {
        let deferred4_0;
        let deferred4_1;
        try {
            const ptr0 = passStringToWasm0(edits, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len0 = WASM_VECTOR_LEN;
            const ptr1 = passArrayJsValueToWasm0(changed, wasm.__wbindgen_malloc);
            const len1 = WASM_VECTOR_LEN;
            const ret = wasm.levelarea_solveLocal(this.__wbg_ptr, ptr0, len0, ptr1, len1);
            var ptr3 = ret[0];
            var len3 = ret[1];
            if (ret[3]) {
                ptr3 = 0; len3 = 0;
                throw takeFromExternrefTable0(ret[2]);
            }
            deferred4_0 = ptr3;
            deferred4_1 = len3;
            return getStringFromWasm0(ptr3, len3);
        } finally {
            wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
        }
    }
    /**
     * The whole solve with the edits (edits.csv text).
     * @param {string} edits
     * @returns {string}
     */
    solve(edits) {
        let deferred3_0;
        let deferred3_1;
        try {
            const ptr0 = passStringToWasm0(edits, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len0 = WASM_VECTOR_LEN;
            const ret = wasm.levelarea_solve(this.__wbg_ptr, ptr0, len0);
            var ptr2 = ret[0];
            var len2 = ret[1];
            if (ret[3]) {
                ptr2 = 0; len2 = 0;
                throw takeFromExternrefTable0(ret[2]);
            }
            deferred3_0 = ptr2;
            deferred3_1 = len2;
            return getStringFromWasm0(ptr2, len2);
        } finally {
            wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
        }
    }
    /**
     * The answer to start from (levels.csv, levels_info.json): 4 numbers for each road; the given-up parts as "upper|lower|part".
     * @param {Int32Array} levels
     * @param {string[]} given_up_parts
     * @param {number} orders_not_kept
     * @param {number} near
     */
    startFrom(levels, given_up_parts, orders_not_kept, near) {
        const ptr0 = passArray32ToWasm0(levels, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passArrayJsValueToWasm0(given_up_parts, wasm.__wbindgen_malloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.levelarea_startFrom(this.__wbg_ptr, ptr0, len0, ptr1, len1, orders_not_kept, near);
        if (ret[1]) {
            throw takeFromExternrefTable0(ret[0]);
        }
    }
}
if (Symbol.dispose) LevelArea.prototype[Symbol.dispose] = LevelArea.prototype.free;

/**
 * A resolved look (roadstyle-look), parsed one time: `resolveLook(options)` makes it, `Look.fromJson(text)` reads a saved look
 * (version 1, or version 0: today's look.json), `toJson()` gives its text (version 1). The calls below take it, not its text.
 */
export class Look {
    static __wrap(ptr) {
        const obj = Object.create(Look.prototype);
        obj.__wbg_ptr = ptr;
        LookFinalization.register(obj, obj.__wbg_ptr, obj);
        return obj;
    }
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        LookFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_look_free(ptr, 0);
    }
    /**
     * Look.fromJson(text): a saved look (version 1 or 0). An error is a thrown Error.
     * @param {string} text
     * @returns {Look}
     */
    static fromJson(text) {
        const ptr0 = passStringToWasm0(text, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.look_fromJson(ptr0, len0);
        if (ret[2]) {
            throw takeFromExternrefTable0(ret[1]);
        }
        return Look.__wrap(ret[0]);
    }
    /**
     * toJson(): the look's text (version 1).
     * @returns {string}
     */
    toJson() {
        let deferred1_0;
        let deferred1_1;
        try {
            const ret = wasm.look_toJson(this.__wbg_ptr);
            deferred1_0 = ret[0];
            deferred1_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
        }
    }
}
if (Symbol.dispose) Look.prototype[Symbol.dispose] = Look.prototype.free;

export class Point {
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        PointFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_point_free(ptr, 0);
    }
    /**
     * @returns {number}
     */
    get x() {
        const ret = wasm.__wbg_get_point_x(this.__wbg_ptr);
        return ret;
    }
    /**
     * @returns {number}
     */
    get y() {
        const ret = wasm.__wbg_get_point_y(this.__wbg_ptr);
        return ret;
    }
    /**
     * @returns {number}
     */
    get z() {
        const ret = wasm.__wbg_get_point_z(this.__wbg_ptr);
        return ret;
    }
    /**
     * @param {number} x
     * @param {number} y
     * @param {number} z
     */
    constructor(x, y, z) {
        const ret = wasm.point_new(x, y, z);
        this.__wbg_ptr = ret;
        PointFinalization.register(this, this.__wbg_ptr, this);
        return this;
    }
    /**
     * @param {number} arg0
     */
    set x(arg0) {
        wasm.__wbg_set_point_x(this.__wbg_ptr, arg0);
    }
    /**
     * @param {number} arg0
     */
    set y(arg0) {
        wasm.__wbg_set_point_y(this.__wbg_ptr, arg0);
    }
    /**
     * @param {number} arg0
     */
    set z(arg0) {
        wasm.__wbg_set_point_z(this.__wbg_ptr, arg0);
    }
}
if (Symbol.dispose) Point.prototype[Symbol.dispose] = Point.prototype.free;

export class Projection {
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        ProjectionFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_projection_free(ptr, 0);
    }
    /**
     * @returns {string}
     */
    get axis() {
        let deferred1_0;
        let deferred1_1;
        try {
            const ret = wasm.projection_axis(this.__wbg_ptr);
            deferred1_0 = ret[0];
            deferred1_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
        }
    }
    /**
     * @returns {boolean}
     */
    get isGeocentric() {
        const ret = wasm.projection_isGeocentric(this.__wbg_ptr);
        return ret !== 0;
    }
    /**
     * @returns {boolean}
     */
    get isLatlon() {
        const ret = wasm.projection_isLatlon(this.__wbg_ptr);
        return ret !== 0;
    }
    /**
     * @returns {boolean}
     */
    get isNormalizedAxis() {
        const ret = wasm.projection_isNormalizedAxis(this.__wbg_ptr);
        return ret !== 0;
    }
    /**
     * @param {string} defn
     */
    constructor(defn) {
        const ptr0 = passStringToWasm0(defn, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.projection_new(ptr0, len0);
        if (ret[2]) {
            throw takeFromExternrefTable0(ret[1]);
        }
        this.__wbg_ptr = ret[0];
        ProjectionFinalization.register(this, this.__wbg_ptr, this);
        return this;
    }
    /**
     * @returns {string}
     */
    get projName() {
        let deferred1_0;
        let deferred1_1;
        try {
            const ret = wasm.projection_projName(this.__wbg_ptr);
            deferred1_0 = ret[0];
            deferred1_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
        }
    }
    /**
     * @returns {number}
     */
    get to_meter() {
        const ret = wasm.projection_to_meter(this.__wbg_ptr);
        return ret;
    }
    /**
     * @returns {string}
     */
    get units() {
        let deferred1_0;
        let deferred1_1;
        try {
            const ret = wasm.projection_units(this.__wbg_ptr);
            deferred1_0 = ret[0];
            deferred1_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
        }
    }
}
if (Symbol.dispose) Projection.prototype[Symbol.dispose] = Projection.prototype.free;

/**
 * Roads that a reader of a road file gave (roadstyle-io: a RoadTable, one row for each road): `readGeoJson(bytes)` makes them. `length`
 * and `columns()` describe them; `sources(look, features?, planner?, name?)` is stage 1 of them (makeSources' arguments after the roads).
 */
export class Roads {
    static __wrap(ptr) {
        const obj = Object.create(Roads.prototype);
        obj.__wbg_ptr = ptr;
        RoadsFinalization.register(obj, obj.__wbg_ptr, obj);
        return obj;
    }
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        RoadsFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_roads_free(ptr, 0);
    }
    /**
     * The names of the roads' columns (the file's properties), in order.
     * @returns {string[]}
     */
    columns() {
        const ret = wasm.roads_columns(this.__wbg_ptr);
        var v1 = getArrayJsValueFromWasm0(ret[0], ret[1]);
        wasm.__wbindgen_free(ret[0], ret[1] * 4, 4);
        return v1;
    }
    /**
     * The number of roads (the file's features).
     * @returns {number}
     */
    get length() {
        const ret = wasm.roads_length(this.__wbg_ptr);
        return ret >>> 0;
    }
    /**
     * page(look, options, given?, features?): the page of these roads in one call, as makePage (its arguments after the roads).
     * @param {Look} look
     * @param {string} options
     * @param {string | null} [given]
     * @param {Uint8Array | null} [features]
     * @returns {string}
     */
    page(look, options, given, features) {
        let deferred5_0;
        let deferred5_1;
        try {
            _assertClass(look, Look);
            const ptr0 = passStringToWasm0(options, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len0 = WASM_VECTOR_LEN;
            var ptr1 = isLikeNone(given) ? 0 : passStringToWasm0(given, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            var len1 = WASM_VECTOR_LEN;
            var ptr2 = isLikeNone(features) ? 0 : passArray8ToWasm0(features, wasm.__wbindgen_malloc);
            var len2 = WASM_VECTOR_LEN;
            const ret = wasm.roads_page(this.__wbg_ptr, look.__wbg_ptr, ptr0, len0, ptr1, len1, ptr2, len2);
            var ptr4 = ret[0];
            var len4 = ret[1];
            if (ret[3]) {
                ptr4 = 0; len4 = 0;
                throw takeFromExternrefTable0(ret[2]);
            }
            deferred5_0 = ptr4;
            deferred5_1 = len4;
            return getStringFromWasm0(ptr4, len4);
        } finally {
            wasm.__wbindgen_free(deferred5_0, deferred5_1, 1);
        }
    }
    /**
     * sources(look, features?, planner?, name?): stage 1 of these roads, as makeSources; `features` and `planner` are Parquet bytes.
     * @param {Look} look
     * @param {Uint8Array | null} [features]
     * @param {Uint8Array | null} [planner]
     * @param {string | null} [name]
     * @returns {Sources}
     */
    sources(look, features, planner, name) {
        _assertClass(look, Look);
        var ptr0 = isLikeNone(features) ? 0 : passArray8ToWasm0(features, wasm.__wbindgen_malloc);
        var len0 = WASM_VECTOR_LEN;
        var ptr1 = isLikeNone(planner) ? 0 : passArray8ToWasm0(planner, wasm.__wbindgen_malloc);
        var len1 = WASM_VECTOR_LEN;
        var ptr2 = isLikeNone(name) ? 0 : passStringToWasm0(name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        var len2 = WASM_VECTOR_LEN;
        const ret = wasm.roads_sources(this.__wbg_ptr, look.__wbg_ptr, ptr0, len0, ptr1, len1, ptr2, len2);
        if (ret[2]) {
            throw takeFromExternrefTable0(ret[1]);
        }
        return Sources.__wrap(ret[0]);
    }
}
if (Symbol.dispose) Roads.prototype[Symbol.dispose] = Roads.prototype.free;

/**
 * Stage 1 (docs/rust/architecture.md, "The three stages and the one call"): the style and its sources in memory.
 */
export class Sources {
    static __wrap(ptr) {
        const obj = Object.create(Sources.prototype);
        obj.__wbg_ptr = ptr;
        SourcesFinalization.register(obj, obj.__wbg_ptr, obj);
        return obj;
    }
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        SourcesFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_sources_free(ptr, 0);
    }
    /**
     * fileNames(format): the names of stage 1's files (style.json, a file for each source, road_table.parquet).
     * @param {string} format
     * @returns {string[]}
     */
    fileNames(format) {
        const ptr0 = passStringToWasm0(format, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.sources_fileNames(this.__wbg_ptr, ptr0, len0);
        if (ret[3]) {
            throw takeFromExternrefTable0(ret[2]);
        }
        var v2 = getArrayJsValueFromWasm0(ret[0], ret[1]);
        wasm.__wbindgen_free(ret[0], ret[1] * 4, 4);
        return v2;
    }
    /**
     * file(name, format, keep): one of stage 1's files ("geojson" or "geoparquet"; the roads' file has their drawing values and
     * `keep`, the road table every field of each road).
     * @param {string} name
     * @param {string} format
     * @param {string[]} keep
     * @returns {Uint8Array}
     */
    file(name, format, keep) {
        const ptr0 = passStringToWasm0(name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(format, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ptr2 = passArrayJsValueToWasm0(keep, wasm.__wbindgen_malloc);
        const len2 = WASM_VECTOR_LEN;
        const ret = wasm.sources_file(this.__wbg_ptr, ptr0, len0, ptr1, len1, ptr2, len2);
        if (ret[3]) {
            throw takeFromExternrefTable0(ret[2]);
        }
        var v4 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
        return v4;
    }
    /**
     * roadTable(): the road table as the page loads it, JSON text (props, mids, bboxes, lines: one item for each road).
     * @returns {Uint8Array}
     */
    roadTable() {
        const ret = wasm.sources_roadTable(this.__wbg_ptr);
        var v1 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
        return v1;
    }
}
if (Symbol.dispose) Sources.prototype[Symbol.dispose] = Sources.prototype.free;

/**
 * A map with vector tiles: `new Tiler(roads, look, features?, name?, prefix, keep)`, then `style()` (the style's JSON text) and
 * `tile(source, z, x, y)` (a vector tile, empty when nothing is in it) for each request of the map, and `props(layer, id)` (the
 * tile layer, for example `roads`).
 */
export class Tiler {
    static __wrap(ptr) {
        const obj = Object.create(Tiler.prototype);
        obj.__wbg_ptr = ptr;
        TilerFinalization.register(obj, obj.__wbg_ptr, obj);
        return obj;
    }
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        TilerFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_tiler_free(ptr, 0);
    }
    /**
     * archive(bounds, layers): a PMTiles archive of every tile in bounds [min lon, min lat, max lon, max lat] (one file of the map).
     * @param {Float64Array} bounds
     * @param {string[]} layers
     * @returns {Uint8Array}
     */
    archive(bounds, layers) {
        const ptr0 = passArrayF64ToWasm0(bounds, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passArrayJsValueToWasm0(layers, wasm.__wbindgen_malloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.tiler_archive(this.__wbg_ptr, ptr0, len0, ptr1, len1);
        if (ret[3]) {
            throw takeFromExternrefTable0(ret[2]);
        }
        var v3 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
        return v3;
    }
    /**
     * @param {Uint8Array} parquet
     * @param {Look} look
     * @param {Uint8Array | null | undefined} features
     * @param {string | null | undefined} name
     * @param {string} prefix
     * @param {string[]} keep
     */
    constructor(parquet, look, features, name, prefix, keep) {
        const ptr0 = passArray8ToWasm0(parquet, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        _assertClass(look, Look);
        var ptr1 = isLikeNone(features) ? 0 : passArray8ToWasm0(features, wasm.__wbindgen_malloc);
        var len1 = WASM_VECTOR_LEN;
        var ptr2 = isLikeNone(name) ? 0 : passStringToWasm0(name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        var len2 = WASM_VECTOR_LEN;
        const ptr3 = passStringToWasm0(prefix, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len3 = WASM_VECTOR_LEN;
        const ptr4 = passArrayJsValueToWasm0(keep, wasm.__wbindgen_malloc);
        const len4 = WASM_VECTOR_LEN;
        const ret = wasm.tiler_new(ptr0, len0, look.__wbg_ptr, ptr1, len1, ptr2, len2, ptr3, len3, ptr4, len4);
        if (ret[2]) {
            throw takeFromExternrefTable0(ret[1]);
        }
        this.__wbg_ptr = ret[0];
        TilerFinalization.register(this, this.__wbg_ptr, this);
        return this;
    }
    /**
     * The properties of the feature `id` of a source, as JSON (`null` when there is none).
     * @param {string} source
     * @param {number} id
     * @returns {string}
     */
    props(source, id) {
        let deferred2_0;
        let deferred2_1;
        try {
            const ptr0 = passStringToWasm0(source, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len0 = WASM_VECTOR_LEN;
            const ret = wasm.tiler_props(this.__wbg_ptr, ptr0, len0, id);
            deferred2_0 = ret[0];
            deferred2_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
        }
    }
    /**
     * @returns {string}
     */
    style() {
        let deferred1_0;
        let deferred1_1;
        try {
            const ret = wasm.tiler_style(this.__wbg_ptr);
            deferred1_0 = ret[0];
            deferred1_1 = ret[1];
            return getStringFromWasm0(ret[0], ret[1]);
        } finally {
            wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
        }
    }
    /**
     * `source` is the style's one source, `roads`: the tile has a layer for each of the old sources.
     * @param {string} source
     * @param {number} z
     * @param {number} x
     * @param {number} y
     * @returns {Uint8Array}
     */
    tile(source, z, x, y) {
        const ptr0 = passStringToWasm0(source, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.tiler_tile(this.__wbg_ptr, ptr0, len0, z, x, y);
        var v2 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
        return v2;
    }
}
if (Symbol.dispose) Tiler.prototype[Symbol.dispose] = Tiler.prototype.free;

/**
 * @param {string} key
 * @param {Uint8Array} array
 */
export function add_nadgrid(key, array) {
    const ptr0 = passStringToWasm0(key, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.add_nadgrid(ptr0, len0, array);
    if (ret[1]) {
        throw takeFromExternrefTable0(ret[0]);
    }
}

/**
 * duckosmFeaturesSelect(specs: number[], run: string) -> string | undefined: the base map's rows from the run's tables of the layers
 * `specs` that were made.
 * @param {Uint32Array} specs
 * @param {string} run
 * @returns {string | undefined}
 */
export function duckosmFeaturesSelect(specs, run) {
    const ptr0 = passArray32ToWasm0(specs, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(run, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.duckosmFeaturesSelect(ptr0, len0, ptr1, len1);
    if (ret[3]) {
        throw takeFromExternrefTable0(ret[2]);
    }
    let v3;
    if (ret[0] !== 0) {
        v3 = getStringFromWasm0(ret[0], ret[1]);
        wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    }
    return v3;
}

/**
 * duckosmLevels(source?, nEdges?, edgeHash?) -> string: the look's keyword `levels` (JSON text) from the stored levels' metadata row
 * (none: the file has no such row); an error says what to do.
 * @param {string | null} [source]
 * @param {number | null} [n_edges]
 * @param {string | null} [edge_hash]
 * @returns {string}
 */
export function duckosmLevels(source, n_edges, edge_hash) {
    let deferred4_0;
    let deferred4_1;
    try {
        var ptr0 = isLikeNone(source) ? 0 : passStringToWasm0(source, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        var len0 = WASM_VECTOR_LEN;
        var ptr1 = isLikeNone(edge_hash) ? 0 : passStringToWasm0(edge_hash, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        var len1 = WASM_VECTOR_LEN;
        const ret = wasm.duckosmLevels(ptr0, len0, !isLikeNone(n_edges), isLikeNone(n_edges) ? 0 : n_edges, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

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
 * @param {string} catalog
 * @param {string} mode
 * @param {boolean} tags
 * @param {string} specs
 * @param {boolean | null} [only]
 * @param {string | null} [run]
 * @returns {string}
 */
export function duckosmPlan(catalog, mode, tags, specs, only, run) {
    let deferred6_0;
    let deferred6_1;
    try {
        const ptr0 = passStringToWasm0(catalog, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(mode, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ptr2 = passStringToWasm0(specs, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len2 = WASM_VECTOR_LEN;
        var ptr3 = isLikeNone(run) ? 0 : passStringToWasm0(run, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        var len3 = WASM_VECTOR_LEN;
        const ret = wasm.duckosmPlan(ptr0, len0, ptr1, len1, tags, ptr2, len2, isLikeNone(only) ? 0xFFFFFF : only ? 1 : 0, ptr3, len3);
        var ptr5 = ret[0];
        var len5 = ret[1];
        if (ret[3]) {
            ptr5 = 0; len5 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred6_0 = ptr5;
        deferred6_1 = len5;
        return getStringFromWasm0(ptr5, len5);
    } finally {
        wasm.__wbindgen_free(deferred6_0, deferred6_1, 1);
    }
}

/**
 * duckosmSubsetLevels(source?, nEdges?, edgeHash?, missing, example?, ids) -> string: the look's keyword `levels` (JSON text) for a map
 * of one mode: the stored levels' metadata row, the row of the plan's "subset" query, and the map's edge_ids (a BigInt64Array).
 * @param {string | null | undefined} source
 * @param {number | null | undefined} n_edges
 * @param {string | null | undefined} edge_hash
 * @param {number} missing
 * @param {bigint | null | undefined} example
 * @param {BigInt64Array} ids
 * @returns {string}
 */
export function duckosmSubsetLevels(source, n_edges, edge_hash, missing, example, ids) {
    let deferred5_0;
    let deferred5_1;
    try {
        var ptr0 = isLikeNone(source) ? 0 : passStringToWasm0(source, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        var len0 = WASM_VECTOR_LEN;
        var ptr1 = isLikeNone(edge_hash) ? 0 : passStringToWasm0(edge_hash, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        var len1 = WASM_VECTOR_LEN;
        const ptr2 = passArray64ToWasm0(ids, wasm.__wbindgen_malloc);
        const len2 = WASM_VECTOR_LEN;
        const ret = wasm.duckosmSubsetLevels(ptr0, len0, !isLikeNone(n_edges), isLikeNone(n_edges) ? 0 : n_edges, ptr1, len1, missing, !isLikeNone(example), isLikeNone(example) ? BigInt(0) : example, ptr2, len2);
        var ptr4 = ret[0];
        var len4 = ret[1];
        if (ret[3]) {
            ptr4 = 0; len4 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred5_0 = ptr4;
        deferred5_1 = len4;
        return getStringFromWasm0(ptr4, len4);
    } finally {
        wasm.__wbindgen_free(deferred5_0, deferred5_1, 1);
    }
}

/**
 * exportLook(look: Look, cols: string[] (highway, oneway, tunnel, bridge, id), positions: number[]) -> string: the simple look
 * for another app's data layer (roadstyle's export_look) from a resolved look.
 * @param {Look} look
 * @param {string[]} cols
 * @param {Int32Array} positions
 * @returns {string}
 */
export function exportLook(look, cols, positions) {
    let deferred4_0;
    let deferred4_1;
    try {
        _assertClass(look, Look);
        const ptr0 = passArrayJsValueToWasm0(cols, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passArray32ToWasm0(positions, wasm.__wbindgen_malloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.exportLook(look.__wbg_ptr, ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

export function main() {
    wasm.main();
}

/**
 * makeArea(edges: Uint8Array, options?: string) -> AreaFiles: a level area's files in memory (roadstyle::level_area::make_files), for
 * a page with no server: `edges` is GeoParquet of the area's edges (the line in `geometry`, longitude and latitude; a duckOSM file's:
 * duckosmPlan's "level_edges"); `options` the JSON text of {"id_col", "highway_col", "layer_col", "bridge_col", "tunnel_col",
 * "junction_col", "band_col", "order" ("priority", "class", a column, or null), "band_dist", "head_m", "near_rules", "heads" (heads.csv
 * text)}, each optional (make_area's defaults).
 * @param {Uint8Array} edges
 * @param {string | null} [options]
 * @returns {AreaFiles}
 */
export function makeArea(edges, options) {
    const ptr0 = passArray8ToWasm0(edges, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    var ptr1 = isLikeNone(options) ? 0 : passStringToWasm0(options, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    var len1 = WASM_VECTOR_LEN;
    const ret = wasm.makeArea(ptr0, len0, ptr1, len1);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return AreaFiles.__wrap(ret[0]);
}

/**
 * makePage(roads: Uint8Array, look: Look, options: string, given?: string) -> string: the page of the roads (GeoParquet) in one
 * call, as render_edges(backend="web") (roadstyle::page_options::page_from; MapLibre stays a placeholder). `look`: resolveLook's of
 * `options` (its JSON text, which a view's palette resolves again), with "state": "live" in its args; `given`: the caller's values
 * over the look's args (JSON text: api_key, street_view_key, resolved_basemaps); `features`: a duckOSM map's base map (Parquet bytes).
 * @param {Uint8Array} roads
 * @param {Look} look
 * @param {string} options
 * @param {string | null} [given]
 * @param {Uint8Array | null} [features]
 * @returns {string}
 */
export function makePage(roads, look, options, given, features) {
    let deferred6_0;
    let deferred6_1;
    try {
        const ptr0 = passArray8ToWasm0(roads, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        _assertClass(look, Look);
        const ptr1 = passStringToWasm0(options, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        var ptr2 = isLikeNone(given) ? 0 : passStringToWasm0(given, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        var len2 = WASM_VECTOR_LEN;
        var ptr3 = isLikeNone(features) ? 0 : passArray8ToWasm0(features, wasm.__wbindgen_malloc);
        var len3 = WASM_VECTOR_LEN;
        const ret = wasm.makePage(ptr0, len0, look.__wbg_ptr, ptr1, len1, ptr2, len2, ptr3, len3);
        var ptr5 = ret[0];
        var len5 = ret[1];
        if (ret[3]) {
            ptr5 = 0; len5 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred6_0 = ptr5;
        deferred6_1 = len5;
        return getStringFromWasm0(ptr5, len5);
    } finally {
        wasm.__wbindgen_free(deferred6_0, deferred6_1, 1);
    }
}

/**
 * makeSources(parquet, look, features, planner, name): stage 1, with makeStyle's arguments.
 * @param {Uint8Array} parquet
 * @param {Look} look
 * @param {Uint8Array | null} [features]
 * @param {Uint8Array | null} [planner]
 * @param {string | null} [name]
 * @returns {Sources}
 */
export function makeSources(parquet, look, features, planner, name) {
    const ptr0 = passArray8ToWasm0(parquet, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    _assertClass(look, Look);
    var ptr1 = isLikeNone(features) ? 0 : passArray8ToWasm0(features, wasm.__wbindgen_malloc);
    var len1 = WASM_VECTOR_LEN;
    var ptr2 = isLikeNone(planner) ? 0 : passArray8ToWasm0(planner, wasm.__wbindgen_malloc);
    var len2 = WASM_VECTOR_LEN;
    var ptr3 = isLikeNone(name) ? 0 : passStringToWasm0(name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    var len3 = WASM_VECTOR_LEN;
    const ret = wasm.makeSources(ptr0, len0, look.__wbg_ptr, ptr1, len1, ptr2, len2, ptr3, len3);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return Sources.__wrap(ret[0]);
}

/**
 * makeStyle(roads: Uint8Array, look: Look, features?: Uint8Array, planner?: Uint8Array, name?: string) -> string; an error is a thrown Error.
 * @param {Uint8Array} parquet
 * @param {Look} look
 * @param {Uint8Array | null} [features]
 * @param {Uint8Array | null} [planner]
 * @param {string | null} [name]
 * @returns {string}
 */
export function makeStyle(parquet, look, features, planner, name) {
    let deferred6_0;
    let deferred6_1;
    try {
        const ptr0 = passArray8ToWasm0(parquet, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        _assertClass(look, Look);
        var ptr1 = isLikeNone(features) ? 0 : passArray8ToWasm0(features, wasm.__wbindgen_malloc);
        var len1 = WASM_VECTOR_LEN;
        var ptr2 = isLikeNone(planner) ? 0 : passArray8ToWasm0(planner, wasm.__wbindgen_malloc);
        var len2 = WASM_VECTOR_LEN;
        var ptr3 = isLikeNone(name) ? 0 : passStringToWasm0(name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        var len3 = WASM_VECTOR_LEN;
        const ret = wasm.makeStyle(ptr0, len0, look.__wbg_ptr, ptr1, len1, ptr2, len2, ptr3, len3);
        var ptr5 = ret[0];
        var len5 = ret[1];
        if (ret[3]) {
            ptr5 = 0; len5 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred6_0 = ptr5;
        deferred6_1 = len5;
        return getStringFromWasm0(ptr5, len5);
    } finally {
        wasm.__wbindgen_free(deferred6_0, deferred6_1, 1);
    }
}

/**
 * The size of the module's memory, in bytes.
 * @returns {number}
 */
export function memoryBytes() {
    const ret = wasm.memoryBytes();
    return ret >>> 0;
}

/**
 * rampStops(cmap: string, n: number) -> string[]: `n` colours ("#rrggbb") at even steps along a ramp (render_edges' cmap: a branca
 * scheme or a matplotlib colormap name, or the JSON text of a list of colours), from the first colour to the last (at least 2), as
 * roadstyle's ColorRamp.stops: for example a colour for each category of a column. An error is a thrown Error.
 * @param {string} cmap
 * @param {number} n
 * @returns {string[]}
 */
export function rampStops(cmap, n) {
    const ptr0 = passStringToWasm0(cmap, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.rampStops(ptr0, len0, n);
    if (ret[3]) {
        throw takeFromExternrefTable0(ret[2]);
    }
    var v2 = getArrayJsValueFromWasm0(ret[0], ret[1]);
    wasm.__wbindgen_free(ret[0], ret[1] * 4, 4);
    return v2;
}

/**
 * readGeoJson(bytes: Uint8Array) -> Roads: the roads of a GeoJSON file (a FeatureCollection in EPSG:4326; roadstyle-io's geojson.rs
 * says how each property becomes a column). An error is a thrown Error.
 * @param {Uint8Array} bytes
 * @returns {Roads}
 */
export function readGeoJson(bytes) {
    const ptr0 = passArray8ToWasm0(bytes, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.readGeoJson(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return Roads.__wrap(ret[0]);
}

/**
 * readGeoParquet(bytes: Uint8Array) -> Roads: the roads of a GeoParquet file (the geometry in the column `geometry`, as makeSources
 * reads it). An error is a thrown Error.
 * @param {Uint8Array} bytes
 * @returns {Roads}
 */
export function readGeoParquet(bytes) {
    const ptr0 = passArray8ToWasm0(bytes, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.readGeoParquet(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return Roads.__wrap(ret[0]);
}

/**
 * readShp(shp: Uint8Array, dbf: Uint8Array, prj?: string, name?: string) -> Roads: the roads of a Shapefile, in EPSG:4326 (roadstyle-io's
 * shp.rs; no prj: no CRS, an error). A GeoPackage is not read here: SQLite is C (the native programs read it). An error is a thrown Error.
 * @param {Uint8Array} shp
 * @param {Uint8Array} dbf
 * @param {string | null} [prj]
 * @param {string | null} [name]
 * @returns {Roads}
 */
export function readShp(shp, dbf, prj, name) {
    const ptr0 = passArray8ToWasm0(shp, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passArray8ToWasm0(dbf, wasm.__wbindgen_malloc);
    const len1 = WASM_VECTOR_LEN;
    var ptr2 = isLikeNone(prj) ? 0 : passStringToWasm0(prj, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    var len2 = WASM_VECTOR_LEN;
    var ptr3 = isLikeNone(name) ? 0 : passStringToWasm0(name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    var len3 = WASM_VECTOR_LEN;
    const ret = wasm.readShp(ptr0, len0, ptr1, len1, ptr2, len2, ptr3, len3);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return Roads.__wrap(ret[0]);
}

/**
 * resolveLook(options: string) -> Look: the look of render_edges' palette, profile and settings; options: {"palette", "profile",
 * "settings", "args", "features", "files"} as JSON text. An error is a thrown Error.
 * @param {string} options
 * @returns {Look}
 */
export function resolveLook(options) {
    const ptr0 = passStringToWasm0(options, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.resolveLook(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return Look.__wrap(ret[0]);
}

/**
 * tileFiles(files, prefix, keep): stage 2 from stage 1's files (GeoJSON or GeoParquet, as style.json names them); the Tiler's
 * style is the saved style with the one vector source (roadstyle::tiled_style).
 * @param {FileSet} files
 * @param {string} prefix
 * @param {string[]} keep
 * @returns {Tiler}
 */
export function tileFiles(files, prefix, keep) {
    _assertClass(files, FileSet);
    const ptr0 = passStringToWasm0(prefix, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passArrayJsValueToWasm0(keep, wasm.__wbindgen_malloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.tileFiles(files.__wbg_ptr, ptr0, len0, ptr1, len1);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return Tiler.__wrap(ret[0]);
}

/**
 * tileSources(sources, prefix, keep): stage 2 from memory (the typed pieces, no GeoJSON text; the sources stay as they are). The
 * Tiler's style has the one vector source `<prefix>roads/{z}/{x}/{y}`, with the pieces' promoteId (roadstyle::tile_stage).
 * @param {Sources} sources
 * @param {string} prefix
 * @param {string[]} keep
 * @returns {Tiler}
 */
export function tileSources(sources, prefix, keep) {
    _assertClass(sources, Sources);
    const ptr0 = passStringToWasm0(prefix, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passArrayJsValueToWasm0(keep, wasm.__wbindgen_malloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.tileSources(sources.__wbg_ptr, ptr0, len0, ptr1, len1);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return Tiler.__wrap(ret[0]);
}

/**
 * @param {string} src
 * @returns {string}
 */
export function toProjstring(src) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(src, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.toProjstring(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * @param {Projection} src
 * @param {Projection} dst
 * @param {Point} point
 */
export function transform(src, dst, point) {
    _assertClass(src, Projection);
    _assertClass(dst, Projection);
    _assertClass(point, Point);
    const ret = wasm.transform(src.__wbg_ptr, dst.__wbg_ptr, point.__wbg_ptr);
    if (ret[1]) {
        throw takeFromExternrefTable0(ret[0]);
    }
}
function __wbg_get_imports() {
    const import0 = {
        __proto__: null,
        __wbg_Error_30c8987f7c2ed4e2: function(arg0, arg1) {
            const ret = Error(getStringFromWasm0(arg0, arg1));
            return ret;
        },
        __wbg___wbindgen_string_get_0380ccaa2f57f0d9: function(arg0, arg1) {
            const obj = arg1;
            const ret = typeof(obj) === 'string' ? obj : undefined;
            var ptr1 = isLikeNone(ret) ? 0 : passStringToWasm0(ret, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            var len1 = WASM_VECTOR_LEN;
            getDataViewMemory0().setInt32(arg0 + 4 * 1, len1, true);
            getDataViewMemory0().setInt32(arg0 + 4 * 0, ptr1, true);
        },
        __wbg___wbindgen_throw_41e9ee4f547fc59a: function(arg0, arg1) {
            throw new Error(getStringFromWasm0(arg0, arg1));
        },
        __wbg_length_7f3c00c40364105e: function(arg0) {
            const ret = arg0.length;
            return ret;
        },
        __wbg_parseFloat_a9cb882d5665c6cb: function(arg0, arg1) {
            const ret = parseFloat(getStringFromWasm0(arg0, arg1));
            return ret;
        },
        __wbg_parseInt_9756a56948abd94c: function(arg0, arg1, arg2) {
            const ret = parseInt(getStringFromWasm0(arg0, arg1), arg2);
            return ret;
        },
        __wbg_prototypesetcall_bc27214492979395: function(arg0, arg1, arg2) {
            Uint8Array.prototype.set.call(getArrayU8FromWasm0(arg0, arg1), arg2);
        },
        __wbg_warn_9760dec0b1364670: function(arg0, arg1) {
            console.warn(getStringFromWasm0(arg0, arg1));
        },
        __wbindgen_generic_0000000000000001: function(arg0, arg1) {
            // Cast intrinsic for `Ref(String) -> Externref`.
            const ret = getStringFromWasm0(arg0, arg1);
            return ret;
        },
        __wbindgen_init_externref_table: function() {
            const table = wasm.__wbindgen_externrefs;
            const offset = table.grow(4);
            table.set(0, undefined);
            table.set(offset + 0, undefined);
            table.set(offset + 1, null);
            table.set(offset + 2, true);
            table.set(offset + 3, false);
        },
    };
    return {
        __proto__: null,
        "./roadstyle_wasm_bg.js": import0,
    };
}

const AreaFilesFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_areafiles_free(ptr, 1));
const FileSetFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_fileset_free(ptr, 1));
const LevelAreaFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_levelarea_free(ptr, 1));
const LookFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_look_free(ptr, 1));
const PointFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_point_free(ptr, 1));
const ProjectionFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_projection_free(ptr, 1));
const RoadsFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_roads_free(ptr, 1));
const SourcesFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_sources_free(ptr, 1));
const TilerFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_tiler_free(ptr, 1));

function addToExternrefTable0(obj) {
    const idx = wasm.__externref_table_alloc();
    wasm.__wbindgen_externrefs.set(idx, obj);
    return idx;
}

function _assertClass(instance, klass) {
    if (!(instance instanceof klass)) {
        throw new Error(`expected instance of ${klass.name}`);
    }
}

function getArrayJsValueFromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    const mem = getDataViewMemory0();
    const result = [];
    for (let i = ptr; i < ptr + 4 * len; i += 4) {
        result.push(wasm.__wbindgen_externrefs.get(mem.getUint32(i, true)));
    }
    wasm.__externref_drop_slice(ptr, len);
    return result;
}

function getArrayU8FromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    return getUint8ArrayMemory0().subarray(ptr / 1, ptr / 1 + len);
}

let cachedBigUint64ArrayMemory0 = null;
function getBigUint64ArrayMemory0() {
    if (cachedBigUint64ArrayMemory0 === null || cachedBigUint64ArrayMemory0.byteLength === 0) {
        cachedBigUint64ArrayMemory0 = new BigUint64Array(wasm.memory.buffer);
    }
    return cachedBigUint64ArrayMemory0;
}

let cachedDataViewMemory0 = null;
function getDataViewMemory0() {
    if (cachedDataViewMemory0 === null || cachedDataViewMemory0.buffer.detached === true || (cachedDataViewMemory0.buffer.detached === undefined && cachedDataViewMemory0.buffer !== wasm.memory.buffer)) {
        cachedDataViewMemory0 = new DataView(wasm.memory.buffer);
    }
    return cachedDataViewMemory0;
}

let cachedFloat64ArrayMemory0 = null;
function getFloat64ArrayMemory0() {
    if (cachedFloat64ArrayMemory0 === null || cachedFloat64ArrayMemory0.byteLength === 0) {
        cachedFloat64ArrayMemory0 = new Float64Array(wasm.memory.buffer);
    }
    return cachedFloat64ArrayMemory0;
}

function getStringFromWasm0(ptr, len) {
    return decodeText(ptr >>> 0, len);
}

let cachedUint32ArrayMemory0 = null;
function getUint32ArrayMemory0() {
    if (cachedUint32ArrayMemory0 === null || cachedUint32ArrayMemory0.byteLength === 0) {
        cachedUint32ArrayMemory0 = new Uint32Array(wasm.memory.buffer);
    }
    return cachedUint32ArrayMemory0;
}

let cachedUint8ArrayMemory0 = null;
function getUint8ArrayMemory0() {
    if (cachedUint8ArrayMemory0 === null || cachedUint8ArrayMemory0.byteLength === 0) {
        cachedUint8ArrayMemory0 = new Uint8Array(wasm.memory.buffer);
    }
    return cachedUint8ArrayMemory0;
}

function isLikeNone(x) {
    return x === undefined || x === null;
}

function passArray32ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 4, 4) >>> 0;
    getUint32ArrayMemory0().set(arg, ptr / 4);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function passArray64ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 8, 8) >>> 0;
    getBigUint64ArrayMemory0().set(arg, ptr / 8);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function passArray8ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 1, 1) >>> 0;
    getUint8ArrayMemory0().set(arg, ptr / 1);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function passArrayF64ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 8, 8) >>> 0;
    getFloat64ArrayMemory0().set(arg, ptr / 8);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function passArrayJsValueToWasm0(array, malloc) {
    const ptr = malloc(array.length * 4, 4) >>> 0;
    for (let i = 0; i < array.length; i++) {
        const add = addToExternrefTable0(array[i]);
        getDataViewMemory0().setUint32(ptr + 4 * i, add, true);
    }
    WASM_VECTOR_LEN = array.length;
    return ptr;
}

function passStringToWasm0(arg, malloc, realloc) {
    if (realloc === undefined) {
        const buf = cachedTextEncoder.encode(arg);
        const ptr = malloc(buf.length, 1) >>> 0;
        getUint8ArrayMemory0().subarray(ptr, ptr + buf.length).set(buf);
        WASM_VECTOR_LEN = buf.length;
        return ptr;
    }

    let len = arg.length;
    let ptr = malloc(len, 1) >>> 0;

    const mem = getUint8ArrayMemory0();

    let offset = 0;

    for (; offset < len; offset++) {
        const code = arg.charCodeAt(offset);
        if (code > 0x7F) break;
        mem[ptr + offset] = code;
    }
    if (offset !== len) {
        if (offset !== 0) {
            arg = arg.slice(offset);
        }
        ptr = realloc(ptr, len, len = offset + arg.length * 3, 1) >>> 0;
        const view = getUint8ArrayMemory0().subarray(ptr + offset, ptr + len);
        const ret = cachedTextEncoder.encodeInto(arg, view);

        offset += ret.written;
        ptr = realloc(ptr, len, offset, 1) >>> 0;
    }

    WASM_VECTOR_LEN = offset;
    return ptr;
}

function takeFromExternrefTable0(idx) {
    const value = wasm.__wbindgen_externrefs.get(idx);
    wasm.__externref_table_dealloc(idx);
    return value;
}

let cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
cachedTextDecoder.decode();
const MAX_SAFARI_DECODE_BYTES = 2146435072;
let numBytesDecoded = 0;
function decodeText(ptr, len) {
    numBytesDecoded += len;
    if (numBytesDecoded >= MAX_SAFARI_DECODE_BYTES) {
        cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
        cachedTextDecoder.decode();
        numBytesDecoded = len;
    }
    return cachedTextDecoder.decode(getUint8ArrayMemory0().subarray(ptr, ptr + len));
}

const cachedTextEncoder = new TextEncoder();

if (!('encodeInto' in cachedTextEncoder)) {
    cachedTextEncoder.encodeInto = function (arg, view) {
        const buf = cachedTextEncoder.encode(arg);
        view.set(buf);
        return {
            read: arg.length,
            written: buf.length
        };
    };
}

let WASM_VECTOR_LEN = 0;

let wasmModule, wasmInstance, wasm;
function __wbg_finalize_init(instance, module) {
    wasmInstance = instance;
    wasm = instance.exports;
    wasmModule = module;
    cachedBigUint64ArrayMemory0 = null;
    cachedDataViewMemory0 = null;
    cachedFloat64ArrayMemory0 = null;
    cachedUint32ArrayMemory0 = null;
    cachedUint8ArrayMemory0 = null;
    wasm.__wbindgen_start();
    return wasm;
}

async function __wbg_load(module, imports) {
    if (typeof Response === 'function' && module instanceof Response) {
        if (!module.ok) {
            throw new Error(`failed to fetch Wasm: ${module.status} ${module.statusText} fetching '${module.url}'`);
        }

        if (typeof WebAssembly.instantiateStreaming === 'function') {
            try {
                return await WebAssembly.instantiateStreaming(module, imports);
            } catch (e) {
                const validResponse = expectedResponseType(module.type);

                if (validResponse && module.headers.get('Content-Type') !== 'application/wasm') {
                    console.warn("`WebAssembly.instantiateStreaming` failed because your server does not serve Wasm with `application/wasm` MIME type. Falling back to `WebAssembly.instantiate` which is slower. Original error:\n", e);

                } else { throw e; }
            }
        }

        const bytes = await module.arrayBuffer();
        return await WebAssembly.instantiate(bytes, imports);
    } else {
        const instance = await WebAssembly.instantiate(module, imports);

        if (instance instanceof WebAssembly.Instance) {
            return { instance, module };
        } else {
            return instance;
        }
    }

    function expectedResponseType(type) {
        switch (type) {
            case 'basic': case 'cors': case 'default': return true;
        }
        return false;
    }
}

function initSync(module) {
    if (wasm !== undefined) return wasm;


    if (module !== undefined) {
        if (Object.getPrototypeOf(module) === Object.prototype) {
            ({module} = module)
        } else {
            console.warn('using deprecated parameters for `initSync()`; pass a single object instead')
        }
    }

    const imports = __wbg_get_imports();
    if (!(module instanceof WebAssembly.Module)) {
        module = new WebAssembly.Module(module);
    }
    const instance = new WebAssembly.Instance(module, imports);
    return __wbg_finalize_init(instance, module);
}

async function __wbg_init(module_or_path) {
    if (wasm !== undefined) return wasm;


    if (module_or_path !== undefined) {
        if (Object.getPrototypeOf(module_or_path) === Object.prototype) {
            ({module_or_path} = module_or_path)
        } else {
            console.warn('using deprecated parameters for the initialization function; pass a single object instead')
        }
    }

    if (module_or_path === undefined) {
        module_or_path = new URL('roadstyle_wasm_bg.wasm', import.meta.url);
    }
    const imports = __wbg_get_imports();

    if (typeof module_or_path === 'string' || (typeof Request === 'function' && module_or_path instanceof Request) || (typeof URL === 'function' && module_or_path instanceof URL)) {
        module_or_path = fetch(module_or_path);
    }

    const { instance, module } = await __wbg_load(await module_or_path, imports);

    return __wbg_finalize_init(instance, module);
}

export { initSync, __wbg_init as default };
