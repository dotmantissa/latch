import { useEffect, useState, type FormEvent } from "react";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { FileText, Plus, Settings, LogOut, ArrowUpRight, Eye, EyeOff } from "lucide-react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useOutletContext,
  useNavigate,
} from "react-router";
import {
  api,
  ApiFailure,
  copy,
  setCsrf,
  timestamp,
  type RequestPage,
  type Session,
  type SavedRequest,
  type Profile,
} from "./api";
import { Brand, ErrorNotice, ThemeControl } from "./ui";

export const useSession = () => useOutletContext<Session>();

function Login({ onSignedIn }: { onSignedIn: (session: Session) => void }) {
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  async function demo() {
    setBusy(true); setError(undefined);
    try { onSignedIn(await api<Session>("/auth/demo", { method: "POST", body: "{}" })); }
    catch (failure) { setError(failure); }
    finally { setBusy(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    const form = new FormData(event.currentTarget);
    try {
      const session = await api<Session>("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
        }),
      });
      onSignedIn(session);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <Link to="/" className="login-brand">
        <Brand />
      </Link>
      <div className="login-paper">
        <span className="eyebrow">{copy("brand.tagline")}</span>
        <h1>{copy("auth.heading")}</h1>
        <p className="lede">{copy("auth.body")}</p>
        <ErrorNotice error={error} />
        <form onSubmit={submit}>
          <label>
            {copy("auth.username")}
            <input
              name="username"
              autoComplete="username"
              required
              maxLength={64}
              autoFocus
            />
          </label>
          <label>
            {copy("auth.password")}
            <input
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              maxLength={256}
            />
          </label>
          <button
            type="button"
            className="text-button"
            aria-pressed={showPassword}
            onClick={() => setShowPassword((value) => !value)}
          >
            {showPassword ? <EyeOff size={18} aria-hidden /> : <Eye size={18} aria-hidden />}
            {copy(showPassword ? "auth.hidePassword" : "auth.showPassword")}
          </button>
          <button className="primary" disabled={busy}>
            {copy(busy ? "auth.working" : "auth.signin")}
          </button>
        </form>
        <p className="muted small">{copy("auth.provision")}</p>
        <button className="primary" disabled={busy} onClick={() => void demo()}>{copy("demo.open")}</button>
        <p className="help">{copy("demo.scope")}</p>
      </div>
      <ThemeControl />
    </main>
  );
}

export function App() {
  const client = useQueryClient();
  const location = useLocation();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/session"),
    refetchInterval: 60000,
  });
  const [logoutError, setLogoutError] = useState<unknown>();
  const [loggingOut, setLoggingOut] = useState(false);
  const user = session.data?.user;
  const rail = useQuery({
    queryKey: ["requests", user?.id, "rail"],
    queryFn: () => api<RequestPage>("/requests?limit=12"),
    enabled: Boolean(user),
  });
  useEffect(() => {
    setCsrf(session.data?.csrf_token ?? "");
  }, [session.data]);
  useEffect(() => {
    const ended = () => {
      client.setQueryData(["session"], null);
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
    };
    window.addEventListener("latch:session-ended", ended);
    return () => window.removeEventListener("latch:session-ended", ended);
  }, [client]);
  useEffect(() => {
    document.title =
      !session.data
        ? copy("title.signin")
        : location.pathname === "/settings"
          ? copy("title.settings")
          : location.pathname === "/status"
            ? copy("title.status")
            : location.pathname === "/requests/new"
        ? copy("title.new")
        : location.pathname.startsWith("/requests/")
          ? copy("title.review")
          : copy("title.requests");
  }, [location.pathname, session.data]);
  async function logout() {
    setLoggingOut(true);
    setLogoutError(undefined);
    try {
      await api("/auth/logout", { method: "POST", body: "{}" });
      setCsrf("");
      client.setQueryData(["session"], null);
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
    } catch (failure) {
      setLogoutError(failure);
    } finally {
      setLoggingOut(false);
    }
  }
  if (session.isPending)
    return (
      <main className="login-page">
        <Brand />
        <p role="status">{copy("common.loading")}</p>
      </main>
    );
  if (
    (!session.data && !session.error) ||
    (session.error instanceof ApiFailure && session.error.status === 401)
  )
    return (
      <Login
        onSignedIn={(value) => {
          setCsrf(value.csrf_token);
          client.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
          client.setQueryData(["session"], value);
        }}
      />
    );
  if (session.error)
    return (
      <main className="login-page">
        <Brand />
        <ErrorNotice
          error={session.error}
          retry={() => void session.refetch()}
        />
      </main>
    );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        {copy("nav.skip")}
      </a>
      <aside className="rail" aria-label={copy("nav.requests")}>
        <Link to="/requests" className="rail-brand">
          <Brand />
        </Link>
        <nav>
          <NavLink to="/requests" end aria-label={copy("nav.requests")}>
            <FileText size={18} aria-hidden />
            <span>{copy("nav.requests")}</span>
          </NavLink>
          <NavLink to="/requests/new" className="new-link" aria-label={copy("nav.new")}>
            <Plus size={18} aria-hidden />
            <span>{copy("nav.new")}</span>
          </NavLink>
        </nav>
        <div className="rail-history">
          <span className="eyebrow">{copy("request.history")}</span>
          {rail.data?.requests.map((request) => (
            <NavLink key={request.id} to={`/requests/${request.id}`}>
              <span className="rail-reference">{request.reference}</span>
              <span>{request.name}</span>
            </NavLink>
          ))}
        </div>
        <div className="rail-bottom">
          <NavLink to="/settings" aria-label={copy("nav.settings")}>
            <Settings size={18} aria-hidden />
            <span>{copy("nav.settings")}</span>
          </NavLink>
          <button onClick={logout} disabled={loggingOut} aria-label={copy("nav.signout")}>
            <LogOut size={18} aria-hidden />
            <span>{copy("nav.signout")}</span>
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <Link to="/requests" className="mobile-brand">
            <Brand />
          </Link>
          <span className="identity">{session.data.user.display_name}</span>
          <Link to="/status" className="availability">
            <span className="status-dot" aria-hidden />
            {copy("request.draft")}
          </Link>
        </header>
        <ErrorNotice error={logoutError} />
        <Outlet context={session.data} />
        <footer className="workspace-footer">{copy("brand.tagline")}</footer>
      </div>
    </div>
  );
}

