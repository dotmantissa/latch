CREATE TABLE jobs (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL, request_id UUID NOT NULL,
 request_version INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('inspect','recheck')),
 state TEXT NOT NULL CHECK(state IN ('queued','running','recovering','cancelling','succeeded','failed','cancelled')),
 idempotency_key TEXT NOT NULL, intent_hash TEXT NOT NULL,
 created_at BIGINT NOT NULL, deadline_at BIGINT NOT NULL,
 attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt BETWEEN 0 AND 2),
 fence UUID, lease_holder UUID, lease_until BIGINT, heartbeat_at BIGINT,
 cancel_requested_at BIGINT, finished_at BIGINT, failure_code TEXT,
 FOREIGN KEY(request_id,owner_id) REFERENCES requests(id,owner_id),
 FOREIGN KEY(request_id,request_version) REFERENCES request_versions(request_id,version),
 UNIQUE(owner_id,request_id,kind,idempotency_key), UNIQUE(id,owner_id,request_id),
 CHECK(deadline_at>created_at),
 CHECK(state NOT IN ('running','recovering','cancelling') OR fence IS NOT NULL)
);
CREATE INDEX jobs_runnable ON jobs(state,created_at);
CREATE UNIQUE INDEX jobs_active_request ON jobs(request_id)
 WHERE state IN ('queued','running','recovering','cancelling');
CREATE TABLE runner_slot (id INTEGER PRIMARY KEY CHECK(id=1));
INSERT INTO runner_slot VALUES(1);
CREATE TABLE job_attempts (
 job_id UUID NOT NULL REFERENCES jobs(id), attempt INTEGER NOT NULL,
 fence UUID NOT NULL UNIQUE, lease_holder UUID NOT NULL,
 started_at BIGINT NOT NULL, PRIMARY KEY(job_id,attempt), UNIQUE(job_id,fence)
);
CREATE TRIGGER attempts_immutable BEFORE UPDATE OR DELETE ON job_attempts
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TABLE job_tasks (
 task_id UUID PRIMARY KEY, job_id UUID NOT NULL, fence UUID NOT NULL,
 source_id UUID NOT NULL REFERENCES supplier_sources(id),
 started_at BIGINT NOT NULL, cleanup_at BIGINT, outcome TEXT,
 artifact_hash TEXT CHECK(artifact_hash IS NULL OR artifact_hash ~ '^[a-f0-9]{64}$'),
 FOREIGN KEY(job_id,fence) REFERENCES job_attempts(job_id,fence),
 UNIQUE(job_id,fence,source_id),
 CHECK(outcome IS NULL OR outcome IN ('captured','failed','cancelled','timed_out','interrupted'))
);
ALTER TABLE events ADD COLUMN job_id UUID;
ALTER TABLE events ADD CONSTRAINT events_job_owner FOREIGN KEY(job_id,owner_id,request_id)
 REFERENCES jobs(id,owner_id,request_id);
CREATE INDEX events_job_replay ON events(owner_id,job_id,id);
