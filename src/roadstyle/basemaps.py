"""Base-map (tile) providers + thumbnail metadata for the switcher control."""
from __future__ import annotations

import os
from dataclasses import dataclass

_CARTO_ATTR = "© OpenStreetMap contributors © CARTO"
_OSM_ATTR = "© OpenStreetMap contributors"
_ESRI_ATTR = "Tiles © Esri"

# In-memory session store for API keys: {"default": "...", "mapbox": "...", ...}
_SESSION_API_KEYS: dict[str, str] = {}
_TOKEN_KEYWORDS = ("api_key", "accessToken", "apikey", "apiKey", "token", "key", "access_token")


def set_api_key(api_key: str, provider: str | None = None) -> None:
    """Set an API key / access token globally for the current Python session.

    Parameters
    ----------
    api_key : str
        The token/API key string.
    provider : str, optional
        Provider name (e.g. "mapbox", "stadia", "maptiler", "thunderforest", "jawg").
        If omitted (None), sets the default key used for any provider without a provider-specific key.
    """
    key_name = provider.lower().strip() if provider else "default"
    _SESSION_API_KEYS[key_name] = api_key


def get_api_key(provider: str | None = None) -> str | None:
    """Resolve an API key from session storage, StyleConfig / roadstyle.json, or environment variables.

    Precedence order (highest to lowest):
    1. Provider-specific key set via ``set_api_key(..., provider="...")``
    2. Default key set via ``set_api_key(...)``
    3. ``StyleConfig.api_keys[provider]`` or ``StyleConfig.api_key`` (from ``roadstyle.json``)
    4. Provider-specific environment variable (e.g. ``MAPBOX_API_KEY``, ``MAPBOX_ACCESS_TOKEN``, ``STADIA_API_KEY``)
    5. ``ROADSTYLE_API_KEY`` environment variable
    """
    p_norm = provider.lower().replace("-", "_").strip() if provider else None

    # 1. Session store (provider-specific, then default)
    if p_norm and p_norm in _SESSION_API_KEYS:
        return _SESSION_API_KEYS[p_norm]
    if "default" in _SESSION_API_KEYS:
        return _SESSION_API_KEYS["default"]

    # 2. Config / roadstyle.json
    try:
        from . import _settings
        cfg = _settings.style().get("config", {})
        if p_norm:
            api_keys = cfg.get("api_keys", {})
            if isinstance(api_keys, dict) and p_norm in api_keys:
                return api_keys[p_norm]
        if cfg.get("api_key"):
            return cfg["api_key"]
    except Exception:
        pass

    # 3. Environment variables
    if p_norm:
        p_upper = p_norm.upper()
        candidates = [
            f"{p_upper}_API_KEY",
            f"{p_upper}_ACCESS_TOKEN",
            f"{p_upper}_TOKEN",
            f"{p_upper}_KEY",
        ]
        for env_var in candidates:
            if val := os.environ.get(env_var):
                return val

    if val := os.environ.get("ROADSTYLE_API_KEY"):
        return val

    return None


def _detect_token_key(tp) -> str | None:
    """Find the keyword argument name used by an xyzservices.TileProvider for its access token."""
    if hasattr(tp, "keys"):
        for k in tp.keys():
            val = str(tp.get(k, ""))
            if val.startswith("<insert") or k in _TOKEN_KEYWORDS:
                return k
    return None


def _replace_token_placeholders(url: str, token: str) -> str:
    """Replace common token/key placeholders in a URL template."""
    for placeholder in ("{api_key}", "{accessToken}", "{apikey}", "{apiKey}", "{token}", "{key}", "{access_token}"):
        url = url.replace(placeholder, token)
    return url


def _inject_token(url: str, token: str) -> str:
    """Inject a token into a URL template, either by replacing placeholders or appending as query param."""
    if not url or not token:
        return url
    if any(p in url for p in ("{api_key}", "{accessToken}", "{apikey}", "{apiKey}", "{token}", "{key}", "{access_token}")):
        return _replace_token_placeholders(url, token)
    param_name = "key" if "cartocdn.com" in url else "api_key"
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{param_name}={token}"


@dataclass(frozen=True)
class Basemap:
    key: str
    label: str
    url: str                       # leaflet tile URL template ({s}{z}{x}{y}{r})
    attr: str
    is_dark: bool = False          # dark canvas?
    satellite: bool = False        # apply the saturate/brightness tile filter
    lonboard: str | None = None    # CartoBasemap name (lonboard backend)
    bg: str = "#444"               # thumbnail background (CSS)
    preview: tuple[str, str, str] = ("#888", "#bbb", "#888")  # 3 preview road colours
    subdomains: str = "abc"


