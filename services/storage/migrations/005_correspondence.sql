CREATE TABLE source_correspondence (
 id UUID PRIMARY KEY, capture_id UUID NOT NULL UNIQUE REFERENCES source_captures(id),
 result_json JSONB NOT NULL, result_hash TEXT NOT NULL CHECK(result_hash ~ '^[a-f0-9]{64}$'),
 usage_json JSONB NOT NULL, created_at BIGINT NOT NULL
);
CREATE TRIGGER correspondence_immutable BEFORE UPDATE OR DELETE ON source_correspondence
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
