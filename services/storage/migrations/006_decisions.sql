CREATE TABLE comparisons (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL, request_id UUID NOT NULL,
 request_version INTEGER NOT NULL, packet_hash TEXT NOT NULL CHECK(packet_hash ~ '^[a-f0-9]{64}$'),
 packet_json JSONB NOT NULL, evaluated_at BIGINT NOT NULL,
 FOREIGN KEY(request_id,owner_id) REFERENCES requests(id,owner_id),
 FOREIGN KEY(request_id,request_version) REFERENCES request_versions(request_id,version),
 UNIQUE(id,request_id,request_version), UNIQUE(request_id,packet_hash)
);
CREATE TABLE selections (
 id UUID PRIMARY KEY, request_id UUID NOT NULL, request_version INTEGER NOT NULL,
 comparison_id UUID NOT NULL, source_id UUID NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 owner_id UUID NOT NULL, idempotency_key TEXT NOT NULL, intent_hash TEXT NOT NULL,
 created_at BIGINT NOT NULL,
 FOREIGN KEY(comparison_id,request_id,request_version)
  REFERENCES comparisons(id,request_id,request_version),
 FOREIGN KEY(source_id,request_id,request_version)
  REFERENCES supplier_sources(id,request_id,version),
 FOREIGN KEY(request_id,owner_id) REFERENCES requests(id,owner_id),
 UNIQUE(request_id,revision), UNIQUE(owner_id,request_id,idempotency_key),
 UNIQUE(id,request_id,request_version)
);
CREATE TABLE approvals (
 id UUID PRIMARY KEY, request_id UUID NOT NULL, request_version INTEGER NOT NULL,
 selection_id UUID NOT NULL, owner_id UUID NOT NULL, session_id UUID NOT NULL REFERENCES sessions(id),
 packet_json JSONB NOT NULL, packet_hash TEXT NOT NULL CHECK(packet_hash ~ '^[a-f0-9]{64}$'),
 created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL,
 idempotency_key TEXT NOT NULL, intent_hash TEXT NOT NULL,
 FOREIGN KEY(selection_id,request_id,request_version)
  REFERENCES selections(id,request_id,request_version),
 FOREIGN KEY(request_id,owner_id) REFERENCES requests(id,owner_id),
 UNIQUE(owner_id,request_id,idempotency_key), UNIQUE(id,request_id,request_version),
 CHECK(expires_at=created_at+600000)
);
CREATE TABLE approval_revocations (
 approval_id UUID PRIMARY KEY REFERENCES approvals(id), revoked_by UUID NOT NULL REFERENCES users(id),
 revoked_at BIGINT NOT NULL
);
CREATE TRIGGER comparisons_immutable BEFORE UPDATE OR DELETE ON comparisons
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER selections_immutable BEFORE UPDATE OR DELETE ON selections
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER approvals_immutable BEFORE UPDATE OR DELETE ON approvals
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER revocations_immutable BEFORE UPDATE OR DELETE ON approval_revocations
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