# NOTE: every basemaps.cartocdn.com entry below (voyager, voyager_nolabels, positron,
# dark_matter) is now served WATERMARKED — a keyless tile comes back stamped "API KEY
# REQUIRED", unconditionally: the response is byte-identical with or without a browser
# Referer. They need a CARTO API key to render clean. The esri_* and osm entries are
# keyless and unstamped; esri_street / esri_dark_gray are the drop-in replacements.
BASEMAPS: dict[str, Basemap] = {
    "voyager": Basemap(
        "voyager", "Voyager",
        "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", _CARTO_ATTR,
        lonboard="Voyager", bg="linear-gradient(180deg,#e8eef0,#d8e0e5)",
        preview=("#ff9933", "#e8ecef", "#9ec5fe")),
    "voyager_nolabels": Basemap(
        # no basemap street names: the map's own labels (arrow-grey, class-aware) are the only
        # ones — otherwise CARTO's dark names show wherever ours don't place (and below z14)
        "voyager_nolabels", "Voyager (no labels)",
        "https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}{r}.png",
        _CARTO_ATTR, lonboard="Voyager", bg="linear-gradient(180deg,#e8eef0,#d8e0e5)",
        preview=("#ff9933", "#e8ecef", "#9ec5fe")),
    "positron": Basemap(
        "positron", "Positron",
        "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", _CARTO_ATTR,
        lonboard="Positron", bg="linear-gradient(180deg,#f3f5f7,#e3e8ed)",
        preview=("#888", "#bbb", "#888")),
    "dark_matter": Basemap(
        "dark_matter", "Dark Matter",
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", _CARTO_ATTR,
        is_dark=True, lonboard="DarkMatter", bg="radial-gradient(circle,#18222e,#0b1014)",
        preview=("#22d3a3", "#9ec5fe", "#5b6573")),
    "osm": Basemap(
        "osm", "OpenStreetMap",
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", _OSM_ATTR,
        bg="linear-gradient(180deg,#f2efe9,#e8e4db)", preview=("#e07020", "#dcdcdc", "#888")),
    "esri_gray": Basemap(
        "esri_gray", "Light Gray",
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        _ESRI_ATTR, bg="linear-gradient(180deg,#eceff1,#d8dde1)", preview=("#9aa", "#ccc", "#9aa")),
    "esri_street": Basemap(
        # the keyless stand-in for CARTO's voyager: coloured, labelled, street-level
        "esri_street", "Streets",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        _ESRI_ATTR, bg="linear-gradient(180deg,#f2efe9,#e8e4db)",
        preview=("#e8a33d", "#f4f1ea", "#a8c8e8")),
    "esri_dark_gray": Basemap(
        # the keyless stand-in for dark_matter
        "esri_dark_gray", "Dark Gray",
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        _ESRI_ATTR, is_dark=True, bg="linear-gradient(180deg,#3a3f45,#25292e)",
        preview=("#22d3a3", "#9ec5fe", "#5b6573")),
    "satellite": Basemap(
        "satellite", "Satellite",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        _ESRI_ATTR, is_dark=True, satellite=True,
        bg="linear-gradient(140deg,#2d3823,#4a3a2a,#2a2820)",
        preview=("#ffe8a0", "#ffd84d", "#fffdf2")),
    # tile-less base maps: url="" means no tile layer at all — just a plain canvas colour (bg).
    # Zero network requests, so a saved map with one of these is fully offline.
    "blank": Basemap(
        "blank", "Blank", "", "", bg="#efede8", preview=("#888", "#bbb", "#888")),
    "blank_dark": Basemap(
        "blank_dark", "Blank dark", "", "", is_dark=True, bg="#14181d",
        preview=("#22d3a3", "#9ec5fe", "#5b6573")),
}

# default set offered by the switcher when the caller doesn't specify one
DEFAULT_SWITCHER = ["voyager", "positron", "dark_matter", "osm", "satellite", "blank"]


def register_basemap(bm: Basemap) -> None:
    """Register (or replace) a base map, keyed by its ``key``."""
    if not isinstance(bm, Basemap):
        raise TypeError(f"expected a Basemap, got {type(bm).__name__}")
    BASEMAPS[bm.key] = bm


