"""The solver's input (docs/design/level_input.md): roads.parquet and pairs.csv in OUT_DIR, from any edges roadstyle draws.

    python scripts/level_input.py edges.gpkg OUT_DIR                     # any geo file roadstyle reads (GeoPackage, GeoJSON, GeoParquet, ...)
    python scripts/level_input.py area.duckdb OUT_DIR --query "SELECT * EXCLUDE (geometry), ST_AsWKB(geometry) AS geometry FROM driving.edges"

roads.parquet and pairs.csv are written again on every run; edits.csv (your changes to the pairs) is created empty once and never written
after that. Then: python scripts/solve_levels.py OUT_DIR
"""
import argparse
from pathlib import Path

import roadstyle as rs


def read_edges(source, query=None, geometry=None):
    if Path(source).suffix == ".duckdb":
        if not query:
            raise SystemExit("a .duckdb source needs --query (a SELECT of the edges, the geometry as WKB or WKT)")
        import duckdb
        con = duckdb.connect(str(source), read_only=True)
        con.execute("LOAD spatial")
        return rs.from_duckdb(con, query, geometry=geometry).gdf
    return rs.load_edges(source).gdf


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="the edges: a geo file, or a .duckdb with --query")
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--query", help="with a .duckdb source: the SELECT of the edges")
    ap.add_argument("--geometry", help="the geometry column of --query (default: found by name)")
    ap.add_argument("--id-col", default="edge_id", help="the edges' id column (default edge_id; the row number when absent)")
    ap.add_argument("--band-col", help="the caller's bands (integers); default: the level from the layer / bridge / tunnel tags")
    ap.add_argument("--order", default="priority", help='"priority" (default), "class", or a column of numbers')
    ap.add_argument("--band-dist", type=float, default=10.0, help="metres: roads of different bands this near are over / under (default 10)")
    a = ap.parse_args(argv)
    edges = read_edges(a.source, a.query, a.geometry)
    roads, pairs = rs.level_input(edges, id_col=a.id_col, band_col=a.band_col, order=a.order, band_dist=a.band_dist)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    roads.to_parquet(a.out_dir / "roads.parquet")
    pairs.to_csv(a.out_dir / "pairs.csv", index=False)
    edits = a.out_dir / "edits.csv"
    if not edits.exists():
        edits.write_text("relation,a,b,a_end,b_end,enabled\n")
    print(f"{len(edges)} edges -> {len(roads)} roads, {len(pairs)} pairs: "
          + ", ".join(f"{k} {v}" for k, v in pairs["relation"].value_counts().items()) + f" -> {a.out_dir}")


if __name__ == "__main__":
    main()
