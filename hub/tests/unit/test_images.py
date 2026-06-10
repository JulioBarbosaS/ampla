import base64
from io import BytesIO

import pytest
from PIL import Image

from app.core.images import decode_data_url, normalize_avatar
from app.services.errors import InvalidInputError


def _png_bytes(size: tuple[int, int] = (40, 20)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


class TestNormalizeAvatar:
    def test_reencodes_to_256_square_jpeg(self):
        out = normalize_avatar(_png_bytes((40, 20)))
        assert out[:2] == b"\xff\xd8"  # JPEG magic
        with Image.open(BytesIO(out)) as img:
            assert img.size == (256, 256)
            assert img.format == "JPEG"

    def test_rejects_non_image(self):
        with pytest.raises(InvalidInputError):
            normalize_avatar(b"definitely not an image")

    def test_rejects_oversized_upload(self):
        with pytest.raises(InvalidInputError):
            normalize_avatar(b"\x00" * (2 * 1024 * 1024 + 1))


class TestDecodeDataUrl:
    def test_decodes_data_url_and_bare_base64(self):
        raw = _png_bytes()
        b64 = base64.b64encode(raw).decode()
        assert decode_data_url(f"data:image/png;base64,{b64}") == raw
        assert decode_data_url(b64) == raw

    def test_rejects_invalid_base64(self):
        with pytest.raises(InvalidInputError):
            decode_data_url("data:image/png;base64,!!!not base64!!!")
