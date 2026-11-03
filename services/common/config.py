"""Configuration for P0 probes. No credential value enters configuration output."""

import os
import stat
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    public_origin: str = "https://localhost:8443"
    data_dir: Path = Path("var")
    inference_base_url: str = "https://api.vultrinference.com/v1"
    model_id: str | None = Field(default=None, max_length=200)
    inference_key_file: Path | None = None
    source_task_file: Path | None = None

    @field_validator("inference_base_url")
    @classmethod
    def vultr_only(cls, value: str) -> str:
        if value != "https://api.vultrinference.com/v1":
            raise ValueError("Only the approved Vultr inference endpoint is supported")
        return value

    @field_validator("public_origin")
    @classmethod
    def https_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("A single HTTPS application origin is required")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls) -> "Settings":
        names = {
            "LATCH_PUBLIC_ORIGIN": "public_origin",
            "LATCH_DATA_DIR": "data_dir",
            "LATCH_INFERENCE_BASE_URL": "inference_base_url",
            "LATCH_MODEL_ID": "model_id",
            "LATCH_INFERENCE_KEY_FILE": "inference_key_file",
            "LATCH_SOURCE_TASK_FILE": "source_task_file",
        }
        return cls(**{field: os.environ[name] for name, field in names.items() if os.getenv(name)})


def read_secret(path: Path) -> str:
    """Open a private regular file without following a final-component symlink."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_uid != os.getuid()
            or info.st_size > 8192
        ):
            raise ValueError("Credential must be an owned private regular file of bounded size")
        value = os.read(fd, 8193).decode("utf-8").strip()
        if not value or len(value) > 8192 or any(c.isspace() for c in value):
            raise ValueError("Credential file must contain one nonempty token")
        return value
    finally:
        os.close(fd)
