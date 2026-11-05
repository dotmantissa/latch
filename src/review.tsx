import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router";
import { Check, CircleHelp, ExternalLink, X } from "lucide-react";
import { api, ApiFailure, copy, timestamp, type Capture, type ReviewField, type ReviewInput, type ReviewPage, type ReviewRecord, type SavedRequest, type SourceReview } from "./api";
import { useSession } from "./pages";
import { ErrorNotice } from "./ui";
import { correctedValue, editableValue, fieldValue, isBoolean, isMoney, sourceSlices } from "./review-values";

const fieldKey = (field: ReviewField) => `${field.original.item_key ?? "terms"}:${field.original.kind}`;
const quotesFrom = (field: ReviewField) => field.original.spans.map(({ page_index, quote }) => ({ page_index, quote }));
const itemLabel = (saved: SavedRequest, key: string | null) => key === null ? copy("review.terms") : saved.worksheet.items.find((item) => item.key === key)?.public_specification ?? key;
const sourceName = (saved: SavedRequest, capture: Capture) => saved.worksheet.sources?.find((source) => source.url === capture.pages[0]?.source_url)?.label ?? capture.pages[0]?.source_url ?? copy("request.source");

export function EvidenceReview() {
  const { id } = useParams();
  const [search, setSearch] = useSearchParams();
  const version = search.get("version");
  const session = useSession();
  const request = useQuery({
    queryKey: ["request", session.user.id, id, version],
    queryFn: () => api<SavedRequest>(`/requests/${id}${version ? `?version=${encodeURIComponent(version)}` : ""}`),
  });
  const captures = useQuery({
    queryKey: ["evidence", session.user.id, id, request.data?.version],
    queryFn: () => api<Capture[]>(`/requests/${id}/evidence?version=${request.data!.version}`),
    enabled: Boolean(request.data),
  });
  const selected = captures.data?.find((capture) => capture.id === search.get("capture")) ?? captures.data?.[0];
  return <main id="main" className="document review-document">
    <div className="page-heading">
      <div><span className="eyebrow">{request.data?.reference ?? copy("review.open")}</span><h1>{request.data?.worksheet.name ?? copy("review.heading")}</h1><p className="lede">{copy("review.intro")}</p>
        {request.data ? <p className="small muted">{copy("request.version")} {request.data.version} / {request.data.owner.display_name} / <time title={request.data.saved_at} dateTime={request.data.saved_at}>{timestamp(request.data.saved_at)}</time></p> : null}
      </div>
      <Link className="text-button" to={`/requests/${id}${version ? `?version=${encodeURIComponent(version)}` : ""}`}>{copy("request.edit")}</Link>
    </div>
    <ErrorNotice error={request.error ?? captures.error} retry={() => { void request.refetch(); void captures.refetch(); }} />
    {request.isPending || (request.data && captures.isPending) ? <p className="review-padding" role="status">{copy("common.loading")}</p> : null}
    {captures.data?.length === 0 ? <div className="review-empty"><h2>{copy("review.empty")}</h2><p>{copy("review.emptyBody")}</p></div> : null}
    {request.data && selected ? <>
      <nav className="source-tabs" aria-label={copy("review.sources")}>{captures.data!.map((capture) => <button key={capture.id} aria-pressed={capture.id === selected.id} onClick={() => setSearch((old) => { const next = new URLSearchParams(old); next.set("capture", capture.id); return next; })}>{sourceName(request.data!, capture)}</button>)}</nav>
      {selected.extraction && selected.extraction_id ? <SourceWorkbench key={selected.id} saved={request.data} capture={selected} extractionId={selected.extraction_id} /> : <div className="review-padding"><p>{copy("review.noExtraction")}</p><SourcePages capture={selected} spans={[]} /></div>}
    </> : null}
  </main>;
}

