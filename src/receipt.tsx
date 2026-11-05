import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, copy, timestamp, type Capture, type Receipt, type ReleaseAttempt } from "./api";
import { useSession } from "./pages";
import { ErrorNotice } from "./ui";
import { blockerText } from "./decision";

export function ReceiptPage() {
  const { receiptId } = useParams();
  const session = useSession();
  const receipt = useQuery({ queryKey: ["receipt", session.user.id, receiptId], queryFn: () => api<Receipt>(`/releases/${receiptId}`) });
  useEffect(() => { document.title = copy("receipt.title"); }, []);
  return <main id="main" className="document receipt-document"><span className="eyebrow">Latch</span><h1>{copy("receipt.heading")}</h1><ErrorNotice error={receipt.error} retry={() => void receipt.refetch()} />{receipt.isPending ? <p role="status">{copy("common.loading")}</p> : null}{receipt.data ? <>
    <p className="lede">{copy("receipt.scope")}</p><p>{copy("receipt.committed")} <time dateTime={receipt.data.committed_at}>{timestamp(receipt.data.committed_at)}</time> / {copy("request.version")} {receipt.data.request_version}</p>
    <ReceiptContent record={receipt.data.record as Record<string, unknown>} />
    <dl><dt>{copy("receipt.hash")}</dt><dd className="receipt-hash">{receipt.data.record_hash}</dd></dl>
    <div className="receipt-downloads">{(["zip", "pdf", "json"] as const).map((format) => <a key={format} className={format === "zip" ? "primary" : "text-button"} href={`/api/v1/releases/${receiptId}/exports/${format}`} download>{copy(format === "zip" ? "receipt.download" : `receipt.${format}`)}</a>)}</div><p><Link to={`/requests/${receipt.data.request_id}/compare`}>{copy("decision.open")}</Link></p>
  </> : null}</main>;
}

type PrintedSource = { label: string; source_id: string; basket: { complete_total_cents: number | null; feasible: boolean } };
type PrintedFresh = { source_id: string; pages: { artifact_id: string; source_url: string; started_at: string; completed_at: string }[] };
function ReceiptContent({ record }: { record: Record<string, unknown> }) {
  const worksheet = record.worksheet as { name: string; budget_cents: number; required_by: string; items: { key: string; specification: string; required_units: number }[] };
  const packet = record.approved_packet as { comparison: { sources: PrintedSource[] }; requester: { display_name: string }; approved_at: string; selection_id: string; selected_source_id: string };
  const sources = record.fresh_sources as PrintedFresh[];
  const dollars = (cents: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
  return <><h2>{worksheet.name}</h2><dl className="comparison-totals"><div><dt>{copy("request.budget")}</dt><dd>{dollars(worksheet.budget_cents)}</dd></div><div><dt>{copy("request.requiredBy")}</dt><dd>{timestamp(worksheet.required_by)}</dd></div></dl><ul>{worksheet.items.map((item) => <li key={item.key}>{item.required_units} / {item.specification}</li>)}</ul><h2>{copy("decision.approval")}</h2><p>{packet.requester.display_name} / {timestamp(packet.approved_at)}</p><h2>{copy("decision.heading")}</h2>{packet.comparison.sources.map((source) => <p key={source.source_id}>{source.label}{source.source_id === packet.selected_source_id ? ` / ${copy("decision.selected")}` : ""} / {source.basket.complete_total_cents === null ? copy("offer.unknown") : dollars(source.basket.complete_total_cents)}</p>)}<h2>{copy("receipt.sources")}</h2>{sources.map((source) => <ul key={source.source_id}>{source.pages.map((page) => <li key={page.artifact_id}><a href={page.source_url} target="_blank" rel="noreferrer">{page.source_url}</a><p className="small muted"><time dateTime={page.started_at}>{timestamp(page.started_at)}</time> / <time dateTime={page.completed_at}>{timestamp(page.completed_at)}</time></p></li>)}</ul>)}</>;
}

export function SourceChanges() {
  const { id, attemptId } = useParams();
  const session = useSession();
  const attempt = useQuery({ queryKey: ["release-attempt", session.user.id, attemptId], queryFn: () => api<ReleaseAttempt>(`/release-attempts/${attemptId}`) });
  useEffect(() => { document.title = copy("changes.title"); }, []);
  return <main id="main" className="document changes-document"><span className="eyebrow">Latch</span><h1>{copy("changes.heading")}</h1><p className="lede">{copy("decision.sourceChanged")}</p><ErrorNotice error={attempt.error} retry={() => void attempt.refetch()} />{attempt.data?.reason ? <p className="notice">{blockerText(attempt.data.reason)}</p> : null}<p>{copy("decision.loadChanges")}</p>{attempt.data?.differences.map((diff) => <section className="source-diff" key={diff.source_id}><h2>{diff.text_changed ? copy("changes.text") : diff.raster_changed ? copy("changes.raster") : copy("changes.none")}</h2><pre className="text-diff">{diff.text_diff.join("\n")}</pre><div className="capture-diff"><DiffCapture id={diff.old_capture_id} heading={copy("changes.old")} /><DiffCapture id={diff.new_capture_id} heading={copy("changes.new")} /></div></section>)}<Link className="text-button" to={`/requests/${id}/compare`}>{copy("decision.open")}</Link></main>;
}

function DiffCapture({ id, heading }: { id: string; heading: string }) {
  const session = useSession();
  const [images, setImages] = useState(false);
  const capture = useQuery({ queryKey: ["capture", session.user.id, id], queryFn: () => api<Capture>(`/captures/${id}`) });
  return <section><h3>{heading}</h3><ErrorNotice error={capture.error} retry={() => void capture.refetch()} />{capture.data ? <><button onClick={() => setImages(!images)} aria-pressed={images}>{copy("review.loadImage")}</button>{capture.data.pages.map((page) => <div className="diff-page" key={page.artifact_id}><p><a href={page.source_url} target="_blank" rel="noreferrer">{page.source_url}</a></p><p className="small muted">{timestamp(page.started_at)} / {timestamp(page.completed_at)}</p><pre className="source-text">{page.source_text}</pre>{images ? <img src={`/api/v1/artifacts/${page.artifact_id}`} alt={copy("changes.imageAlt")} loading="lazy" /> : null}</div>)}</> : null}</section>;
}
