"""Private command authority and durable revocation checks, without simulated browser results."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from services.common.source_policy import SourceProfile
from services.common.task_contracts import TaskCommand, TaskRef
from services.supervisor.spike import WorkerSettings
from services.supervisor.tasks import Registry, TaskError, Tasks


def task():
    return TaskCommand(
        job_id=uuid4(),
        fence=uuid4(),
        task_id=uuid4(),
        profile_id="boundary_assertion",
        profile_version=1,
        url="https://vendor.example.com/offer",
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"image": "custom:latest"},
        {"mode": "timeout"},
        {"proxy": "http://127.0.0.1:1"},
        {"selector": "body"},
        {"mount": "/"},
        {"timeout_seconds": 3600},
        {"flags": ["--privileged"]},
        {"profile_version": True},
        {"job_id": "../other"},
    ],
)
def test_remote_commands_cannot_expand_authority(extra):
    with pytest.raises(ValidationError):
        TaskCommand.model_validate(task().model_dump() | extra)


def test_revoked_fence_survives_service_reconstruction_and_denies_late_submit(tmp_path):
    tmp_path.chmod(0o700)
    profile = SourceProfile(
        id="boundary_assertion",
        version=1,
        origin="https://vendor.example.com",
        offer_paths=["/offer"],
        main_selector="main",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    settings = WorkerSettings(
        image="sha256:" + "a" * 64, network="latch_egress", proxy="http://172.29.240.1:3128"
    )
    command = task()
    service = Tasks(Registry(tmp_path), settings, [profile])
    ref = TaskRef(job_id=command.job_id, fence=command.fence)
    assert service.revoke(ref)["revoked"]
    restarted = Tasks(Registry(tmp_path), settings, [profile])
    with pytest.raises(TaskError, match="TASK_FENCE_REVOKED"):
        restarted.submit(command)
    with pytest.raises(TaskError, match="TASK_NOT_FOUND"):
        restarted.read(command.task_id, ref)
    with pytest.raises(ValueError):
        restarted.payload(command.model_copy(update={"url": "https://vendor.example.com/private"}))
    assert not list(tmp_path.glob("*.json"))
