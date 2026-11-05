import { copy, type ReviewInput } from "./api";

type Kind = ReviewInput["kind"];
export const isMoney = (kind: Kind) => kind === "price_cents" || kind === "shipping_cents";
export const isBoolean = (kind: Kind) => ["exact_match", "tax_included", "conditions_satisfied"].includes(kind);
export function fieldValue(kind: Kind, value: unknown): string {
  if (value == null) return copy("offer.unknown");
  if (typeof value === "boolean") return copy(value ? "review.yes" : "review.no");
  if (kind === "coverage") return copy(value === "quoted" ? "review.quoted" : "review.excluded");
  if (isMoney(kind) && typeof value === "number") return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value / 100);
  return String(value);
}
export function editableValue(kind: Kind, value: unknown): string {
  if (value == null) return "";
  if (isMoney(kind) && typeof value === "number") return (value / 100).toFixed(2);
  return String(value);
}
export function correctedValue(kind: Kind, text: string): unknown {
  if (kind === "coverage" && ["quoted", "excluded"].includes(text)) return text;
  if (isBoolean(kind) && ["true", "false"].includes(text)) return text === "true";
  if (kind === "latest_arrival" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(text) && Number.isFinite(Date.parse(text))) return text;
  if (isMoney(kind) && /^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?$/.test(text)) {
    const [whole, fraction = ""] = text.split(".");
    const value = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
    if (value <= (kind === "price_cents" ? 100_000_000 : 100_000_000_000)) return value;
  }
  if (!isMoney(kind) && !isBoolean(kind) && kind !== "coverage" && kind !== "latest_arrival" && /^(?:0|[1-9][0-9]{0,8})$/.test(text)) {
    const value = Number(text);
    if (kind === "available_units" ? value <= 100_000_000 : value >= 1 && value <= 10000) return value;
  }
  throw new Error(copy("review.valueInvalid"));
}

// Python source offsets count Unicode code points, including non-BMP characters.
export function sourceSlices(text: string, ranges: { start: number; end: number }[]) {
  const chars = Array.from(text);
  const merged: { start: number; end: number }[] = [];
  for (const span of [...ranges].sort((a, b) => a.start - b.start)) {
    if (span.start < 0 || span.end > chars.length || span.end <= span.start) continue;
    const last = merged.at(-1);
    if (last && span.start <= last.end) last.end = Math.max(last.end, span.end);
    else merged.push({ ...span });
  }
  const slices: { text: string; marked: boolean }[] = [];
  let cursor = 0;
  for (const span of merged) {
    slices.push({ text: chars.slice(cursor, span.start).join(""), marked: false });
    slices.push({ text: chars.slice(span.start, span.end).join(""), marked: true });
    cursor = span.end;
  }
  slices.push({ text: chars.slice(cursor).join(""), marked: false });
  return slices;
}
