CREATE TABLE release_attempts (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL, request_id UUID NOT NULL,
 request_version INTEGER NOT NULL, approval_id UUID NOT NULL, session_id UUID NOT NULL REFERENCES sessions(id),
 job_id UUID NOT NULL UNIQUE, idempotency_key TEXT NOT NULL, intent_hash TEXT NOT NULL,
 created_at BIGINT NOT NULL,
 FOREIGN KEY(approval_id,request_id,request_version)
  REFERENCES approvals(id,request_id,request_version),
 FOREIGN KEY(job_id,owner_id,request_id) REFERENCES jobs(id,owner_id,request_id),
 UNIQUE(owner_id,request_id,idempotency_key), UNIQUE(id,request_id,request_version)
);
CREATE TABLE release_outcomes (
 attempt_id UUID PRIMARY KEY REFERENCES release_attempts(id),
 state TEXT NOT NULL CHECK(state IN ('changed','blocked','released')),
 reason TEXT, diff_json JSONB NOT NULL, finished_at BIGINT NOT NULL
);
CREATE TABLE receipts (
 id UUID PRIMARY KEY, attempt_id UUID NOT NULL UNIQUE, request_id UUID NOT NULL,
 request_version INTEGER NOT NULL, owner_id UUID NOT NULL, approval_id UUID NOT NULL,
 record_json JSONB NOT NULL, record_hash TEXT NOT NULL CHECK(record_hash ~ '^[a-f0-9]{64}$'),
 committed_at BIGINT NOT NULL,
 FOREIGN KEY(attempt_id,request_id,request_version)
  REFERENCES release_attempts(id,request_id,request_version),
 FOREIGN KEY(approval_id,request_id,request_version)
  REFERENCES approvals(id,request_id,request_version),
 FOREIGN KEY(request_id,owner_id) REFERENCES requests(id,owner_id),
 UNIQUE(request_id,request_version), UNIQUE(id,owner_id)
);
CREATE TRIGGER attempts_command_immutable BEFORE UPDATE OR DELETE ON release_attempts
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER outcomes_immutable BEFORE UPDATE OR DELETE ON release_outcomes
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER receipts_immutable BEFORE UPDATE OR DELETE ON receipts
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
