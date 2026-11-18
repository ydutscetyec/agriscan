"""p43: the Content Security Policy must permit every tile host the map uses, and
tile URLs must be declared in exactly one place.

Two separate faults, found a day apart, with the same shape — the map renders
blank or full of error tiles and nothing in the interface says why.

1. The base map moved to Esri World Imagery and OpenStreetMap Germany, but
   img-src in app/site.py still allowed only https://*.tile.openstreetmap.org.
   The browser blocked every tile from both layers. The only evidence was a
   console line per tile:

       Loading the image 'https://server.arcgisonline.com/...' violates the
       following Content Security Policy directive: "img-src 'self' data: blob:
       https://*.tile.openstreetmap.org". The action has been blocked.

2. FieldBoundaries.jsx had kept its own hardcoded OpenStreetMap TileLayer while
   the other map pages moved to BaseTiles. CSP allowed it, so the tiles loaded —
   and every one of them was OSM's "Access blocked: app is not following the
   tile usage policy" 403 image, tiled across the map.

The first version of this test only read BaseMap.jsx, so it passed cleanly while
fault 2 was live. It now scans the whole frontend, and additionally requires that
tile URLs appear only in BaseMap.jsx, because a page that declares its own is a
page that will be forgotten the next time the provider changes.
"""

from __future__ import annotations

import pathlib
import re
import urllib.parse

import pytest

from app.site import build_csp

WEB_SRC = pathlib.Path(__file__).resolve().parents[2] / "web" / "src"
CANONICAL = "BaseMap.jsx"

# A Leaflet tile template: a URL carrying the {z}/{x}/{y} placeholders. Precise
# enough not to match API calls, documentation links or attribution hrefs.
TILE_URL = re.compile(r"""['"](https?://[^'"]*\{z\}[^'"]*)['"]""")


def tile_url_sites() -> list[tuple[pathlib.Path, str]]:
    """(file, url) for every tile template literal in the frontend."""
    found = []
    for path in sorted(WEB_SRC.rglob("*.js")) + sorted(WEB_SRC.rglob("*.jsx")):
        for url in TILE_URL.findall(path.read_text(encoding="utf-8")):
            found.append((path, url))
    return found


def host_of(url: str) -> str:
    # Leaflet's {s} subdomain placeholder is not valid in a hostname; the CSP
    # sees the expanded form, so compare against the wildcard-friendly remainder.
    return urllib.parse.urlsplit(url.replace("{s}.", "")).hostname or ""


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
        if source_host.startswith("*.") and host.endswith(source_host[1:]):
            return True
    return False


def test_the_frontend_is_where_we_think_it_is():
    """Guards the test itself: a moved tree must not silently pass."""
    assert WEB_SRC.is_dir(), f"{WEB_SRC} not found; update this test"
    assert tile_url_sites(), "no tile URLs found anywhere in the frontend"


@pytest.mark.parametrize("host", sorted({host_of(u) for _, u in tile_url_sites()}))
def test_csp_permits_every_tile_host(host):
    sources = img_src_sources(build_csp())
    assert permits(sources, host), (
        f"the map loads tiles from {host}, which img-src does not allow "
        f"({' '.join(sources)}). Every tile will be blocked and the map will render "
        f"blank. Add the origin to DEFAULT_TILE_ORIGINS in app/site.py, or set "
        f"AGRISCAN_TILE_ORIGINS."
    )


def test_tile_urls_are_declared_only_in_basemap():
    """One source of truth. A page with its own TileLayer gets left behind when
    the provider changes, which is precisely how FieldBoundaries.jsx ended up
    still pointed at servers that had started refusing us."""
    strays = sorted(
        f"{path.relative_to(WEB_SRC)} -> {url}"
        for path, url in tile_url_sites()
        if path.name != CANONICAL
    )
    assert not strays, (
        "tile URLs outside components/" + CANONICAL + ":\n  "
        + "\n  ".join(strays)
        + "\nUse <BaseTiles layer={baseMap} /> instead, so every map page follows "
          "the provider defined in one place."
    )


def test_extra_origins_can_be_added_without_a_code_change(monkeypatch):
    monkeypatch.setenv("AGRISCAN_TILE_ORIGINS", "https://tiles.example.test")
    assert permits(img_src_sources(build_csp()), "tiles.example.test")


def test_the_policy_is_still_restrictive():
    """Allowing the tile hosts must not have opened img-src to everything."""
    sources = img_src_sources(build_csp())
    assert "*" not in sources and "https:" not in sources
    assert not permits(sources, "evil.example.test")
