CREATE FUNCTION guard_internal_release_eligibility() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
 at TIMESTAMPTZ := clock_timestamp();
 approved JSONB;
 worksheet JSONB;
 candidate JSONB;
 deadline TIMESTAMPTZ;
 arrival TIMESTAMPTZ;
BEGIN
 SELECT packet_json INTO approved FROM approvals WHERE id=NEW.approval_id;
 SELECT snapshot_json INTO worksheet FROM request_versions
  WHERE request_id=NEW.request_id AND version=NEW.request_version;
 SELECT value INTO candidate FROM jsonb_array_elements(approved->'comparison'->'sources')
  WHERE value->>'source_id'=approved->>'selected_source_id';
 SELECT (value->>'value')::timestamptz INTO arrival
  FROM jsonb_array_elements(candidate->'reviewed_fields')
  WHERE value->'original'->>'kind'='latest_arrival';
 deadline := (worksheet->>'required_by')::timestamptz;
 IF candidate IS NULL OR deadline IS NULL OR arrival IS NULL
  OR deadline<=at OR arrival<at OR arrival>deadline
  OR candidate->'selectable' IS DISTINCT FROM 'true'::jsonb
  OR candidate->'basket'->'complete' IS DISTINCT FROM 'true'::jsonb
  OR candidate->'basket'->'reviewed' IS DISTINCT FROM 'true'::jsonb
  OR candidate->'basket'->'feasible' IS DISTINCT FROM 'true'::jsonb
  OR candidate->'basket'->'complete_total_cents' IS NULL
  OR candidate->'basket'->'complete_total_cents'='null'::jsonb
  OR (candidate->'basket'->>'complete_total_cents')::bigint>(worksheet->>'budget_cents')::bigint
 THEN RAISE EXCEPTION 'Internal release eligibility expired'; END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER receipt_eligibility_guard AFTER INSERT ON receipts
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_internal_release_eligibility();
