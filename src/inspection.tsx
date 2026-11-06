import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, copy, timestamp, type SavedRequest } from "./api";
import type { components } from "../packages/contracts/api";
import { ErrorNotice } from "./ui";

type Inspection = components["schemas"]["InspectionView"];
const active = new Set(["queued", "running", "recovering", "cancelling"]);

export function InspectionControl({ saved, dirty }: { saved: SavedRequest; dirty: boolean }) {
  const client = useQueryClient();
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const pending = useRef<string | null>(null);
  const query = useQuery({
    queryKey: ["inspection", saved.id, saved.version],
    queryFn: () => api<Inspection>(`/requests/${saved.id}/inspection`),
    refetchInterval: 5000,
  });
  const job = query.data?.job;
  const running = Boolean(job && active.has(job.state));
  useEffect(() => {
    if (!job || !active.has(job.state)) return;
    const stream = new EventSource(`/api/v1/jobs/${job.id}/events`);
    const refresh = () => {
      void client.invalidateQueries({ queryKey: ["inspection", saved.id] });
      void client.invalidateQueries({ queryKey: ["evidence"] });
      void client.invalidateQueries({ queryKey: ["reviews"] });
    };
    stream.addEventListener("status", refresh);
    stream.onerror = () => stream.close(); // Polling also recovers reloads and interrupted streams.
    return () => stream.close();
  }, [job?.id, job?.state, saved.id, client]);
  async function command(cancel = false) {
    setBusy(true);
    setError(undefined);
    try {
      if (cancel && job) {
        await api(`/jobs/${job.id}/cancel`, { method: "POST", body: "{}" });
      } else {
        pending.current ??= crypto.randomUUID();
        await api(`/requests/${saved.id}/inspections`, {
          method: "POST",
          headers: { "If-Match": `"${saved.version}"`, "Idempotency-Key": pending.current },
          body: JSON.stringify({ current_version: saved.version, public_scope_seen: ack }),
        });
        pending.current = null;
      }
      await query.refetch();
    } catch (failure) { setError(failure); }
    finally { setBusy(false); }
  }
  return <section className="inspection-control" aria-label={copy("request.inspect")}>
    <p className="help">{copy("inspection.disclosure")}</p>
    {!running && <label className="check-label">
      <input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />
      <span>{copy("inspection.ack")}</span>
    </label>}
    <ErrorNotice error={error ?? query.error} retry={() => void query.refetch()} />
    {job && <div role="status" aria-live="polite" className="notice neutral">
      <strong>{copy(`inspection.${job.state}`)}</strong>
      <p className="small">{copy("request.version")} {job.request_version} · {timestamp(job.created_at)}</p>
      {job.failure_code && <p className="small">{job.failure_code}</p>}
      {job.state === "succeeded" && <p>{copy("inspection.reviewNext")}</p>}
    </div>}
    {running ? <button type="button" disabled={busy || job?.state === "cancelling"}
      onClick={() => void command(true)}>{copy("inspection.cancel")}</button>
      : <button className="primary" type="button"
        disabled={busy || dirty || !ack || !query.data?.enabled || query.data.request_version !== saved.version}
        onClick={() => void command()}>{copy(busy ? "common.loading" : "request.inspect")}</button>}
    {dirty ? <p className="help">{copy("inspection.saveFirst")}</p>
      : query.data?.reason ? <p className="help">{copy(`inspection.reason.${query.data.reason}`)}</p> : null}
  </section>;
}
