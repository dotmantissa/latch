"""P0 commands. Missing live evidence never becomes an application success."""

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from services.common.config import Settings
from services.common.source_policy import BuyerTask
from services.common.sqlite import assert_runtime, connect
from services.runner.vultr import ProviderFailure, VultrClient

ROOT = Path(__file__).resolve().parents[2]


def timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write_report(settings: Settings, name: str, report: dict) -> Path:
    directory = settings.data_dir / "p0"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    fd, temporary = tempfile.mkstemp(prefix="report-", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump({"schema_version": 1, "at": timestamp(), **report}, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        destination = directory / f"{name}.json"
        os.replace(temporary, destination)
        return destination
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def runtime_probe(settings: Settings) -> dict:
    expected_python = (ROOT / ".python-version").read_text().strip()
    if platform.python_version() != expected_python:
        raise ValueError("Configured exact Python runtime is required")
    sqlite_version = assert_runtime()
    node = ROOT / ".tools/node/node_modules/node/bin/node"
    if not node.is_file():
        node = Path(shutil.which("node") or "/node-unavailable")
    result = subprocess.run(
        [str(node), str(ROOT / "scripts/check_node.mjs")],
        capture_output=True,
        timeout=10,
        check=True,
        text=True,
    )
    node_report = json.loads(result.stdout)
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="runtime-", dir=settings.data_dir) as directory:
        database = Path(directory) / "probe.sqlite"
        first, second = connect(database), connect(database)
        try:
            first.execute(
                "CREATE TABLE runtime_probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
            first.execute("INSERT INTO runtime_probe VALUES (1, 'persisted')")
            if second.execute("SELECT value FROM runtime_probe").fetchone()[0] != "persisted":
                raise ValueError("Second connection could not read committed data")
            pragmas = {
                name: second.execute(f"PRAGMA {name}").fetchone()[0]
                for name in ("foreign_keys", "journal_mode", "synchronous", "busy_timeout")
            }
            if pragmas != {
                "foreign_keys": 1,
                "journal_mode": "wal",
                "synchronous": 2,
                "busy_timeout": 5000,
            }:
                raise ValueError("Required SQLite settings are not effective")
            restored = connect(Path(directory) / "backup.sqlite")
            try:
                first.backup(restored)
                if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed")
                if restored.execute("SELECT value FROM runtime_probe").fetchone()[0] != "persisted":
                    raise ValueError("Online backup did not preserve data")
            finally:
                restored.close()
        finally:
            first.close()
            second.close()
    packages = {
        name: importlib.metadata.version(name)
        for name in ("fastapi", "pydantic", "httpx", "playwright")
    }
    return {
        "status": "passed",
        "scope": "local_runtime",
        "python": platform.python_version(),
        "node": node_report["node"],
        "sqlite": sqlite_version,
        "sqlite_pragmas": pragmas,
        "online_backup_restore": "passed",
        "packages": packages,
        "locks": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("uv.lock", "package-lock.json")
        },
    }


def load_task(settings: Settings) -> BuyerTask:
    if settings.source_task_file is None:
        raise ValueError("SOURCE_TASK_NOT_CONFIGURED")
    if settings.source_task_file.stat().st_size > 256 * 1024:
        raise ValueError("Source task exceeds its size cap")
    return BuyerTask.model_validate_json(settings.source_task_file.read_bytes())


def source_probe(settings: Settings) -> dict:
    task = load_task(settings)
    sources = task.admitted_sources(datetime.now(UTC))
    return {
        "status": "input_validated",
        "scope": "source_admission",
        "source_count": len(sources),
        "item_count": len(task.items),
        "task_hash": hashlib.sha256(task.model_dump_json().encode()).hexdigest(),
        "live_compatibility": "pending",
        "reason": (
            "Independent review of actual captured stock, quantity and delivery terms is required"
        ),
    }


def require_json_object(message: dict, required_keys: set[str]) -> dict:
    content = message.get("content")
    if not isinstance(content, str) or len(content.encode()) > 20 * 1024:
        raise ProviderFailure("MODEL_OUTPUT_INVALID")
    try:
        value = json.loads(content)
    except ValueError as exc:
        raise ProviderFailure("MODEL_OUTPUT_INVALID") from exc
    if not isinstance(value, dict) or set(value) != required_keys:
        raise ProviderFailure("MODEL_OUTPUT_INVALID")
    return value


def model_probe(settings: Settings, capture_file: Path) -> dict:
    task = load_task(settings)
    allowed = task.admitted_sources(datetime.now(UTC))
    if capture_file.stat().st_size > 15 * 1024 * 1024:
        raise ValueError("Capture exceeds its size cap")
    capture = json.loads(capture_file.read_bytes())
    if capture.get("url") not in allowed or capture.get("complete") is not True:
        raise ValueError("An actual complete capture of an admitted source is required")
    raster = base64.b64decode(capture["png_base64"], validate=True)
    if len(raster) > 10 * 1024 * 1024 or raster[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Bounded captured PNG required")
    if hashlib.sha256(raster).hexdigest() != capture["png_sha256"]:
        raise ValueError("Capture hash mismatch")
    client = VultrClient(settings)
    message, text_usage = client.complete(
        [{"role": "user", "content": 'Return the JSON object {"capability":"text"}.'}],
        response_format={"type": "json_object"},
    )
    if require_json_object(message, {"capability"}) != {"capability": "text"}:
        raise ProviderFailure("TEXT_CAPABILITY_FAILED")
    page_token = "p0_captured_page"
    tool = {
        "type": "function",
        "function": {
            "name": "inspect_page",
            "description": "Read a public captured page by its token",
            "parameters": {
                "type": "object",
                "properties": {"page_token": {"type": "string"}},
                "required": ["page_token"],
                "additionalProperties": False,
            },
        },
    }
    message, tool_usage = client.complete(
        [{"role": "user", "content": f"Call inspect_page with page_token {page_token}."}],
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": "inspect_page"}},
    )
    calls = message.get("tool_calls", [])
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "inspect_page":
        raise ProviderFailure("TOOL_CAPABILITY_FAILED")
    arguments = calls[0]["function"].get("arguments")
    if not isinstance(arguments, str) or len(arguments.encode()) > 20 * 1024:
        raise ProviderFailure("TOOL_CAPABILITY_FAILED")
    if json.loads(arguments) != {"page_token": page_token}:
        raise ProviderFailure("TOOL_CAPABILITY_FAILED")
    # Only public capture content goes to inference. No buyer identity, budget or credential.
    message, vision_usage = client.complete(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Read this actual supplier capture. Return JSON with only "
                            '"visible_text", '
                            'a short transcription, and "uncertain", a boolean. '
                            "Abstain if illegible."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + capture["png_base64"]},
                    },
                ],
            }
        ],
        response_format={"type": "json_object"},
    )
    vision = require_json_object(message, {"visible_text", "uncertain"})
    if not isinstance(vision["visible_text"], str) or type(vision["uncertain"]) is not bool:
        raise ProviderFailure("VISION_CAPABILITY_FAILED")
    if not vision["visible_text"].strip() or vision["uncertain"]:
        raise ProviderFailure("VISION_CAPABILITY_ABSTAINED")
    return {
        "status": "passed",
        "scope": "live_vultr_capability",
        "endpoint": settings.inference_base_url,
        "capture_sha256": capture["png_sha256"],
        "text": text_usage,
        "tools": tool_usage,
        "vision": vision_usage,
        "vision_correctness": (
            "Requires independent source review; model schema validity is not truth"
        ),
    }


