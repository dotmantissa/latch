import type { components } from "../packages/contracts/api";
import catalog from "../COPY.json";

type GeneratedInput = components["schemas"]["RequestInput"];
export type WorksheetInput = Omit<GeneratedInput, "sources"> & {
  sources: NonNullable<GeneratedInput["sources"]>;
};
export type SavedRequest = components["schemas"]["RequestView"];
export type RequestPage = components["schemas"]["RequestPage"];
export type Session = components["schemas"]["SessionView"];
export type Profile = components["schemas"]["ProfileView"];
export const copy = (key: string): string =>
  (catalog as Record<string, string>)[key] ?? catalog["error.generic"];
let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}

export class ApiFailure extends Error {
  constructor(
    public status: number,
    public code: string,
    public messageKey: string,
    public fields: Record<string, string> = {},
    public reference = "",
  ) {
    super(copy(messageKey));
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(options.method
        ? { "Content-Type": "application/json", "X-CSRF-Token": csrf }
        : {}),
      ...options.headers,
    },
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login") {
      setCsrf("");
      window.dispatchEvent(new Event("latch:session-ended"));
    }
    throw new ApiFailure(
      response.status,
      body.code,
      body.message_key,
      body.field_errors,
      body.correlation_id,
    );
  }
  return body.data as T;
}

export const money = (amount: string) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    Number(amount),
  );
export const timestamp = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
