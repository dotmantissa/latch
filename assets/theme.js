(() => {
  let preference = "system";
  try {
    preference = localStorage.getItem("latch.theme.v1") || "system";
  } catch {}
  if (!["light", "dark", "system"].includes(preference)) preference = "system";
  document.documentElement.dataset.theme =
    preference === "system"
      ? matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : preference;
})();
