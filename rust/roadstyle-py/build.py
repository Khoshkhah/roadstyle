"""Build the Rust extension roadstyle._rust for this Python and put it next to the Python package (a development build; the
wheels come from maturin in CI). Run it with the Python that runs roadstyle:

    python rust/roadstyle-py/build.py            # release build
"""
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
env = {**os.environ, "PYO3_PYTHON": sys.executable, "CARGO_BUILD_JOBS": os.environ.get("CARGO_BUILD_JOBS", "4")}
subprocess.run(["cargo", "build", "--release", "--offline", "-p", "roadstyle-py"], cwd=ROOT / "rust", env=env, check=True)
target = Path(env.get("CARGO_TARGET_DIR", ROOT / "rust" / "target")) / "release"
lib = {"linux": "lib_rust.so", "darwin": "lib_rust.dylib", "win32": "_rust.dll"}[sys.platform]
ext = ".pyd" if sys.platform == "win32" else ".abi3.so"
dest = ROOT / "src" / "roadstyle" / f"_rust{ext}"
shutil.copyfile(target / lib, dest)
print(f"{dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB) for {sysconfig.get_platform()}")
