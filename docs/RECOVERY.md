# Encrypted backup and recovery

Application history and captured evidence remain private. Archive preserves history;
there is no automatic deletion or invented retention consent. Local evidence/export
files require owned private directories and reject links, public modes, hash changes and
oversized bytes. An encrypted persistent volume remains a deployment requirement and
has not been claimed for this local checkout. Backups themselves are encrypted.

The operator tool takes a PostgreSQL repeatable-read snapshot, verifies immutable
migration checksums, reads bounded rows through server cursors and copies only referenced
immutable sanitized evidence/export bytes. The entire logical bundle is authenticated
with AES256 GCM and a fresh nonce. Plaintext never enters a backup file. The key lives
in an owned ignored private file and must have a separate secure recovery copy; losing
that key loses access to the backup. Do not keep the only key with the backup or publish
backup bundles, which contain private records and password hashes.

```bash
.venv/bin/python -m services.storage.recovery create-key
.venv/bin/python -m services.storage.recovery backup
.venv/bin/python -m services.storage.recovery restore --backup-hash HASH
```

The default store is `var/backups`; hashes identify encrypted `.blob` files. Commands
never print credentials. A schema4 pre-upgrade backup of the actual empty application
and isolated restore into the current schema passed. Populated isolated Neon receipts,
reviews, captures, exports and hashes also survived recovery; all restored sessions were
revoked. Restoration can read supported legacy schema4 onward and applies the current
additive migrations into a newly generated isolated schema. It never overwrites the
application schema or performs production cutover.

Authenticated restoration disables only the two named receipt commit guards while
inserting historical receipts in the fresh isolated schema, then reenables them. Historical
receipts are verified by their immutable hashes, not presented as new fresh releases.
Sessions are revoked; worker fences and task cleanup records remain available for exact
runner reconciliation. A restore cannot prove a remote container was cleaned. Sequence
positions are restored above existing IDs. Failed or interrupted restores retain exact
schema names under `var/restore-schemas`; inspect those notes and clean only the recorded
isolated schema after diagnosis. Keep recovery notes and private directories out of Git.

Current finite limits are 64 MiB of plaintext logical snapshot, 10000 rows per table,
70 MiB encrypted/export files, 2 MiB renderer input/output and a 12 second PDF process
limit. Limit or authentication failure produces no successful backup/restore claim.
Large deployments require measured streaming recovery tooling before exceeding these
bounds. Backups omit unrelated quarantine/orphan files and infrastructure/private keys.

There is no automatic backup purge or record destruction. Preserve verified recovery
points before upgrades; test an isolated restore and compare receipt/export/source hashes
before a separately authorized production cutover. Database downgrade is refused. A
compatible code rollback may use the additive current schema; otherwise recover the
prior encrypted snapshot into an isolated schema and plan the cutover. Actual public
restore, volume encryption, retention consent and production disaster recovery drills
remain deployment/evaluation work.

The [current recovery record](evidence/RECOVERY_STATUS.json) records the verified
schema4 recovery point, isolated legacy restore, populated schema10 restore and the
actual application upgrade to schema10. The application inventory remained empty.
