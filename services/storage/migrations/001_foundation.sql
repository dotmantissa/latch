CREATE TABLE users (
 id UUID PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
 password_hash TEXT NOT NULL, active BOOLEAN NOT NULL,
 created_at BIGINT NOT NULL, password_changed_at BIGINT NOT NULL
);
CREATE TABLE sessions (
 id UUID PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, user_id UUID NOT NULL REFERENCES users(id),
 created_at BIGINT NOT NULL, last_seen_at BIGINT NOT NULL, absolute_expires_at BIGINT NOT NULL,
 reauthenticated_at BIGINT NOT NULL, revoked_at BIGINT
);
CREATE INDEX sessions_user ON sessions(user_id);
CREATE TABLE source_profiles (
 id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0), profile_json JSONB NOT NULL,
 active BOOLEAN NOT NULL, expires_at BIGINT NOT NULL, PRIMARY KEY(id,version)
);
CREATE TABLE requests (
 seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, id UUID NOT NULL UNIQUE,
 owner_id UUID NOT NULL REFERENCES users(id), current_version INTEGER NOT NULL CHECK(current_version>0),
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, archived_at BIGINT, UNIQUE(id,owner_id)
);
CREATE INDEX requests_owner_seq ON requests(owner_id,seq DESC);
CREATE TABLE request_versions (
 request_id UUID NOT NULL REFERENCES requests(id), version INTEGER NOT NULL CHECK(version>0),
 snapshot_json JSONB NOT NULL, content_hash TEXT NOT NULL, created_at BIGINT NOT NULL,
 PRIMARY KEY(request_id,version)
);
CREATE TABLE required_items (
 id UUID PRIMARY KEY, request_id UUID NOT NULL, version INTEGER NOT NULL, stable_item_key TEXT NOT NULL,
 specification TEXT NOT NULL, public_specification TEXT NOT NULL,
 required_units INTEGER NOT NULL CHECK(required_units BETWEEN 1 AND 10000), ordered_position INTEGER NOT NULL,
 FOREIGN KEY(request_id,version) REFERENCES request_versions(request_id,version),
 UNIQUE(request_id,version,stable_item_key)
);
CREATE TABLE supplier_sources (
 id UUID PRIMARY KEY, request_id UUID NOT NULL, version INTEGER NOT NULL, label TEXT NOT NULL,
 canonical_public_url TEXT NOT NULL, profile_id TEXT NOT NULL, profile_version INTEGER NOT NULL,
 supplier_key TEXT NOT NULL,
 FOREIGN KEY(request_id,version) REFERENCES request_versions(request_id,version),
 FOREIGN KEY(profile_id,profile_version) REFERENCES source_profiles(id,version),
 UNIQUE(request_id,version,canonical_public_url)
);
CREATE TABLE idempotency (
 owner_id UUID NOT NULL REFERENCES users(id), route_scope TEXT NOT NULL, key TEXT NOT NULL,
 intent_hash TEXT NOT NULL, resource_id UUID NOT NULL, resource_version INTEGER NOT NULL,
 status INTEGER NOT NULL, created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL,
 PRIMARY KEY(owner_id,route_scope,key)
);
CREATE TABLE events (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, owner_id UUID NOT NULL REFERENCES users(id),
 request_id UUID NOT NULL, kind TEXT NOT NULL, safe_payload_json JSONB NOT NULL, at BIGINT NOT NULL,
 FOREIGN KEY(request_id,owner_id) REFERENCES requests(id,owner_id)
);
CREATE INDEX events_owner_request ON events(owner_id,request_id,id);
CREATE FUNCTION reject_immutable_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Immutable application record'; END; $$;
CREATE TRIGGER request_versions_immutable BEFORE UPDATE OR DELETE ON request_versions FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER items_immutable BEFORE UPDATE OR DELETE ON required_items FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER sources_immutable BEFORE UPDATE OR DELETE ON supplier_sources FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER profiles_immutable BEFORE UPDATE OF profile_json,expires_at ON source_profiles FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
CREATE TRIGGER events_immutable BEFORE UPDATE OR DELETE ON events FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
