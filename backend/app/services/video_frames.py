"""Pull still frames out of a flight video and store them as positioned images.

The phone records a 1 Hz GPS track alongside the video (capture.upload_track), and
that track is the only thing that can say where a frame was taken. A field boundary
cannot: it says where the field is, not where in it the drone was at second 47. So
this module interpolates the track and nothing else, and where there is no track the
frames are stored with gps_source='missing' rather than a guessed position.

Every frame written here is marked exactly as the single-frame grab in
api/images.py marks one:

    gps_source          'video_interpolated' (or 'missing' with no track)
    from_video_offset_s where in the clip it came from

A video frame is roughly a sixth of the pixels of a camera still, is inter-frame
compressed, and has a position worked out rather than recorded. Nothing derived from
one should be counted as ground truth without someone deciding so deliberately.

ON THE SAMPLING INTERVAL
    The track is 1 Hz. Sampling faster than that does not buy position resolution it
    does not have: at 0.5 s every other frame sits on a straight line drawn between
    two fixes, and at 0.3 s two out of three do. With the ±5-10 m accuracy a phone
    reports in a field, frames a couple of metres apart are not distinguishable
    positions. 1.0 s is the default because it is one frame per real fix. Smaller is
    allowed because denser visual coverage can still be worth having for detection
    even when the positions blur -- but it is a choice about pictures, not about
    mapping, and the caller should know which one they are making.
"""

from __future__ import annotations

import datetime as dt
import json
import logging

from sqlalchemy import select, text

from app.models import CaptureSession, Field, Image
from app.services import storage
from app.utils.clock import utc_now

log = logging.getLogger(__name__)

# A runaway interval on a long clip should not fill the disk before anyone notices.
# At the 1.0 s default this is over four hours of flight.
MAX_FRAMES = 15000


def interpolate_track(points: list[dict], t: float) -> tuple[float | None, float | None, float | None]:
    """Position at time t from a 1 Hz track, by linear interpolation between the two
    surrounding fixes. Returns (lat, lon, accuracy). Outside the track, the nearest
    endpoint, because a frame a second past the last fix is still near it."""
    if not points:
        return None, None, None
    if t <= points[0]["t"]:
        p = points[0]
        return p["lat"], p["lon"], p.get("acc")
    if t >= points[-1]["t"]:
        p = points[-1]
        return p["lat"], p["lon"], p.get("acc")
    for before, after in zip(points, points[1:]):
        if before["t"] <= t <= after["t"]:
            span = after["t"] - before["t"]
            share = 0.0 if span <= 0 else (t - before["t"]) / span
            lat = before["lat"] + (after["lat"] - before["lat"]) * share
            lon = before["lon"] + (after["lon"] - before["lon"]) * share
            # The worse of the two fixes, plus the distance the drone covered between
            # them: an interpolated point cannot be better than what it sits between.
            acc = max(before.get("acc") or 0, after.get("acc") or 0)
            return lat, lon, acc
    return None, None, None


def _load_track(capture_session: CaptureSession) -> list[dict]:
    if not capture_session.track_path:
        return []
    path = storage.resolve_stored(capture_session.track_path)
    if not path.is_file():
        return []
    try:
        points = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return points if isinstance(points, list) else []


def sample_offsets(duration_s: float, interval_s: float) -> list[float]:
    """The offsets to grab, from 0 up to but not past the end of the clip.

    Built with integer arithmetic rather than by adding interval_s repeatedly, because
    repeated addition of something like 0.3 drifts: after 300 steps a float sum is
    visibly short, and the offsets are written into from_video_offset_s where that
    drift would be a lie about which moment the frame came from.
    """
    if duration_s <= 0 or interval_s <= 0:
        return []
    count = int(duration_s / interval_s) + 1
    offsets = [round(i * interval_s, 3) for i in range(count)]
    # Strictly inside the clip. duration_s is where the video ends, not a moment that
    # has a picture: a 6.0 s clip at 30 fps has its last frame at 5.967 s. Including
    # the endpoint asks for a frame that is never decoded, and the job then reports
    # one more frame than it wrote.
    return [o for o in offsets if o < duration_s][:MAX_FRAMES]


