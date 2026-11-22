"""Remote capture: the drone-mounted phone, and the technician who arms it.

Protocol, in order:
  1. Phone opens /capture, signs in as a technician, registers itself    POST /capture/devices
  2. Phone polls every few seconds; each poll is also a heartbeat        POST /capture/devices/<id>/poll
  3. Technician arms a session for that device from the dashboard       POST /capture/sessions
  4. Phone's next poll receives the session and starts capturing        (poll response)
  5. Phone reports progress on later polls while it still has signal    (poll body)
  6. Session ends by: technician stop, shot limit, or duration limit    POST /capture/sessions/<id>/stop

The duration limit is enforced on BOTH sides. The phone stops itself when time runs out
even if it never hears the stop command, because at 20-30 m over a paddy the Wi-Fi link
is exactly the thing most likely to fail.

This controls the camera only. Nothing here commands the aircraft.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import json

from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy import func, select, text

from app.utils.clock import utc_now
from app.auth.decorators import requires_role
from app.extensions import SessionLocal
from app.models import (
    CaptureDevice, CaptureSession, Detection, Field, Image, Mission,
)
from app.services import audit, storage, video_frames
from app.utils.errors import ApiError

bp = Blueprint("capture", __name__, url_prefix="/capture")
fields_summary_bp = Blueprint("fields_summary", __name__, url_prefix="/fields-summary")

ONLINE_WINDOW_S = 15            # a device not heard from in this long is offline
# Arming is refused past this. A phone polls every few seconds, so a minute of silence
# means it is not listening — and a session armed at a phone that is not listening sits
# there until it expires, which is a wasted flight discovered after landing.
ARMABLE_SILENCE_S = 60
# A phone taking full-resolution stills rarely sustains better than one every 1-2 s;
# below that the camera, not this limit, becomes the constraint and frames are simply
# skipped. Allowed down to 0.3 s anyway, because for a short burst over one spot a
# phone can manage it, and refusing a number the operator asked for teaches nothing.
MIN_INTERVAL_S = 0.3
MAX_INTERVAL_S = 60.0
MAX_DURATION_S = 20 * 60        # hard ceiling: no session may run longer than 20 min
OPERATOR_ROLES = ("admin", "technician", "researcher")


# --- viewfinder ------------------------------------------------------------------
#
# A near-live view of what the drone phone is pointing at, so an operator can check
# framing and focus before takeoff and keep an eye on coverage during a flight.
#
# Deliberately not video. A WebRTC stream needs a signalling server and almost certainly
# a TURN relay, because both ends sit behind carrier NAT, and it loses whatever it drops.
# This pushes one small JPEG every couple of seconds: roughly 10 kB/s, survives a bad
# link, and reuses the polling the phone already does.
#
# Frames are throwaway. They never become Image rows, are never analysed, and the file
# is overwritten each time — only the newest one exists. The phone is told to send them
# only while an operator is actually looking, so a flight nobody is watching costs
# nothing. In memory rather than in a column, because a viewfinder is live state and has
# no business outliving the process that served it.
PREVIEW_MAX_BYTES = 400 * 1024
PREVIEW_WANTED_FOR = dt.timedelta(seconds=12)


def _preview_path(cfg, device_id: int) -> pathlib.Path:
    return cfg.image_root_path / "_preview" / f"device-{device_id}.jpg"


def _preview_wanted(device: CaptureDevice) -> bool:
    seen = device.preview_requested_at
    return bool(seen and _now() - seen < PREVIEW_WANTED_FOR)


def _now() -> dt.datetime:
    return utc_now()


def _device_payload(device: CaptureDevice, active_session: CaptureSession | None) -> dict:
    seen = device.last_seen_at
    online = bool(seen and (_now() - seen).total_seconds() <= ONLINE_WINDOW_S)
    return {
        "id": device.id,
        "name": device.name,
        "online": online,
        "last_seen_at": seen.isoformat() if seen else None,
        "reported_state": device.reported_state,
        "reported_session_id": device.reported_session_id,
        # The case worth naming: polling happily, says it is idle, and a session is
        # sitting armed for it. That is the phone ignoring the command, not a dead link.
        # Flagged only once the phone has polled since the session was armed and is
        # still not on it. Before that first poll it is simply behind, not ignoring,
        # and saying so would cry wolf on every single session.
        "ignoring_command": bool(
            online
            and active_session is not None
            and device.reported_session_id != active_session.id
            and seen is not None
            and active_session.created_at is not None
            # >= because DATETIME has no sub-second precision: a poll and an arm in the
            # same second are indistinguishable, and treating that as "has not polled
            # yet" hid the flag entirely in exactly the case worth catching.
            and seen >= active_session.created_at
        ),
        "seconds_since_seen": int((_now() - seen).total_seconds()) if seen else None,
        "battery_pct": device.battery_pct,
        "charging": device.charging,
        "gps_accuracy_m": float(device.gps_accuracy_m) if device.gps_accuracy_m is not None else None,
        "camera_ready": device.camera_ready,
        "capabilities": device.capabilities or {},
        "active_session": _session_payload(active_session) if active_session else None,
    }


def _session_payload(session_row: CaptureSession) -> dict:
    return {
        "id": session_row.id,
        "device_id": session_row.device_id,
        "field_id": session_row.field_id,
        "mission_id": session_row.mission_id,
        "interval_s": float(session_row.interval_s),
        "max_duration_s": session_row.max_duration_s,
        "max_shots": session_row.max_shots,
        "status": session_row.status,
        "has_video": bool(session_row.video_path),
        "video_bytes": int(session_row.video_bytes) if session_row.video_bytes else None,
        "video_duration_s": (float(session_row.video_duration_s)
                             if session_row.video_duration_s is not None else None),
        "track_points": session_row.track_points,
        "last_report_at": (session_row.last_report_at.isoformat()
                           if session_row.last_report_at else None),
        "phone_ever_reported": session_row.last_report_at is not None,
        "created_at": session_row.created_at.isoformat() if session_row.created_at else None,
        "started_at": session_row.started_at.isoformat() if session_row.started_at else None,
        "ended_at": session_row.ended_at.isoformat() if session_row.ended_at else None,
        "end_reason": session_row.end_reason,
        "shots_reported": session_row.shots_reported,
    }


def _active_session(session, device_id: int) -> CaptureSession | None:
    row = session.execute(
        select(CaptureSession)
        .where(CaptureSession.device_id == device_id)
        .where(CaptureSession.status.in_(("armed", "running")))
        .order_by(CaptureSession.id.desc())
    ).scalars().first()
    if row is None:
        return None
    # Server-side expiry mirrors the phone's own timer.
    reference = row.started_at or row.created_at
    if reference and (_now() - reference).total_seconds() > row.max_duration_s + 30:
        row.status = "expired"
        row.ended_at = _now()
        row.end_reason = "Duration limit reached without a completion report."
        session.commit()
        return None
    return row


# --------------------------------------------------------------------------- devices


@bp.post("/devices")
@requires_role(*OPERATOR_ROLES)
def register_device():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        raise ApiError("Give this phone a name, e.g. 'Drone phone 1'.", 400)
    session = SessionLocal()
    device = CaptureDevice(
        name=name[:120],
        registered_by=g.current_user.id,
        user_agent=(request.headers.get("User-Agent") or "")[:255],
        capabilities=data.get("capabilities") or {},
        last_seen_at=_now(),
    )
    session.add(device)
    session.commit()
    audit.record(g.current_user.id, "register_capture_device", "capture_device", device.id)
    return jsonify(_device_payload(device, None)), 201


@bp.get("/devices")
@requires_role(*OPERATOR_ROLES)
def list_devices():
    session = SessionLocal()
    rows = session.execute(
        select(CaptureDevice).where(CaptureDevice.active.is_(True)).order_by(CaptureDevice.id)
    ).scalars().all()
    return jsonify([_device_payload(d, _active_session(session, d.id)) for d in rows])


@bp.delete("/devices/<int:device_id>")
@requires_role("admin")
def delete_device(device_id: int):
    """Remove a pairing.

    Re-pairing a phone makes a new device row and leaves the old one behind, looking
    exactly as real as the live one in the arm dropdown. Being able to clear them out is
    what stops the next person arming a ghost.

    Sessions are kept and keep their device id; deleting the pairing does not rewrite
    the history of what was flown.
    """
    session = SessionLocal()
    device = session.get(CaptureDevice, device_id)
    if device is None:
        raise ApiError("That device is not registered.", 404)
    active = _active_session(session, device.id)
    if active is not None:
        raise ApiError(
            f"Session {active.id} is still {active.status} on '{device.name}'. "
            "Stop it first, then remove the pairing.",
            409,
        )

    # Soft: the row stays so old sessions still resolve a name, it just leaves the list.
    device.active = False
    session.commit()
    audit.record(g.current_user.id, "delete_capture_device", "capture_device", device_id,
                 {"name": device.name})
    return jsonify({"deleted": device_id})


@bp.post("/devices/<int:device_id>/poll")
@requires_role(*OPERATOR_ROLES)
def poll(device_id: int):
    """Heartbeat in, instructions out. Called by the phone every few seconds."""
    session = SessionLocal()
    device = session.get(CaptureDevice, device_id)
    if device is None or not device.active:
        raise ApiError("This device is not registered. Register it again.", 404)

    data = request.get_json(silent=True) or {}
    device.last_seen_at = _now()
    if "battery_pct" in data and data["battery_pct"] is not None:
        device.battery_pct = max(0, min(100, int(data["battery_pct"])))
    if "charging" in data:
        device.charging = data["charging"]
    if "gps_accuracy_m" in data:
        device.gps_accuracy_m = data["gps_accuracy_m"]
    if "camera_ready" in data:
        device.camera_ready = bool(data["camera_ready"])
    # What the phone believes it is doing, whatever the server thinks it ordered.
    if "local_session_id" in data:
        raw = data.get("local_session_id")
        device.reported_session_id = int(raw) if raw else None
        device.reported_state = "capturing" if raw else "idle"

    active = _active_session(session, device.id)

    # The phone reports what it is actually doing; the server records it.
    report = data.get("session_report") or {}
    if active and report.get("session_id") == active.id:
        # Proof the phone picked this session up at all. "Expired with 0 frames and no
        # report" means the phone never saw it; "expired with 0 frames but reports" means
        # it ran and the camera produced nothing. Those need different fixes.
        active.last_report_at = _now()
        if report.get("state") == "running" and active.status == "armed":
            active.status = "running"
            active.started_at = _now()
        if isinstance(report.get("shots"), int):
            active.shots_reported = max(active.shots_reported, report["shots"])
        if report.get("state") in ("completed", "failed"):
            active.status = report["state"]
            active.ended_at = _now()
            active.end_reason = (report.get("reason") or report["state"])[:160]
            active = None

    session.commit()
    return jsonify(
        {
            "device": _device_payload(device, active),
            "command": (
                {"action": "capture", "session": _session_payload(active)}
                if active
                else {"action": "idle"}
            ),
            "server_time": _now().isoformat(),
            # Only while someone has the Drone camera page open on this device.
            "preview_wanted": _preview_wanted(device),
        }
    )


@bp.post("/devices/<int:device_id>/preview")
@requires_role(*OPERATOR_ROLES)
def put_preview(device_id: int):
    """The phone pushes its latest viewfinder frame here."""
    session = SessionLocal()
    device = session.get(CaptureDevice, device_id)
    if device is None or not device.active:
        raise ApiError("This device is not registered. Register it again.", 404)

    frame = request.files.get("frame")
    if frame is None:
        raise ApiError("No frame supplied.", 400)
    data = frame.read(PREVIEW_MAX_BYTES + 1)
    if not data:
        raise ApiError("Empty frame.", 400)
    if len(data) > PREVIEW_MAX_BYTES:
        raise ApiError("Preview frame is too large.", 413)

    cfg = current_app.config["AGRISCAN"]
    path = _preview_path(cfg, device_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written to a temporary name first, so a reader never catches a half-written frame.
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)

    device.last_seen_at = _now()
    session.commit()
    return jsonify({"ok": True, "bytes": len(data)})


@bp.get("/devices/<int:device_id>/preview")
@requires_role(*OPERATOR_ROLES)
def get_preview(device_id: int):
    """The newest frame, and a note that an operator is watching."""
    session = SessionLocal()
    device = session.get(CaptureDevice, device_id)
    if device is None:
        raise ApiError("This device is not registered.", 404)
    device.preview_requested_at = _now()
    session.commit()

    cfg = current_app.config["AGRISCAN"]
    path = _preview_path(cfg, device_id)
    if not path.is_file():
        # Not an error: the phone has simply not sent one yet. The page shows why.
        raise ApiError("No preview frame yet.", 404)
    response = send_file(path, mimetype="image/jpeg")
    # A viewfinder must never be cached; the whole point is that it is the newest frame.
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Age-Seconds"] = str(
        max(0, int((_now().timestamp() - path.stat().st_mtime)))
    )
    return response


# -------------------------------------------------------------------------- sessions


@bp.post("/sessions")
@requires_role("admin", "technician")
def arm_session():
    data = request.get_json(silent=True) or {}
    session = SessionLocal()

    device = session.get(CaptureDevice, int(data.get("device_id") or 0))
    if device is None or not device.active:
        raise ApiError("Choose a registered device.", 400)
    field = session.get(Field, int(data.get("field_id") or 0))
    if field is None:
        raise ApiError("Choose a field.", 400)

    try:
        interval = float(data.get("interval_s", 2.0))
        duration = int(data.get("max_duration_s", 600))
    except (TypeError, ValueError):
        raise ApiError("Interval and duration must be numbers.", 400) from None
    if not MIN_INTERVAL_S <= interval <= MAX_INTERVAL_S:
        raise ApiError(
            f"Interval must be between {MIN_INTERVAL_S:g} and {MAX_INTERVAL_S:g} seconds.", 400
        )
    if not 10 <= duration <= MAX_DURATION_S:
        raise ApiError(
            f"Duration must be between 10 seconds and {MAX_DURATION_S // 60} minutes.", 400
        )

    max_shots = data.get("max_shots")
    if max_shots is not None:
        max_shots = int(max_shots)
        if max_shots < 1:
            raise ApiError("Shot limit must be at least 1.", 400)

    mission_id = data.get("mission_id")
    if mission_id:
        mission = session.get(Mission, int(mission_id))
        if mission is None or mission.field_id != field.id:
            raise ApiError("That flight record belongs to a different field.", 400)

    if _active_session(session, device.id) is not None:
        raise ApiError("This device already has an armed or running session. Stop it first.", 409)

    # The fault this prevents: pairing a phone more than once leaves several device rows
    # for one physical phone, and the phone only ever polls as the most recent. Arming an
    # older row looks completely normal — the session appears, the dashboard is happy —
    # and nothing happens, because nobody is listening on that row.
    silence = None if device.last_seen_at is None else (_now() - device.last_seen_at).total_seconds()
    if silence is None or silence > ARMABLE_SILENCE_S:
        how_long = "has never connected" if silence is None else f"was last seen {int(silence // 60)} min ago"
        raise ApiError(
            f"'{device.name}' {how_long}, so it would not pick this session up. "
            "Open /camera on the phone, then arm the device that shows as online. "
            "If this is an old pairing of a phone you have re-paired, delete it.",
            409,
        )

    row = CaptureSession(
        device_id=device.id,
        field_id=field.id,
        mission_id=int(mission_id) if mission_id else None,
        interval_s=interval,
        max_duration_s=duration,
        max_shots=max_shots,
        status="armed",
        created_by=g.current_user.id,
    )
    session.add(row)
    session.commit()
    audit.record(
        g.current_user.id, "arm_capture_session", "capture_session", row.id,
        {"device_id": device.id, "field_id": field.id, "interval_s": interval,
         "max_duration_s": duration},
    )
    return jsonify(_session_payload(row)), 201


@bp.post("/sessions/<int:session_id>/stop")
@requires_role("admin", "technician")
def stop_session(session_id: int):
    session = SessionLocal()
    row = session.get(CaptureSession, session_id)
    if row is None:
        raise ApiError("Session not found.", 404)
    if row.status in ("armed", "running"):
        row.status = "stopped"
        row.ended_at = _now()
        row.end_reason = "Stopped by operator."
        session.commit()
        audit.record(g.current_user.id, "stop_capture_session", "capture_session", row.id)
    return jsonify(_session_payload(row))


VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
}


def _owned_session(session, session_id: int) -> CaptureSession:
    row = session.get(CaptureSession, session_id)
    if row is None:
        raise ApiError("That session does not exist.", 404)
    return row


@bp.post("/sessions/<int:session_id>/video")
@requires_role(*OPERATOR_ROLES)
def upload_video(session_id: int):
    """The flight video, uploaded after landing.

    Deliberately after, not during: a 10-minute clip is 100-150 MB, and competing with
    the stills for a rural uplink mid-flight would cost the thing that actually matters.
    The phone holds it and sends it when asked.
    """
    db = SessionLocal()
    row = _owned_session(db, session_id)
    if row.video_path:
        raise ApiError("This session already has a video. Delete the session to replace it.", 409)

    clip = request.files.get("video")
    if clip is None:
        raise ApiError("No video supplied.", 400)
    mime = (clip.mimetype or "").split(";")[0].strip().lower()
    suffix = VIDEO_TYPES.get(mime)
    if suffix is None:
        raise ApiError(
            "Unsupported video type. The phone should send MP4 or WebM.", 415
        )

    cfg = current_app.config["AGRISCAN"]
    target = storage.session_media_path(cfg, session_id, f"flight{suffix}")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    clip.save(tmp)
    size = tmp.stat().st_size
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise ApiError("The video was empty.", 400)
    if size > cfg.MAX_VIDEO_BYTES:
        tmp.unlink(missing_ok=True)
        raise ApiError("The video is larger than this server accepts.", 413)
    tmp.replace(target)

    duration = request.form.get("duration_s", type=float)
    row.video_path = storage.stored_ref(target)
    row.video_bytes = size
    row.video_mime = mime
    row.video_duration_s = duration
    row.video_uploaded_at = _now()
    db.commit()
    audit.record(g.current_user.id, "upload_flight_video", "capture_session", session_id,
                 {"bytes": size, "mime": mime})
    return jsonify({"ok": True, "bytes": size}), 201


# Cloudflare's free tier refuses a request body over 100 MB, and a ten-minute clip is
# several hundred. The phone sends it in pieces instead, which also means a dropped
# connection costs one piece rather than the whole upload.
VIDEO_CHUNK_MAX = 8 * 1024 * 1024


def _part_path(cfg, session_id: int) -> pathlib.Path:
    return storage.session_media_path(cfg, session_id, "flight.part")


@bp.post("/sessions/<int:session_id>/video/chunk")
@requires_role(*OPERATOR_ROLES)
def upload_video_chunk(session_id: int):
    """One piece of the flight video, appended in order.

    `index` 0 starts a new upload and discards anything half-sent before it, so a retry
    after a failure is simply sending from the beginning again. Pieces must arrive in
    order; anything else is rejected rather than silently producing a corrupt file.
    """
    db = SessionLocal()
    row = _owned_session(db, session_id)
    if row.video_path:
        raise ApiError("This session already has a video.", 409)

    try:
        index = int(request.form["index"])
    except (KeyError, TypeError, ValueError):
        raise ApiError("'index' is required.", 400) from None
    piece = request.files.get("chunk")
    if piece is None:
        raise ApiError("No chunk supplied.", 400)
    data = piece.read(VIDEO_CHUNK_MAX + 1)
    if len(data) > VIDEO_CHUNK_MAX:
        raise ApiError(f"Chunks must be {VIDEO_CHUNK_MAX // (1024 * 1024)} MB or smaller.", 413)

    cfg = current_app.config["AGRISCAN"]
    part = _part_path(cfg, session_id)
    part.parent.mkdir(parents=True, exist_ok=True)
    if index == 0:
        part.unlink(missing_ok=True)
    have = part.stat().st_size if part.is_file() else 0

    # The client knows how much it has sent; disagreeing means pieces were lost or
    # duplicated, and appending anyway would produce a file that plays as garbage.
    expected = request.form.get("offset", type=int)
    if expected is not None and expected != have:
        raise ApiError(
            f"Out of step: the server has {have} bytes, the phone expected {expected}. "
            "Start the upload again.",
            409,
        )
    if have + len(data) > cfg.MAX_VIDEO_BYTES:
        part.unlink(missing_ok=True)
        raise ApiError("The video is larger than this server accepts.", 413)

    with part.open("ab") as fh:
        fh.write(data)
    return jsonify({"received": len(data), "total": have + len(data)})


@bp.post("/sessions/<int:session_id>/video/complete")
@requires_role(*OPERATOR_ROLES)
def complete_video(session_id: int):
    """Turn the accumulated pieces into the session's video."""
    db = SessionLocal()
    row = _owned_session(db, session_id)
    if row.video_path:
        raise ApiError("This session already has a video.", 409)

    cfg = current_app.config["AGRISCAN"]
    part = _part_path(cfg, session_id)
    if not part.is_file() or part.stat().st_size == 0:
        raise ApiError("No video was uploaded.", 400)

    data = request.get_json(silent=True) or {}
    mime = (data.get("mime") or "video/webm").split(";")[0].strip().lower()
    suffix = VIDEO_TYPES.get(mime)
    if suffix is None:
        part.unlink(missing_ok=True)
        raise ApiError("Unsupported video type. The phone should send MP4 or WebM.", 415)

    target = storage.session_media_path(cfg, session_id, f"flight{suffix}")
    part.replace(target)
    size = target.stat().st_size

    row.video_path = storage.stored_ref(target)
    row.video_bytes = size
    row.video_mime = mime
    row.video_duration_s = data.get("duration_s")
    row.video_uploaded_at = _now()
    db.commit()
    audit.record(g.current_user.id, "upload_flight_video", "capture_session", session_id,
                 {"bytes": size, "mime": mime, "chunked": True})
    return jsonify({"ok": True, "bytes": size}), 201


