"""The bridge profile of the 3D bridges (docs/guides/bridge-profile.md, docs/reference/formats.md).

The engine makes the 3D decks in two parts. The filler reads an input profile that can be incomplete (every value is optional), keeps what you give and fills the rest with the rules. The maker
makes the decks from the complete profile. ``bridge_profile(edges, given)`` gives the complete profile, and ``render_edges(..., bridge_profile=given)`` makes a page from an input (a dictionary or the
path of a JSON file).
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


def bridge_profile(edges, given=None, **kwargs) -> dict:
    """The complete bridge profile of the 3D bridges of ``edges``, as a dictionary.

    The engine finds the groups, the chains and the nodes of the bridges, keeps every value of ``given`` (an input profile that can be incomplete: a dictionary or the path of a JSON file,
    ``None`` or ``{}`` for none) and fills every value that is missing with the rules. A node of ``given`` is named by its position (``lonlat``, within 5 m) or by its ``id``. Give a height
    and read the whole profile::

        profile = rs.bridge_profile(edges, {"groups": [{"nodes": [{"lonlat": [18.0003, 59.3002], "z_m": 9.0}]}]})
        rs.render_dashboard(edges, view_3d=True, bridge_profile=profile)

    A node has a height ``z_m``; a chain has a full height ``top_m`` and optionally a width ``width_m``. The first build has one curve, ``smooth``, and no interior control
    points (``points`` is empty). ``kwargs`` are the keywords of ``render_edges``; ``bridge_profile=`` in them is the same as ``given``.
    """
    from ._engine import export_inline

    kwargs.pop("view_3d", None)
    kwargs.pop("bridge_profile_export", None)
    if given is not None:
        if kwargs.get("bridge_profile") is not None:
            raise TypeError("give the input profile once: as given or as bridge_profile=, not both")
        kwargs["bridge_profile"] = given
    if kwargs.get("bridge_profile") is not None:
        kwargs["bridge_profile"] = read_bridge_profile(kwargs["bridge_profile"])
    return export_inline(edges, view_3d=True, bridge_profile_export=True, **kwargs)["metadata"]["roadstyle:bridge_profile"]
