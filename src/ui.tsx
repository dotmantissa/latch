import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { CircleAlert, Monitor, Moon, Sun } from "lucide-react";
import { ApiFailure, copy } from "./api";

export function Brand() {
  return (
    <span className="brand">
      <img className="logo-light" src="/brand/wordmark-light.svg" alt="Latch" />
      <img className="logo-dark" src="/brand/wordmark-dark.svg" alt="Latch" />
    </span>
  );
}

export function ErrorNotice({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [error]);
  if (!error) return null;
  return (
    <div className="notice error" role="alert" tabIndex={-1} ref={ref}>
      <CircleAlert aria-hidden size={20} />
      <div>
        <p>
          {error instanceof ApiFailure ? error.message : copy("error.network")}
        </p>
        {error instanceof ApiFailure && error.reference ? (
          <small>
            {copy("common.reference")}: {error.reference}
          </small>
        ) : null}
        {retry ? (
          <button className="text-button" onClick={retry}>
            {copy("common.retry")}
          </button>
        ) : null}
      </div>
    </div>
  );
}

type Theme = "light" | "dark" | "system";
const ThemeContext = createContext<{ preference: Theme; setPreference: (value: Theme) => void } | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState(() => {
    try {
      const saved = localStorage.getItem("latch.theme.v1");
      return ["light", "dark", "system"].includes(saved ?? "")
        ? saved as Theme
        : "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        preference === "system"
          ? media.matches
            ? "dark"
            : "light"
          : preference;
    };
    apply();
    media.addEventListener("change", apply);
    try {
      localStorage.setItem("latch.theme.v1", preference);
    } catch {
      /* Appearance still works in memory. */
    }
    return () => media.removeEventListener("change", apply);
  }, [preference]);
  return <ThemeContext.Provider value={{ preference, setPreference }}>{children}</ThemeContext.Provider>;
}

export function ThemeControl() {
  const { preference, setPreference } = useContext(ThemeContext)!;
  return (
    <fieldset className="theme-control">
      <legend>{copy("theme.label")}</legend>
      <div className="segments">
        {(
          [
            ["light", Sun],
            ["dark", Moon],
            ["system", Monitor],
          ] as const
        ).map(([name, Icon]) => (
          <button
            key={name}
            type="button"
            aria-pressed={preference === name}
            onClick={() => setPreference(name)}
          >
            <Icon size={16} aria-hidden />
            {copy(`theme.${name}`)}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
