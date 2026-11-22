# Vehicles of a SUMO run on the dashboard

This page plays a SUMO run on roadstyle's dashboard with `rs.vehicles` (`dashboard/vehicles.js`). The vehicles are 3D boxes in
their lanes, drawn by a custom layer from a `VehicleScene` (`rust/roadstyle-wasm` built with the feature `vehicles`, and
`rust/roadstyle-sim`). The design is `docs/design/vehicles_spec.md`. This is phase P1: flat ground, boxes, play, pause and seek.

From Python, one call makes a self-contained page with the play bar (the module is in the package; in a source checkout, run
`rust/roadstyle-wasm/build_vehicles.sh` first):

```python
rs.render_dashboard(edges, vehicles={"fcd": "monaco_fcd.parquet", "net": "monaco.net.xml"}).save("vehicles.html")
```

The page below loads the module and the run from files next to it.

## Build the WebAssembly module

Run these commands in the root of the repository:

```bash
CARGO_BUILD_JOBS=4 cargo build --release --target wasm32-unknown-unknown --manifest-path rust/Cargo.toml -p roadstyle-wasm --features vehicles
```

```bash
wasm-bindgen --target web --out-dir examples/vehicles/pkg rust/target/wasm32-unknown-unknown/release/roadstyle_wasm.wasm
```

## Make the SUMO run

The run must come from the same network as the roads of the page: duckOSM's Monaco build.

1. Write the SUMO network with duckOSM: `duckosm.sumo.to_sumo(con, out_dir, net_name="monaco")` on `monaco.duckdb`.
2. Make random trips: `python $SUMO_HOME/tools/randomTrips.py -n monaco.net.xml -r routes.rou.xml -e 600 -p 1.5 --validate`.
3. Run SUMO with the FCD output as Parquet, in lon/lat:
   `sumo -n monaco.net.xml -r routes.rou.xml --end 900 --fcd-output monaco_fcd.parquet --fcd-output.geo true`.
4. Put `monaco_fcd.parquet` and `monaco.net.xml` in `examples/vehicles/data/`.

Git ignores `pkg/` and `data/`.

## The dashboard page (the Rust page writer)

`dashboard.html` is the same run on roadstyle's full dashboard (the panel, the toolbar, the themes), written by the Rust CLI. The page loads the
run itself (the option `vehicles`), with the colours and sizes of the look's `vehicles` section; roadstyle's play bar (`rust/roadstyle-assets/files/static/vehicles/play_bar.js`) and `dashboard_script.js` (the view) are the page script. Build the CLI, then run this in `examples/vehicles/`:

```bash
cargo build --release --manifest-path ../../rust/Cargo.toml -p roadstyle-cli
```

```bash
../../rust/target/release/roadstyle page ../../rust/roadstyle-rs/tests/data/monaco/roads.parquet dashboard.html --template dashboard --vehicles '{"wasm": "./pkg/roadstyle_wasm.js", "fcd": "./data/monaco_fcd.parquet", "net": "./data/monaco.net.xml"}' --page-script "$(cat ../../rust/roadstyle-assets/files/static/vehicles/play_bar.js dashboard_script.js)"
```

Open `http://localhost:8000/examples/vehicles/dashboard.html`. Git ignores `dashboard.html`.

## Open the page

Serve the root of the repository, because the page reads the modules and the data from there:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/examples/vehicles/`.
