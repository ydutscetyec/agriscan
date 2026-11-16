"""A farmer must not reach another farmer's rows, by any route."""

from __future__ import annotations

from tests.conftest import auth_headers, login


def test_farmer_list_fields_shows_only_own(client, users):
    token = login(client, "t_farmer_a")
    body = client.get("/fields", headers=auth_headers(token)).get_json()
    names = {f["name"] for f in body}
    assert "field_farm_a" in names
    assert "field_farm_b" not in names


def test_farmer_cannot_read_other_farmers_field_by_id(client, users):
    token = login(client, "t_farmer_a")
    other = users["field_farm_b"].id
    resp = client.get(f"/fields/{other}", headers=auth_headers(token))
    assert resp.status_code == 403


def test_farmer_can_read_own_field_by_id(client, users):
    token = login(client, "t_farmer_a")
    own = users["field_farm_a"].id
    assert client.get(f"/fields/{own}", headers=auth_headers(token)).status_code == 200


def test_technician_sees_all_fields(client, users):
    token = login(client, "t_tech")
    body = client.get("/fields", headers=auth_headers(token)).get_json()
    names = {f["name"] for f in body}
    assert {"field_farm_a", "field_farm_b"} <= names


def test_farmer_cannot_create_field(client, users):
    token = login(client, "t_farmer_a")
    resp = client.post(
        "/fields",
        headers=auth_headers(token),
        json={"name": "sneaky", "farm_id": users["farm_b"].id},
    )
    assert resp.status_code == 403


def test_farmer_farms_list_is_filtered(client, users):
    token = login(client, "t_farmer_b")
    body = client.get("/farms", headers=auth_headers(token)).get_json()
    assert {f["name"] for f in body} == {"farm_b"}
