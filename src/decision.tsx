import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, ApiFailure, copy, timestamp, type Decision, type ReleaseAttempt, type SavedRequest } from "./api";
import { useSession } from "./pages";
import { fieldValue } from "./review-values";
import { ErrorNotice } from "./ui";

export function blockerText(reason: string) {
  const code = reason.split(":").at(-1)!;
  const value = copy(`block.${code}`);
  return value === copy("error.generic") ? copy("decision.blocked") : value;
}

export function DecisionWorkbench() {
  const { id } = useParams();
  const session = useSession();
  return <RequestDecision key={`${session.user.id}:${id}`} id={id} />;
}

function RequestDecision({ id }: { id: string | undefined }) {
  const session = useSession();
  const client = useQueryClient();
  const queryKey = ["decision", session.user.id, id];
  const saved = useQuery({ queryKey: ["request", session.user.id, id, null], queryFn: () => api<SavedRequest>(`/requests/${id}`) });
  const decision = useQuery({ queryKey, queryFn: () => api<Decision>(`/requests/${id}/decision`), refetchInterval: 15000 });
  const attempts = useQuery({ queryKey: ["release-history", session.user.id, id], queryFn: () => api<ReleaseAttempt[]>(`/requests/${id}/release-attempts`) });
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const activeId = attemptId ?? attempts.data?.[0]?.id;
  const attempt = useQuery({ queryKey: ["release-attempt", session.user.id, activeId], queryFn: () => api<ReleaseAttempt>(`/release-attempts/${activeId}`), enabled: Boolean(activeId), refetchInterval: (query) => ["queued", "running"].includes(query.state.data?.state ?? "") ? 3000 : false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState("");
  const [approving, setApproving] = useState(false);
  const [releaseSeen, setReleaseSeen] = useState(false);
  const intent = useRef<{ body: string; path: string; key: string } | null>(null);
  const busyRef = useRef(false);
  const opener = useRef<HTMLButtonElement | null>(null);
  const c = decision.data?.comparison;
  const selection = decision.data?.selection;
  const approval = decision.data?.approval;
  const chosen = c?.sources.find((source) => source.source_id === selection?.source_id);
  const pending = attempt.data?.state === "queued" || attempt.data?.state === "running";
  const released = Boolean(attempt.data?.receipt_id && attempt.data.request_version === saved.data?.version);
  const version = saved.data?.version;
  useEffect(() => { document.title = copy("decision.title"); }, []);
  async function refresh() {
    await Promise.allSettled([decision.refetch(), attempts.refetch(), attempt.refetch(), saved.refetch()]);
  }
  async function command<T>(path: string, body: object): Promise<T | undefined> {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(undefined); setNotice("");
    const serialized = JSON.stringify(body);
    if (intent.current?.body !== serialized || intent.current.path !== path) intent.current = { body: serialized, path, key: crypto.randomUUID() };
    try {
      const result = await api<T>(path, { method: "POST", body: serialized, headers: { "If-Match": `"${version}"`, "Idempotency-Key": intent.current.key } });
      intent.current = null;
      await client.invalidateQueries({ queryKey });
      await client.invalidateQueries({ queryKey: ["release-history", session.user.id, id] });
      setNotice(copy("decision.saved"));
      return result;
    } catch (failure) { setError(failure); return undefined; }
    finally { busyRef.current = false; setBusy(false); }
  }
  function closeApproval() { setApproving(false); requestAnimationFrame(() => opener.current?.focus()); }
  async function approve(scopeSeen: boolean) {
    if (!c || !selection) return;
    const result = await command(`/requests/${id}/approvals`, { request_version: version, selection_id: selection.id, comparison_hash: c.packet_hash, scope_seen: scopeSeen });
    if (result) closeApproval();
  }
  async function release() {
    if (!approval) return;
    const result = await command<ReleaseAttempt>(`/requests/${id}/release-attempts`, { request_version: version, approval_id: approval.id, approval_hash: approval.packet_hash, scope_seen: releaseSeen });
    if (result) { setAttemptId(result.id); setReleaseSeen(false); }
  }
  async function cancel() {
    if (!attempt.data) return;
    await command(`/release-attempts/${attempt.data.id}/cancel`, {});
    await attempt.refetch();
  }
  const errorValue = error ?? saved.error ?? decision.error ?? attempts.error ?? attempt.error;
  return <main id="main" className="document decision-document">
    <div className="page-heading"><div><span className="eyebrow">{saved.data?.reference ?? copy("decision.heading")}</span><h1>{saved.data?.worksheet.name ?? copy("decision.heading")}</h1><p className="lede">{copy("decision.intro")}</p>{version ? <p className="small muted">{copy("request.version")} {version}</p> : null}</div><Link className="text-button" to={`/requests/${id}/evidence`}>{copy("review.open")}</Link></div>
    <ErrorNotice error={errorValue} retry={() => void refresh()} />
    {error instanceof ApiFailure && error.code === "REAUTH_REQUIRED" ? <p><Link to="/settings">{copy("decision.reauth")}</Link></p> : null}
    <p role="status" className="small review-notice">{busy ? copy("decision.busy") : notice}</p>
    <div className="decision-stage"><section className="decision-ledger" aria-label={copy("decision.heading")}>
      <div className="decision-tools"><h2>{copy("decision.heading")}</h2><button disabled={busy || pending || released || !version || saved.data?.status === "archived"} onClick={() => void command(`/requests/${id}/comparisons`, { request_version: version })}>{copy("decision.compare")}</button></div>
      {!c ? <div className="review-empty"><h3>{copy("decision.empty")}</h3><p>{copy("decision.emptyBody")}</p></div> : <>
        {!c.current ? <p className="notice">{copy("decision.changed")}</p> : null}
        {c.blockers.map((reason) => <p className="help" key={reason}>{blockerText(reason)}</p>)}
        {c.sources.map((source) => <article className="compared-source" key={source.source_id}>
          <div className="decision-source-heading"><h3>{source.label}{source.rank ? <span className="small muted"> / {copy("decision.rank")} {source.rank}</span> : null}</h3><Link to={`/requests/${id}/evidence?capture=${source.capture_id}`}>{copy("decision.source")}</Link></div>
          <dl className="comparison-totals"><div><dt>{copy("decision.subtotal")}</dt><dd>{source.basket.lines.some((line) => line.extended_cents != null) ? fieldValue("price_cents", source.basket.quoted_subtotal_cents) : copy("offer.unknown")}</dd></div><div><dt>{copy("decision.total")}</dt><dd className="review-total">{source.basket.complete_total_cents === null ? copy("offer.unknown") : fieldValue("price_cents", source.basket.complete_total_cents)}</dd></div></dl>
          <div className="comparison-table-wrap" tabIndex={0} role="region" aria-label={copy("decision.basis")}><table><caption>{copy("decision.basis")}</caption><thead><tr><th>{copy("request.item")}</th><th>{copy("decision.quantity")}</th><th>{copy("decision.delivered")}</th><th>{copy("decision.extended")}</th></tr></thead><tbody>{source.basket.lines.map((line, i) => <tr key={i}><th scope="row">{saved.data?.worksheet.items.find((item) => item.key === line.item_key)?.public_specification ?? line.item_key}</th><td>{line.sell_units ?? copy("offer.unknown")}</td><td>{line.delivered_units ?? copy("offer.unknown")}</td><td>{line.extended_cents == null ? copy("offer.unknown") : fieldValue("price_cents", line.extended_cents)}</td></tr>)}</tbody></table></div>
          <ul className="decision-reasons">{[...source.blockers, ...source.basket.reasons].map((reason) => <li key={reason}>{blockerText(reason)}</li>)}</ul>
          <button aria-pressed={selection?.source_id === source.source_id && selection.current} disabled={busy || pending || released || !c.current || !source.selectable} onClick={() => void command(`/requests/${id}/selections`, { request_version: version, comparison_id: c.id, comparison_hash: c.packet_hash, source_id: source.source_id, expected_revision: selection?.revision ?? 0 })}>{selection?.source_id === source.source_id && selection.current ? copy("decision.selected") : copy("decision.choose")}</button>
        </article>)}
        {c.current && !c.sources.some((source) => source.selectable) ? <p className="notice">{copy("decision.none")}</p> : null}
      </>}
    </section><aside className="decision-summary" aria-label={copy("decision.summary")}>
      <h2>{copy("decision.summary")}</h2><p>{copy("decision.scope")}</p><p className="small muted">{copy("decision.freshness")}</p>
      {chosen && selection?.current ? <><h3>{chosen.label}</h3><p className="review-total">{fieldValue("price_cents", chosen.basket.complete_total_cents)}</p></> : <p>{copy("decision.none")}</p>}
      <div className={`latch-seam${approval?.state === "active" ? " approved" : ""}`} aria-hidden><span /></div>
      {approval ? <div className="approval-attribution"><h3>{copy(approval.state === "active" ? "decision.approval" : "decision.earlier")}</h3><p>{approval.requester.display_name} / {copy(`decision.${approval.state}`)}</p><p className="small"><time dateTime={approval.created_at}>{timestamp(approval.created_at)}</time></p><p className="small">{copy("decision.expires")} <time dateTime={approval.expires_at}>{timestamp(approval.expires_at)}</time></p>{approval.state === "active" ? <button disabled={busy || pending} onClick={() => void command(`/approvals/${approval.id}/revoke`, {})}>{copy("decision.revoke")}</button> : null}</div> : null}
      {released ? <Link className="primary" to={`/releases/${attempt.data!.receipt_id}`}>{copy("decision.record")}</Link> : !approval || approval.state !== "active" ? <button className="primary" disabled={busy || pending || !selection?.current || !c?.current} onClick={(event) => { opener.current = event.currentTarget; setApproving(true); }}>{copy("decision.approve")}</button> : <><label className="decision-ack"><input type="checkbox" checked={releaseSeen} onChange={(event) => setReleaseSeen(event.target.checked)} disabled={busy || pending} />{copy("decision.releaseAck")}</label><button className="primary" disabled={busy || pending || !releaseSeen || Date.now() >= Date.parse(approval.expires_at)} onClick={() => void release()}>{copy("decision.release")}</button></>}
      {attempt.data ? <div className="recheck-state" role="status"><p>{copy(`decision.${attempt.data.state === "released" ? "record" : attempt.data.state === "changed" ? "sourceChanged" : attempt.data.state}`)}</p>{attempt.data.reason ? <p className="help">{blockerText(attempt.data.reason)}</p> : null}{pending ? <button disabled={busy} onClick={() => void cancel()}>{copy("decision.cancel")}</button> : null}{attempt.data.state === "changed" ? <><Link to={`/requests/${id}/changes/${attempt.data.id}`}>{copy("decision.changes")}</Link><p className="help">{copy("decision.loadChanges")}</p></> : null}{attempt.data.receipt_id ? <Link className="primary" to={`/releases/${attempt.data.receipt_id}`}>{copy("decision.record")}</Link> : null}</div> : null}
    </aside></div>
    {approving && chosen && c && selection && saved.data ? <ApprovalDialog label={chosen.label} total={chosen.basket.complete_total_cents} saved={saved.data} version={version!} busy={busy} error={error} onClose={closeApproval} onApprove={approve} /> : null}
  </main>;
}

function ApprovalDialog({ label, total, saved, version, busy, error, onClose, onApprove }: { label: string; total: number | null; saved: SavedRequest; version: number; busy: boolean; error: unknown; onClose: () => void; onApprove: (seen: boolean) => Promise<void> }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close(); }, []);
  function submit(event: FormEvent) { event.preventDefault(); if (seen) void onApprove(seen); }
  return <dialog ref={dialog} className="approval-dialog" aria-labelledby="approval-heading" onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}><form onSubmit={submit}><h2 id="approval-heading">{copy("decision.approveHeading")}</h2><ErrorNotice error={error} /><p>{copy("request.version")} {version} / {label}</p><p className="review-total">{fieldValue("price_cents", total)}</p><p>{copy("request.budget")} {saved.worksheet.budget} USD / {copy("request.requiredBy")} {timestamp(saved.worksheet.required_by)}</p><ul>{saved.worksheet.items.map((item) => <li key={item.key}>{item.required_units} / {item.specification}</li>)}</ul><p>{copy("decision.scope")}</p><label className="decision-ack"><input type="checkbox" checked={seen} onChange={(event) => setSeen(event.target.checked)} disabled={busy} required />{copy("decision.ack")}</label><div className="dialog-actions"><button type="button" disabled={busy} onClick={onClose}>{copy("common.cancel")}</button><button className="primary" disabled={busy || !seen}>{copy(busy ? "decision.busy" : "decision.approve")}</button></div></form></dialog>;
}
