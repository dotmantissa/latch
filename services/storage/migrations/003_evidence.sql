ALTER TABLE supplier_sources ADD UNIQUE(id,request_id,version);
ALTER TABLE job_tasks ADD UNIQUE(task_id,job_id,fence,source_id);

CREATE TABLE source_captures (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL, request_id UUID NOT NULL,
 request_version INTEGER NOT NULL, job_id UUID NOT NULL, fence UUID NOT NULL,
 task_id UUID NOT NULL UNIQUE, source_id UUID NOT NULL,
 capture_hash TEXT NOT NULL CHECK(capture_hash ~ '^[a-f0-9]{64}$'),
 content_fingerprint TEXT NOT NULL CHECK(content_fingerprint ~ '^[a-f0-9]{64}$'),
 fingerprint_version TEXT NOT NULL CHECK(fingerprint_version='visible-text-v1'),
 profile_id TEXT NOT NULL, profile_version INTEGER NOT NULL,
 page_count INTEGER NOT NULL CHECK(page_count BETWEEN 1 AND 2), created_at BIGINT NOT NULL,
 FOREIGN KEY(job_id,owner_id,request_id) REFERENCES jobs(id,owner_id,request_id),
 FOREIGN KEY(task_id,job_id,fence,source_id) REFERENCES job_tasks(task_id,job_id,fence,source_id),
 FOREIGN KEY(source_id,request_id,request_version) REFERENCES supplier_sources(id,request_id,version),
 FOREIGN KEY(profile_id,profile_version) REFERENCES source_profiles(id,version)
);
CREATE INDEX captures_owner_request ON source_captures(owner_id,request_id,request_version);

CREATE TABLE captured_pages (
 id UUID PRIMARY KEY, capture_id UUID NOT NULL REFERENCES source_captures(id),
 page_index INTEGER NOT NULL CHECK(page_index BETWEEN 0 AND 1), source_url TEXT NOT NULL,
 source_text TEXT NOT NULL CHECK(octet_length(source_text) BETWEEN 1 AND 32768),
 text_hash TEXT NOT NULL CHECK(text_hash ~ '^[a-f0-9]{64}$'),
 started_at BIGINT NOT NULL, completed_at BIGINT NOT NULL,
 raw_png_hash TEXT NOT NULL CHECK(raw_png_hash ~ '^[a-f0-9]{64}$'),
 sanitized_png_hash TEXT NOT NULL CHECK(sanitized_png_hash ~ '^[a-f0-9]{64}$'),
 sanitized_bytes INTEGER NOT NULL CHECK(sanitized_bytes BETWEEN 33 AND 10485760),
 width INTEGER NOT NULL CHECK(width BETWEEN 1 AND 4000),
 height INTEGER NOT NULL CHECK(height BETWEEN 1 AND 16000),
 sanitizer_version TEXT NOT NULL CHECK(sanitizer_version='png-rgb-seccomp-v1'),
 UNIQUE(capture_id,page_index), CHECK(width::bigint*height<=12000000),
 CHECK(completed_at>=started_at AND completed_at-started_at<=90000)
);

CREATE TABLE source_extractions (
 id UUID PRIMARY KEY, capture_id UUID NOT NULL UNIQUE REFERENCES source_captures(id),
 proposal_json JSONB NOT NULL, proposal_hash TEXT NOT NULL CHECK(proposal_hash ~ '^[a-f0-9]{64}$'),
 usage_json JSONB NOT NULL, created_at BIGINT NOT NULL
);
CREATE TRIGGER captures_immutable BEFORE UPDATE OR DELETE ON source_captures
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER pages_immutable BEFORE UPDATE OR DELETE ON captured_pages
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER extractions_immutable BEFORE UPDATE OR DELETE ON source_extractions
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
