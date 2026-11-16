"""p7: removing a saved field boundary must actually remove it."""

from __future__ import annotations

from tests.conftest import auth_headers, login

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[124.745, 6.370], [124.747, 6.370], [124.747, 6.372],
                     [124.745, 6.372], [124.745, 6.370]]],
}


def _field(client, users, token, name):
    return client.post(
        "/fields", headers=auth_headers(token),
        json={"name": name, "farm_id": users["farm_a"].id,
              "boundary_geojson": SQUARE, "area_ha": 4.9},
    ).get_json()


def test_clearing_a_boundary_persists(client, users):
    admin = login(client, "t_admin")
    created = _field(client, users, admin, "p7 boundary field")
    assert created["boundary_geojson"] is not None

    resp = client.put(
        f"/fields/{created['id']}", headers=auth_headers(admin),
        json={"boundary_geojson": None, "area_ha": None},
    )
    assert resp.status_code == 200

    reread = client.get(f"/fields/{created['id']}", headers=auth_headers(admin)).get_json()
    assert reread["boundary_geojson"] is None
    assert reread["area_ha"] is None


def test_summary_reports_no_boundary_after_clearing(client, users):
    admin = login(client, "t_admin")
    created = _field(client, users, admin, "p7 summary field")
    client.put(f"/fields/{created['id']}", headers=auth_headers(admin),
               json={"boundary_geojson": None, "area_ha": None})

    rows = client.get("/fields-summary", headers=auth_headers(admin)).get_json()
    row = next(r for r in rows if r["id"] == created["id"])
    assert row["has_boundary"] is False


def test_redrawing_after_clearing_works(client, users):
    admin = login(client, "t_admin")
    created = _field(client, users, admin, "p7 redraw field")
    client.put(f"/fields/{created['id']}", headers=auth_headers(admin),
               json={"boundary_geojson": None, "area_ha": None})
    client.put(f"/fields/{created['id']}", headers=auth_headers(admin),
               json={"boundary_geojson": SQUARE, "area_ha": 4.9})
    reread = client.get(f"/fields/{created['id']}", headers=auth_headers(admin)).get_json()
    assert reread["boundary_geojson"]["type"] == "Polygon"


def test_farmer_summary_is_scoped(client, users):
    farmer = login(client, "t_farmer_b")
    rows = client.get("/fields-summary", headers=auth_headers(farmer)).get_json()
    assert all(r["farm_id"] == users["farm_b"].id for r in rows)
