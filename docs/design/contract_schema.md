# The dashboard contract as types and a schema (T4 plan)

Date: 2026-10-25. Status: approved, a plan for phase T4 of the target architecture (`target_architecture.md`, (h)). It has no code. It starts
after T3's `Mark` (N30), because the contract's property names come from `Mark`.

## The problem

The contract between the engine and the dashboard is hidden today (review pattern 6):

- The engine writes the metadata keys with `json!` in `roadstyle-engine/src/contract.rs` and `layers.rs`. Python writes the same keys in
  `render_web.py`. No type says what a key holds.
- The dashboard reads the keys by name in `index.js` (`fromStyle`) and in the modules. `index.d.ts` is written by hand.
- `roadstyle:contract` is 1 in each style with the contract, but no code reads it. A style of a newer version gives a wrong map with no
  message.
- `docs/reference/contract.md` is the inventory, and `tests/test_contract_names.py` checks the names only, not the values.

## What is in the contract

(h) item 1 lists six parts. This plan gives each part one owner and one check.

| Part | The one definition | Check |
|---|---|---|
| (1) the `roadstyle:*` metadata keys of a style | Rust structs in `roadstyle-engine::contract` (below) | serde round trip of each golden style; the schema |
| (2) the road table (format, columns) | `roadstyle-model` (target architecture (b)) | not in this step: (b) owns it |
| (3) the feature-state names (`hover`, `select`, `rs_c`, `rs_w`) | constants in `contract.rs`, written into `roadstyle:live` | `test_contract_names.py` |
| (4) the global-state names `rs_*` | the `State` struct (below) | the schema; `test_contract_names.py` |
| (5) the layer roles and groups | `Role` (`roadstyle:sources`), `contract::pick_layers` | the schema |
| (6) the `rs` methods and events | `index.d.ts` | the `index.d.ts` check (below) |

The page's own keywords (`RS_OPTIONS`: the base maps, Street View, the panel) are not in the style. They stay in `PageOptions`
(`rust/roadstyle/src/page.rs`), as (h) item 5 says. The schema has a second part for them (below), because a host page writes them too.

## Step 1: the types

In `roadstyle-engine/src/contract.rs`, one struct for each metadata key, with serde:

```rust
#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Metadata {
    #[serde(rename = "roadstyle:contract")]       pub contract: u32,
    #[serde(rename = "roadstyle:sources")]        pub sources: BTreeMap<Role, SourceRef>,
    #[serde(rename = "roadstyle:arrows")]         pub arrows: Option<ArrowKind>,
    #[serde(rename = "roadstyle:interaction")]    pub interaction: Interaction,
    #[serde(rename = "roadstyle:color_options")]  pub color_options: Vec<ColorOption>,
    #[serde(rename = "roadstyle:images")]         pub images: Images,
    #[serde(rename = "roadstyle:state", skip_serializing_if = "Option::is_none")]    pub state: Option<State>,       // state "live"
    #[serde(rename = "roadstyle:controls", skip_serializing_if = "Option::is_none")] pub controls: Option<Controls>, // state "live"
    #[serde(rename = "roadstyle:live", skip_serializing_if = "Option::is_none")]     pub live: Option<Live>,         // live_data
}
```

- `Role` is an enum of the road roles (`simple`, `slots`, `arrows`, `decks`, `shadows`, and the full look's four until N16). `ArrowKind`
  is `points` or `line`. `Controls` has the facts of the look and of the roads: the filter panel, the overlays, the tunnel look, the
  road fill, `fill_layers`, `pick`, `modes`, `dashes`, `views`, `items`. It has no page keyword (rule 5).
- The writers (`describe`, `filter_panel`, `page_state` and the others) build these structs. They do not build `json!` trees. The style
  writer serializes them, so the bytes do not change. A test checks this on the goldens before the old code goes.
- The keys that only stage 1's saved `style.json` has (`roadstyle:tiles`, `roadstyle:columns`, `roadstyle:planner*`) are not in the
  contract. They are the engine's own (stage 1 to stage 2). They get their own struct in `roadstyle-tiles`, not in `Metadata`.
- The layer metadata (`roadstyle:group`, `roadstyle:over`, `roadstyle:position`) is not in a page's style (the page writer removes it)
  and is not read by the dashboard (b3d-extrude). It stays the export's. It is not in the contract.

**Decided (2026-10-25):** every style that the engine writes has `roadstyle:contract` (the version number only), the same direction as
"`pick` and `sources` for every style" (design-tile-minzoom). `state`, `controls` and `live` stay optional: only a style with state
"live" has them. Then the version check (step 4) covers the duckosm-rust page and the level editor, which have no `state`.

## Step 2: the schema

- `schemars` (version 1, already in the lock file through rmcp) derives the schema from `Metadata` and from `PageOptions`. It is a
  dev-dependency of the engine and the facade, or a feature `schema` that only a test turns on. The wasm module does not get it.
- A test writes `contract.schema.json` (`ROADSTYLE_BLESS=1`, as the goldens) and fails when the file differs from the types. The file
  goes to `rust/roadstyle-assets/files/static/dashboard/contract.schema.json`, so the npm package `roadstyle-dashboard` has it beside
  `index.d.ts`. It has two definitions: `Metadata` (the style) and `PageOptions` (`RS_OPTIONS`).
- **The check of the styles.** A Rust test reads each golden style (Monaco and Södermalm pages, the cases, the export styles) and
  deserializes its `metadata` into `Metadata`. Because of `deny_unknown_fields`, a key that the types do not have fails. Python's
  styles go through the same check in `tests/test_contract_schema.py`, with `jsonschema` (4.26, in the environment) and the schema file.
  This is the check that Python and Rust write the same contract, until P7 removes Python's writer.

## Step 3: the `index.d.ts` check

Generated TypeScript is a later step ((h) item 2). Until then, a test in `tests/test_contract_names.py`:

- each property of `PageOptions` and of `Controls` in the schema is a key of `DashboardOptions` in `index.d.ts` and of `RS_DEFAULTS` in
  `dashboard/index.js`;
- each key of `RS_DEFAULTS` is in the schema, or in a short list of the dashboard's own options (`style`, `prefix`, `road_table`), each
  with its reason.

## Step 4: the version error

- `dashboard/core.js` gets `CONTRACT = 1`, the newest version that it knows. A test checks that it equals `contract::CONTRACT`.
- A style with no `roadstyle:contract` was made before every style had it. The dashboard reads it as version 1 and writes a note on
  the console, not an error.
- `rsDashboard` reads `roadstyle:contract` of the style (also in `setStyle`). A newer version is an error: `console.error` with the two
  versions, and the returned object has `error` (the same text). The dashboard then adds no road interaction for that style, because a
  wrong map with no message is the fault that (h) item 4 removes. An older version is read as it is.
- A change that an older dashboard cannot read increases `CONTRACT` by one, in the same commit as the change. A new optional key does
  not change it. The CHANGELOG names each increase.
- Test: a page whose style has `roadstyle:contract` 2 shows the error in the console and in `rsDashboard`'s result, and has no hover.

## The order and the size

1. The types and the writers (step 1), with the goldens unchanged: roadstyle-rs's files (`contract.rs`, `layers.rs`), so with its go,
   or by roadstyle-rs. About 300 lines changed in the engine.
2. The schema and its two checks (step 2): this lane. One new file, two tests.
3. The `index.d.ts` check (step 3) and the version error (step 4): this lane, the dashboard. About 40 lines of JS and two tests.

Each step lands alone. Steps 2 to 4 need step 1.
