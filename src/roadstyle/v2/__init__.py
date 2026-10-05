"""roadstyle v2: Decoupled, multi-modal transport network cartography."""

from roadstyle.v2 import adapters
from roadstyle.v2.engine.casing import split_casing_geometry
from roadstyle.v2.engine.compiler import (
    WebMap,
    compile_map,
    lateral_offset_expr,
    meter_to_pixel_width_expr,
)
from roadstyle.v2.engine.pairs import (
    discover_pair_table,
    merge_pair_overrides,
    read_pair_table,
    write_pair_table,
)
from roadstyle.v2.engine.primitives import (
    Channel,
    Corridor,
    Demarcation,
    Glyph,
    Patch,
    ViewPreset,
)
from roadstyle.v2.engine.solver import StackingSolution, solve_stacking, write_pair_tables
from roadstyle.v2.render import render

__all__ = [
    "Corridor",
    "Channel",
    "Demarcation",
    "Patch",
    "Glyph",
    "ViewPreset",
    "split_casing_geometry",
    "solve_stacking",
    "discover_pair_table",
    "merge_pair_overrides",
    "read_pair_table",
    "write_pair_table",
    "write_pair_tables",
    "StackingSolution",
    "compile_map",
    "WebMap",
    "meter_to_pixel_width_expr",
    "lateral_offset_expr",
    "render",
    "adapters",
]
