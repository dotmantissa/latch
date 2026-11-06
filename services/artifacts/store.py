"""Owned content-addressed files, atomic admission and bounded reads without link following."""

import ctypes
import errno
import hashlib
import os
import re
import stat
from pathlib import Path
from uuid import uuid4

from services.artifacts.sanitize import MAX_BYTES, ArtifactRejected, Raster


class ArtifactStore:
    suffix = ".png"
    minimum = 33
    limit = MAX_BYTES

    def __init__(self, root: Path, *, group_id: int | None = None, owner_ids: tuple[int, ...] = ()):
        self.group_id = group_id
        self.owner_ids = frozenset((*owner_ids, os.getuid()))
        if group_id is not None and (
            group_id not in (*os.getgroups(), os.getgid()) or not owner_ids
        ):
            raise ArtifactRejected("ARTIFACT_TRUSTED_GROUP_REQUIRED")
        absolute = root.absolute()
        # Check each ancestor before traversing it. resolve() would follow an untrusted link.
        if ".." in absolute.parts:
            raise ArtifactRejected("ARTIFACT_DIRECTORY_REQUIRED")
        current = Path(absolute.anchor)
        for part in absolute.parts[1:]:
            current = current / part
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                current.mkdir(mode=0o700)
                if current == absolute and group_id is not None:
                    os.chown(current, -1, group_id)
                    os.chmod(current, 0o2770)
                mode = current.lstat().st_mode
            if not stat.S_ISDIR(mode):
                raise ArtifactRejected("ARTIFACT_DIRECTORY_REQUIRED")
        fd = os.open(absolute, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not self.private(info, directory=True):
                raise ArtifactRejected("ARTIFACT_PRIVATE_DIRECTORY_REQUIRED")
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd

    def private(self, info, *, directory=False):
        if self.group_id is None:
            return info.st_uid == os.getuid() and not info.st_mode & 0o077
        return (
            info.st_uid in self.owner_ids
            and info.st_gid == self.group_id
            and not info.st_mode & (0o007 if directory else 0o037)
            and (not directory or bool(info.st_mode & stat.S_ISGID))
        )

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @classmethod
    def name(cls, digest: str) -> str:
        if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
            raise ArtifactRejected("ARTIFACT_HASH_REQUIRED")
        return digest + cls.suffix

    def read(self, digest: str, *, size: int | None = None) -> bytes:
        try:
            fd = os.open(
                self.name(digest),
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self.fd,
            )
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or not self.private(info)
                    or not self.minimum <= info.st_size <= self.limit
                    or (size is not None and info.st_size != size)
                ):
                    raise ArtifactRejected("ARTIFACT_FILE_REJECTED")
                # A bounded read also detects file mutation after fstat.
                chunks, total = [], 0
                while chunk := os.read(fd, min(65536, self.limit + 1 - total)):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > self.limit:
                        raise ArtifactRejected("ARTIFACT_FILE_REJECTED")
                value = b"".join(chunks)
                if len(value) != info.st_size or hashlib.sha256(value).hexdigest() != digest:
                    raise ArtifactRejected("ARTIFACT_HASH_MISMATCH")
                return value
            finally:
                os.close(fd)
        except OSError:
            raise ArtifactRejected("ARTIFACT_FILE_UNAVAILABLE") from None

    def put(self, raster: Raster):
        if not self.minimum <= len(raster.data) <= self.limit or hashlib.sha256(
            raster.data
        ).hexdigest() != (raster.sanitized_hash):
            raise ArtifactRejected("ARTIFACT_HASH_MISMATCH")
        name = self.name(raster.sanitized_hash)
        temporary = uuid4().hex + ".pending"
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.fd,
        )
        try:
            if self.group_id is not None:
                os.fchown(fd, -1, self.group_id)
                os.fchmod(fd, 0o640)
            with os.fdopen(fd, "wb") as output:
                output.write(raster.data)
                output.flush()
                os.fsync(output.fileno())
            # Linux's atomic no-replace rename has no intermediate hardlink. A crash can
            # leave an unreferenced .pending file, never a target with two links or partial bytes.
            libc = ctypes.CDLL(None, use_errno=True)
            rename = libc.renameat2
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            if rename(self.fd, temporary.encode(), self.fd, name.encode(), 1) != 0:
                code = ctypes.get_errno()
                if code != errno.EEXIST:
                    raise ArtifactRejected("ARTIFACT_ATOMIC_ADMISSION_UNAVAILABLE")
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass
        os.fsync(self.fd)
        # Existing files must agree; never silently overwrite corrupted evidence.
        self.read(raster.sanitized_hash, size=len(raster.data))


class BinaryStore(ArtifactStore):
    suffix = ".blob"
    minimum = 1
    limit = 70 * 1024 * 1024

    def put_bytes(self, data):
        from types import SimpleNamespace

        digest = hashlib.sha256(data).hexdigest()
        self.put(SimpleNamespace(data=data, sanitized_hash=digest))
        return digest
