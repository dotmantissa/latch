CREATE TABLE review_heads (
 extraction_id UUID PRIMARY KEY REFERENCES source_extractions(id),
 version INTEGER NOT NULL CHECK(version BETWEEN 0 AND 10000)
);
CREATE TABLE field_reviews (
 id UUID PRIMARY KEY, extraction_id UUID NOT NULL REFERENCES source_extractions(id),
 version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 10000),
 reviewer_id UUID NOT NULL REFERENCES users(id), request_version INTEGER NOT NULL,
 proposal_hash TEXT NOT NULL CHECK(proposal_hash ~ '^[a-f0-9]{64}$'),
 decision_json JSONB NOT NULL, command_json JSONB NOT NULL,
 idempotency_key TEXT NOT NULL, intent_hash TEXT NOT NULL CHECK(intent_hash ~ '^[a-f0-9]{64}$'),
 created_at BIGINT NOT NULL,
 UNIQUE(extraction_id,version), UNIQUE(extraction_id,reviewer_id,idempotency_key)
);
CREATE INDEX reviews_extraction_version ON field_reviews(extraction_id,version DESC);
CREATE TRIGGER field_reviews_immutable BEFORE UPDATE OR DELETE ON field_reviews
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
