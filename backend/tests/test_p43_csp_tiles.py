"""p43: the Content Security Policy must permit the tile hosts the map actually uses.

The base map moved from OpenStreetMap's tile servers to Esri World Imagery and
OpenStreetMap Germany. The CSP in app/site.py still allowed only
https://*.tile.openstreetmap.org, so the browser blocked every tile from both
layers. The map rendered blank — controls, markers and field polygons drawn over
an empty background — with nothing in the interface to say why. The only evidence
was a console line:

    Loading the image 'https://server.arcgisonline.com/...' violates the following
    Content Security Policy directive: "img-src 'self' data: blob:
    https://*.tile.openstreetmap.org". The action has been blocked.

Two files in two languages had to agree and nothing checked that they did. This
reads the tile URLs straight out of the frontend and fails if any of them is not
permitted by the policy the backend serves.
"""

from __future__ import annotations

import pathlib
import re
import urllib.parse

import pytest

from app.site import build_csp

BASEMAP_JS = (
    pathlib.Path(__file__).resolve().parents[2] / "web" / "src" / "components" / "BaseMap.jsx"
)

# url: 'https://host/path/{z}/{y}/{x}'
URL_IN_LAYERS = re.compile(r"url:\s*['\"](https?://[^'\"]+)['\"]")


def tile_hosts() -> list[str]:
    source = BASEMAP_JS.read_text(encoding="utf-8")
    hosts = []
    for url in URL_IN_LAYERS.findall(source):
        host = urllib.parse.urlsplit(url).hostname
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def img_src_sources(csp: str) -> list[str]:
    for directive in csp.split(";"):
        parts = directive.split()
        if parts and parts[0] == "img-src":
            return parts[1:]
    raise AssertionError(f"no img-src directive in CSP: {csp!r}")


def permits(sources: list[str], host: str) -> bool:
    """CSP host matching, limited to the forms this policy uses: an exact origin,
    or one leading-wildcard label such as https://*.tile.openstreetmap.org."""
    for source in sources:
        if "://" not in source:
            continue  # 'self', data:, blob:
        source_host = source.split("://", 1)[1].rstrip("/")
        if source_host == host:
            return True
        if source_host.startswith("*."):
            suffix = source_host[1:]  # ".tile.openstreetmap.org"
            if host.endswith(suffix):
                return True
    return False


def test_basemap_source_is_where_we_think_it_is():
    """Guards the test itself: a moved or renamed file must not silently pass."""
    assert BASEMAP_JS.is_file(), f"{BASEMAP_JS} not found; update this test"
    assert tile_hosts(), f"no tile URLs parsed out of {BASEMAP_JS.name}"


@pytest.mark.parametrize("host", tile_hosts())
def test_csp_permits_every_tile_host(host):
    sources = img_src_sources(build_csp())
    assert permits(sources, host), (
        f"the map loads tiles from {host}, which img-src does not allow "
        f"({' '.join(sources)}). Every tile will be blocked and the map will render "
        f"blank. Add the origin to DEFAULT_TILE_ORIGINS in app/site.py, or set "
        f"AGRISCAN_TILE_ORIGINS."
    )


def test_extra_origins_can_be_added_without_a_code_change(monkeypatch):
    monkeypatch.setenv("AGRISCAN_TILE_ORIGINS", "https://tiles.example.test")
    assert permits(img_src_sources(build_csp()), "tiles.example.test")


def test_the_policy_is_still_restrictive():
    """Allowing the tile hosts must not have opened img-src to everything."""
    sources = img_src_sources(build_csp())
    assert "*" not in sources and "https:" not in sources
    assert not permits(sources, "evil.example.test")
