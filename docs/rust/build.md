# Build from source

<p class="lead">Build the Rust engine from a roadstyle checkout: the Python wheel, the development module, the WebAssembly package
and the crate documentation.</p>

You need this page only for a source install or for work on the engine. The wheels on PyPI have the engine in them.

## Install a Rust toolchain

Install Rust with [rustup](https://rustup.rs). CI uses Rust 1.99.1, the version that the golden tests were checked with:

```bash
rustup toolchain install 1.99.1
```

On a machine with little memory, set the number of parallel compiler jobs. The release build uses link-time optimization, which
needs much memory for each job:

```bash
export CARGO_BUILD_JOBS=4
```

## Install roadstyle from the source

The package builds with [maturin](https://www.maturin.rs) (`pyproject.toml`: `build-backend = "maturin"`). pip gets maturin and
builds the module `roadstyle._rust`:

```bash
git clone https://github.com/Khoshkhah/roadstyle.git && cd roadstyle
pip install ".[dev]"
```

To make a wheel and not install it:

```bash
pip wheel . --no-deps -w dist
```

The result is one wheel for your platform, for example `roadstyle-0.25.0-cp39-abi3-linux_x86_64.whl`. The tag `abi3` means
that one wheel works with each Python version that roadstyle supports (3.10 and newer). The source distribution (sdist) builds
the same way, so it also needs a Rust toolchain.

## Build the module for development

To work on the engine with `PYTHONPATH=src` and no install, build the module and copy it next to the Python package:

```bash
python rust/roadstyle-py/build.py
```

The script writes `src/roadstyle/_rust.abi3.so` (`_rust.pyd` on Windows) for the Python that runs it. Git ignores this file. Run
the script again after each change in `rust/` or in `rust/roadstyle-assets/files/data/` and `rust/roadstyle-assets/files/static/`, because the crates read
these files when they are built.

## Build the WebAssembly package

Add the WebAssembly target and the `wasm-bindgen` program. Its version must be the version of the `wasm-bindgen` crate in
`rust/roadstyle-wasm/Cargo.toml` (0.2.129):

```bash
rustup target add wasm32-unknown-unknown
cargo install wasm-bindgen-cli --version 0.2.129
```

Build the module and make its JavaScript glue:

```bash
cargo build --profile dist --target wasm32-unknown-unknown --manifest-path rust/Cargo.toml -p roadstyle-wasm
wasm-bindgen --target web --out-dir pkg rust/target/wasm32-unknown-unknown/dist/roadstyle_wasm.wasm
```

The profile `dist` is release with fat LTO and one codegen unit (`rust/Cargo.toml`): the wheels and the wasm packages use it. The tests
and the development builds use `release`, which builds much faster. `cargo test` at `rust/` tests the libraries; the programs are not
default members, so test them by name: `cargo test --release -p roadstyle-cli -p roadstyle-snapshot`.

`pkg/` then has `roadstyle_wasm.js`, `roadstyle_wasm_bg.wasm` (about 6 MB) and the TypeScript types. How to use them:
[Use roadstyle in the browser](browser.md).

## Run the tests

The Rust tests compare the engine with the outputs of the Python engine (the goldens). The large goldens are on the GitHub
pre-release `rust-test-data`. `get_goldens.sh` gets them and checks their SHA-256:

```bash
cd rust
roadstyle-rs/tests/get_goldens.sh
cargo test --release
```

The Python tests run the whole suite with the Rust engine:

```bash
pytest
```

## One shared build folder

On Kaveh's machine, all worktrees of roadstyle use one build folder: `.shared-target` in the main checkout. Thus the
dependencies compile one time, not one time for each worktree. The `cargo` wrapper of duckosm-rust (`tools/cargo`,
installed as `~/.local/bin/cargo`) does this for roadstyle and for duckosm-rust. Its description is in duckosm-rust
`docs/development.md`, "One shared build folder". In summary:

- If `rust/` has no `target`, the wrapper makes `rust/target` a link to `.shared-target`. The paths `rust/target/...` on
  this page and in the scripts thus stay correct. A worktree that has a `rust/target/` folder of its own keeps it: the
  change starts when you delete the old folder.
- When the workspace that builds changes, the wrapper touches the files of the new workspace that Git tracks. Without
  this step, a worktree with older files can get the binary of the worktree that built last. The workspace crates then
  compile again, but the dependencies do not.
- A lock lets the cargo commands of only one worktree use the folder at a time. A `cargo run` that does not stop (for
  example `roadstyle serve`) thus stops the builds of the other worktrees: run the program from `rust/target/` instead.

CI has no wrapper and uses a plain `rust/target/`. To stop the shared folder, delete `~/.local/bin/cargo`, or set
`CARGO_TARGET_DIR` to a folder outside `.shared-target`.

## Read the crate documentation

The crates are not on crates.io yet, so docs.rs does not have them. Make the documentation from the source:

```bash
cd rust
cargo doc --no-deps --open
```

**See also:** [Architecture of the Rust version](architecture.md)