def gate_report(settings: Settings) -> dict:
    required = {
        "runtime": "Exact runtime and fixed SQLite",
        "source": "Independent real buyer and source compatibility review",
        "model": "Authenticated Vultr text, tool schema and actual screenshot input",
        "worker": "Actual isolated browser, allowed fetch, denied egress, timeout and cleanup",
    }
    checks = {}
    for name, description in required.items():
        path = settings.data_dir / "p0" / f"{name}.json"
        status = "pending"
        if path.is_file():
            report = json.loads(path.read_bytes())
            status = report.get("status", "pending")
        checks[name] = {"status": status, "requires": description}
    # This is a readiness inventory, never an automatic authorization to skip human gates.
    return {
        "status": "pending",
        "scope": "p0_gate_inventory",
        "checks": checks,
        "next_package": "P1 remains blocked until all live evidence is independently reviewed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("runtime")
    commands.add_parser("source")
    commands.add_parser("gate")
    model = commands.add_parser("model")
    model.add_argument("--capture", type=Path, required=True)
    args = parser.parse_args()
    settings = None
    try:
        settings = Settings.from_environment()
        if args.command == "runtime":
            report = runtime_probe(settings)
        elif args.command == "source":
            report = source_probe(settings)
        elif args.command == "model":
            report = model_probe(settings, args.capture)
        else:
            report = gate_report(settings)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        # Do not serialize exception details; they may contain input, URLs or local paths.
        code = "CONFIG_OR_INPUT_INVALID"
        if isinstance(exc, ValidationError):
            code = "SCHEMA_INVALID"
        report = {"status": "failed", "scope": args.command, "code": code}
    except ProviderFailure as exc:
        report = {"status": "failed", "scope": "live_vultr_capability", "code": str(exc)}
    if settings is not None:
        write_report(settings, args.command, report)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] in ("passed", "input_validated") else 1


if __name__ == "__main__":
    raise SystemExit(main())
