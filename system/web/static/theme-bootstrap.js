(() => {
  const key = "agentic-consensus-theme";
  const allowed = new Set(["light", "dark"]);
  let preference = "light";
  try {
    const stored = localStorage.getItem(key);
    if (allowed.has(stored)) preference = stored;
    else localStorage.setItem(key, "light");
  } catch (_) {}
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.dataset.theme = preference;
  document.documentElement.style.colorScheme = preference;
  document.querySelector("#theme-color")?.setAttribute("content", preference === "dark" ? "#131614" : "#f4f5f2");
})();