function SourceWorkbench({ saved, capture, extractionId }: { saved: SavedRequest; capture: Capture; extractionId: string }) {
  const session = useSession();
  const client = useQueryClient();
  const queryKey = ["source-review", session.user.id, extractionId];
  const review = useQuery({ queryKey, queryFn: () => api<SourceReview>(`/extractions/${extractionId}/review`) });
  const [selected, setSelected] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const opener = useRef<HTMLButtonElement | null>(null);
  const active = review.data?.fields.find((field) => fieldKey(field) === selected);
  function close() { setSelected(null); requestAnimationFrame(() => opener.current?.focus()); }
  async function savedDecision() {
    setNotice(copy("review.saved"));
    // Never claim checked or recompute a total until a fresh server view arrives.
    await Promise.allSettled([
      client.invalidateQueries({ queryKey }),
      client.invalidateQueries({ queryKey: ["review-history", session.user.id, extractionId] }),
    ]);
    close();
  }
  const basket = review.data?.basket;
  return <>
    <div className="review-padding"><ErrorNotice error={review.error} retry={() => void review.refetch()} />
      <p className="small review-notice" role="status">{notice || (review.isPending ? copy("common.loading") : "")}</p>
      {review.data && !review.data.review_allowed ? <p className="notice">{copy(`review.blocker.${review.data.review_blocker}`)}</p> : null}
    </div>
    {review.data ? <div className={`review-stage${active ? " has-evidence" : ""}`}>
      <section className="review-ledger" aria-label={copy("review.fields")}>
        <h2>{copy("review.heading")}</h2>
        {Array.from(new Set(review.data.fields.map((field) => field.original.item_key))).map((key) => <section key={JSON.stringify(key)} className="term-group">
          <h3>{itemLabel(saved, key)}</h3>
          {review.data!.fields.filter((field) => field.original.item_key === key).map((field) => <button className="term-row" key={fieldKey(field)} aria-pressed={selected === fieldKey(field)} onClick={(event) => { opener.current = event.currentTarget; setSelected(fieldKey(field)); setNotice(""); }}>
            <span className="term-label">{copy(`review.field.${field.original.kind}`)}</span>
            <span className="term-value">{fieldValue(field.original.kind, field.value)}</span>
            <span className={`term-state ${field.state}`}>{field.state === "buyer_checked" ? <Check size={16} aria-hidden /> : <CircleHelp size={16} aria-hidden />}{copy(`review.state.${field.state}`)}</span>
          </button>)}
        </section>)}
        <History saved={saved} extractionId={extractionId} />
      </section>
      {active ? <EvidencePanel key={selected!} field={active} review={review.data} capture={capture} label={itemLabel(saved, active.original.item_key)} onClose={close} onSaved={savedDecision} onReload={async () => { const result = await review.refetch(); if (result.error) throw result.error; return result.data!; }} /> : null}
      <aside className="review-summary" aria-label={copy("request.summary")}>
        <h2>{copy("review.basket")}</h2>
        <p className="review-total">{basket?.complete_total_cents != null ? fieldValue("price_cents", basket.complete_total_cents) : copy("offer.unknown")}</p>
        <p>{copy("review.count").replace("{checked}", String(review.data.checked_fields)).replace("{total}", String(review.data.total_fields))}</p>
        <p className="muted">{copy(!basket ? "review.basketAbsent" : !basket.complete ? "review.basketIncomplete" : !basket.reviewed ? "review.basketUnreviewed" : !basket.feasible ? "review.basketUnfit" : "review.basketFits")}</p>
        <div className="latch-seam" aria-hidden><span /></div><p className="help">{copy("review.noApproval")}</p>
      </aside>
    </div> : null}
  </>;
}

function History({ saved, extractionId }: { saved: SavedRequest; extractionId: string }) {
  const [open, setOpen] = useState(false);
  const session = useSession();
  const history = useInfiniteQuery({
    queryKey: ["review-history", session.user.id, extractionId], enabled: open,
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) => api<ReviewPage>(`/extractions/${extractionId}/reviews?limit=25${pageParam == null ? "" : `&before=${pageParam}`}`),
    getNextPageParam: (page) => page.next_before ?? undefined,
  });
  return <section className="review-history"><button className="text-button" aria-expanded={open} aria-controls="review-history" onClick={() => setOpen(!open)}>{copy("review.history")}</button>
    {open ? <div id="review-history"><ErrorNotice error={history.error} retry={() => void history.refetch()} />
      {history.isPending ? <p role="status">{copy("common.loading")}</p> : null}
      {history.data?.pages[0].items.length === 0 ? <p>{copy("review.historyEmpty")}</p> : null}
      {history.data?.pages.flatMap((page) => page.items).map((record) => <article key={record.id} className="history-record"><h3>{itemLabel(saved, record.decision.item_key)} / {copy(`review.field.${record.decision.kind}`)}</h3><ReviewAttribution record={record} /></article>)}
      {history.hasNextPage ? <button disabled={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>{copy(history.isFetchingNextPage ? "common.loading" : "review.historyMore")}</button> : null}
    </div> : null}
  </section>;
}