@bp.get("/sessions/<int:session_id>/video")
@requires_role(*OPERATOR_ROLES)
def get_video(session_id: int):
    db = SessionLocal()
    row = _owned_session(db, session_id)
    if not row.video_path:
        raise ApiError("This session has no video.", 404)
    cfg = current_app.config["AGRISCAN"]
    path = storage.resolve_stored(row.video_path)
    if cfg.image_root_path not in path.parents or not path.is_file():
        raise ApiError("The video file is not on this server.", 404)
    # conditional=True gives Range support, which is what lets the player scrub without
    # pulling the whole clip first.
    return send_file(path, mimetype=row.video_mime or "video/mp4", conditional=True)


@bp.post("/sessions/<int:session_id>/frames")
@requires_role("admin", "technician")
def extract_frames(session_id: int):
    """Queue a job that pulls stills out of this session's video.

    Queued rather than done here: a five-minute clip is a full decode pass and
    hundreds of writes, which is not something to hold a request open for. The
    worker picks it up and each frame it writes queues its own inference job.

    interval_s defaults to 1.0 because the track is 1 Hz, so one frame per real fix
    is as much position resolution as exists. Smaller is allowed -- denser visual
    coverage can be worth having on its own -- but the frames in between sit on a
    straight line drawn between two fixes, and the response says how many of those
    there would be so the caller is not guessing.
    """
    db = SessionLocal()
    row = _owned_session(db, session_id)
    if not row.video_path:
        raise ApiError("This session has no video to take frames from.", 400)

    body = request.get_json(silent=True) or {}
    try:
        interval = float(body.get("interval_s", 1.0))
    except (TypeError, ValueError):
        raise ApiError("'interval_s' must be a number.", 400) from None
    if not 0.05 <= interval <= 60:
        raise ApiError("'interval_s' must be between 0.05 and 60 seconds.", 400)

    duration = float(row.video_duration_s or 0)
    estimate = int(duration / interval) if duration > 0 and interval > 0 else None
    if estimate is not None and estimate > video_frames.MAX_FRAMES:
        raise ApiError(
            f"That interval would ask for about {estimate} frames, over the "
            f"{video_frames.MAX_FRAMES} limit. Use a larger interval.", 400)

    db.execute(
        text("INSERT INTO jobs (type, status, priority, payload) "
             "VALUES ('video_frames', 'QUEUED', 0, :payload)"),
        {"payload": json.dumps({
            "capture_session_id": session_id,
            "interval_s": interval,
            "requested_by": g.current_user.id,
        })},
    )
    db.commit()
    job_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
    audit.record(g.current_user.id, "extract_frames", "capture_session", session_id,
                 {"interval_s": interval, "estimated_frames": estimate})
    return jsonify({
        "job_id": int(job_id),
        "interval_s": interval,
        "estimated_frames": estimate,
        "has_track": bool(row.track_path),
    }), 202


