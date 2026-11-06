import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  useBlocker,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router";
import { Plus, X, Check, FileText } from "lucide-react";
import {
  api,
  ApiFailure,
  copy,
  money,
  timestamp,
  type Profile,
  type SavedRequest,
  type WorksheetInput,
} from "./api";
import { useSession } from "./pages";
import { ErrorNotice } from "./ui";
import { InspectionControl } from "./inspection";

function normalize(input: SavedRequest["worksheet"]): WorksheetInput {
  return { ...input, sources: input.sources ?? [] };
}

function blank(): WorksheetInput {
  return {
    name: "",
    currency: "USD",
    budget: "",
    required_by: "",
    required_by_local: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    delivery_basis: "",
    items: [
      {
        key: "item_1",
        specification: "",
        public_specification: "",
        required_units: 1,
      },
    ],
    sources: [],
  };
}

function deadlineISO(local: string, zone: string): string {
  const parts = local.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/);
  if (!parts) throw new Error("deadline");
  const desired = Date.UTC(
    ...([+parts[1], +parts[2] - 1, +parts[3], +parts[4], +parts[5]] as [
      number,
      number,
      number,
      number,
      number,
    ]),
  );
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const wall = (epoch: number) => {
    const values = Object.fromEntries(
      formatter.formatToParts(epoch).map((p) => [p.type, p.value]),
    );
    return Date.UTC(
      +values.year,
      +values.month - 1,
      +values.day,
      +values.hour,
      +values.minute,
    );
  };
  let candidate = desired;
  for (let i = 0; i < 3; i++) candidate += desired - wall(candidate);
  if (
    wall(candidate) !== desired ||
    [-7200000, -3600000, -1800000, 1800000, 3600000, 7200000].some(
      (offset) => wall(candidate + offset) === desired,
    )
  )
    throw new Error("timezone");
  return new Date(candidate).toISOString();
}

export function Worksheet() {
  const { id } = useParams();
  const [search] = useSearchParams();
  const version = search.get("version");
  const session = useSession();
  const request = useQuery({
    queryKey: ["request", session.user.id, id, version],
    queryFn: () =>
      api<SavedRequest>(
        `/requests/${id}${version ? `?version=${version}` : ""}`,
      ),
    enabled: Boolean(id),
    refetchOnWindowFocus: false,
  });
  const profiles = useQuery({
    queryKey: ["profiles", session.user.id],
    queryFn: () => api<Profile[]>("/source-profiles"),
  });
  if (id && request.isPending)
    return (
      <main id="main" className="document">
        <p role="status">{copy("common.loading")}</p>
      </main>
    );
  if (request.error)
    return (
      <main id="main" className="document">
        <ErrorNotice
          error={request.error}
          retry={() => void request.refetch()}
        />
        <Link to="/requests">{copy("common.return")}</Link>
      </main>
    );
  return (
    <Editor
      key={`${id ?? "new"}:${version ?? "current"}`}
      saved={id ? request.data : undefined}
      historical={Boolean(version)}
      profiles={profiles.data ?? []}
      profileError={profiles.error}
    />
  );
}

