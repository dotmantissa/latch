CREATE TABLE runner_health (
 id INTEGER PRIMARY KEY CHECK(id=1), holder UUID NOT NULL,
 checked_at BIGINT NOT NULL, available BOOLEAN NOT NULL,
 profiles_json JSONB NOT NULL CHECK(jsonb_typeof(profiles_json)='array')
);
CREATE TABLE inspection_plans (
 job_id UUID NOT NULL, fence UUID NOT NULL, plan_json JSONB NOT NULL,
 plan_hash TEXT NOT NULL CHECK(plan_hash ~ '^[a-f0-9]{64}$'),
 usage_json JSONB NOT NULL, created_at BIGINT NOT NULL,
 PRIMARY KEY(job_id,fence),
 FOREIGN KEY(job_id,fence) REFERENCES job_attempts(job_id,fence)
);
CREATE TRIGGER inspection_plans_immutable BEFORE UPDATE OR DELETE ON inspection_plans
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