@bp.post("/sessions/<int:session_id>/track")
@requires_role(*OPERATOR_ROLES)
def upload_track(session_id: int):
    """The 1 Hz position track for the flight, as [{t, lat, lon, acc}].

    A frame pulled from the video gets its position by interpolating this. That is an
    inference, not a record, and anything derived from it is marked accordingly.
    """
    db = SessionLocal()
    row = _owned_session(db, session_id)
    points = (request.get_json(silent=True) or {}).get("points")
    if not isinstance(points, list) or not points:
        raise ApiError("'points' must be a non-empty list.", 400)

    clean = []
    for p in points[:20000]:
        try:
            clean.append({
                "t": round(float(p["t"]), 2),
                "lat": round(float(p["lat"]), 7),
                "lon": round(float(p["lon"]), 7),
                "acc": round(float(p.get("acc") or 0), 1),
            })
        except (KeyError, TypeError, ValueError):
            continue
    if not clean:
        raise ApiError("No usable points in the track.", 400)

    cfg = current_app.config["AGRISCAN"]
    target = storage.session_media_path(cfg, session_id, "track.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(clean), encoding="utf-8")
    row.track_path = storage.stored_ref(target)
    row.track_points = len(clean)
    db.commit()
    return jsonify({"ok": True, "points": len(clean)}), 201


@bp.get("/sessions/<int:session_id>/track")
@requires_role(*OPERATOR_ROLES)
def get_track(session_id: int):
    db = SessionLocal()
    row = _owned_session(db, session_id)
    if not row.track_path:
        return jsonify({"points": []})
    path = storage.resolve_stored(row.track_path)
    if not path.is_file():
        return jsonify({"points": []})
    return jsonify({"points": json.loads(path.read_text(encoding="utf-8"))})


@bp.delete("/sessions/<int:session_id>")
@requires_role("admin")
def delete_session(session_id: int):
    """Remove a session row from the history.

    The photos it produced are kept and stay in Captured images — they are the work, and
    a session row is only the record of a command. Deleting one that is still running is
    refused: stop it first, or the phone keeps shooting for a session nobody can see.
    """
    session = SessionLocal()
    row = session.get(CaptureSession, session_id)
    if row is None:
        raise ApiError("That session does not exist.", 404)
    if row.status in ("armed", "running"):
        raise ApiError("Stop this session before deleting it.", 409)

    captures = session.execute(
        text("SELECT COUNT(*) FROM images WHERE capture_session_id = :s"), {"s": session_id}
    ).scalar_one()
    # The photos outlive the record of the command that took them.
    session.execute(
        text("UPDATE images SET capture_session_id = NULL WHERE capture_session_id = :s"),
        {"s": session_id},
    )
    session.delete(row)
    session.commit()
    audit.record(g.current_user.id, "delete_capture_session", "capture_session", session_id,
                 {"status": row.status, "images_kept": int(captures)})
    return jsonify({"deleted": session_id, "images_kept": int(captures)})


@bp.get("/sessions/<int:session_id>/images.zip")
@requires_role(*OPERATOR_ROLES)
def session_images_zip(session_id: int):
    """Every photo from one session, as a single zip.

    Built on disk and streamed, not assembled in memory: a ten-minute flight is a few
    hundred full-resolution captures, and holding that in RAM to serve one download is
    how a laptop server falls over mid-defence.

    Filenames carry the capture order and time, so the archive is still meaningful once
    it is away from the database.
    """
    import tempfile
    import zipfile

    db = SessionLocal()
    row = _owned_session(db, session_id)
    cfg = current_app.config["AGRISCAN"]

    images = db.execute(
        text("SELECT id, file_path, captured_at FROM images "
             "WHERE capture_session_id = :s ORDER BY captured_at, id"),
        {"s": session_id},
    ).fetchall()
    if not images:
        raise ApiError("This session has no photos to download.", 404)

    handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    handle.close()
    written = 0
    with zipfile.ZipFile(handle.name, "w", zipfile.ZIP_STORED) as archive:
        # ZIP_STORED, not DEFLATE: JPEGs are already compressed, so deflating them costs
        # CPU on every file and saves almost nothing.
        for order, (image_id, file_path, captured_at) in enumerate(images, start=1):
            path = storage.resolve_stored(file_path)
            if cfg.image_root_path not in path.parents or not path.is_file():
                continue
            stamp = captured_at.strftime("%Y%m%d-%H%M%S") if captured_at else "unknown"
            archive.write(path, f"session-{session_id}/{order:04d}_{stamp}_img{image_id}.jpg")
            written += 1
        archive.writestr(
            f"session-{session_id}/README.txt",
            f"AGRISCAN capture session {session_id}\n"
            f"Field: {row.field_id}\nInterval: {row.interval_s}s\n"
            f"Photos in this archive: {written} of {len(images)} recorded\n"
            "Times are UTC. Any photo missing from this archive is a row whose file is\n"
            "not on the server.\n",
        )
    if written == 0:
        pathlib.Path(handle.name).unlink(missing_ok=True)
        raise ApiError("None of this session's photo files are on this server.", 404)

    response = send_file(handle.name, mimetype="application/zip", as_attachment=True,
                         download_name=f"agriscan-session-{session_id}.zip",
                         max_age=0)
    # The temporary file is the response body, so it can only go once Flask is done.
    @response.call_on_close
    def _cleanup():
        pathlib.Path(handle.name).unlink(missing_ok=True)

    audit.record(g.current_user.id, "download_session_images", "capture_session", session_id,
                 {"photos": written})
    return response


@bp.get("/sessions")
@requires_role(*OPERATOR_ROLES)
def list_sessions():
    session = SessionLocal()
    rows = session.execute(
        select(CaptureSession).order_by(CaptureSession.id.desc()).limit(50)
    ).scalars().all()
    out = []
    for row in rows:
        uploaded = session.execute(
            select(func.count()).select_from(Image).where(Image.capture_session_id == row.id)
        ).scalar_one()
        field = session.get(Field, row.field_id)
        device = session.get(CaptureDevice, row.device_id)
        out.append({
            **_session_payload(row),
            "images_uploaded": uploaded,
            "field_name": field.name if field else "NOT_AVAILABLE",
            "device_name": device.name if device else "NOT_AVAILABLE",
        })
    return jsonify(out)


# ------------------------------------------------------------------- field summary


@fields_summary_bp.get("")
@requires_role(*OPERATOR_ROLES, "farmer")
def fields_summary():
    """Every field the user may see, with boundary and activity counts, in one query set.

    Feeds the Field map page. Growth stage is derived per field for today.
    """
    from flask import current_app

    from app.services.growth_stage import derive_growth_stage
    from app.services.ownership import visible_farm_ids

    session = SessionLocal()
    cfg = current_app.config["AGRISCAN"]
    stmt = select(Field)
    allowed = visible_farm_ids(g.current_user)
    if allowed is not None:
        stmt = stmt.where(Field.farm_id.in_(allowed or [-1]))
    fields = session.execute(stmt.order_by(Field.name)).scalars().all()

    ids = [f.id for f in fields] or [-1]
    image_counts = dict(session.execute(
        select(Image.field_id, func.count()).where(Image.field_id.in_(ids)).group_by(Image.field_id)
    ).all())
    detection_rows = session.execute(
        select(Image.field_id, Detection.status, func.count())
        .join(Detection, Detection.image_id == Image.id)
        .where(Image.field_id.in_(ids))
        .group_by(Image.field_id, Detection.status)
    ).all()
    detections: dict[int, dict[str, int]] = {}
    for field_id, status, count in detection_rows:
        detections.setdefault(field_id, {})[status] = count

    today = dt.date.today()
    out = []
    for f in fields:
        counts = detections.get(f.id, {})
        out.append({
            **f.to_dict(),
            "has_boundary": f.boundary_geojson is not None,
            "images": image_counts.get(f.id, 0),
            "detections_total": sum(counts.values()),
            "detections_verified": counts.get("technician_verified", 0),
            "detections_unverified": sum(
                v for k, v in counts.items() if k in ("ai_detected", "low_confidence", "farmer_confirmed")
            ),
            "growth_stage": derive_growth_stage(f.planting_date, today, cfg),
        })
    return jsonify(out)
