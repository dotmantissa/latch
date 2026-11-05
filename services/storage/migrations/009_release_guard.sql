ALTER TABLE approvals ADD COLUMN generation BIGINT GENERATED ALWAYS AS IDENTITY;
CREATE FUNCTION guard_internal_release_commit() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
 at BIGINT := floor(extract(epoch FROM clock_timestamp())*1000)::bigint;
 a approvals%ROWTYPE;
 s sessions%ROWTYPE;
 j jobs%ROWTYPE;
 selected selections%ROWTYPE;
 expected INTEGER;
BEGIN
 SELECT * INTO a FROM approvals WHERE id=NEW.approval_id;
 SELECT * INTO s FROM sessions WHERE id=a.session_id;
 SELECT sel.* INTO selected FROM selections sel WHERE sel.id=a.selection_id;
 SELECT job.* INTO j FROM jobs job JOIN release_attempts attempt ON attempt.job_id=job.id
  WHERE attempt.id=NEW.attempt_id AND attempt.approval_id=a.id
   AND attempt.session_id=a.session_id AND attempt.owner_id=NEW.owner_id;
 IF a.id IS NULL OR s.id IS NULL OR j.id IS NULL OR selected.id IS NULL
  OR a.owner_id<>NEW.owner_id OR a.request_version<>NEW.request_version
  OR at<a.created_at OR at>=a.expires_at
  OR s.user_id<>NEW.owner_id OR s.revoked_at IS NOT NULL
  OR at<s.created_at OR at<s.last_seen_at OR at>=s.absolute_expires_at
  OR at-s.last_seen_at>=7200000
  OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.owner_id AND active)
  OR NOT EXISTS(SELECT 1 FROM requests WHERE id=NEW.request_id AND owner_id=NEW.owner_id
      AND current_version=NEW.request_version AND archived_at IS NULL)
  OR EXISTS(SELECT 1 FROM approval_revocations WHERE approval_id=a.id)
  OR a.id<>(SELECT id FROM approvals WHERE request_id=NEW.request_id ORDER BY generation DESC LIMIT 1)
  OR selected.id<>(SELECT id FROM selections WHERE request_id=NEW.request_id ORDER BY revision DESC LIMIT 1)
  OR j.request_id<>NEW.request_id OR j.request_version<>NEW.request_version
  OR j.kind<>'recheck' OR j.state<>'succeeded' OR j.cancel_requested_at IS NOT NULL
  OR j.finished_at<j.created_at OR j.finished_at>j.deadline_at OR j.finished_at>at
 THEN RAISE EXCEPTION 'Internal release commit authority invalid'; END IF;
 SELECT count(*) INTO expected FROM supplier_sources
  WHERE request_id=NEW.request_id AND version=NEW.request_version;
 IF expected<1 OR expected>3 OR expected<>(SELECT count(*) FROM source_captures
    WHERE job_id=j.id AND fence=j.fence)
  OR expected<>jsonb_array_length(a.packet_json->'comparison'->'sources')
  OR EXISTS(SELECT 1 FROM job_tasks WHERE job_id=j.id AND fence=j.fence AND cleanup_at IS NULL)
 THEN RAISE EXCEPTION 'Internal release source set incomplete'; END IF;
 IF EXISTS(
  SELECT 1 FROM source_captures fresh
  JOIN supplier_sources source ON source.id=fresh.source_id
  JOIN source_profiles profile ON profile.id=source.profile_id AND profile.version=source.profile_version
  LEFT JOIN LATERAL (SELECT v FROM jsonb_array_elements(a.packet_json->'comparison'->'sources') v
      WHERE v->>'source_id'=fresh.source_id::text) approved ON true
  LEFT JOIN source_captures original ON original.id=(approved.v->>'capture_id')::uuid
  LEFT JOIN review_heads head ON head.extraction_id=(approved.v->>'extraction_id')::uuid
  WHERE fresh.job_id=j.id AND fresh.fence=j.fence AND (
    original.id IS NULL OR approved.v IS NULL OR COALESCE(head.version,0) IS DISTINCT FROM
     (approved.v->>'review_version')::integer
    OR NOT profile.active OR profile.expires_at<=at
    OR fresh.profile_id<>source.profile_id OR fresh.profile_version<>source.profile_version
    OR fresh.content_fingerprint<>original.content_fingerprint
    OR fresh.page_count<>(SELECT count(*) FROM captured_pages WHERE capture_id=fresh.id)
    OR EXISTS(SELECT 1 FROM captured_pages page LEFT JOIN captured_pages prior
      ON prior.capture_id=original.id AND prior.page_index=page.page_index
      WHERE page.capture_id=fresh.id AND (
       prior.id IS NULL OR prior.source_url<>page.source_url
       OR prior.sanitized_png_hash<>page.sanitized_png_hash
       OR page.started_at<j.created_at OR page.completed_at<page.started_at
       OR page.completed_at>at OR at-page.completed_at>60000))
  )
 ) THEN RAISE EXCEPTION 'Internal release evidence expired or changed'; END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER receipt_release_guard AFTER INSERT ON receipts
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_internal_release_commit();