export function RequestList() {
  const session = useSession();
  const navigate = useNavigate();
  const [demoError, setDemoError] = useState<unknown>();
  const [demoBusy, setDemoBusy] = useState(false);
  async function sourceDemo() {
    setDemoBusy(true); setDemoError(undefined);
    try {
      const profiles = await api<Profile[]>("/source-profiles");
      const profile = profiles.find(p => p.id === "ubiquiti_u6plus_research");
      if (!profile) throw new ApiFailure(503, "SOURCE_PROFILE_UNAVAILABLE", "inspection.sourceRequired");
      const deadline = new Date(Date.now() + 7 * 86400000);
      deadline.setUTCSeconds(0, 0);
      const saved = await api<SavedRequest>("/requests", {
        method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ name: "U6+ public source demonstration", currency: "USD", budget: "200.00",
          required_by: deadline.toISOString(), required_by_local: deadline.toISOString().slice(0,16),
          timezone: "UTC", delivery_basis: "Demonstration only; destination and supplier delivery quote not supplied.",
          items: [{ key: "u6_plus", specification: "Demonstration: inspect the Ubiquiti U6+ public offer; no purchase requested.",
            public_specification: "Ubiquiti Access Point U6 Plus", required_units: 1 }],
          sources: [{ label: "Ubiquiti U6+ public offer", url: profile.origin + profile.offer_paths[0],
            profile_id: profile.id, profile_version: profile.version }] }),
      });
      navigate(`/requests/${saved.id}`);
    } catch (failure) { setDemoError(failure); }
    finally { setDemoBusy(false); }
  }
  const query = useInfiniteQuery({
    queryKey: ["requests", session.user.id, "list"],
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) =>
      api<RequestPage>(
        `/requests?limit=20${pageParam ? `&cursor=${pageParam}` : ""}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const requests = query.data?.pages.flatMap((page) => page.requests) ?? [];
  return (
    <main id="main" className="document list-document">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{copy("brand.name")}</span>
          <h1>{copy("list.heading")}</h1>
          <p className="lede">{copy("list.intro")}</p>
        </div>
        <Link to="/requests/new" className="primary button">
          <Plus size={18} aria-hidden />
          {copy("nav.new")}
        </Link>
      </div>
      <ErrorNotice error={query.error} retry={() => void query.refetch()} />
      <ErrorNotice error={demoError} />
      <section className="notice neutral">
        <button disabled={demoBusy} onClick={() => void sourceDemo()}>{copy("demo.source")}</button>
        <p className="help">{copy("demo.sourceScope")}</p>
      </section>
      {query.isPending ? (
        <p role="status">{copy("common.loading")}</p>
      ) : requests.length ? (
        <div className="request-ledger">
          {requests.map((request) => (
            <Link
              className="ledger-entry"
              key={request.id}
              to={`/requests/${request.id}`}
            >
              <span className="reference">{request.reference}</span>
              <div>
                <h2>{request.name}</h2>
                <p>
                  {copy("request.version")} {request.version}{" "}
                  <span className="separator">/</span>{" "}
                  {timestamp(request.saved_at)}
                </p>
              </div>
              <span className="status-label">
                {copy(
                  request.status === "archived"
                    ? "request.archived"
                    : "request.draft",
                )}
              </span>
              <ArrowUpRight size={20} aria-hidden />
            </Link>
          ))}
        </div>
      ) : !query.error ? (
        <section className="empty-state">
          <div className="paper-mark" aria-hidden>
            <FileText size={32} strokeWidth={1.25} />
          </div>
          <h2>{copy("empty.heading")}</h2>
          <p>{copy("empty.body")}</p>
          <Link to="/requests/new" className="text-button">
            {copy("empty.action")} <Plus size={16} aria-hidden />
          </Link>
        </section>
      ) : null}
      {query.hasNextPage ? (
        <button
          onClick={() => void query.fetchNextPage()}
          disabled={query.isFetchingNextPage}
        >
          {copy("list.more")}
        </button>
      ) : null}
    </main>
  );
}

export function SettingsPage() {
  const session = useSession();
  const client = useQueryClient();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  async function reauth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    setSuccess(false);
    const form = event.currentTarget;
    try {
      const next = await api<Session>("/auth/reauth", {
        method: "POST",
        body: JSON.stringify({ password: new FormData(form).get("password") }),
      });
      setCsrf(next.csrf_token);
      client.setQueryData(["session"], next);
      form.reset();
      setSuccess(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main id="main" className="document settings-document">
      <span className="eyebrow">{copy("nav.settings")}</span>
      <h1>{copy("settings.heading")}</h1>
      <ThemeControl />
      <section className="section">
        <h2>{copy("auth.session")}</h2>
        <dl>
          <dt>{copy("settings.identity")}</dt>
          <dd>
            {session.user.display_name}{" "}
            <span className="muted">({session.user.username})</span>
          </dd>
          <dt>{copy("settings.expiry")}</dt>
          <dd>{timestamp(session.expires_at)}</dd>
        </dl>
        <p className="muted">
          {copy(session.reauth_fresh ? "settings.fresh" : "settings.stale")}
        </p>
        <ErrorNotice error={error} />
        <form onSubmit={reauth}>
          <label>
            {copy("auth.password")}
            <input
              type="password"
              name="password"
              required
              autoComplete="current-password"
              maxLength={256}
            />
          </label>
          <button disabled={busy}>{copy("auth.reauth")}</button>
        </form>
        {success ? (
          <p role="status" className="success-text">
            {copy("auth.reauthSuccess")}
          </p>
        ) : null}
      </section>
    </main>
  );
}

export function StatusPage() {
  const status = useQuery({
    queryKey: ["public-status"],
    queryFn: async () => {
      const response = await fetch("/health/ready", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new ApiFailure(response.status, "UNAVAILABLE", "error.database");
      return response.json() as Promise<{ status: string }>;
    },
    refetchInterval: 60000,
  });
  useEffect(() => { document.title = copy("title.status"); }, []);
  return (
    <main id="main" className="document public-document">
      <Link to="/"><Brand /></Link>
      <span className="eyebrow">{copy("brand.name")}</span>
      <h1>{copy("status.heading")}</h1>
      <div className="section">
        <ErrorNotice error={status.error} retry={() => void status.refetch()} />
        {status.isPending ? <p role="status">{copy("common.loading")}</p>
          : status.data ? <><p>{copy("status.draft")}</p><p className="muted">{copy(status.data.status === "ready" ? "status.ready" : "status.worker")}</p></> : null}
        <Link to="/requests" className="text-button">
          {copy("common.return")}
        </Link>
      </div>
      <ThemeControl />
    </main>
  );
}

export function HomePage() {
  useEffect(() => { document.title = copy("title.home"); }, []);
  return (
    <div className="public-page">
      <header className="public-header">
        <Link to="/"><Brand /></Link>
        <Link to="/requests" className="button">{copy("home.primary")}</Link>
      </header>
      <main className="public-document">
        <span className="eyebrow">{copy("brand.tagline")}</span>
        <h1>{copy("home.heading")}</h1>
        <p className="lede">{copy("home.draftBody")}</p>
        <Link to="/requests" className="primary button">{copy("home.primary")}</Link>
        <section className="section home-scope">
          <h2>{copy("home.secondary")}</h2>
          <p>{copy("home.workflow")}</p>
          <p className="muted">{copy("home.pending")}</p>
          <Link to="/status" className="text-button">{copy("status.heading")}</Link>
        </section>
      </main>
      <footer className="public-footer"><ThemeControl /></footer>
    </div>
  );
}
