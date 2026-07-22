"""``roadstyle`` command-line interface — turn a road file into a styled map without writing Python.

    roadstyle edges.gpkg -o map.html --basemap dark_matter
    roadstyle edges.gpkg --color-by aadt --cmap viridis --width-by 1 6 -f web
    roadstyle edges.gpkg --include motorway trunk primary -o major.html

A thin wrapper over :func:`roadstyle.render_edges` (the ``web`` MapLibre backend — the default — and
``folium``) and :func:`roadstyle.save` / :func:`roadstyle.save_spec` / :func:`roadstyle.to_geojson`
(the ``rsjs`` roadstyle.js page / JSON outputs). Every styling flag mirrors the Python keyword of
the same name, so the CLI and the library stay in lock-step.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__

# output format → default file extension for the derived output name
_EXT = {"web": ".html", "folium": ".html", "rsjs": ".html", "spec": ".json", "geojson": ".geojson"}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="roadstyle",
        description="Render a road-edge file (GPKG, GeoJSON, Shapefile, …) into a styled "
                    "interactive map or a portable JSON spec.",
        epilog="examples:\n"
               "  roadstyle edges.gpkg -o map.html --basemap dark_matter\n"
               "  roadstyle edges.gpkg --palette carto --basemap positron\n"
               "  roadstyle edges.gpkg --include motorway trunk primary -o major.html\n"
               "  roadstyle edges.gpkg --color-by aadt --cmap viridis --width-by 1 6 -f web\n"
               "  roadstyle edges.gpkg -f spec -o map_data.json   # JSON for your own frontend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", help="road-data file with a road-class column (any CRS).")
    p.add_argument("-o", "--output",
                   help="output path (default: input name with the format's extension).")
    p.add_argument("-f", "--format", default="web",
                   choices=["web", "folium", "rsjs", "spec", "geojson"],
                   help="web = self-contained MapLibre map (default); folium = interactive folium "
                        "HTML; rsjs = standalone roadstyle.js page; spec = JSON spec; "
                        "geojson = styled GeoJSON.")
    p.add_argument("--version", action="version", version=f"roadstyle {__version__}")

    style = p.add_argument_group("styling")
    style.add_argument("--palette", default="highsat", choices=["highsat", "carto"],
                       help="class palette (default: highsat).")
    style.add_argument("--basemap", help="the primary base map layer (a key in BASEMAPS; "
                       "default from settings: voyager).")
    style.add_argument("--tooltip", nargs="+", metavar="COL",
                       help="columns to show in the hover tooltip.")

    flt = p.add_argument_group("filtering")
    flt.add_argument("--include", nargs="+", metavar="TYPE", help="highway types to keep.")
    flt.add_argument("--exclude", nargs="+", metavar="TYPE", help="highway types to drop.")

    dd = p.add_argument_group("data-driven styling (colour/size by your own column)")
    dd.add_argument("--color-by", metavar="COLUMN",
                    help="colour edges by this column instead of road class.")
    dd.add_argument("--colors", metavar="JSON",
                    help='categorical map for --color-by, as JSON, e.g. \'{"a":"#f00"}\'.')
    dd.add_argument("--cmap", help="continuous colormap for a numeric --color-by (e.g. viridis).")
    dd.add_argument("--vmin", type=float, help="lower bound of the numeric colour ramp.")
    dd.add_argument("--vmax", type=float, help="upper bound of the numeric colour ramp.")
    dd.add_argument("--width-by", nargs=2, type=float, metavar=("MIN", "MAX"),
                    help="scale line width between MIN and MAX px by the numeric --color-by.")

    web = p.add_argument_group("web backend (-f web)")
    web.add_argument("--view-3d", action="store_true",
                     help="3D view: tilted camera + extruded, ramped bridge decks.")
    web.add_argument("--pitch", type=float, help="starting camera tilt in degrees (0-85).")
    web.add_argument("--bearing", type=float, help="starting camera rotation in degrees.")
    web.add_argument("--no-arrows", action="store_true", help="hide one-way direction arrows.")
    web.add_argument("--no-labels", action="store_true", help="hide street-name labels.")
    web.add_argument("--no-filter", action="store_true", help="hide the road-class filter panel.")
    web.add_argument("--no-basemap-switcher", action="store_true",
                     help="hide the in-map base-layer dropdown.")
    web.add_argument("--tiles", action="store_true",
                     help="pack the roads as an embedded-PMTiles vector tileset instead of "
                          "inline GeoJSON (client-side scale for big networks; needs the "
                          "'tiles' extra).")
    web.add_argument("--no-compress", action="store_true",
                     help="write the map data as plain JSON instead of gzipped blobs "
                          "(bigger files; for very old browsers without DecompressionStream).")

    src = p.add_argument_group("input")
    src.add_argument("--highway-col", default="highway",
                     help="name of the road-class column (default: highway).")
    src.add_argument("--layer", help="layer to read from a multi-layer file (e.g. a GPKG).")
    return p


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``roadstyle`` console script. Returns a process exit code."""
    args = _build_parser().parse_args(argv)

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"roadstyle: input file not found: {in_path}", file=sys.stderr)
        return 2

    out_path = Path(args.output) if args.output else in_path.with_suffix(_EXT[args.format])

    colors = None
    if args.colors:
        try:
            colors = json.loads(args.colors)
        except json.JSONDecodeError as e:
            print(f"roadstyle: --colors is not valid JSON: {e}", file=sys.stderr)
            return 2

    # Imported lazily so `roadstyle --version` / `--help` stay fast and don't pull in geopandas.
    from .edges import load_edges
    from .emit import save, save_spec, to_geojson
    from .filters import filter_edges
    from .render import render_edges

    try:
        edges = load_edges(str(in_path), class_col=args.highway_col, layer=args.layer)
        g = edges.gdf
        col = edges.class_col

        if args.include or args.exclude:
            g = filter_edges(g, include=args.include, exclude=args.exclude, highway_col=col)

        # Styling keywords shared by every output path; drop the ones the user didn't set so each
        # function keeps its own defaults.
        style_kw = {
            "palette": args.palette, "highway_col": col,
            "color_by": args.color_by, "colors": colors, "cmap": args.cmap,
            "vmin": args.vmin, "vmax": args.vmax,
            "width_by": tuple(args.width_by) if args.width_by else None,
            "basemap": args.basemap, "tooltip": args.tooltip,
        }
        style_kw = {k: v for k, v in style_kw.items() if v is not None}

        if args.format == "web":
            web_kw = {"arrows": not args.no_arrows, "labels": not args.no_labels,
                      "filter_control": not args.no_filter,
                      "basemap_switcher": not args.no_basemap_switcher,
                      "compress": not args.no_compress,
                      "tiles": args.tiles,
                      "view_3d": args.view_3d}
            if args.pitch is not None:
                web_kw["pitch"] = args.pitch
            if args.bearing is not None:
                web_kw["bearing"] = args.bearing
            render_edges(g, backend="web", **style_kw, **web_kw).save(str(out_path))
        elif args.format == "folium":
            render_edges(g, backend="folium", **style_kw).save(str(out_path))
        elif args.format == "rsjs":
            save(g, str(out_path), **style_kw)
        elif args.format == "spec":
            save_spec(g, str(out_path), **style_kw)
        elif args.format == "geojson":
            out_path.write_text(json.dumps(to_geojson(g, **style_kw)), encoding="utf-8")
    except (ValueError, KeyError, FileNotFoundError) as e:
        print(f"roadstyle: {e}", file=sys.stderr)
        return 1

    print(f"wrote {out_path}  ({len(g):,} edges, {args.format})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
