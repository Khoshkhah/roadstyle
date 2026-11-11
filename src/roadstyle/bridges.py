"""The bridge profile of the 3D bridges (docs/guides/bridge-profile.md, docs/reference/formats.md).

The engine makes the 3D decks in two parts. Today's rule writes a complete profile: the groups of bridges with their nodes (a height for each) and their chains. The maker makes the decks from a
profile. ``bridge_profile(edges)`` gives the profile that a page uses, and ``render_edges(..., bridge_profile=profile)`` makes the page from a profile (a dictionary or the path of a JSON file).
"""
import json
from pathlib import Path

__all__ = ["bridge_profile", "read_bridge_profile"]


def read_bridge_profile(profile):
    """A complete bridge profile as a dictionary: ``profile`` is a dictionary, or the path of a JSON file."""
    if isinstance(profile, dict):
        return profile
    if isinstance(profile, (str, Path)):
        return json.loads(Path(profile).read_text())
    raise TypeError(f"bridge_profile= is a dictionary or the path of a JSON file, not {type(profile).__name__}")


def bridge_profile(edges, **kwargs) -> dict:
    """The complete bridge profile of the 3D bridges of ``edges``, as a dictionary.

    It is the profile that today's rule gives, or the profile that the page is given (``bridge_profile=`` in ``kwargs``). Change a number and give it back::

        profile = rs.bridge_profile(edges)
        profile["groups"][0]["nodes"][2]["z_m"] = 9.0
        rs.render_dashboard(edges, view_3d=True, bridge_profile=profile)

    A node has a height ``z_m``; a chain has a full height ``top_m`` and optionally a width ``width_m``. The first build of the maker has one curve, ``smooth``, and no interior control
    points (``points`` is empty). ``kwargs`` are the keywords of ``render_edges``.
    """
    from ._engine import export_inline

    kwargs.pop("view_3d", None)
    kwargs.pop("bridge_profile_export", None)
    if kwargs.get("bridge_profile") is not None:
        kwargs["bridge_profile"] = read_bridge_profile(kwargs["bridge_profile"])
    return export_inline(edges, view_3d=True, bridge_profile_export=True, **kwargs)["metadata"]["roadstyle:bridge_profile"]
