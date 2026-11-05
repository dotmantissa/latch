"""Bounded parent-side byte validation; image decoding occurs only in a restricted child."""

import hashlib
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 12_000_000
POLICY_VERSION = "png-rgb-seccomp-v1"


class ArtifactRejected(ValueError):
    """Fixed operator-safe failure code, without supplier content or filesystem paths."""


def dimensions(value: bytes) -> tuple[int, int]:
    if (len(value) < 33 or len(value) > MAX_BYTES
            or value[:8] != b"\x89PNG\r\n\x1a\n" or value[12:16] != b"IHDR"):
        raise ArtifactRejected("ARTIFACT_PNG_REQUIRED")
    width, height = int.from_bytes(value[16:20], "big"), int.from_bytes(value[20:24], "big")
    if (not 1 <= width <= 4000 or not 1 <= height <= 16000 or width * height > MAX_PIXELS):
        raise ArtifactRejected("ARTIFACT_DIMENSIONS_LIMIT")
    return width, height


@dataclass(frozen=True)
class Raster:
    data: bytes
    raw_hash: str
    sanitized_hash: str
    width: int
    height: int
    sanitizer_version: str = POLICY_VERSION


def sanitize(png: bytes) -> Raster:
    expected = dimensions(png)
    # Anonymous bounded output cannot be followed through a filename. The child inherits
    # only its three standard descriptors and receives neither environment nor credentials.
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).with_name("decode.py"))],
                input=png, stdout=output, stderr=subprocess.DEVNULL,
                cwd="/", env={"LC_ALL": "C"}, close_fds=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ArtifactRejected("ARTIFACT_SANITIZER_UNAVAILABLE") from None
        if result.returncode != 0:
            raise ArtifactRejected("ARTIFACT_DECODE_REJECTED")
        output.seek(0)
        data = output.read(MAX_BYTES + 1)
    if dimensions(data) != expected:
        raise ArtifactRejected("ARTIFACT_DIMENSIONS_MISMATCH")
    return Raster(
        data=data, raw_hash=hashlib.sha256(png).hexdigest(),
        sanitized_hash=hashlib.sha256(data).hexdigest(), width=expected[0], height=expected[1],
    )
