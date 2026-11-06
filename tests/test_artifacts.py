"""Actual isolated decoding and filesystem boundaries; generated rasters are codec inputs only."""

import hashlib
import io
import os
import struct
import subprocess
import sys

import pytest
from PIL import Image, PngImagePlugin

from services.artifacts.packet import fingerprint
from services.artifacts.sanitize import ArtifactRejected, dimensions, sanitize
from services.artifacts.store import ArtifactStore
from services.common.source_policy import SourceProfile


def png(*, metadata=False):
    image = Image.new("RGB", (19, 23), (120, 30, 45))
    out = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    if metadata:
        info.add_text("Comment", "Untrusted decoder assertion")
    image.save(out, format="PNG", pnginfo=info)
    return out.getvalue()


def test_real_seccomp_denies_file_network_fork_and_exec():
    child = subprocess.run(
        [sys.executable, "-I", "services/artifacts/decode.py", "--probe"],
        capture_output=True,
        timeout=10,
        env={"LC_ALL": "C"},
        close_fds=True,
    )
    assert child.returncode == 0 and child.stdout == b"restricted\n"


def test_actual_decode_discards_metadata_and_preserves_pixels():
    value = png(metadata=True)
    clean = sanitize(value)
    assert clean.raw_hash == hashlib.sha256(value).hexdigest()
    assert clean.sanitized_hash == hashlib.sha256(clean.data).hexdigest()
    assert clean.width == 19 and clean.height == 23
    with Image.open(io.BytesIO(clean.data)) as image:
        assert image.mode == "RGB" and image.info == {}
        assert image.getpixel((0, 0)) == (120, 30, 45)
    assert b"Untrusted decoder assertion" not in clean.data
    assert sanitize(value).data == clean.data


def test_decoder_rejects_header_only_bad_crc_animation_transparency_and_limits():
    value = png()
    broken = bytearray(value)
    broken[29] ^= 1  # IHDR CRC
    for bad in (value[:33], bytes(broken), b"<svg></svg>"):
        with pytest.raises(ArtifactRejected):
            sanitize(bad)
    # Check pixel limits before starting a decoder or allocating the declared pixels.
    oversized = bytearray(value)
    oversized[16:24] = struct.pack(">II", 4000, 16000)
    with pytest.raises(ArtifactRejected):
        dimensions(bytes(oversized))
    for options in (
        {"save_all": True, "append_images": [Image.new("RGB", (19, 23), "white")]},
        {"transparency": (120, 30, 45)},
    ):
        output = io.BytesIO()
        Image.new("RGB", (19, 23), (120, 30, 45)).save(output, format="PNG", **options)
        with pytest.raises(ArtifactRejected):
            sanitize(output.getvalue())


def test_private_atomic_files_reject_links_corruption_paths_and_public_modes(tmp_path):
    clean = sanitize(png())
    root = tmp_path / "evidence"
    with ArtifactStore(root) as store:
        store.put(clean)
        store.put(clean)
        assert store.read(clean.sanitized_hash) == clean.data
        assert sorted(p.name for p in root.iterdir()) == [clean.sanitized_hash + ".png"]
        for value in ("../assertion", "A" * 64, "a" * 65):
            with pytest.raises(ArtifactRejected):
                store.read(value)
        target = root / (clean.sanitized_hash + ".png")
        os.chmod(target, 0o644)
        with pytest.raises(ArtifactRejected):
            store.read(clean.sanitized_hash)
        target.unlink()
        os.mkfifo(target, mode=0o600)
        with pytest.raises(ArtifactRejected):
            store.read(clean.sanitized_hash)
        target.unlink()
        store.put(clean)
        os.chmod(target, 0o600)
        other = tmp_path / "hardlink"
        os.link(target, other)
        with pytest.raises(ArtifactRejected):
            store.read(clean.sanitized_hash)
        other.unlink()
        target.write_bytes(b"x" * len(clean.data))
        with pytest.raises(ArtifactRejected):
            store.put(clean)
        target.unlink()
        target.symlink_to(tmp_path / "absent")
        with pytest.raises(ArtifactRejected):
            store.read(clean.sanitized_hash)
    link = tmp_path / "linked_directory"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ArtifactRejected):
        ArtifactStore(link / "child")
    os.chmod(root, 0o755)
    with pytest.raises(ArtifactRejected):
        ArtifactStore(root)


def test_fingerprint_preserves_new_terms_and_profile_or_source_changes():
    profile = SourceProfile(
        id="projection_assertion",
        version=1,
        origin="https://vendor.example.com",
        offer_paths=["/offer"],
        main_selector="main",
        expires_at="2026-11-07T00:00:00Z",
    )
    first = [{"url": "https://vendor.example.com/offer", "text": "Cafe\u0301  $12.34\r\nTerms"}]
    normalized = [{"url": first[0]["url"], "text": "Café $12.34\nTerms"}]
    assert fingerprint(first, profile) == fingerprint(normalized, profile)
    for changed in (
        [{"url": first[0]["url"], "text": "Café $12.34\nTerms\nNew exclusion"}],
        [{"url": "https://vendor.example.com/other", "text": normalized[0]["text"]}],
    ):
        assert fingerprint(changed, profile) != fingerprint(first, profile)
    assert fingerprint(first, profile.model_copy(update={"version": 2})) != (
        fingerprint(first, profile)
    )


def test_explicit_shared_store_retains_link_hash_owner_and_mode_checks(tmp_path):
    root = tmp_path / "shared"
    clean = sanitize(png())
    with ArtifactStore(root, group_id=os.getgid(), owner_ids=(os.getuid(),)) as store:
        store.put(clean)
        target = root / store.name(clean.sanitized_hash)
        assert root.stat().st_mode & 0o2770 == 0o2770
        assert target.stat().st_mode & 0o777 == 0o640
        assert store.read(clean.sanitized_hash) == clean.data
        with pytest.raises(ArtifactRejected):
            ArtifactStore(root)
        for mode in (0o644, 0o660, 0o650):
            target.chmod(mode)
            with pytest.raises(ArtifactRejected):
                store.read(clean.sanitized_hash)
        target.chmod(0o640)
        link = tmp_path / "linked"
        os.link(target, link)
        with pytest.raises(ArtifactRejected):
            store.read(clean.sanitized_hash)
        link.unlink()
        target.write_bytes(b"x" * len(clean.data))
        with pytest.raises(ArtifactRejected):
            store.read(clean.sanitized_hash)
    root.chmod(0o2775)
    with pytest.raises(ArtifactRejected):
        ArtifactStore(root, group_id=os.getgid(), owner_ids=(os.getuid(),))
