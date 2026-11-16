"""p41: the flight video goes up in pieces.

A whole-file upload through a Cloudflare tunnel fails with 502 once the body passes
100 MB, and a ten-minute clip is several hundred. Pieces also mean a dropped connection
costs one piece rather than the entire upload after a flight.
"""

from __future__ import annotations

import io

from tests.conftest import auth_headers, login


def _session(client, token, users):
    device_id = client.post("/capture/devices", headers=auth_headers(token),
                            json={"name": "Chunk phone"}).get_json()["id"]
    session_id = client.post(
        "/capture/sessions",
        headers=auth_headers(token),
        json={"device_id": device_id, "field_id": users["field_farm_a"].id,
              "interval_s": 2, "max_duration_s": 300},
    ).get_json()["id"]
    return session_id


def _chunk(client, token, session_id, index, offset, data):
    return client.post(
        f"/capture/sessions/{session_id}/video/chunk",
        headers=auth_headers(token),
        data={"chunk": (io.BytesIO(data), "part"), "index": str(index),
              "offset": str(offset)},
        content_type="multipart/form-data",
    )


def _complete(client, token, session_id, mime="video/webm", duration=12.5):
    return client.post(f"/capture/sessions/{session_id}/video/complete",
                       headers=auth_headers(token),
                       json={"mime": mime, "duration_s": duration})


PIECES = [b"\x1a\x45\xdf\xa3first-", b"second-", b"third-piece"]
WHOLE = b"".join(PIECES)


def test_pieces_are_reassembled_in_order(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    offset = 0
    for index, piece in enumerate(PIECES):
        resp = _chunk(client, token, session_id, index, offset, piece)
        assert resp.status_code == 200, resp.get_json()
        offset += len(piece)
    assert _complete(client, token, session_id).status_code == 201

    got = client.get(f"/capture/sessions/{session_id}/video", headers=auth_headers(token))
    assert got.status_code == 200
    assert got.data == WHOLE


def test_a_piece_out_of_step_is_refused_rather_than_corrupting_the_file(client, users):
    """Appending a piece the server did not expect produces a file that plays as
    garbage, which is worse than a failed upload."""
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    _chunk(client, token, session_id, 0, 0, PIECES[0])
    # Claims to continue from a point the server has not reached.
    resp = _chunk(client, token, session_id, 1, 9999, PIECES[1])
    assert resp.status_code == 409
    assert "Start the upload again" in resp.get_json()["error"]


def test_restarting_at_index_zero_discards_the_failed_attempt(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    _chunk(client, token, session_id, 0, 0, b"abandoned-attempt")
    offset = 0
    for index, piece in enumerate(PIECES):
        _chunk(client, token, session_id, index, offset, piece)
        offset += len(piece)
    _complete(client, token, session_id)
    got = client.get(f"/capture/sessions/{session_id}/video", headers=auth_headers(token))
    assert got.data == WHOLE


def test_completing_with_nothing_uploaded_is_refused(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    assert _complete(client, token, session_id).status_code == 400


def test_an_unsupported_container_is_refused_at_completion(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    _chunk(client, token, session_id, 0, 0, PIECES[0])
    assert _complete(client, token, session_id, mime="video/avi").status_code == 415


def test_a_second_video_cannot_overwrite_the_first(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    _chunk(client, token, session_id, 0, 0, WHOLE)
    _complete(client, token, session_id)
    assert _chunk(client, token, session_id, 0, 0, b"newer").status_code == 409


def test_the_session_reports_the_video_after_completion(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    _chunk(client, token, session_id, 0, 0, WHOLE)
    _complete(client, token, session_id, duration=42.0)
    row = next(s for s in client.get("/capture/sessions",
                                     headers=auth_headers(token)).get_json()
               if s["id"] == session_id)
    assert row["has_video"] is True
    assert row["video_bytes"] == len(WHOLE)
    assert row["video_duration_s"] == 42.0


def test_farmers_cannot_upload_pieces(client, users):
    operator = login(client, "t_tech")
    session_id = _session(client, operator, users)
    farmer = login(client, "t_farmer_a")
    assert _chunk(client, farmer, session_id, 0, 0, PIECES[0]).status_code == 403