function ReviewAttribution({ record }: { record: ReviewRecord }) {
  return <><p>{copy(`review.action.${record.decision.action}`)} / {fieldValue(record.decision.kind, record.decision.value)}</p>
    <p className="small muted">{record.reviewer.display_name} / <time title={record.created_at} dateTime={record.created_at}>{timestamp(record.created_at)}</time> / {copy("request.version")} {record.version}</p>
    {record.decision.reason ? <p className="source-quote">{record.decision.reason}</p> : null}
    {record.decision.spans.map((span, index) => <blockquote className="source-quote" key={index}><span className="small muted">{copy("review.page")} {span.page_index + 1}</span><br />{span.quote}</blockquote>)}
  </>;
}

function EvidencePanel({ field, review, capture, label, onClose, onSaved, onReload }: {
  field: ReviewField; review: SourceReview; capture: Capture; label: string;
  onClose: () => void; onSaved: () => Promise<void>; onReload: () => Promise<SourceReview>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const errorFocus = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [action, setAction] = useState<ReviewInput["action"]>(field.original.state === "supported" ? "confirm" : "correct");
  const [value, setValue] = useState(editableValue(field.original.kind, field.value));
  const [quotes, setQuotes] = useState(quotesFrom(field));
  const [reason, setReason] = useState("");
  const [seen, setSeen] = useState(false);
  const [error, setError] = useState<unknown>();
  const [localError, setLocalError] = useState("");
  const [conflict, setConflict] = useState(false);
  const expectedRevision = useRef(review.review_version);
  const intent = useRef<{ body: string; key: string } | null>(null);
  useEffect(() => {
    const media = matchMedia("(max-width: 1023px)");
    const element = dialog.current!;
    const open = () => { element.close(); if (media.matches) element.showModal(); else element.show(); heading.current?.focus(); };
    open(); media.addEventListener("change", open);
    return () => { media.removeEventListener("change", open); element.close(); };
  }, []);
  useEffect(() => { if (localError) errorFocus.current?.focus(); }, [localError]);
  useEffect(() => {
    if (review.review_version !== expectedRevision.current && !busyRef.current) setConflict(true);
  }, [review.review_version]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busyRef.current || conflict || !review.review_allowed) return;
    setError(undefined); setLocalError("");
    let corrected: unknown = null;
    try {
      if (!seen) throw new Error(copy("review.acknowledgeInvalid"));
      if (action !== "confirm" && reason.trim().length < 3) throw new Error(copy("review.reasonInvalid"));
      if (action === "correct") {
        corrected = correctedValue(field.original.kind, value);
        if (quotes.length === 0 || quotes.some((quote) => {
          const text = capture.pages.find((page) => page.page_index === quote.page_index)?.source_text;
          return !quote.quote || !text || text.split(quote.quote).length !== 2;
        })) throw new Error(copy("review.quoteInvalid"));
      }
    } catch (failure) { setLocalError((failure as Error).message); return; }
    const body: ReviewInput = {
      request_version: review.request_version, expected_review_version: expectedRevision.current,
      proposal_hash: capture.extraction!.proposal_hash, item_key: field.original.item_key, kind: field.original.kind,
      action, corrected_value: corrected, evidence: action === "confirm" ? quotesFrom(field) : action === "correct" ? quotes : [],
      reason: action === "confirm" ? null : reason.trim(), evidence_seen: seen,
    };
    const serialized = JSON.stringify(body);
    if (intent.current?.body !== serialized) intent.current = { body: serialized, key: crypto.randomUUID() };
    busyRef.current = true; setBusy(true);
    try {
      await api<ReviewRecord>(`/extractions/${review.extraction_id}/reviews`, { method: "POST", body: serialized, headers: { "If-Match": `"${expectedRevision.current}"`, "Idempotency-Key": intent.current.key } });
      await onSaved();
    } catch (failure) { setError(failure); if (failure instanceof ApiFailure && (failure.status === 412 || failure.status === 409 || failure.code === "SOURCE_PROFILE_EXPIRED")) setConflict(true); }
    finally { busyRef.current = false; setBusy(false); }
  }
  return <dialog className="evidence-panel" ref={dialog} aria-labelledby="evidence-heading" onKeyDown={(event) => {
    if (event.key !== "Tab" || !dialog.current?.matches(":modal")) return;
    const controls = Array.from(dialog.current.querySelectorAll<HTMLElement>("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])")).filter((control) => !control.matches(":disabled") && control.getClientRects().length > 0);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === heading.current)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }} onCancel={(event) => { event.preventDefault(); if (!busyRef.current) onClose(); }}>
    <header className="evidence-heading"><div><span className="eyebrow">{label}</span><h2 id="evidence-heading" tabIndex={-1} ref={heading}>{copy(`review.field.${field.original.kind}`)}</h2></div><button type="button" disabled={busy} onClick={onClose}><X size={18} aria-hidden /><span>{copy("common.back")}</span></button></header>
    <div className="evidence-body">
      <section className="original-field"><h3>{copy("review.currentValue")}</h3><p>{fieldValue(field.original.kind, field.value)} / {copy(`review.state.${field.state}`)}</p><h3>{copy("review.original")}</h3><p>{fieldValue(field.original.kind, field.original.value)} / {copy(`review.original.${field.original.state}`)}</p>
        {field.original.reason ? <p className="help">{copy(`review.reason.${field.original.reason}`)}</p> : null}
        {field.original.spans.length === 0 ? <p className="help">{copy("review.noQuotes")}</p> : null}
        {field.latest_review ? <ReviewAttribution record={field.latest_review} /> : null}
      </section>
      <SourcePages capture={capture} spans={[...field.original.spans, ...(field.latest_review?.decision.spans ?? [])]} />
      <ErrorNotice error={error} />
      {localError ? <div className="notice error" ref={errorFocus} tabIndex={-1} role="alert">{localError}</div> : null}
      {!review.review_allowed || conflict ? <div className="notice"><p>{copy(conflict ? "review.conflict" : `review.blocker.${review.review_blocker}`)}</p><button type="button" disabled={busy} onClick={async () => { if (busyRef.current) return; busyRef.current = true; setBusy(true); try { const latest = await onReload(); expectedRevision.current = latest.review_version; const refreshedField = latest.fields.find((candidate) => fieldKey(candidate) === fieldKey(field)); if (refreshedField) setValue(editableValue(field.original.kind, refreshedField.value)); setReason(""); setConflict(false); setError(undefined); setLocalError(""); setSeen(false); intent.current = null; } catch (failure) { setError(failure); } finally { busyRef.current = false; setBusy(false); } }}>{copy("review.reload")}</button></div> : null}
      <form onSubmit={submit} className="field-review-form">
        <fieldset disabled={busy || conflict || !review.review_allowed}><legend>{copy("review.heading")}</legend>
          <div className="review-actions">{(["confirm", "correct", "dispute"] as const).map((choice) => <button key={choice} type="button" disabled={choice === "confirm" && field.original.state !== "supported"} aria-pressed={action === choice} onClick={() => { setAction(choice); setSeen(false); setLocalError(""); }}>{copy(choice === "confirm" ? "review.confirm" : choice === "correct" ? "review.correct" : "review.unclear")}</button>)}</div>
          {action === "correct" ? <>
            <label htmlFor="corrected-value">{copy("review.corrected")}</label>{field.original.kind === "coverage" || isBoolean(field.original.kind) ? <select id="corrected-value" value={value} required onChange={(event) => setValue(event.target.value)}><option value="">{copy("offer.unknown")}</option>{(field.original.kind === "coverage" ? [["quoted", "review.quoted"], ["excluded", "review.excluded"]] : [["true", "review.yes"], ["false", "review.no"]]).map(([val, key]) => <option key={val} value={val}>{copy(key)}</option>)}</select> : <input id="corrected-value" value={value} required maxLength={64} inputMode={isMoney(field.original.kind) ? "decimal" : field.original.kind === "latest_arrival" ? "text" : "numeric"} aria-describedby="value-help" onChange={(event) => setValue(event.target.value)} />}
            <p id="value-help" className="help">{copy(isMoney(field.original.kind) ? "review.moneyHelp" : field.original.kind === "latest_arrival" ? "review.arrivalHelp" : isBoolean(field.original.kind) || field.original.kind === "coverage" ? "review.choiceHelp" : "review.integerHelp")}</p>
            <fieldset className="quote-editor"><legend>{copy("review.quotes")}</legend><p className="help">{copy("review.quoteHelp")}</p>
              {quotes.map((quote, index) => <div className="quote-entry" key={index}><label htmlFor={`quote-page-${index}`}>{copy("review.page")} {index + 1}</label><select id={`quote-page-${index}`} value={quote.page_index} onChange={(event) => setQuotes(quotes.map((current, i) => i === index ? { ...current, page_index: Number(event.target.value) } : current))}>{capture.pages.map((page) => <option key={page.page_index} value={page.page_index}>{copy("review.page")} {page.page_index + 1}</option>)}</select><label htmlFor={`quote-text-${index}`}>{copy("review.quote")} {index + 1}</label><textarea id={`quote-text-${index}`} required value={quote.quote} maxLength={1000} rows={3} onChange={(event) => setQuotes(quotes.map((current, i) => i === index ? { ...current, quote: event.target.value } : current))} /><button className="text-button" type="button" onClick={() => setQuotes(quotes.filter((_, i) => i !== index))}>{copy("review.removeQuote")} {index + 1}</button></div>)}
              <button type="button" disabled={quotes.length >= 4} onClick={() => setQuotes([...quotes, { page_index: 0, quote: "" }])}>{copy("review.addQuote")}</button>
            </fieldset>
          </> : <p className="help">{copy(action === "confirm" ? "review.confirmHelp" : "review.disputeHelp")}</p>}
          {action !== "confirm" ? <><label htmlFor="review-reason">{copy("review.reasonLabel")}</label><textarea id="review-reason" value={reason} required minLength={3} maxLength={1000} rows={3} onChange={(event) => setReason(event.target.value)} /></> : null}
          <label className="evidence-ack"><input type="checkbox" checked={seen} onChange={(event) => setSeen(event.target.checked)} />{copy("review.acknowledge")}</label>
          <p className="help">{copy("review.attribution")}</p><button type="submit" className="primary">{copy(busy ? "review.saving" : "review.submit")}</button>
        </fieldset>
      </form>
    </div>
  </dialog>;
}