def _basemap_from_provider(tp, api_key: str | None = None) -> Basemap:
    """Convert an ``xyzservices.TileProvider`` (duck-typed) into a :class:`Basemap`.

    Lets any of the hundreds of xyzservices tile sources be used directly, e.g.
    ``render_edges(edges, basemap=xyzservices.providers.CartoDB.Positron)``.
    """
    name = getattr(tp, "name", None) or (
        tp.get("name", "custom") if hasattr(tp, "get") else "custom"
    )
    provider_root = str(name).split(".")[0].lower()
    resolved_key = api_key or get_api_key(provider_root)

    requires_tok = getattr(tp, "requires_token", lambda: False)()
    if requires_tok and not resolved_key:
        env_hint = f"{provider_root.upper()}_API_KEY"
        raise ValueError(
            f"Basemap provider {name!r} requires an API key or access token.\n"
            f"Provide one via:\n"
            f"  • Pass explicitly: roadstyle.render_edges(..., api_key='YOUR_KEY')\n"
            f"  • Set globally: roadstyle.set_api_key('YOUR_KEY', provider={provider_root!r})\n"
            f"  • Environment variable: export {env_hint}='YOUR_KEY' or export ROADSTYLE_API_KEY='YOUR_KEY'\n"
            f"  • Add to roadstyle.json config: {{\"config\": {{\"api_keys\": {{{provider_root!r}: 'YOUR_KEY'}}}}}}"
        )

    url = ""
    if hasattr(tp, "build_url"):
        t_key = _detect_token_key(tp)
        if resolved_key:
            kwargs = {t_key: resolved_key} if t_key else {"api_key": resolved_key, "accessToken": resolved_key}
            try:
                url = tp.build_url(**kwargs)
            except Exception:
                try:
                    url = tp.build_url()
                except Exception:
                    url = tp.get("url", "") if hasattr(tp, "get") else ""
        else:
            try:
                url = tp.build_url()
            except Exception:
                url = tp.get("url", "") if hasattr(tp, "get") else ""
    elif hasattr(tp, "get"):
        url = tp.get("url", "")

    if resolved_key and url:
        url = _inject_token(url, resolved_key)

    attr = ""
    if hasattr(tp, "get"):
        attr = tp.get("attribution", "") or tp.get("html_attribution", "") or ""
    is_dark = "dark" in str(name).lower()
    return Basemap(key=str(name), label=str(name).replace("_", " "), url=url, attr=attr,
                   is_dark=is_dark)


def _warn_unkeyed(url: str, resolved_key: str | None) -> None:
    """Say so when a CARTO base map is about to render watermarked.

    CARTO stamps a keyless tile "API KEY REQUIRED" and still answers 200, so nothing downstream
    can tell: the request succeeds, the image arrives, the map looks built. A page published that
    way is wrong in the one way nobody checks, and it stayed wrong for a day on a site whose
    nightly job reported success throughout.

    A warning and not an exception, deliberately. The map still draws, and a deployment that fails
    its whole night over a watermark is worse than one that says the watermark is there. It goes
    to stderr, which is where a nightly job's health is read from.
    """
    if resolved_key or "cartocdn.com" not in (url or ""):
        return
    import warnings
    warnings.warn(
        "CARTO base map requested with no API key: the tiles will come back stamped "
        "'API KEY REQUIRED'. Set one in roadstyle.json, or use a keyless base map "
        "(esri_street, esri_dark_gray, osm).",
        stacklevel=3,
    )


def get_basemap(key: str | Basemap, api_key: str | None = None) -> Basemap:
    """Resolve a base map from a registered key, a :class:`Basemap`, or an
    ``xyzservices.TileProvider`` (duck-typed via its ``build_url`` method)."""
    if isinstance(key, Basemap):
        resolved_key = api_key or get_api_key(key.key) or get_api_key("carto" if "cartocdn.com" in key.url else None)
        _warn_unkeyed(key.url, resolved_key)
        if resolved_key and key.url:
            new_url = _inject_token(key.url, resolved_key)
            if new_url != key.url:
                return Basemap(
                    key=key.key, label=key.label, url=new_url, attr=key.attr,
                    is_dark=key.is_dark, satellite=key.satellite, lonboard=key.lonboard,
                    bg=key.bg, preview=key.preview, subdomains=key.subdomains
                )
        return key
    if isinstance(key, str):
        if key in BASEMAPS:
            bm = BASEMAPS[key]
            provider = "carto" if "cartocdn.com" in bm.url else key
            resolved_key = api_key or get_api_key(provider) or get_api_key(key) or get_api_key()
            _warn_unkeyed(bm.url, resolved_key)
            if resolved_key and bm.url:
                new_url = _inject_token(bm.url, resolved_key)
                if new_url != bm.url:
                    return Basemap(
                        key=bm.key, label=bm.label, url=new_url, attr=bm.attr,
                        is_dark=bm.is_dark, satellite=bm.satellite, lonboard=bm.lonboard,
                        bg=bm.bg, preview=bm.preview, subdomains=bm.subdomains
                    )
            return bm
        if "{z}" in key and "{x}" in key and "{y}" in key:
            resolved_key = api_key or get_api_key()
            url = _inject_token(key, resolved_key) if resolved_key else key
            return Basemap(key="custom", label="Custom Basemap", url=url, attr="")
        raise ValueError(
            f"unknown basemap {key!r}; choose from {list(BASEMAPS)}"
        )
    if hasattr(key, "build_url"):         # xyzservices.TileProvider
        return _basemap_from_provider(key, api_key=api_key)
    raise TypeError(
        f"basemap must be a key, Basemap, or xyzservices.TileProvider, "
        f"got {type(key).__name__}"
    )