def extract(session, cfg, capture_session_id: int, interval_s: float = 1.0,
            requested_by: int | None = None) -> dict:
    """Grab a frame every interval_s and store each as a positioned Image.

    Idempotent through the same content_hash check the upload endpoint uses: running
    it twice does not duplicate frames, and running it again at a smaller interval
    adds only the offsets that landed on new pictures.
    """
    import cv2  # imported here: the web process never needs it, only the worker.

    capture_session = session.get(CaptureSession, capture_session_id)
    if capture_session is None:
        raise ValueError(f"capture session {capture_session_id} does not exist")
    if not capture_session.video_path:
        raise ValueError(f"capture session {capture_session_id} has no video")

    video = storage.resolve_stored(capture_session.video_path)
    if not video.is_file():
        raise ValueError(f"the video file for session {capture_session_id} is missing")

    field = session.get(Field, capture_session.field_id)
    points = _load_track(capture_session)
    if not points:
        log.warning(
            "Session %s has no track. Frames will be stored with gps_source='missing' "
            "and will not appear on the map; a boundary cannot supply a position.",
            capture_session_id,
        )

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f"could not open the video for session {capture_session_id}")
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        frames = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        duration = (frames / fps) if fps > 0 and frames > 0 else 0.0
        if duration <= 0 and capture_session.video_duration_s:
            # WebM from MediaRecorder often carries no frame count, because the
            # container is written for streaming rather than seeking. The phone
            # reported the length when it uploaded, so fall back to that.
            duration = float(capture_session.video_duration_s)
        if duration <= 0:
            raise ValueError("could not determine the video's length")

        offsets = sample_offsets(duration, interval_s)
        started = utc_now()
        counts = {"requested": len(offsets), "written": 0, "duplicate": 0,
                  "unreadable": 0, "positioned": 0, "image_ids": []}

        # Decoded straight through rather than seeking per offset. Seeking by
        # timestamp in VP9/WebM is unreliable -- MediaRecorder writes few keyframes
        # and a seek lands on the nearest one, so offsets would silently snap
        # together. Reading in order costs one pass and gives honest timestamps.
        wanted = iter(offsets)
        target = next(wanted, None)
        index = 0
        while target is not None:
            ok, frame = capture.read()
            if not ok:
                break
            now = index / fps if fps > 0 else 0.0
            index += 1
            if now + 1e-9 < target:
                continue

            ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            if not ok:
                counts["unreadable"] += 1
                target = next(wanted, None)
                continue
            data = buffer.tobytes()

            content_hash = storage.sha256_hex(data)
            existing = session.execute(
                select(Image).where(Image.content_hash == content_hash)
            ).scalar_one_or_none()
            if existing is not None:
                counts["duplicate"] += 1
                target = next(wanted, None)
                continue

            lat, lon, acc = interpolate_track(points, target)
            stored = storage.reencode_and_store(data, cfg)
            captured = capture_session.started_at or capture_session.created_at or started
            image = Image(
                uuid=stored["uuid"],
                mission_id=capture_session.mission_id,
                capture_session_id=capture_session.id,
                field_id=capture_session.field_id,
                source="drone",
                file_path=stored["file_path"],
                content_hash=content_hash,
                lat=lat,
                lon=lon,
                gps_accuracy_m=acc,
                gps_source="video_interpolated" if lat is not None else "missing",
                from_video_offset_s=target,
                captured_at=captured + dt.timedelta(seconds=float(target)),
                uploaded_by=requested_by,
                is_demo=bool(field.is_demo) if field is not None else False,
            )
            session.add(image)
            session.flush()

            session.execute(
                text("INSERT INTO jobs (type, status, priority, payload) "
                     "VALUES ('inference', 'QUEUED', 0, :payload)"),
                {"payload": json.dumps({"image_id": image.id})},
            )
            counts["written"] += 1
            counts["image_ids"].append(image.id)
            if lat is not None:
                counts["positioned"] += 1
            target = next(wanted, None)

        session.commit()
    finally:
        capture.release()

    log.info(
        "Session %s: %s frames written, %s positioned, %s duplicates, %s unreadable, "
        "from %.1fs at %.2fs intervals",
        capture_session_id, counts["written"], counts["positioned"],
        counts["duplicate"], counts["unreadable"], duration, interval_s,
    )
    counts["duration_s"] = round(duration, 2)
    counts["interval_s"] = interval_s
    counts["had_track"] = bool(points)
    # The ids are useful to a caller but pointless in a stored job result, and a
    # thousand of them would blow past the column.
    counts["image_ids"] = counts["image_ids"][:50]
    return counts