function SourcePages({ capture, spans }: { capture: Capture; spans: ReviewField["original"]["spans"] }) {
  return <section className="source-pages" aria-label={copy("review.source")}>{capture.pages.map((page) => <CapturedPage key={page.artifact_id} page={page} spans={spans.filter((span) => span.page_index === page.page_index)} />)}</section>;
}
function CapturedPage({ page, spans }: { page: Capture["pages"][number]; spans: ReviewField["original"]["spans"] }) {
  const [loaded, setLoaded] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const [zoom, setZoom] = useState("fit");
  const zoomId = useId();
  const firstMark = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const mark = firstMark.current;
      const box = mark?.closest<HTMLElement>(".captured-text");
      if (mark && box) box.scrollTop += mark.getBoundingClientRect().top - box.getBoundingClientRect().top - 16;
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  const publicUrl = (() => { try { const url = new URL(page.source_url); return url.protocol === "https:" && !url.username && !url.password ? url.href : null; } catch { return null; } })();
  return <article className="captured-page"><h3>{copy("review.page")} {page.page_index + 1}</h3>
    {publicUrl ? <a className="source-link text-button" href={publicUrl} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer"><ExternalLink size={16} aria-hidden />{copy("common.openSource")}<span className="source-url">{page.source_url}</span></a> : <p className="source-quote">{page.source_url}</p>}
    <p className="small muted">{copy("common.checkTime")} / <time dateTime={page.completed_at} title={`${page.started_at} / ${page.completed_at}`}>{timestamp(page.completed_at)}</time></p>
    <h3>{copy("review.text")}</h3><div className="captured-text" tabIndex={0} aria-label={copy("review.text")}>{sourceSlices(page.source_text, spans).map((slice, index) => slice.marked ? <mark key={index} ref={(element) => { if (element && !firstMark.current) firstMark.current = element; }}>{slice.text}</mark> : slice.text)}</div>
    <h3>{copy("review.image")}</h3><p className="help">{copy("review.imageHelp")}</p>
    {imageFailed ? <p role="alert">{copy("review.imageUnavailable")}</p> : null}
    {!loaded || imageFailed ? <button type="button" onClick={() => { setImageFailed(false); setLoaded(true); }}>{copy(imageFailed ? "common.retry" : "review.loadImage")}</button> : null}
    {loaded && !imageFailed ? <><div className="zoom-control"><label htmlFor={zoomId}>{copy("review.zoom")}</label><select id={zoomId} value={zoom} onChange={(event) => setZoom(event.target.value)}><option value="fit">{copy("review.fit")}</option><option value="actual">{copy("review.actual")}</option><option value="double">{copy("review.double")}</option></select></div>
      <div className="capture-image-scroll" tabIndex={0} aria-label={copy("review.image")}><img src={`/api/v1/artifacts/${page.artifact_id}`} alt={copy("review.imageAlt")} width={zoom === "fit" ? page.width : page.width * (zoom === "double" ? 2 : 1)} height={zoom === "fit" ? page.height : page.height * (zoom === "double" ? 2 : 1)} className={zoom === "fit" ? "fit-image" : "sized-image"} onError={() => { setImageFailed(true); setLoaded(false); }} /></div>
    </> : null}
  </article>;
}
