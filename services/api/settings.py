"""Private server configuration. Credentials are never serialized into API responses."""

import os
from pathlib import Path

from pydantic import Field

from services.common.config import Settings, read_secret


class AppSettings(Settings):
    database_url_file: Path = Path("private/database-url")
    csrf_key_file: Path = Path("private/csrf-key")
    database_schema: str = Field(default="latch", pattern=r"^latch(?:_test_[a-f0-9]{32})?$")
    static_dir: Path = Path("dist")
    evidence_dir: Path = Path("var/evidence")
    enable_inspections: bool = False
    enable_demo: bool = False
    artifact_group_id: int | None = Field(default=None, ge=0)
    artifact_owner_ids: tuple[int, ...] = ()

    def artifact_store(self, *, binary=False):
        from services.artifacts.store import ArtifactStore, BinaryStore

        store = BinaryStore if binary else ArtifactStore
        root = self.evidence_dir.parent / "exports" if binary else self.evidence_dir
        return store(root, group_id=self.artifact_group_id, owner_ids=self.artifact_owner_ids)

    @classmethod
    def from_environment(cls) -> "AppSettings":
        base = Settings.from_environment().model_dump()
        names = {
            "LATCH_DATABASE_URL_FILE": "database_url_file",
            "LATCH_CSRF_KEY_FILE": "csrf_key_file",
            "LATCH_DB_SCHEMA": "database_schema",
            "LATCH_STATIC_DIR": "static_dir",
            "LATCH_EVIDENCE_DIR": "evidence_dir",
            "LATCH_ENABLE_INSPECTIONS": "enable_inspections",
            "LATCH_ENABLE_DEMO": "enable_demo",
            "LATCH_ARTIFACT_GROUP_ID": "artifact_group_id",
        }
        base.update({field: os.environ[name] for name, field in names.items() if os.getenv(name)})
        if os.getenv("LATCH_ARTIFACT_OWNER_IDS"):
            base["artifact_owner_ids"] = tuple(
                int(v) for v in os.environ["LATCH_ARTIFACT_OWNER_IDS"].split(",")
            )
        return cls(**base)

    def database_url(self) -> str:
        return read_secret(self.database_url_file)
