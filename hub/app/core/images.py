"""Avatar image normalization. We never store client bytes verbatim — every
upload is decoded, validated and re-encoded into a fixed 256x256 JPEG, which
strips metadata and rejects non-images / decompression bombs."""

import base64
import binascii
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.errors import InvalidInputError

OUTPUT_SIZE = 256
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # raw upload cap, before decode
# A 256px avatar never needs more; this bounds decompression bombs at open().
Image.MAX_IMAGE_PIXELS = 50_000_000


def decode_data_url(value: str) -> bytes:
    """Accept a `data:<mime>;base64,<payload>` URL (or a bare base64 string) and
    return the raw bytes. Strict base64 — rejects junk."""
    payload = value.split(",", 1)[1] if value.startswith("data:") else value
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidInputError("Imagem inválida.") from exc


def normalize_avatar(raw: bytes) -> bytes:
    """Return a normalized 256x256 JPEG, or raise InvalidInputError if the input
    isn't a decodable image within the limits."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise InvalidInputError("A imagem deve ter no máximo 2 MB.")
    try:
        # verify() detects truncated files without loading pixels; open() rejects
        # oversized images (DecompressionBombError) from the header.
        with Image.open(BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(BytesIO(raw)) as img:
            rgb = ImageOps.exif_transpose(img).convert("RGB")
            square = ImageOps.fit(rgb, (OUTPUT_SIZE, OUTPUT_SIZE))
            out = BytesIO()
            square.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise InvalidInputError("Arquivo de imagem inválido.") from exc
