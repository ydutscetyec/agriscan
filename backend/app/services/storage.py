"""Image validation, hashing, re-encoding and on-disk layout.

The client filename is never trusted and never used. Files land at
<IMAGE_ROOT>/<year>/<month>/<uuid>.jpg, named by a server-generated UUID.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import logging
import pathlib
import uuid

from PIL import Image as PILImage

from app.utils.clock import utc_now
from app.config import BACKEND_DIR, Config, resolve_path
from app.utils.errors import ApiError

MAX_PIXELS = 80_000_000  # decompression-bomb guard


def resolve_stored(file_path: str) -> pathlib.Path:
    """Where a stored image actually is on disk.

    `images.file_path` keeps the form it has always had (IMAGE_ROOT as configured, plus
    year/month/uuid.jpg), so rows written before p21 still match. What changed is that a
    relative path now resolves against backend/, not against whatever directory the
    process happened to be started from. Before, a worker started from the project root
    looked for photos the web server had written somewhere else.
    """
    return resolve_path(file_path)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_upload(filename: str, mimetype: str, data: bytes, cfg: Config) -> None:
    if not data:
        raise ApiError("Empty upload.", 400)
    if len(data) > cfg.MAX_UPLOAD_BYTES:
        raise ApiError(
            f"File exceeds the {cfg.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.", 413
        )
    ext = pathlib.Path(filename or "").suffix.lower()
    if ext not in cfg.ALLOWED_IMAGE_EXT:
        raise ApiError(f"Extension '{ext or 'none'}' is not allowed.", 415)
    if (mimetype or "").lower() not in cfg.ALLOWED_IMAGE_MIME:
        raise ApiError(f"Content type '{mimetype}' is not allowed.", 415)


def reencode_and_store(data: bytes, cfg: Config, when: dt.datetime | None = None) -> dict:
    """Decode, verify, strip everything, re-encode as JPEG, write to disk.

    Re-encoding is the sanitising step: whatever was appended to or embedded in the
    uploaded bytes does not survive a decode/encode round trip. EXIF is read BEFORE
    this, from the original bytes, because re-encoding deliberately discards it.
    """
    when = when or utc_now()
    try:
        probe = PILImage.open(io.BytesIO(data))
        probe.verify()  # structural check; consumes the object
        img = PILImage.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise ApiError("Image dimensions are implausibly large.", 413)
        img = img.convert("RGB")
    except ApiError:
        raise
    except Exception:  # noqa: BLE001
        raise ApiError("File is not a readable image.", 400) from None

    file_uuid = str(uuid.uuid4())
    rel_dir = pathlib.Path(f"{when.year:04d}") / f"{when.month:02d}"
    abs_dir = cfg.image_root_path / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / f"{file_uuid}.jpg"

    img.save(abs_path, format="JPEG", quality=92, optimize=True)

    return {
        "uuid": file_uuid,
        "file_path": str(pathlib.Path(cfg.IMAGE_ROOT) / rel_dir / f"{file_uuid}.jpg"),
        "width": img.width,
        "height": img.height,
    }


def write_temp_original(data: bytes, cfg: Config) -> str:
    """Write the untouched upload to a temp file so exifread can parse it."""
    tmp_dir = cfg.image_root_path / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4()}.orig"
    tmp_path.write_bytes(data)
    return str(tmp_path)


# Thumbnails. The Captured images page drew 84 px squares by downloading the full
# JPEG for every row: one flight is ~300 photos of a few MB each, so the page pulled
# close to a gigabyte to render a grid. These are generated once, cached on disk beside
# the image store, and are a few kB each.
THUMB_MAX = 320
THUMB_QUALITY = 72


def thumb_path(cfg: Config, image_id: int) -> pathlib.Path:
    return cfg.image_root_path / "_thumbs" / f"{image_id}.jpg"


def ensure_thumbnail(cfg: Config, image_id: int, source: pathlib.Path) -> pathlib.Path | None:
    """Return the cached thumbnail, making it if needed. None if it cannot be made.

    Regenerated when the source is newer, so replacing a file is picked up. A failure
    here is never fatal: the caller falls back to the full image.
    """
    target = thumb_path(cfg, image_id)
    try:
        if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
            return target
        from PIL import Image as PILImage

        target.parent.mkdir(parents=True, exist_ok=True)
        with PILImage.open(source) as img:
            img = img.convert("RGB")
            img.thumbnail((THUMB_MAX, THUMB_MAX))
            tmp = target.with_suffix(".tmp")
            img.save(tmp, "JPEG", quality=THUMB_QUALITY, optimize=True)
            tmp.replace(target)
        return target
    except Exception:  # noqa: BLE001
        logging.getLogger("agriscan").warning("Could not thumbnail image %s", image_id)
        return None


def drop_thumbnail(cfg: Config, image_id: int) -> None:
    try:
        thumb_path(cfg, image_id).unlink(missing_ok=True)
    except OSError:
        pass


def session_media_path(cfg: Config, session_id: int, name: str) -> pathlib.Path:
    """Where a session's video and track live. One folder per session, so deleting a
    flight's media is one directory, and nothing of it sits among the stills."""
    return cfg.image_root_path / "_flights" / str(session_id) / name


def stored_ref(path: pathlib.Path) -> str:
    """The form a path is written to the database in: relative to backend/ when it sits
    under it, matching images.file_path, so resolve_stored() finds it again. Getting this
    wrong stores a path that round-trips to nothing."""
    path = path.resolve()
    try:
        return str(path.relative_to(BACKEND_DIR))
    except ValueError:
        return str(path)
