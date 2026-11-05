CREATE TABLE receipt_exports (
 receipt_id UUID NOT NULL REFERENCES receipts(id), format TEXT NOT NULL CHECK(format IN ('json','pdf','zip')),
 exporter_version TEXT NOT NULL CHECK(exporter_version='receipt-export-v1'),
 content_hash TEXT NOT NULL CHECK(content_hash ~ '^[a-f0-9]{64}$'),
 bytes BIGINT NOT NULL CHECK(bytes BETWEEN 1 AND 73400320), created_at BIGINT NOT NULL,
 PRIMARY KEY(receipt_id,format)
);
CREATE TRIGGER exports_immutable BEFORE UPDATE OR DELETE ON receipt_exports
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_change();
