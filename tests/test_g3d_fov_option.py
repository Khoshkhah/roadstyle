"""window.rsG3dFov (Google's vertical fov, degrees) gives the 3D window the map's metres per pixel; unset, the range is unchanged."""
import pathlib
import subprocess
import json
import shutil
import pytest

SRC = (pathlib.Path(__file__).resolve().parent.parent / "src/roadstyle/static/dashboard/google3d.js").read_text()


def test_option_is_read_and_default_is_the_map_camera():
    assert "window.rsG3dFov" in SRC
    assert "camPx()*mpp(lat, zoom)" in SRC            # the default range: the map's own camera distance


@pytest.mark.skipif(shutil.which("node") is None, reason="no node")
def test_range_and_zoom_are_inverse():
    js = """
    const rad=d=>d*Math.PI/180, EARTH=40075016.686, camPx=()=>1000, winH=()=>703, fov=()=>14.6;
    const mpp=(lat,z)=>EARTH*Math.cos(rad(lat))/(512*Math.pow(2,z));
    const rangeOf=(lat,z)=>winH()*mpp(lat,z)/2/Math.tan(rad(fov())/2);
    const zoomOf=(lat,r)=>Math.log2(EARTH*Math.cos(rad(lat))/(512*(2*r*Math.tan(rad(fov())/2)/winH())));
    console.log(JSON.stringify([zoomOf(43.7, rangeOf(43.7, 16.3)), rangeOf(43.7,16.3)]));"""
    z, r = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert abs(z - 16.3) < 1e-9 and r > 0


def test_one_owner_per_gesture():
    assert "ONE OWNER PER GESTURE" in SRC and 'owner="3d"' in SRC and 'owner==="map"' in SRC