function Editor({
  saved: initial,
  historical,
  profiles,
  profileError,
}: {
  saved?: SavedRequest;
  historical: boolean;
  profiles: Profile[];
  profileError: unknown;
}) {
  const [saved, setSaved] = useState(initial);
  const [model, setModel] = useState<WorksheetInput>(() =>
    normalize(initial?.worksheet ?? blank()),
  );
  const [baseline, setBaseline] = useState(() =>
    JSON.stringify(initial?.worksheet ?? model),
  );
  const [error, setError] = useState<unknown>();
  const [saving, setSaving] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const pending = useRef<{ intent: string; key: string } | null>(null);
  const allowNavigation = useRef(false);
  const client = useQueryClient();
  const session = useSession();
  const navigate = useNavigate();
  const dirty = JSON.stringify(model) !== baseline;
  const readonly = historical || saved?.status === "archived";
  const blocker = useBlocker(() => dirty && !allowNavigation.current);
  const history = useQuery({
    queryKey: ["history", session.user.id, saved?.id],
    queryFn: () => api<number[]>(`/requests/${saved!.id}/history`),
    enabled: Boolean(saved),
  });
  useEffect(() => {
    if (blocker.state === "blocked") {
      if (window.confirm(copy("request.leave"))) blocker.proceed();
      else blocker.reset();
    }
  }, [blocker]);
  useEffect(() => {
    const before = (event: BeforeUnloadEvent) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", before);
    return () => window.removeEventListener("beforeunload", before);
  }, [dirty]);
  function update(next: WorksheetInput) {
    setModel(next);
    setAcknowledged(false);
  }
  const fieldErrors = error instanceof ApiFailure ? error.fields : {};
  const attributes = (key: string) => ({
    "aria-invalid": Boolean(fieldErrors[key]),
    "aria-describedby": fieldErrors[key] ? `${key}-error` : undefined,
  });
  const fieldError = (key: string) =>
    fieldErrors[key] ? (
      <span id={`${key}-error`} className="field-error">
        {copy(fieldErrors[key])}
      </span>
    ) : null;
  async function save(event: FormEvent) {
    event.preventDefault();
    setError(undefined);
    let input: WorksheetInput;
    try {
      input = {
        ...model,
        required_by: deadlineISO(model.required_by_local, model.timezone),
      };
    } catch {
      setError(
        new ApiFailure(422, "DEADLINE_TIMEZONE", "error.timezone", {
          required_by_local: "error.timezone",
          timezone: "error.timezone",
        }),
      );
      return;
    }
    const intent = JSON.stringify({ input, version: saved?.version });
    if (pending.current?.intent !== intent)
      pending.current = { intent, key: crypto.randomUUID() };
    setSaving(true);
    try {
      const next = await api<SavedRequest>(
        saved ? `/requests/${saved.id}` : "/requests",
        {
          method: saved ? "PATCH" : "POST",
          body: JSON.stringify(input),
          headers: {
            "Idempotency-Key": pending.current!.key,
            ...(saved ? { "If-Match": `"${saved.version}"` } : {}),
          },
        },
      );
      setSaved(next);
      setModel(normalize(next.worksheet));
      setBaseline(JSON.stringify(next.worksheet));
      setAcknowledged(true);
      pending.current = null;
      client.setQueryData(["request", session.user.id, next.id, null], next);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["requests", session.user.id] }),
        client.invalidateQueries({
          queryKey: ["history", session.user.id, next.id],
        }),
      ]);
      if (!saved) {
        allowNavigation.current = true;
        navigate(`/requests/${next.id}`, { replace: true });
      }
    } catch (failure) {
      setError(failure);
      if (failure instanceof ApiFailure && failure.status === 401)
        void client.invalidateQueries({ queryKey: ["session"] });
    } finally {
      setSaving(false);
    }
  }
  async function loadLatest() {
    if (dirty && !window.confirm(copy("request.leave"))) return;
    try {
      const latest = await api<SavedRequest>(`/requests/${saved!.id}`);
      setSaved(latest);
      setModel(normalize(latest.worksheet));
      setBaseline(JSON.stringify(latest.worksheet));
      setError(undefined);
      pending.current = null;
      client.setQueryData(["request", session.user.id, latest.id, null], latest);
      await client.invalidateQueries({ queryKey: ["history", session.user.id, latest.id] });
    } catch (failure) {
      setError(failure);
    }
  }
  async function archive() {
    if (dirty && !window.confirm(copy("request.leave"))) return;
    setSaving(true);
    setError(undefined);
    try {
      const next = await api<SavedRequest>(`/requests/${saved!.id}/archive`, {
        method: "POST",
        body: JSON.stringify({ current_version: saved!.version }),
        headers: { "If-Match": `"${saved!.version}"` },
      });
      setSaved(next);
      setModel(normalize(next.worksheet));
      setBaseline(JSON.stringify(next.worksheet));
      client.setQueryData(["request", session.user.id, next.id, null], next);
      await client.invalidateQueries({
        queryKey: ["requests", session.user.id],
      });
    } catch (failure) {
      setError(failure);
    } finally {
      setSaving(false);
    }
  }
  return (
    <main id="main" className="document worksheet-document">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{saved?.reference ?? copy("nav.new")}</span>
          <h1>{saved ? saved.worksheet.name : copy("request.heading")}</h1>
          <p className="lede">
            {saved
              ? `${copy("request.version")} ${saved.version} / ${copy(saved.status === "archived" ? "request.archived" : historical ? "request.readonly" : "request.draft")}`
              : copy("request.intro")}
          </p>
        </div>
        {saved ? (
          <div className="saved-meta">
            <Check size={16} aria-hidden />
            <span>
              {copy("request.saved")}
              <small>{timestamp(saved.saved_at)}</small>
            </span>
          </div>
        ) : null}
      </div>
      <div className="worksheet-layout">
        <form id="worksheet" onSubmit={save} className="worksheet-form">
          <ErrorNotice error={error} />
          {error instanceof ApiFailure && error.status === 412 ? (
            <button type="button" onClick={loadLatest}>
              {copy("request.loadLatest")}
            </button>
          ) : null}
          {readonly ? (
            <p className="notice">
              {copy(historical ? "request.readonly" : "request.archivedHelp")}{" "}
              {historical ? (
                <Link to={`/requests/${saved!.id}`}>
                  {copy("request.current")}
                </Link>
              ) : null}
            </p>
          ) : null}
          <fieldset disabled={readonly || saving} className="worksheet-fields">
            <legend className="sr-only">{copy("request.edit")}</legend>
            <section className="section first-section">
              <label>
                {copy("request.name")}
                <input
                  value={model.name}
                  required
                  maxLength={200}
                  {...attributes("name")}
                  onChange={(e) => update({ ...model, name: e.target.value })}
                />
                {fieldError("name")}
              </label>
              <div className="two-columns">
                <label>
                  {copy("request.budget")} <span className="unit">USD</span>
                  <input
                    value={model.budget}
                    inputMode="decimal"
                    pattern="(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?"
                    required
                    {...attributes("budget")}
                    onChange={(e) =>
                      update({ ...model, budget: e.target.value })
                    }
                  />
                  <span className="help">{copy("request.budgetHelp")}</span>
                  {fieldError("budget")}
                </label>
                <label>
                  {copy("request.deadline")}
                  <input
                    type="datetime-local"
                    value={model.required_by_local}
                    required
                    {...attributes("required_by_local")}
                    onChange={(e) =>
                      update({ ...model, required_by_local: e.target.value })
                    }
                  />
                  {fieldError("required_by_local")}
                </label>
              </div>
              <label>
                {copy("request.timezone")}
                <input
                  value={model.timezone}
                  required
                  maxLength={100}
                  {...attributes("timezone")}
                  onChange={(e) =>
                    update({ ...model, timezone: e.target.value })
                  }
                />
                <span className="help">{copy("request.deadlineHelp")}</span>
                {fieldError("timezone")}
              </label>
              <label>
                {copy("request.deliveryBasis")}
                <textarea
                  value={model.delivery_basis}
                  required
                  minLength={3}
                  maxLength={500}
                  {...attributes("delivery_basis")}
                  onChange={(e) =>
                    update({ ...model, delivery_basis: e.target.value })
                  }
                />
                {fieldError("delivery_basis")}
              </label>
            </section>
            <section className="section">
              <div className="section-heading">
                <h2>{copy("request.items")}</h2>
                <span className="muted small">{model.items.length} / 3</span>
              </div>
              <p className="help">{copy("request.publicHelp")}</p>
              {model.items.map((item, index) => (
                <fieldset key={item.key} className="item-row">
                  <legend>
                    {copy("request.item")} {index + 1}
                  </legend>
                  <div className="item-main">
                    <label>
                      {copy("request.spec")}
                      <textarea
                        value={item.specification}
                        required
                        minLength={3}
                        maxLength={1000}
                        {...attributes(`items.${index}.specification`)}
                        onChange={(e) =>
                          update({
                            ...model,
                            items: model.items.map((current, i) =>
                              i === index
                                ? { ...current, specification: e.target.value }
                                : current,
                            ),
                          })
                        }
                      />
                      {fieldError(`items.${index}.specification`)}
                    </label>
                    <label>
                      {copy("request.publicSpec")}
                      <textarea
                        value={item.public_specification}
                        required
                        minLength={3}
                        maxLength={1000}
                        {...attributes(`items.${index}.public_specification`)}
                        onChange={(e) =>
                          update({
                            ...model,
                            items: model.items.map((current, i) =>
                              i === index
                                ? {
                                    ...current,
                                    public_specification: e.target.value,
                                  }
                                : current,
                            ),
                          })
                        }
                      />
                      {fieldError(`items.${index}.public_specification`)}
                    </label>
                  </div>
                  <div className="item-quantity">
                    <label>
                      {copy("request.quantity")}
                      <input
                        type="number"
                        min={1}
                        max={10000}
                        step={1}
                        required
                        value={item.required_units || ""}
                        {...attributes(`items.${index}.required_units`)}
                        onChange={(e) =>
                          update({
                            ...model,
                            items: model.items.map((current, i) =>
                              i === index
                                ? {
                                    ...current,
                                    required_units: Number(e.target.value),
                                  }
                                : current,
                            ),
                          })
                        }
                      />
                      {fieldError(`items.${index}.required_units`)}
                    </label>
                    {model.items.length > 1 ? (
                      <button
                        type="button"
                        className="text-button remove"
                        onClick={() =>
                          update({
                            ...model,
                            items: model.items.filter((_, i) => i !== index),
                          })
                        }
                      >
                        <X size={16} aria-hidden />
                        {copy("request.remove")}
                      </button>
                    ) : null}
                  </div>
                </fieldset>
              ))}
              {model.items.length < 3 ? (
                <button
                  type="button"
                  className="text-button"
                  onClick={() =>
                    update({
                      ...model,
                      items: [
                        ...model.items,
                        {
                          key: `item_${crypto.randomUUID().replaceAll("-", "_")}`,
                          specification: "",
                          public_specification: "",
                          required_units: 1,
                        },
                      ],
                    })
                  }
                >
                  <Plus size={16} aria-hidden />
                  {copy("request.addItem")}
                </button>
              ) : null}
            </section>
            <section className="section">
              <div className="section-heading">
                <h2>{copy("request.suppliers")}</h2>
                <span className="muted small">{model.sources.length} / 3</span>
              </div>
              <ErrorNotice error={profileError} />
              {!profiles.length && !profileError ? (
                <p className="notice neutral">{copy("request.noProfiles")}</p>
              ) : null}
              {model.sources.map((source, index) => (
                <fieldset className="source-row" key={index}>
                  <legend>
                    {copy("request.source")} {index + 1}
                  </legend>
                  <label>
                    {copy("request.sourceLabel")}
                    <input
                      required
                      maxLength={100}
                      value={source.label}
                      onChange={(e) =>
                        update({
                          ...model,
                          sources: model.sources.map((current, i) =>
                            i === index
                              ? { ...current, label: e.target.value }
                              : current,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    {copy("request.profile")}
                    <select
                      value={`${source.profile_id}:${source.profile_version}`}
                      onChange={(e) => {
                        const profile = profiles.find(
                          (p) => `${p.id}:${p.version}` === e.target.value,
                        );
                        if (!profile) return;
                        update({
                          ...model,
                          sources: model.sources.map((current, i) =>
                            i === index
                              ? {
                                  ...current,
                                  profile_id: profile.id,
                                  profile_version: profile.version,
                                  url: `${profile.origin}${profile.offer_paths[0]}`,
                                }
                              : current,
                          ),
                        });
                      }}
                    >
                      {!profiles.some((p) => p.id === source.profile_id && p.version === source.profile_version)
                        ? <option value={`${source.profile_id}:${source.profile_version}`} disabled>
                            {copy("request.profileUnavailable")} / {copy("request.version")} {source.profile_version}
                          </option> : null}
                      {profiles.map((p) => (
                        <option
                          key={`${p.id}:${p.version}`}
                          value={`${p.id}:${p.version}`}
                        >
                          {p.origin} / {copy("request.version")} {p.version}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {copy("request.sourceURL")}
                    <input
                      type="url"
                      value={source.url}
                      required
                      maxLength={2048}
                      {...attributes(`sources.${index}.url`)}
                      onChange={(e) =>
                        update({
                          ...model,
                          sources: model.sources.map((current, i) =>
                            i === index
                              ? { ...current, url: e.target.value }
                              : current,
                          ),
                        })
                      }
                    />
                    {fieldError(`sources.${index}.url`)}
                  </label>
                  <button
                    type="button"
                    className="text-button remove"
                    onClick={() =>
                      update({
                        ...model,
                        sources: model.sources.filter((_, i) => i !== index),
                      })
                    }
                  >
                    <X size={16} aria-hidden />
                    {copy("request.remove")}
                  </button>
                </fieldset>
              ))}
              {profiles.length && model.sources.length < 3 ? (
                <button
                  type="button"
                  className="text-button"
                  onClick={() =>
                    update({
                      ...model,
                      sources: [
                        ...model.sources,
                        {
                          label: "",
                          url: `${profiles[0].origin}${profiles[0].offer_paths[0]}`,
                          profile_id: profiles[0].id,
                          profile_version: profiles[0].version,
                        },
                      ],
                    })
                  }
                >
                  <Plus size={16} aria-hidden />
                  {copy("request.addSource")}
                </button>
              ) : null}
            </section>
          </fieldset>
          {!readonly ? (
            <div className="save-bar">
              <button
                className="primary"
                disabled={saving || (!dirty && Boolean(saved))}
              >
                {copy(saving ? "request.saveWorking" : "request.save")}
              </button>
              <span
                role="status"
                className={acknowledged ? "success-text" : "muted"}
              >
                {copy(
                  dirty
                    ? "request.unsaved"
                    : acknowledged
                      ? "request.saveSuccess"
                      : saved
                        ? "request.savedHelp"
                        : "request.historyHelp",
                )}
              </span>
            </div>
          ) : null}
        </form>
        <aside className="release-margin" aria-label={copy("request.summary")}>
          <div className="margin-paper">
            <span className="eyebrow">{copy("request.summary")}</span>
            <div className="margin-total">
              {model.budget && Number(model.budget) > 0
                ? money(model.budget)
                : "USD"}
            </div>
            <span className="muted small">{copy("request.budget")}</span>
            <dl>
              <dt>{copy("request.deadline")}</dt>
              <dd>
                {model.required_by_local
                  ? model.required_by_local.replace("T", " ")
                  : copy("offer.unknown")}
                <small>{model.timezone}</small>
              </dd>
              <dt>{copy("request.owner")}</dt>
              <dd>{session.user.display_name}</dd>
            </dl>
            <div className="latch-seam" aria-hidden>
              <span />
            </div>
            {saved && !historical && saved.status !== "archived"
              ? <InspectionControl key={`${saved.id}:${saved.version}`} saved={saved} dirty={dirty} />
              : <p className="help">{copy("inspection.saveFirst")}</p>}
            {saved ? <Link className="text-button" to={`/requests/${saved.id}/evidence${historical ? `?version=${saved.version}` : ""}`}>
              {copy("review.open")}
            </Link> : null}
            {saved && !historical ? <Link className="text-button" to={`/requests/${saved.id}/compare`}>{copy("decision.open")}</Link> : null}
          </div>
          <div className="margin-note">
            <FileText size={20} aria-hidden />
            <h3>{copy("request.future")}</h3>
            <p>{copy("request.futureBody")}</p>
          </div>
          {saved ? (
            <div className="history">
              <h3>{copy("request.history")}</h3>
              <ErrorNotice error={history.error} retry={() => void history.refetch()} />
              {history.isPending ? <p role="status">{copy("common.loading")}</p> : null}
              {history.data?.map((v) => (
                <Link key={v} to={`/requests/${saved.id}?version=${v}`}>
                  {copy("request.version")} {v}
                </Link>
              ))}
              <p className="help">{copy("request.historyHelp")}</p>
              {!readonly ? (
                <button
                  type="button"
                  className="text-button"
                  disabled={saving}
                  onClick={archive}
                >
                  {copy("request.archive")}
                </button>
              ) : null}
            </div>
          ) : null}
        </aside>
      </div>
    </main>
  );
}
