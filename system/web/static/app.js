const state = {
  auth: null,
  signupAllowed: false,
  csrfToken: null,
  runtime: null,
  users: [],
  authEvents: [],
  resetUser: null,
  projects: [],
  activeProject: null,
  intents: [],
  reviews: [],
  activeReview: null,
  contractGraph: null,
  manifest: null,
  events: [],
  projectEvents: [],
  projectTree: null,
  projectTreeLoading: false,
  filePanelOpen: false,
  changeMapDirectory: "",
  inspectorTab: "files",
  aiRuns: [],
  aiEvals: null,
  activeCopilotRun: null,
  reviewsLoading: false,
  reviewListExpanded: false,
  projectLoadError: null,
  viewMode: "canvas",
  filePanelPreference: false,
  diffReviewId: null,
  diffRevision: null,
  diffRequestVersion: 0,
  diffText: null,
  diffFiles: [],
  diffPath: null,
  diffInspection: null,
  diffQuery: "",
  diffLoading: false,
  diffError: null,
  diffTruncated: false,
  diffCharacters: 0,
  diffPromise: null,
  evidenceTab: "requirements",
  evidenceQuery: "",
  evidenceFilter: "all",
  evidenceObligation: "",
  github: {
    status: null,
    repositories: [],
    selectedRepositoryId: null,
    pullRequests: [],
    selectedPullNumber: null,
    source: "github",
  },
  selectionVersion: 0,
  reviewSelectionVersion: 0,
  paperMode: new URLSearchParams(window.location.search).get("paper") === "1",
};
let trustSigningPackage = null;
let contractGraphInstance = null;
let projectCanvasInstance = null;
let projectCanvasResizeObserver = null;
let projectCanvasData = { nodes: [], edges: [] };
let canvasState = { query: "", selected: null, panel: "overview", panelOpen: true, mode: "focus", focusId: null, snapshotFile: null, filesExpanded:false };
let snapshotReader = null;
let workspaceNavigationReady = false;
let restoringWorkspaceHistory = false;
let contractGraphResizeObserver = null;
let contractGraphLens = "decision";
let contractGraphView = "graph";
let reviewWorkspaceTab = "overview";
let governanceReviewOrigin = null;
let filePanelWasWide = window.matchMedia("(min-width: 1180px)").matches;
let inspectorOpener = null;
const reviewOperationDialogs = ["decision-dialog", "evidence-dialog", "dsse-dialog", "test-command-dialog", "commitment-dialog"];
const reviewOperations = new WeakMap();
const reviewSyncNotices = new Map();
const reviewQueries = new Map();
const reviewNavigation = NavigationModel.createSession();
const comparisonDrafts = new Map();
const copilotSession = AssistantModel.createSession();
const comparisonFields = ["intent_summary", "target_ref", "base_ref", "proposer"];
let comparisonContext = null;
let intakeVersion = 0;
let intakeOperation = null;
const githubRequests = { status: 0, repositories: 0, pulls: 0 };
const THEME_STORAGE_KEY = "agentic-consensus-theme";
const THEME_PREFERENCES = ["light", "dark"];

const $ = (selector) => document.querySelector(selector);
const esc = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
}[char]));
function uiIcon(name) {
  const safeName = String(name).replace(/[^a-z0-9-]/gi, "");
  return `<svg class="ui-icon" aria-hidden="true"><use href="#icon-${safeName}"></use></svg>`;
}
function controlTooltip(label) {
  return `<span class="control-tooltip" aria-hidden="true">${I18n.mark(label)}</span>`;
}
function setControlTooltip(control, label) {
  if (!control) return;
  I18n.setAttribute(control,'data-tooltip',label);
  const tooltip = control.querySelector(".control-tooltip");
  if (tooltip) I18n.setText(tooltip,label);
}
const short = (value = "") => String(value).slice(0, 8);
const title = (value = "") => String(value).replaceAll("_", " ");
const plural = (count, singular, many = `${singular}s`) => `${count} ${count === 1 ? singular : many}`;
const sentence = (value = "") => {
  const text = title(value).trim();
  return text ? text[0].toUpperCase() + text.slice(1) : text;
};
const plainVersion = (value = "") => String(value).replace(/C\^(\d+)/g, "version $1");

function reviewRef(review) {
  if (!review) return "";
  if (review.external_label) return review.external_label;
  const tail = String(review.id || "").split("-").pop() || "";
  return `Review ${tail.slice(0, 7)}`;
}

function relativeTime(value) {
  const stamp = Date.parse(value);
  if (!Number.isFinite(stamp)) return "";
  const seconds = Math.round((Date.now() - stamp) / 1000);
  if (seconds < 45) return "just now";
  const units = [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [name, size] of units) {
    if (seconds >= size) {
      const amount = Math.floor(seconds / size);
      return `${amount} ${name}${amount === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
}

function absoluteTime(value) {
  const stamp = Date.parse(value);
  return Number.isFinite(stamp) ? new Date(stamp).toLocaleString() : "";
}

function safeHttpUrl(value) {
  if (!value) return "";
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
  } catch {
    return "";
  }
}

function restyleContractGraph() {
  if (contractGraphInstance) contractGraphInstance.style(contractGraphStyles());
  if (projectCanvasInstance) projectCanvasInstance.style(projectCanvasStyles());
}

function applyThemePreference(preference, persist = true) {
  const safePreference = THEME_PREFERENCES.includes(preference) ? preference : "light";
  const resolved = safePreference;
  document.documentElement.dataset.themePreference = safePreference;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  if (persist) {
    try { localStorage.setItem(THEME_STORAGE_KEY, safePreference); } catch (_) {}
  }
  const next = safePreference === "light" ? "dark" : "light";
  document.querySelectorAll("[data-theme-cycle]").forEach((button) => {
    button.dataset.preference = safePreference;
    setControlTooltip(button, `Switch to ${next}`);
    I18n.setAttribute(button,"aria-label",`Switch to ${next} theme`);
  });
  $("#theme-mode-icon")?.setAttribute("href", `#icon-${next === "dark" ? "moon" : "sun"}`);
  const themeColor = state.paperMode ? "#f5f2e9" : (resolved === "dark" ? "#11120f" : "#f3f0e8");
  $("#theme-color")?.setAttribute("content", themeColor);
  if (contractGraphInstance) contractGraphInstance.style(contractGraphStyles());
}

function apiError(detail, status) {
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      const location = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(" → ") : "request";
      return `${location || "request"}: ${item.msg || "invalid value"}`;
    }).join("; ");
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  return `Request failed (${status})`;
}

let pendingRequests = 0;
let busyTimer = null;
function trackRequest(delta) {
  pendingRequests = Math.max(0, pendingRequests + delta);
  const bar = document.getElementById("busy-bar");
  if (!bar) return;
  window.clearTimeout(busyTimer);
  if (pendingRequests > 0) {
    busyTimer = window.setTimeout(() => bar.setAttribute("data-active", "true"), 140);
  } else {
    bar.removeAttribute("data-active");
  }
}

async function api(path, options = {}) {
  trackRequest(1);
  try {
    return await apiRequest(path, options);
  } finally {
    trackRequest(-1);
  }
}

async function apiRequest(path, options = {}) {
  const requestUserId = state.auth?.user?.id;
  const requestCsrfToken = state.csrfToken;
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  const method = String(options.method || "GET").toUpperCase();
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && state.csrfToken) {
    headers["X-CSRF-Token"] = state.csrfToken;
  }
  const response = await window.PaperDemo.request(path, { credentials: "same-origin", ...options, headers }, state.csrfToken);
  if (response.status === 401 && !path.startsWith("/api/auth/")
    && requestUserId === state.auth?.user?.id && requestCsrfToken === state.csrfToken) {
    state.auth = null;
    state.csrfToken = null;
    window.PaperDemo.clear();
    showAuthGate(false, "Your session expired. Sign in again to continue.");
  }
  if (response.status === 204) return {};
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(apiError(body.detail, response.status));
    error.status = response.status;
    throw error;
  }
  return body;
}

function setAuthMode(mode, focus = true) {
  const selectedMode = mode === "signup" && state.signupAllowed ? "signup" : "signin";
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    const selected = button.dataset.authMode === selectedMode;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  $("#login-form").classList.toggle("hidden", selectedMode !== "signin");
  $("#signup-form").classList.toggle("hidden", selectedMode !== "signup");
  I18n.setText($("#auth-kicker"),selectedMode === "signup" ? "New operator · Identity boundary" : "Identity boundary");
  I18n.setText($("#auth-title"),selectedMode === "signup" ? "Create your account" : "Sign in to your workspace");
  I18n.setText($("#auth-copy"),selectedMode === "signup"
    ? "Your name and audit identity will be recorded with the actions you take."
    : "Review proposed changes, trace the evidence, and record your decision.");
  I18n.setText($("#auth-access-note"),selectedMode === "signup"
    ? "Project permissions are assigned separately. Creating an account does not grant approval authority."
    : state.signupAllowed ? "New here? Choose Sign up to create an account for this installation."
      : "Use the account created for this installation. Need access? Ask the administrator who runs this workspace.");
  if (focus) window.requestAnimationFrame(() => $(selectedMode === "signup" ? "#signup-form" : "#login-form").querySelector("[autofocus]")?.focus());
}

function showAuthGate(setupRequired, message = "") {
  closeSnapshotFile(false);
  copilotSession.syncOwner(null, null);
  state.activeCopilotRun = null;
  resetIntakeSession();
  closeReviewOperations();
  $("#candidate-revision-dialog").close();
  for (const draft of candidateRevisionDrafts.values()) {
    if (!draft.saving) continue;
    draft.uncertain = true;
    draft.needsReview = true;
    draft.error = "Sign-in changed while saving. Review the latest revision before retrying. Your draft is kept.";
  }
  state.selectionVersion += 1;
  state.reviewSelectionVersion += 1;
  reviewSyncNotices.clear();
  reviewQueries.clear();
  reviewNavigation.clear();
  comparisonDrafts.clear();
  $("#review-form").reset();
  $("#review-filter").value = "";
  reviewOperationDialogs.forEach(id => reviewOperations.delete($(`#${id} form`)));
  ["#evidence-form", "#dsse-form"].forEach(selector => {
    const form = $(selector);
    form.reset();
    delete form.dataset.draftKey;
    form.closest("dialog").close();
  });
  document.body.classList.add("auth-locked");
  document.body.classList.remove("viewer-mode");
  $("#auth-gate").classList.remove("hidden");
  $("#bootstrap-form").classList.toggle("hidden", !setupRequired);
  $("#auth-mode-tabs").classList.toggle("hidden", setupRequired || !state.signupAllowed);
  $("#signup-form").classList.add("hidden");
  $("#forced-password-form").classList.add("hidden");
  if (setupRequired) {
    $("#login-form").classList.add("hidden");
    $("#auth-kicker").textContent = "First run · Identity boundary";
    $("#auth-title").textContent = "Create the first administrator.";
    $("#auth-copy").textContent = message || "The first account becomes the local administrator. Its audit identity must match the authority grants you intend to use.";
    $("#auth-access-note").textContent = "You’ll use this account to sign in and manage other accounts. Project permissions are assigned separately.";
    window.requestAnimationFrame(() => $("#bootstrap-form").querySelector("[autofocus]")?.focus());
    return;
  }
  setAuthMode("signin");
  if (message) $("#auth-copy").textContent = message;
}

function showForcedPasswordGate(auth) {
  renderAuthenticatedUser(auth);
  document.body.classList.add("auth-locked");
  $("#auth-gate").classList.remove("hidden");
  $("#auth-mode-tabs").classList.add("hidden");
  $("#bootstrap-form").classList.add("hidden");
  $("#login-form").classList.add("hidden");
  $("#signup-form").classList.add("hidden");
  $("#forced-password-form").classList.remove("hidden");
  $("#auth-kicker").textContent = "Temporary credential · Action required";
  $("#auth-title").textContent = "Replace the temporary password.";
  $("#auth-copy").textContent = "This identity cannot open project data until its temporary credential is replaced. Every prior session will be revoked.";
  $("#auth-access-note").textContent = "Use the temporary password provided by your administrator, then choose your own password.";
  window.requestAnimationFrame(() => $("#forced-password-form").elements.current_password.focus());
}

function renderAuthenticatedUser(auth) {
  if (state.auth?.user?.id !== auth.user.id || state.csrfToken !== auth.csrf_token) closeSnapshotFile(false);
  copilotSession.syncOwner(auth.user.id, auth.csrf_token);
  if (state.auth?.user?.id !== auth.user.id || state.csrfToken !== auth.csrf_token) resetIntakeSession();
  if (state.auth?.user?.id !== auth.user.id) comparisonDrafts.clear();
  if (intentDraftOwner !== auth.user.id) {
    intentDrafts.clear();
    intentDraft = null;
    clarificationSnapshot = null;
    clearCandidateRevisionDrafts();
    $("#intent-form").reset();
    $("#intent-candidate-editors").replaceChildren();
    intentDraftOwner = auth.user.id;
  }
  state.auth = { ...auth, authenticated: true };
  state.csrfToken = auth.csrf_token;
  document.body.classList.remove("auth-locked");
  document.body.classList.toggle("viewer-mode", auth.user.role === "viewer");
  $("#auth-gate").classList.add("hidden");
  $("#current-user").classList.remove("hidden");
  $("#password-button").classList.remove("hidden");
  $("#github-account-button").classList.toggle("hidden", auth.user.role === "viewer");
  $("#logout-button").classList.remove("hidden");
  $("#manage-users-button").classList.toggle("hidden", auth.user.role !== "admin");
  $("#current-user-actor").textContent = auth.user.actor;
  $("#current-user-role").textContent = auth.user.role;
  document.querySelectorAll(".authenticated-actor").forEach((node) => {
    node.textContent = auth.user.actor;
  });
}

function toast(message, tone = "neutral") {
  const node = $("#toast");
  node.dataset.tone = tone;
  I18n.setText(node,message);
  node.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => node.classList.remove("show"), 3200);
}

function setBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    if (button.getAttribute("aria-busy") !== "true") button.dataset.idleHtml = button.innerHTML;
    button.innerHTML = `<span class="button-spinner" aria-hidden="true"></span><span>${I18n.mark(label)}</span>`;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  } else {
    button.innerHTML = button.dataset.idleHtml || button.innerHTML;
    button.disabled = false;
    button.removeAttribute("aria-busy");
    delete button.dataset.idleHtml;
  }
}

function setIconButtonFeedback(button, { label, tooltip, iconName, duration = 1600 }) {
  const original = {
    html: button.innerHTML,
    label: button.getAttribute("aria-label") || "",
    tooltip: button.dataset.tooltip || "",
  };
  button.innerHTML = `${uiIcon(iconName)}${controlTooltip(tooltip)}`;
  button.setAttribute("aria-label", label);
  setControlTooltip(button, tooltip);
  button.disabled = true;
  window.setTimeout(() => {
    if (!button.isConnected) return;
    button.innerHTML = original.html;
    button.setAttribute("aria-label", original.label);
    setControlTooltip(button, original.tooltip);
    button.disabled = false;
  }, duration);
}

function setProjectMenuOpen(open) {
  const menu = $("#project-menu");
  const button = $("#project-menu-button");
  if (!menu || !button) return;
  menu.hidden = !open;
  button.setAttribute("aria-expanded", String(open));
  if (open) window.requestAnimationFrame(() => (menu.querySelector(".active") || menu.querySelector("button"))?.focus());
}

function setSecondaryActionsOpen(open) {
  const menu = $("#secondary-actions");
  const button = $("#more-actions-button");
  if (!menu || !button) return;
  menu.classList.toggle("open", open);
  button.setAttribute("aria-expanded", String(open));
  if (open) {
    window.requestAnimationFrame(() =>
      menu.querySelector("button:not(.hidden)")?.focus()
    );
  }
}

function handleSecondaryActionsKeydown(event) {
  if (event.key === "Tab") {
    setSecondaryActionsOpen(false);
    return;
  }
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const items = [...$("#secondary-actions").querySelectorAll('[role^="menuitem"]:not(.hidden):not(:disabled)')];
  if (!items.length) return;
  event.preventDefault();
  const currentIndex = items.indexOf(document.activeElement);
  let nextIndex = currentIndex;
  if (event.key === "ArrowDown") nextIndex = (currentIndex + 1) % items.length;
  if (event.key === "ArrowUp") nextIndex = (currentIndex - 1 + items.length) % items.length;
  if (event.key === "Home") nextIndex = 0;
  if (event.key === "End") nextIndex = items.length - 1;
  items[nextIndex].focus();
}

function parseCommand(value) {
  const source = value.trim();
  if (!source) return [];
  const parts = [];
  let current = "";
  let quote = null;
  let escaped = false;
  let started = false;
  for (const char of source) {
    if (escaped) {
      current += char;
      escaped = false;
      started = true;
    } else if (char === "\\" && quote !== "'") {
      escaped = true;
      started = true;
    } else if (quote) {
      if (char === quote) quote = null;
      else current += char;
      started = true;
    } else if (char === '"' || char === "'") {
      quote = char;
      started = true;
    } else if (/\s/.test(char)) {
      if (started) {
        parts.push(current);
        current = "";
        started = false;
      }
    } else {
      current += char;
      started = true;
    }
  }
  if (escaped) current += "\\";
  if (quote) throw new Error("Test command contains an unclosed quote");
  if (started) parts.push(current);
  return parts;
}

function displayRepo(project) {
  if (project.repo_label) return project.repo_label;
  return state.paperMode ? "registered://local-repository" : project.repo_path;
}

function applyPaperMode() {
  setSecondaryActionsOpen(false);
  document.body.classList.toggle("paper-mode", state.paperMode);
  const paperButton = $("#paper-mode-button");
  paperButton?.setAttribute("aria-checked", String(state.paperMode));
  paperButton?.setAttribute("aria-label", state.paperMode ? "Exit presentation view" : "Enter presentation view");
  const paperLabel = $("#paper-mode-label");
  if (paperLabel) paperLabel.textContent = state.paperMode ? "Exit presentation view" : "Presentation view";
  applyThemePreference(document.documentElement.dataset.themePreference || "light", false);
  if (state.activeProject) renderWorkspace();
  if (state.activeReview) renderReview();
}

function renderProjects() {
  const projectList = $("#project-list");
  if (projectList) {
    projectList.innerHTML = state.projects.map((project) => `
      <button type="button" class="project-card ${state.activeProject?.id === project.id ? "active" : ""}" data-project="${esc(project.id)}"${state.activeProject?.id === project.id ? ' aria-current="true"' : ""}>
        <strong>${esc(project.name)}</strong><span>Version ${project.version} · ${esc(short(project.head_ref))}</span>
      </button>`).join("");
  }
  const context = $("#project-context");
  if (context) context.hidden = state.projects.length === 0;
  const menu = $("#project-menu");
  if (menu) {
    const sourceLabel = (project) => project.source?.provider === "github" ? "GitHub" : "Local";
    menu.innerHTML = `${state.projects.map((project) => `
      <button type="button" class="project-menu-item${state.activeProject?.id === project.id ? " active" : ""}" role="menuitemradio" aria-checked="${state.activeProject?.id === project.id}" data-project-menu="${esc(project.id)}">
        <span class="project-menu-item-copy"><strong>${esc(project.name)}</strong><small>${esc(displayRepo(project))}</small></span>
        <span class="project-menu-item-meta"><span class="tag">${esc(sourceLabel(project))}</span><small>v${project.version}</small></span>
      </button>`).join("")}
      <div class="project-menu-actions"><button type="button" class="button button-small button-with-icon" role="menuitem" data-project-menu-action="github">${uiIcon("github")}<span>Analyze a pull request</span></button><button type="button" class="button button-small button-quiet" role="menuitem" data-project-menu-action="local" data-i18n=Register%20a%20local%20repository>Register a local repository</button></div>`;
    menu.querySelectorAll("[data-project-menu]").forEach((node) => node.addEventListener("click", () => {
      setProjectMenuOpen(false);
      if (node.dataset.projectMenu !== state.activeProject?.id) selectProject(node.dataset.projectMenu);
    }));
    menu.querySelectorAll("[data-project-menu-action]").forEach((node) => node.addEventListener("click", () => {
      setProjectMenuOpen(false);
      openProject(node.dataset.projectMenuAction);
    }));
  }
  const menuName = $("#project-menu-name");
  const menuMeta = $("#project-menu-meta");
  if (menuName) menuName.textContent = state.activeProject?.name || "Choose a project";
  if (menuMeta) menuMeta.textContent = state.activeProject ? `v${state.activeProject.version} · ${short(state.activeProject.head_ref)}` : "";
  const mobileProjectSelect = $("#mobile-project-select");
  if (mobileProjectSelect) {
    const mobileProjectControl = mobileProjectSelect.closest(".mobile-project-control");
    mobileProjectControl.hidden = state.projects.length === 0;
    mobileProjectSelect.innerHTML = state.projects.length
      ? state.projects.map((project) => `<option value="${esc(project.id)}">${esc(project.name)}</option>`).join("")
      : '<option value="" data-i18n=No%20project>No project</option>';
    mobileProjectSelect.disabled = state.projects.length === 0;
    mobileProjectSelect.value = state.activeProject?.id || "";
  }
  document.querySelectorAll("[data-project]").forEach((node) => {
    node.addEventListener("click", () => selectProject(node.dataset.project));
  });
}

function intakeIsOwned(operation) {
  return Boolean(operation && intakeOperation === operation
    && operation.userId === state.auth?.user?.id && operation.csrf === state.csrfToken
    && !document.body.classList.contains("auth-locked"));
}

function intakeViewIsCurrent(operation, opening = operation?.opening) {
  return intakeIsOwned(operation) && opening === intakeVersion && $("#project-dialog").open;
}

function beginIntakeOperation(source, details) {
  const operation = { ...details, source, status: "pending", userId: state.auth.user.id,
    csrf: state.csrfToken, opening: ++intakeVersion, selectionVersion: state.selectionVersion,
    startedUrl: location.href, error: "", result: null };
  intakeOperation = operation;
  renderIntakeOperation();
  $("#intake-operation").focus();
  return operation;
}

function resetIntakeSession() {
  intakeVersion += 1;
  intakeOperation = null;
  $("#project-dialog").close();
  $("#project-form").reset();
  state.github.status = null;
  state.github.repositories = [];
  state.github.selectedRepositoryId = null;
  state.github.pullRequests = [];
  state.github.selectedPullNumber = null;
  setBusy($("#project-submit-button"), false);
  setRepositorySource("github");
  renderIntakeOperation();
}

function renderIntakeOperation() {
  const operation = intakeIsOwned(intakeOperation) ? intakeOperation : null;
  const status = operation?.status;
  const github = operation?.source === "github";
  const receipt = ["pending", "saved", "uncertain"].includes(status);
  $(".project-intake-layout").hidden = receipt;
  $("#intake-operation").hidden = !receipt;
  $("#project-dialog").dataset.operationStatus = receipt ? status : "";
  $("#project-intake-selection").hidden = receipt;
  $("#intake-close-button").textContent = receipt ? "Close" : "Cancel";
  $("#project-error").textContent = operation?.error || "";
  $("#intake-open-result").hidden = status !== "saved";
  $("#intake-open-result").disabled = Boolean(operation?.openingResult);
  $("#intake-open-result").textContent = operation?.openingResult ? "Opening…" : github ? "Open review" : "Open project";
  $("#intake-check-workspace").hidden = status !== "uncertain";
  $("#intake-check-workspace").disabled = Boolean(operation?.checking);
  $("#intake-check-workspace").textContent = operation?.checking ? "Checking…" : "Check workspace";
  $("#intake-edit-settings").hidden = status !== "uncertain";
  $("#intake-edit-settings").disabled = Boolean(operation?.checking);
  const label = status === "pending" ? (github ? "Analysis running" : "Registering repository")
    : status === "saved" ? (github ? "Review saved" : "Repository registered") : "Import needs attention";
  const statusButton = $("#intake-status-button");
  statusButton.hidden = !operation;
  statusButton.querySelector(".intake-status-label").textContent = label;
  statusButton.querySelector(".intake-status-short").textContent = status === "pending" ? "Running" : status === "saved" ? "Saved" : "Check";
  statusButton.querySelector("use").setAttribute("href", status === "pending" ? "#icon-refresh" : status === "saved" ? "#icon-file-text" : "#icon-search");
  statusButton.setAttribute("aria-label", `${label}: ${operation?.label || ""}`);
  statusButton.title = `${label}: ${operation?.label || ""}`;
  if (receipt) {
    $("#intake-operation-context").textContent = operation.label;
    $("#intake-operation-title").textContent = status === "pending"
      ? github ? "Analyzing pull request" : "Registering repository"
      : status === "saved" ? github ? "Review saved" : "Repository registered" : "Response interrupted";
    $("#intake-operation-subject").textContent = operation.title;
    $("#intake-operation-detail").textContent = status === "pending"
      ? github ? "Preparing a read-only snapshot and checking the proposed change. Nothing is approved or merged."
        : "Reading the checkout and recording its current revision. Your repository is not modified."
      : status === "saved" ? "The result is saved in your workspace. Open it to continue; you do not need to submit it again."
        : "We could not confirm the result. Check the workspace for a matching saved result before submitting again.";
    $("#intake-operation-note").textContent = status === "pending"
      ? "You can close this window and keep working. Closing it does not cancel the request. Keep this browser page open to receive the result."
      : status === "saved" ? github ? "This is an analysis result, not a merge decision."
        : "Your checkout is unchanged. Open the project to compare revisions or describe a proposed change."
        : "Checking the workspace only reads saved projects and reviews.";
  }
  setBusy($("#project-submit-button"), false);
  updateProjectIntakeReadiness();
}

function rememberIntakeResult(operation, result) {
  if (!intakeIsOwned(operation)) return;
  operation.status = "saved";
  operation.result = result;
  operation.error = "";
  const index = state.projects.findIndex(item => item.id === result.project.id);
  if (index < 0) state.projects.unshift(result.project);
  else state.projects[index] = result.project;
  renderProjects();
  renderIntakeOperation();
}

async function openIntakeResult() {
  const operation = intakeOperation;
  if (!intakeIsOwned(operation) || operation.status !== "saved" || operation.openingResult) return;
  const opening = intakeVersion;
  operation.openingResult = true;
  operation.error = "";
  renderIntakeOperation();
  const version = state.selectionVersion + 1;
  try {
    await selectProject(operation.result.project.id);
    if (!intakeViewIsCurrent(operation, opening) || state.selectionVersion !== version) return;
    if (state.projectLoadError) throw new Error(state.projectLoadError);
    const reviewId = operation.result.review?.id;
    if (reviewId && state.activeReview?.id !== reviewId) {
      // selectProject may already have attempted this exact deep link.
      if (new URL(location.href).searchParams.get("review") === reviewId && state.viewMode === "review") {
        throw new Error("The saved review could not be loaded.");
      }
      const review = await selectReview(reviewId, version);
      if (!intakeViewIsCurrent(operation, opening) || state.selectionVersion !== version) return;
      if (!review) throw new Error("The saved review could not be loaded.");
    }
    if (intakeViewIsCurrent(operation, opening)) resetIntakeSession();
  } catch (error) {
    if (!intakeIsOwned(operation)) return;
    operation.error = `Saved, but the view could not be opened. ${error.message} Use Open ${operation.source === "github" ? "review" : "project"} to retry without submitting again.`;
  } finally {
    if (intakeIsOwned(operation)) {
      operation.openingResult = false;
      renderIntakeOperation();
      if (intakeViewIsCurrent(operation, opening) && operation.error) $("#project-error").focus();
    }
  }
}

async function checkIntakeWorkspace() {
  const operation = intakeOperation;
  if (!intakeIsOwned(operation) || operation.status !== "uncertain" || operation.checking) return;
  operation.checking = true;
  renderIntakeOperation();
  try {
    const projects = await api("/api/projects");
    if (!intakeIsOwned(operation)) return;
    const project = projects.find(item => operation.source === "github"
      ? item.source?.provider === "github" && item.source.repository_id === operation.repositoryId && item.source.installation_id === operation.installationId
      : item.repo_path === operation.repoPath && item.name === operation.title);
    let review = null;
    if (project && operation.source === "github") {
      const reviews = await api(`/api/projects/${project.id}/reviews`);
      if (!intakeIsOwned(operation)) return;
      review = reviews.find(item => item.external_url === operation.pullUrl
        && item.base_ref === operation.baseRef && item.target_ref === operation.targetRef);
    }
    if (project && (operation.source === "local" || review)) rememberIntakeResult(operation, { project, review });
    else operation.error = "No matching saved result was found yet. The request may still be running. Check again before submitting a new request.";
  } catch (error) {
    if (intakeIsOwned(operation)) operation.error = `Could not check the workspace. ${error.message} No new request was submitted.`;
  } finally {
    if (intakeIsOwned(operation)) {
      operation.checking = false;
      renderIntakeOperation();
      if ($("#project-dialog").open) $(operation.error ? "#project-error" : "#intake-operation").focus();
    }
  }
}

function updateProjectIntakeReadiness() {
  const button = $("#project-submit-button");
  const selection = $("#project-intake-selection");
  if (!button || !selection) return;
  const dialog = $("#project-dialog");
  if (intakeIsOwned(intakeOperation) && ["pending", "saved", "uncertain"].includes(intakeOperation.status)) {
    button.hidden = true;
    button.disabled = true;
    return;
  }
  if (state.github.source === "local") {
    const path = $("#project-form").elements.namedItem("repo_path").value.trim();
    button.disabled = !path;
    button.hidden = false;
    selection.dataset.ready = String(Boolean(path));
    if (dialog) dialog.dataset.intakeStage = path ? "ready" : "repository";
    selection.textContent = path ? `Local repository · ${path}` : "Enter an absolute local repository path";
    return;
  }
  const repository = state.github.repositories.find(
    (item) => item.id === state.github.selectedRepositoryId
  );
  const pullRequest = state.github.pullRequests.find(
    (item) => item.number === state.github.selectedPullNumber
  );
  const pullRequestReady = Boolean(pullRequest && !pullRequest.draft && !state.github.pullsLoading);
  button.disabled = !repository || !pullRequestReady;
  button.hidden = !repository || !pullRequestReady;
  selection.dataset.ready = String(Boolean(repository && pullRequestReady));
  if (dialog) dialog.dataset.intakeStage = pullRequestReady ? "ready" : repository ? "pull-request" : "repository";
  selection.textContent = repository && pullRequestReady
    ? `PR #${pullRequest.number} ready to analyze`
    : repository
      ? "Choose an open pull request"
      : state.github.status?.connected ? "Choose a repository" : "Connect GitHub to choose a pull request";
  $("#github-repository-picker").hidden = !state.github.status?.connected || Boolean(repository);
  $("#github-connection").hidden = Boolean(repository);
  $("#github-pull-request-step").classList.toggle("hidden", !repository);
}

function focusProjectIntake(source = state.github.source) {
  window.requestAnimationFrame(() => {
    if (!$("#project-dialog").open || state.github.source !== source) return;
    const target = source === "local"
      ? $("#project-form").elements.namedItem("repo_path")
      : !state.github.status?.connected
        ? $("#github-connect-button").disabled ? $("#github-connection summary") : $("#github-connect-button")
        : state.github.selectedRepositoryId
          ? $("#github-pull-request-search").checkVisibility() ? $("#github-pull-request-search") : $("#github-pull-request-title")
          : $("#github-repository-search");
    target?.focus();
  });
}

// A repository ID is not enough: A → B → A can have two requests for A.
// Also bind reads to this opening, source and authenticated session.
function githubRequestIsCurrent(kind) {
  const request = ++githubRequests[kind];
  const opening = intakeVersion;
  const userId = state.auth?.user?.id;
  const csrf = state.csrfToken;
  const source = state.github.source;
  return () => request === githubRequests[kind] && opening === intakeVersion
    && userId === state.auth?.user?.id && csrf === state.csrfToken
    && source === state.github.source && !document.body.classList.contains("auth-locked");
}

function setRepositorySource(source) {
  const normalized = source === "local" ? "local" : "github";
  if (state.github.source !== normalized) intakeVersion += 1;
  state.github.source = normalized;
  const githubActive = normalized === "github";
  $("#project-dialog").dataset.intakeSource = normalized;
  $("#project-form").elements.namedItem("repository_source").value = normalized;
  document.querySelectorAll(".repository-source-tabs [role=\"tab\"]").forEach((item) => {
    const selected = item.id === `${normalized}-source-tab`;
    item.classList.toggle("active", selected);
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  $("#github-source-panel").classList.toggle("hidden", !githubActive);
  $("#local-source-panel").classList.toggle("hidden", githubActive);
  $("#github-pull-request-step").classList.toggle(
    "hidden", !githubActive || !state.github.selectedRepositoryId
  );
  const form = $("#project-form");
  const settings = $("#project-intake-settings");
  for (const name of ["repo_path", "repo_label", "head_ref"]) {
    form.elements.namedItem(name).disabled = githubActive;
  }
  form.elements.namedItem("repo_path").required = !githubActive;
  form.elements.namedItem("head_ref").required = !githubActive;
  if (settings) settings.open = !githubActive;
  const intakeTitle = document.querySelector("#project-dialog .project-intake-head h2");
  const intakeIntro = document.querySelector("#project-dialog .project-intake-intro");
  $("#intake-safety-note").textContent = githubActive
    ? "Read-only: Consensus cannot change or merge the PR."
    : "Registration reads your checkout; it does not change files or run tests.";
  if (intakeTitle) intakeTitle.textContent = githubActive ? "Review a pull request" : "Register a local repository";
  if (intakeIntro) {
    intakeIntro.textContent = githubActive
      ? "Choose a repository and an open pull request to inspect its changes and evidence."
      : "Point to a Git checkout on this machine. Reviews then compare two immutable revisions of that repository.";
  }
  $("#project-submit-button").textContent = githubActive ? "Analyze PR" : "Register repository";
  updateProjectIntakeReadiness();
}

function handleRepositorySourceTabKeydown(event) {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  const tabs = [...document.querySelectorAll(".repository-source-tabs [role=\"tab\"]")];
  const current = tabs.indexOf(event.currentTarget);
  if (current < 0) return;
  let next = current;
  if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
  if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") next = 0;
  if (event.key === "End") next = tabs.length - 1;
  event.preventDefault();
  const target = tabs[next];
  const source = target.id === "local-source-tab" ? "local" : "github";
  setRepositorySource(source);
  target.focus();
  if (source === "github") loadGitHubStatus({ loadRepositories: true });
}

function renderGitHubConnection() {
  const status = state.github.status;
  const connect = $("#github-connect-button");
  const install = $("#github-install-button");
  const disconnect = $("#github-disconnect-button");
  const connection = $("#github-connection");
  $("#github-status-retry-button").classList.add("hidden");
  connection.open = !status?.connected;
  connection.dataset.connected = String(Boolean(status?.connected));
  updateProjectIntakeReadiness();
  if (!status) {
    $("#github-connection-status").textContent = "Checking connection…";
    $("#github-connection-detail").textContent = "Only repositories explicitly granted to the app are listed.";
    connect.disabled = true;
    connect.classList.remove("hidden");
    install.classList.add("hidden");
    disconnect.classList.add("hidden");
    return;
  }
  connect.classList.toggle("hidden", status.connected);
  disconnect.classList.toggle("hidden", !status.connected);
  install.classList.toggle("hidden", !status.configured || !status.install_url);
  if (status.install_url) install.href = status.install_url;
  connect.disabled = !status.connection_allowed || (status.setup_required && !status.setup_allowed);
  if (!status.configured) {
    $("#github-connection-status").textContent = "Sign in with GitHub";
    $("#github-connection-detail").textContent = status.setup_allowed
      ? "Continue in your browser. The read-only connector is prepared automatically on first use."
      : "An administrator needs to enable GitHub once for this instance.";
    return;
  }
  if (!status.connected) {
    $("#github-connection-status").textContent = "No GitHub account connected";
    $("#github-connection-detail").textContent = status.connection_allowed
      ? "Sign in in your browser, then choose which repositories may be read."
      : "A read-only role cannot connect an external account.";
    return;
  }
  $("#github-connection-status").textContent = `Connected as @${status.login}`;
  $("#github-connection-detail").textContent = "Tokens are encrypted locally. Remote writes are not enabled.";
}

function renderGitHubRepositories() {
  const query = $("#github-repository-search").value.trim().toLowerCase();
  const repositories = state.github.repositories.filter((repository) =>
    !query || repository.full_name.toLowerCase().includes(query)
      || String(repository.description || "").toLowerCase().includes(query)
  );
  if (!repositories.length) {
    $("#github-repository-list").innerHTML = `<p class="repository-list-empty">${state.github.repositories.length ? "No repositories match this search." : "No accessible repositories. Use Repository access to grant one."}</p>`;
    updateProjectIntakeReadiness();
    return;
  }
  $("#github-repository-list").innerHTML = repositories.map((repository) => {
    const selected = state.github.selectedRepositoryId === repository.id;
    const visibility = repository.visibility === "private" ? "Private" : title(repository.visibility);
    const updated = repository.updated_at
      ? `Updated ${new Date(repository.updated_at).toLocaleDateString()}`
      : "Update time unavailable";
    return `<button class="github-repository-card ${selected ? "selected" : ""}" type="button" data-github-repository="${repository.id}" aria-pressed="${selected}">
      <span class="repository-selection-dot" aria-hidden="true"></span>
      <span class="repository-card-copy"><strong>${esc(repository.full_name)}</strong><small>${esc(repository.description || "No repository description")}</small><span>${esc(visibility)} · ${esc(repository.default_branch)} · ${esc(updated)}</span></span>
    </button>`;
  }).join("");
  document.querySelectorAll("[data-github-repository]").forEach((button) => {
    button.addEventListener("click", () => {
      const repository = state.github.repositories.find(
        (item) => item.id === Number(button.dataset.githubRepository)
      );
      if (!repository) return;
      const changedRepository = state.github.selectedRepositoryId !== repository.id;
      state.github.selectedRepositoryId = repository.id;
      if (changedRepository) {
        state.github.pullRequests = [];
        state.github.selectedPullNumber = null;
      }
      const nameField = $("#project-form").elements.name;
      nameField.value = repository.name;
      renderGitHubRepositories();
      loadGitHubPullRequests(repository);
    });
  });
  updateProjectIntakeReadiness();
}

function renderGitHubPullRequests(repository) {
  const step = $("#github-pull-request-step");
  const list = $("#github-pull-request-list");
  if (!step || !list) return;
  step.classList.toggle("hidden", !repository || state.github.source !== "github");
  $("#github-pull-request-repository").textContent = repository?.full_name || "";
  if (!repository) {
    list.innerHTML = '<p class="repository-list-empty" data-i18n=Select%20a%20repository%20first.>Select a repository first.</p>';
    return;
  }
  const query = $("#github-pull-request-search").value.trim().toLowerCase();
  const pulls = state.github.pullRequests.filter(pull => !query || [pull.title, `#${pull.number}`, pull.head_ref, pull.base_ref, pull.author].some(value => String(value).toLowerCase().includes(query)));
  $(".github-pull-search").hidden = !state.github.pullRequests.length;
  $("#github-pull-search-status").textContent = query
    ? `${pulls.length} of ${plural(state.github.pullRequests.length, "pull request")}`
    : state.github.pullRequests.length ? `${plural(state.github.pullRequests.length, "open pull request")}. Drafts must be marked ready on GitHub.` : "";
  if (!state.github.pullRequests.length) {
    list.innerHTML = '<div class="repository-list-empty"><strong>No open pull requests</strong><p>Open a PR on GitHub, or register a local checkout to compare revisions.</p><button class="button button-small" id="use-local-comparison-button" type="button" data-i18n=Use%20a%20local%20repository>Use a local repository</button></div>';
    $("#use-local-comparison-button")?.addEventListener("click", () => {
      setRepositorySource("local");
      focusProjectIntake("local");
    });
    updateProjectIntakeReadiness();
    return;
  }
  if (!pulls.length) {
    list.innerHTML = '<div class="repository-list-empty"><strong>No pull requests match this search</strong><button class="button button-small" id="github-clear-pull-search" type="button" data-i18n=Clear%20search>Clear search</button></div>';
    $("#github-clear-pull-search").addEventListener("click", () => {
      $("#github-pull-request-search").value = "";
      renderGitHubPullRequests(repository);
      $("#github-pull-request-search").focus();
    });
    updateProjectIntakeReadiness();
    return;
  }
  list.innerHTML = pulls.map((pullRequest) => {
    const selected = state.github.selectedPullNumber === pullRequest.number;
    const updated = pullRequest.updated_at
      ? `Updated ${new Date(pullRequest.updated_at).toLocaleDateString()}`
      : "Update time unavailable";
    return `<button class="github-pull-request-card ${selected ? "selected" : ""}" type="button" data-github-pull-request="${pullRequest.number}" aria-pressed="${selected}" ${pullRequest.draft ? "disabled" : ""} aria-label="${esc(pullRequest.draft ? `Draft pull request #${pullRequest.number}; mark it ready for review before analysis` : `Select pull request #${pullRequest.number}: ${pullRequest.title}`)}">
      <span class="repository-selection-dot" aria-hidden="true"></span>
      <span class="pull-request-card-copy"><span><b>#${pullRequest.number}</b>${pullRequest.draft ? '<em data-i18n=Draft>Draft</em>' : ""}</span><strong>${esc(pullRequest.title)}</strong><small>${esc(pullRequest.head_ref)} → ${esc(pullRequest.base_ref)}</small><small>@${esc(pullRequest.author)} · ${esc(updated)}</small></span>
    </button>`;
  }).join("");
  document.querySelectorAll("[data-github-pull-request]").forEach((button) => {
    button.addEventListener("click", () => {
      state.github.selectedPullNumber = Number(button.dataset.githubPullRequest);
      document.querySelectorAll("[data-github-pull-request]").forEach(item => {
        const selected = Number(item.dataset.githubPullRequest) === state.github.selectedPullNumber;
        item.classList.toggle("selected", selected);
        item.setAttribute("aria-pressed", String(selected));
      });
      updateProjectIntakeReadiness();
    });
  });
  updateProjectIntakeReadiness();
}

async function loadGitHubPullRequests(repository) {
  const step = $("#github-pull-request-step");
  const list = $("#github-pull-request-list");
  if (!step || !list || !repository) return;
  const current = githubRequestIsCurrent("pulls");
  state.github.pullsLoading = true;
  state.github.pullRequests = [];
  state.github.selectedPullNumber = null;
  $("#github-pull-request-search").value = "";
  $(".github-pull-search").hidden = true;
  $("#github-pull-search-status").textContent = "";
  step.classList.remove("hidden");
  $("#github-pull-request-repository").textContent = repository.full_name;
  list.innerHTML = '<p class="repository-list-empty loading">Loading open pull requests…</p>';
  updateProjectIntakeReadiness();
  focusProjectIntake();
  try {
    const pullRequests = await api(
      `/api/github/repositories/${repository.id}/pulls?installation_id=${repository.installation_id}`
    );
    if (!current() || state.github.selectedRepositoryId !== repository.id) return;
    state.github.pullsLoading = false;
    state.github.pullRequests = pullRequests;
    renderGitHubPullRequests(repository);
    if (document.activeElement === $("#github-pull-request-title")) focusProjectIntake();
  } catch (error) {
    if (!current() || state.github.selectedRepositoryId !== repository.id) return;
    state.github.pullsLoading = false;
    state.github.pullRequests = [];
    state.github.selectedPullNumber = null;
    const installUrl = safeHttpUrl(state.github.status?.install_url);
    list.innerHTML = `<div class="repository-list-error"><p role="alert">${esc(error.message)}</p><div><button class="button button-small" id="github-pull-retry-button" type="button" data-i18n=Try%20again>Try again</button>${installUrl ? `<a class="button button-small" href="${esc(installUrl)}">Manage GitHub access</a>` : ""}</div></div>`;
    $("#github-pull-retry-button")?.addEventListener("click", () => loadGitHubPullRequests(repository));
    updateProjectIntakeReadiness();
  }
}

async function loadGitHubRepositories() {
  const current = githubRequestIsCurrent("repositories");
  $("#github-repository-list").innerHTML = '<p class="repository-list-empty loading">Loading accessible repositories…</p>';
  try {
    const repositories = await api("/api/github/repositories");
    if (!current()) return;
    state.github.repositories = repositories;
    if (!state.github.repositories.some((item) => item.id === state.github.selectedRepositoryId)) {
      state.github.selectedRepositoryId = null;
      state.github.pullRequests = [];
      state.github.selectedPullNumber = null;
    }
    renderGitHubRepositories();
  } catch (error) {
    if (!current()) return;
    $("#github-repository-list").innerHTML = `<div class="repository-list-error"><p>${esc(error.message)}</p><button class="button button-small" id="github-retry-button" type="button" data-i18n=Try%20again>Try again</button></div>`;
    $("#github-retry-button")?.addEventListener("click", loadGitHubRepositories);
  }
}

async function loadGitHubStatus({ loadRepositories = false } = {}) {
  const current = githubRequestIsCurrent("status");
  state.github.status = null;
  renderGitHubConnection();
  try {
    const status = await api("/api/github/status");
    if (!current()) return;
    state.github.status = status;
    renderGitHubConnection();
    // Do not steal focus if the user already moved to another control.
    if ([ $("#github-connection summary"), $("#github-connect-button") ].includes(document.activeElement)) focusProjectIntake();
    if (loadRepositories && state.github.status.connected) await loadGitHubRepositories();
  } catch (error) {
    if (!current()) return;
    $("#github-connection-status").textContent = "GitHub status unavailable";
    $("#github-connection-detail").textContent = error.message;
    $("#github-status-retry-button").classList.remove("hidden");
  }
}

async function selectProject(projectId) {
  rememberReviewLocation();
  closeSnapshotFile(false);
  const version = ++state.selectionVersion;
  state.reviewSelectionVersion += 1;
  const project = state.projects.find((item) => item.id === projectId);
  if (!project) return;
  governanceReviewOrigin = null;
  closeReviewOperations();
  const switchingProject = state.activeProject && state.activeProject.id !== projectId;
  state.activeProject = project;
  $("#review-filter").value = reviewQueries.get(projectId) || "";
  if (switchingProject && !restoringWorkspaceHistory) {
    state.viewMode = "canvas";
    setViewParam("canvas");
  }
  canvasState = { query: "", selected: null, panel: "overview", panelOpen: true, mode: "focus", focusId: null, snapshotFile: null, filesExpanded:false };
  state.activeReview = null;
  state.contractGraph = null;
  state.manifest = null;
  state.events = [];
  state.projectEvents = [];
  state.projectTree = null;
  state.projectTreeLoading = true;
  state.reviewsLoading = true;
  state.projectLoadError = null;
  state.intents = [];
  state.reviews = [];
  state.aiRuns = [];
  state.aiEvals = null;
  state.activeCopilotRun = null;
  renderProjects();
  renderWorkspace();
  try {
    const [reviews, projectEvents, intents, aiRuns, aiEvals, projectTree] = await Promise.all([
      api(`/api/projects/${projectId}/reviews`),
      api(`/api/projects/${projectId}/events`),
      api(`/api/projects/${projectId}/intents`),
      api(`/api/projects/${projectId}/ai/runs`),
      api(`/api/projects/${projectId}/ai/evals`),
      loadProjectTree(projectId).catch((error) => ({ error: error.message, entries: [] })),
    ]);
    if (version !== state.selectionVersion) return;
    state.reviewsLoading = false;
    state.reviews = reviews;
    state.projectEvents = projectEvents;
    state.intents = intents;
    state.aiRuns = aiRuns;
    state.aiEvals = aiEvals;
    state.projectTree = projectTree;
    state.projectTreeLoading = false;
    renderWorkspace();
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("review");
    const selected = reviews.find((item) => item.id === requested);
    if (selected) await selectReview(selected.id, version);
    else if (params.get("view") === "governance") showGovernance();
    else if (params.get("view") === "intents") showIntents();
    else if (params.get("view") === "review") { state.viewMode = "review"; showReviews(); }
    else showProjectCanvas();
  } catch (error) {
    if (version === state.selectionVersion) {
      state.projectTreeLoading = false;
      state.reviewsLoading = false;
      state.projectLoadError = error.message;
      renderProjectTree();
      renderWorkspace();
      toast(error.message, "error");
    }
  }
}

async function loadProjectTree(projectId) {
  return api(`/api/projects/${projectId}/tree`);
}

function buildProjectTree(entries = []) {
  const root = { children: new Map() };
  entries.filter((entry) => entry.kind === "file").forEach((entry) => {
    const parts = entry.path.split("/").filter(Boolean);
    let branch = root;
    let currentPath = "";
    parts.forEach((name, index) => {
      currentPath = currentPath ? `${currentPath}/${name}` : name;
      if (!branch.children.has(name)) {
        branch.children.set(name, {
          name,
          path: currentPath,
          kind: index === parts.length - 1 ? "file" : "directory",
          children: new Map(),
        });
      }
      branch = branch.children.get(name);
    });
  });
  const sortBranch = (node) => [...node.children.values()]
    .sort((left, right) => {
      if (left.kind !== right.kind) return left.kind === "directory" ? -1 : 1;
      return left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
    })
    .map((child) => ({ ...child, children: sortBranch(child) }));
  return sortBranch(root);
}

function renderProjectTreeNodes(nodes, changedPaths, level = 1) {
  return nodes.map((node) => {
    const changed = node.kind === "file"
      ? changedPaths.has(node.path)
      : node.children.some((child) => child.kind === "file" ? changedPaths.has(child.path) : child.path && [...changedPaths].some((path) => path.startsWith(`${child.path}/`)));
    if (node.kind === "directory") {
      return `<details class="file-tree-directory"${level < 2 ? " open" : ""}>
        <summary title="${esc(node.path)}"><span class="file-tree-chevron" aria-hidden="true">›</span><span class="file-tree-folder" aria-hidden="true"></span><span>${esc(node.name)}</span>${changed ? '<i aria-label="Contains reviewed changes"></i>' : ""}</summary>
        <div>${renderProjectTreeNodes(node.children, changedPaths, level + 1)}</div>
      </details>`;
    }
    return `<button class="file-tree-file${changed ? " changed" : ""}" type="button" data-file-path="${esc(node.path)}" title="${esc(node.path)}"><span class="file-tree-file-icon" aria-hidden="true"></span><span>${esc(node.name)}</span>${changed ? '<i aria-label="Changed in this review"></i>' : ""}</button>`;
  }).join("");
}

function renderProjectTree() {
  const tree = $("#project-file-tree");
  const status = $("#project-file-state");
  const revision = $("#project-tree-revision");
  if (!tree || !status || !revision) return;
  renderInspectorChangedFiles();
  if (state.projectTreeLoading) {
    status.textContent = "Loading snapshot…";
    revision.textContent = "Loading files…";
    tree.innerHTML = '<div class="file-tree-empty" role="status">Reading the governed Git snapshot…</div>';
    return;
  }
  if (!state.projectTree || state.projectTree.error) {
    const message = state.projectTree?.error || "Choose a project to see its files.";
    status.textContent = state.projectTree?.error ? "Snapshot unavailable" : "No project selected";
    revision.textContent = "Project snapshot";
    tree.innerHTML = `<div class="file-tree-empty">${esc(message)}</div>`;
    return;
  }
  const files = state.projectTree.entries.filter((entry) => entry.kind === "file");
  const changedPaths = new Set(state.activeReview?.changed_paths || []);
  const filterBox = $("#project-file-filter");
  if (filterBox) filterBox.classList.toggle("hidden", files.length <= 12);
  const query = ($("#project-file-search")?.value || "").trim().toLowerCase();
  const visibleEntries = query
    ? state.projectTree.entries.filter((entry) => entry.kind === "file" && entry.path.toLowerCase().includes(query))
    : state.projectTree.entries;
  const nodes = buildProjectTree(visibleEntries);
  status.textContent = state.projectTree.truncated
    ? `${plural(files.length, "file")} shown · limited view`
    : plural(files.length, "tracked file");
  revision.textContent = `Snapshot ${short(state.projectTree.revision)}`;
  tree.innerHTML = nodes.length
    ? renderProjectTreeNodes(nodes, changedPaths, query ? 0 : 1)
    : `<div class="file-tree-empty">${query ? `No file matches “${esc(query)}”.` : "No tracked files at this revision."}</div>`;
  tree.querySelectorAll("[data-file-path]").forEach((node) => {
    node.addEventListener("click", () => openChangedFile(node.dataset.filePath));
  });
}

async function openChangedFile(path, findingId = "") {
  if (!state.activeReview?.changed_paths?.includes(path)) {
    openSnapshotFile(path);
    return;
  }
  const reviewId = state.activeReview.id;
  state.diffInspection = findingId ? {reviewId, revision:state.activeReview.revision, path, findingId} : null;
  state.diffPath = path;
  state.diffQuery = "";
  setReviewWorkspaceTab("changes", { focus: true });
  await ensureDiffLoaded();
  if (state.activeReview?.id !== reviewId || state.diffPath !== path) return;
  renderDiffViewer();
  if (window.innerWidth <= 960) setFilePanelOpen(false);
  const target = findingId ? document.querySelector(`[data-finding-location="${CSS.escape(findingId)}"]`) : null;
  const destination = target || $("#diff-viewer");
  destination?.focus({ preventScroll: true });
  destination?.scrollIntoView({ behavior: "instant", block: "nearest" });
}

function closeSnapshotFile(restoreFocus = true) {
  if (!snapshotReader) return;
  snapshotReader.restoreFocus = restoreFocus;
  const dialog = $("#snapshot-file-dialog");
  if (dialog.open) dialog.close();
  resetSnapshotReader();
}

function resetSnapshotReader() {
  const context = snapshotReader;
  snapshotReader = null;
  context?.controller.abort();
  $("#snapshot-file-code").replaceChildren();
  $("#snapshot-file-title").textContent = "Read snapshot file";
  $("#snapshot-file-context").textContent = "";
  $("#snapshot-file-metadata").replaceChildren();
  $("#snapshot-file-search").value = "";
  $("#snapshot-file-error p").textContent = "";
  $("#snapshot-file-notice").textContent = "";
  $("#snapshot-file-limit").textContent = "";
  if (context?.restoreFocus && context.opener?.isConnected && context.opener.checkVisibility()
    && !document.body.classList.contains("auth-locked")) context.opener.focus({ preventScroll: true });
}

async function openSnapshotFile(path) {
  const project = state.activeProject, revision = state.projectTree?.revision;
  if (!project || !revision || !state.projectTree.entries?.some(entry => entry.kind === "file" && entry.path === path)) {
    toast("This file is not in the loaded project snapshot. Open Files and refresh the snapshot.", "error");
    return;
  }
  closeSnapshotFile(false);
  snapshotReader = { projectId: project.id, projectName: project.name, revision, path,
    owner: state.auth?.user?.id, session: state.csrfToken, opener: document.activeElement,
    restoreFocus: true, controller: new AbortController(), lines: [], matches: [], match: -1 };
  $("#snapshot-file-title").textContent = path.split("/").at(-1);
  $("#snapshot-file-context").textContent = `Read-only · ${project.name} · Snapshot ${short(revision)}. Not the working copy or a proposed change.`;
  $("#snapshot-file-details").open = false;
  $("#snapshot-file-code").classList.toggle("wrap", window.matchMedia("(max-width: 600px)").matches);
  $("#snapshot-file-wrap").setAttribute("aria-pressed", String($("#snapshot-file-code").classList.contains("wrap")));
  $("#snapshot-file-dialog").showModal();
  await loadSnapshotFile(snapshotReader);
}

async function loadSnapshotFile(context) {
  if (!context || snapshotReader !== context) return;
  const current = () => snapshotReader === context && state.activeProject?.id === context.projectId
    && state.auth?.user?.id === context.owner && state.csrfToken === context.session;
  $("#snapshot-file-body").setAttribute("aria-busy", "true");
  $("#snapshot-file-error").hidden = true;
  $("#snapshot-file-code").hidden = true;
  $("#snapshot-file-code").replaceChildren();
  $("#snapshot-file-notice").textContent = "Reading this Git snapshot…";
  $("#snapshot-file-search-status").textContent = "";
  $("#snapshot-file-limit").textContent = "";
  ["#snapshot-file-search", "#snapshot-file-wrap", "#snapshot-match-previous", "#snapshot-match-next"].forEach(selector => { $(selector).disabled = true; });
  try {
    const query = new URLSearchParams({ path: context.path, revision: context.revision });
    const file = await api(`/api/projects/${encodeURIComponent(context.projectId)}/file?${query}`, { signal: context.controller.signal });
    if (!current()) return;
    if (file.project_id !== context.projectId || file.revision !== context.revision || file.path !== context.path) throw new Error("The response does not match this snapshot. Close the file and reload the workspace.");
    const metadata = { Path: file.path, "Snapshot commit": file.revision, "Git object": file.object_id,
      "File size": file.byte_size === null ? "Not a file blob" : `${file.byte_size.toLocaleString()} bytes` };
    $("#snapshot-file-metadata").innerHTML = Object.entries(metadata).map(([label,value]) => `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join("");
    const notices = { empty: "This file is empty at the selected snapshot.",
      binary: "A text preview is unavailable for binary or non-UTF-8 content. Nothing has been executed.",
      too_large: `This file exceeds the ${Math.round(file.byte_limit / 1024)} KiB preview limit. Its content has not been loaded.`,
      symlink: "This is a symbolic link. Its target is not followed or read.",
      submodule: "This entry is a Git submodule. Its checkout is not opened." };
    if (file.status === "text") {
      const lines = file.content.split("\n");
      if (lines.at(-1) === "") lines.pop();
      context.lines = lines.slice(0, 3000);
      $("#snapshot-file-code").innerHTML = context.lines.map((line,index) => `<span class="snapshot-code-line" data-line="${index + 1}"><span class="snapshot-line-number" aria-hidden="true">${index + 1}</span><code class="snapshot-line-text">${esc(line.replace(/\r$/, ""))}</code></span>`).join("");
      $("#snapshot-file-code").hidden = false;
      $("#snapshot-file-notice").textContent = "";
      $("#snapshot-file-limit").textContent = lines.length > 3000 ? `Showing the first 3,000 of ${lines.length.toLocaleString()} lines. Search covers this preview only.` : "";
      $("#snapshot-file-search").disabled = false;
      $("#snapshot-file-wrap").disabled = false;
      searchSnapshotFile();
    } else $("#snapshot-file-notice").textContent = notices[file.status] || "This entry cannot be previewed as text.";
    $("#snapshot-file-body").scrollTop = 0;
  } catch (error) {
    if (!current()) return;
    $("#snapshot-file-notice").textContent = "";
    $("#snapshot-file-error p").textContent = `Couldn’t read this file. ${error.message}`;
    $("#snapshot-file-error").hidden = false;
    $("#snapshot-file-retry").hidden = error.status === 409;
    $("#snapshot-file-reload").hidden = error.status !== 409;
  } finally {
    if (current()) $("#snapshot-file-body").setAttribute("aria-busy", "false");
  }
}

function searchSnapshotFile(direction = 0) {
  const context = snapshotReader;
  if (!context) return;
  const query = $("#snapshot-file-search").value.toLowerCase();
  if (!direction) {
    context.matches = query ? context.lines.flatMap((line,index) => line.toLowerCase().includes(query) ? [index] : []) : [];
    context.match = context.matches.length ? 0 : -1;
  } else if (context.matches.length) context.match = (context.match + direction + context.matches.length) % context.matches.length;
  const matches = new Set(context.matches);
  $("#snapshot-file-code").querySelectorAll(".snapshot-code-line").forEach((line,index) => {
    line.classList.toggle("search-match", matches.has(index));
    line.classList.toggle("search-current", context.matches[context.match] === index);
  });
  $("#snapshot-file-search-status").textContent = !query ? "" : context.matches.length
    ? `${context.match + 1} of ${plural(context.matches.length, "matching line")} · Line ${context.matches[context.match] + 1}`
    : "No matching lines in this preview. Try a different term.";
  ["#snapshot-match-previous", "#snapshot-match-next"].forEach(selector => { $(selector).disabled = !context.matches.length; });
  $("#snapshot-file-code .search-current")?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
}

$("#snapshot-file-dialog").addEventListener("close", () => { if (!$("#snapshot-file-dialog").open) resetSnapshotReader(); });
$("#snapshot-file-dialog").addEventListener("cancel", event => {
  event.preventDefault();
  closeSnapshotFile();
});
$("#snapshot-file-dialog").addEventListener("keydown", event => {
  if (event.key !== "Tab") return;
  const controls = [...event.currentTarget.querySelectorAll("button,input,summary,[tabindex]")]
    .filter(node => !node.disabled && node.tabIndex >= 0 && node.checkVisibility());
  const first = controls[0], last = controls.at(-1);
  if ((event.shiftKey && document.activeElement === first)
    || (!event.shiftKey && document.activeElement === last)) {
    event.preventDefault();
    (event.shiftKey ? last : first)?.focus();
  }
});
$("#snapshot-file-search").addEventListener("input", () => searchSnapshotFile());
$("#snapshot-file-search").addEventListener("keydown", event => {
  if (event.key === "Enter") { event.preventDefault(); searchSnapshotFile(event.shiftKey ? -1 : 1); }
});
$("#snapshot-match-previous").onclick = () => searchSnapshotFile(-1);
$("#snapshot-match-next").onclick = () => searchSnapshotFile(1);
$("#snapshot-file-wrap").onclick = () => {
  const wrapped = $("#snapshot-file-code").classList.toggle("wrap");
  $("#snapshot-file-wrap").setAttribute("aria-pressed", String(wrapped));
};
$("#snapshot-file-retry").onclick = () => loadSnapshotFile(snapshotReader);
$("#snapshot-file-reload").onclick = () => window.location.reload();

function renderInspectorChangedFiles() {
  const mount = $("#inspector-changed-files");
  if (!mount) return;
  const review = state.activeReview;
  if (!review?.changed_paths?.length) {
    mount.innerHTML = "";
    return;
  }
  const files = changedFileStats(review);
  mount.innerHTML = `<div class="inspector-changed-head">Changed in this review<span>${plural(files.length, "file")}</span></div>
    <div class="inspector-changed-list">${files.map((item) => `<button type="button" class="inspector-changed-file" data-changed-file="${esc(item.path)}" aria-current="${state.diffPath === item.path ? "true" : "false"}" title="${esc(item.path)}"><span>${esc(item.path)}</span><small>${item.additions === null ? "Open diff" : `<b class="add">+${item.additions}</b> <b class="del">−${item.deletions}</b>${item.partial ? " shown" : ""}`}</small></button>`).join("")}</div>`;
  mount.querySelectorAll("[data-changed-file]").forEach((node) => {
    node.addEventListener("click", () => openChangedFile(node.dataset.changedFile));
  });
}

function setFilePanelOpen(open, { focus = false } = {}) {
  const entering = open && !state.filePanelOpen;
  if (open && !state.filePanelOpen) inspectorOpener = document.activeElement;
  state.filePanelOpen = Boolean(open);
  if (state.viewMode === "review") state.filePanelPreference = state.filePanelOpen;
  const workbench = $("#review-workbench");
  const panel = $("#project-file-panel");
  const toggle = $("#toggle-file-panel-button");
  workbench?.classList.toggle("files-collapsed", !state.filePanelOpen);
  panel?.classList.toggle("open", state.filePanelOpen);
  panel?.setAttribute("aria-hidden", String(!state.filePanelOpen));
  toggle?.setAttribute("aria-expanded", String(state.filePanelOpen));
  toggle?.setAttribute("aria-label", state.filePanelOpen ? "Hide review inspector" : "Show review inspector");
  const label = $("#file-panel-button-label");
  if (label) I18n.setText(label,"Inspector");
  if (toggle) setControlTooltip(toggle, state.filePanelOpen ? "Hide inspector" : "Show inspector");
  if (entering) ReviewMotion.enter(panel,"inspector");
  if (focus && state.filePanelOpen) document.querySelector(`[data-inspector-tab="${state.inspectorTab}"]`)?.focus();
}

function closeReviewInspector() {
  setFilePanelOpen(false);
  const entryPoint = state.inspectorTab === "assistant" ? ".open-ai-inspector-button" : ".open-files-inspector-button";
  const target = [inspectorOpener, $(entryPoint), $("#toggle-file-panel-button")].find((node) =>
    node?.isConnected && node.getClientRects().length && node.matches("button, summary, a[href], input, select, textarea, [tabindex]"));
  target?.focus({ preventScroll: true });
  inspectorOpener = null;
}

function setInspectorTab(tab, { focus = false, open = false } = {}) {
  const button = document.querySelector(`[data-inspector-tab="${tab}"]`);
  const panel = document.querySelector(`[data-inspector-panel="${tab}"]`);
  if (!button || !panel) return;
  state.inspectorTab = tab;
  if (open) setFilePanelOpen(true);
  document.querySelectorAll("[data-inspector-tab]").forEach((item) => {
    const selected = item.dataset.inspectorTab === tab;
    item.classList.toggle("active", selected);
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll("[data-inspector-panel]").forEach((item) => {
    item.classList.toggle("hidden", item.dataset.inspectorPanel !== tab);
  });
  if (focus) button.focus();
}

function handleInspectorTabKeydown(event) {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  const tabs = [...document.querySelectorAll("[data-inspector-tab]")];
  const current = tabs.indexOf(event.currentTarget);
  if (current < 0) return;
  let next = current;
  if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
  if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") next = 0;
  if (event.key === "End") next = tabs.length - 1;
  event.preventDefault();
  setInspectorTab(tabs[next].dataset.inspectorTab, { focus: true });
}

function claimTone(claim) {
  return claim.status === "validated" ? "ok" : claim.status === "contested" ? "danger" : claim.status === "superseded" ? "neutral" : "warn";
}

function renderProjectClaims() {
  const list = $("#project-claims-list");
  const count = $("#project-claims-count");
  const project = state.activeProject;
  if (!list || !project) return;
  if($("#rules-context")) $("#rules-context").innerHTML=`<span>${uiIcon('shield-check')}<span><span data-i18n=Policy>Policy</span> <code>${esc(project.policy_id)}</code></span></span><span>${uiIcon('user')}<span>Decision authority <b>${esc(project.default_authority || 'Unassigned')}</b></span></span>`;
  const expanded = new Set(list.dataset.projectId === project.id
    ? [...list.querySelectorAll("details[open][data-governance-claim]")].map(node => node.dataset.governanceClaim) : []);
  list.dataset.projectId = project.id;
  const claims = project.claims || [];
  if (count) count.textContent = claims.length ? `${plural(claims.length, "claim")} · ${plural(claims.filter((claim) => claim.status === "validated").length, "validated")}` : "";
  list.innerHTML = claims.length ? claims.map((claim) => {
    const touching = governanceClaimReviews(project, claim);
    const obligations = (claim.evidence_obligations || []).length;
    return `<details class="claim-row" data-governance-claim="${esc(claim.id)}"${expanded.has(claim.id) ? " open" : ""}>
      <summary>
      <div class="claim-row-copy">
        <div class="claim-row-title"><strong>${esc(claim.title)}</strong><span class="tag" data-tone="${claimTone(claim)}">${esc(sentence(claim.status))}</span></div>
        <p>${esc(claim.rationale || "No rationale recorded.")}</p>
      </div>
      <div class="claim-row-side"><span>${plural(obligations, "evidence requirement")}</span><span>${state.reviewsLoading ? "Loading related reviews…" : state.projectLoadError ? "Review context unavailable" : plural(touching.length, "related review")}</span></div>
      </summary>
      <div class="claim-detail">
        <p class="claim-state-context"><strong>Current project state · version ${esc(project.version)}</strong><span>${esc(sentence(claim.status))} is this claim’s recorded status, not an approval of a proposed change. Review evidence and readiness are assessed separately.</span></p>
        <div class="claim-detail-grid">
          <section aria-label="Evidence requirements for ${esc(claim.title)}"><h4>Evidence requirements</h4><p class="claim-detail-hint">Configured for this claim now. Each review keeps its own requirement snapshot.</p>${renderGovernanceRequirements(claim)}</section>
          <section aria-label="Related reviews for ${esc(claim.title)}"><h4>Related reviews</h4>${state.reviewsLoading ? '<p role="status">Loading related reviews…</p>' : state.projectLoadError ? `<div role="alert"><p>Project context could not be loaded. Related reviews are unavailable.</p><button type="button" class="button" data-retry-governance>Retry project</button></div>` : touching.length ? `<ul class="claim-related-reviews">${touching.map(review => `<li><button type="button" data-governance-review="${esc(review.id)}" data-governance-review-claim="${esc(claim.id)}"><strong>${esc(review.intent_summary || review.summary || reviewRef(review))}</strong><span>${esc(reviewRef(review))} · ${I18n.mark(reviewStatusLabel(review.status))}</span><span class="claim-review-action">Inspect evidence</span></button></li>`).join("")}</ul>` : '<p class="claim-detail-hint">No recorded review references this claim yet.</p>'}</section>
        </div>
        <details class="claim-policy-details"><summary>Rule details</summary><dl><div><dt data-i18n=Claim%20ID>Claim ID</dt><dd>${esc(claim.id)}</dd></div><div><dt>Scope</dt><dd>${esc(claim.scope || "*")}</dd></div><div><dt>Severity</dt><dd>${esc(sentence(claim.severity))}</dd></div><div><dt data-i18n=Authority>Authority</dt><dd>${esc(claim.authority || project.default_authority || "Not assigned")}</dd></div><div><dt>Forbidden imports</dt><dd>${esc((claim.forbidden_modules || []).join(", ") || "None recorded")}</dd></div><div><dt>Validity</dt><dd>Version ${esc(claim.introduced_version)}${claim.superseded_version ? `–${esc(claim.superseded_version)}` : "–present"}</dd></div></dl></details>
      </div>
    </details>`;
  }).join("") : `<div class="workspace-empty-guide"><span class="workspace-empty-symbol">${uiIcon('shield-check')}</span><p class="eyebrow">${I18n.mark("Rules")} · ${esc(project.name)}</p><h3 data-i18n=No%20governed%20claims>No governed claims</h3><p data-i18n=Claims%20are%20declared%20when%20a%20repository%20is%20registered.%20Existing%20checks%20and%20decisions%20are%20available%20in%20its%20reviews.>Claims are declared when a repository is registered. Existing checks and decisions are available in its reviews.</p><div class="workspace-guide-actions"><button type="button" class="button button-with-icon" data-workspace-open="reviews">${uiIcon('shield-check')}<span data-i18n=Inspect%20existing%20reviews>Inspect existing reviews</span></button></div><div class="workspace-guide-example" role="note"><span data-i18n=Claim>Claim</span>${uiIcon('arrow-right')}<span data-i18n=Versioned%20evidence>Versioned evidence</span>${uiIcon('arrow-right')}<span data-i18n=Authorized%20decision>Authorized decision</span><small data-i18n=Record%20structure%20%C2%B7%20no%20claims%20configured%20yet>Record structure · no claims configured yet</small></div></div>`;
  list.querySelectorAll("[data-governance-review]").forEach(node => node.addEventListener("click", () => openGovernanceReview(node.dataset.governanceReview, node.dataset.governanceReviewClaim)));
  list.querySelectorAll("[data-retry-governance]").forEach(node => node.addEventListener("click", () => selectProject(project.id)));
}

function governanceClaimReviews(project, claim) {
  return state.reviews.filter(review => review.project_id === project.id && (
    (review.claim_deltas || []).some(delta => delta.claim_id === claim.id)
    || (review.evidence_obligations || []).some(obligation => obligation.claim_id === claim.id)
  )).sort((a, b) => Number(b.status === "open") - Number(a.status === "open"));
}

function renderGovernanceRequirements(claim) {
  const requirements = claim.evidence_obligations || [];
  if (!requirements.length) return '<p class="claim-detail-hint">No evidence requirements are configured for this claim. This does not establish that a review is ready to approve.</p>';
  return `<ul class="claim-requirements">${requirements.map(item => {
    const signed = item.verification === "dsse_ed25519";
    return `<li><h5>${esc(sentence(item.label))}</h5><p><strong>${I18n.mark(signed ? "Signed verification" : "Authorized record")}</strong> · ${item.waivable ? "A bounded waiver is allowed" : "Mandatory; cannot be waived"}</p><details class="claim-policy-details"><summary>Accepted evidence source</summary><dl><div><dt data-i18n=Requirement%20ID>Requirement ID</dt><dd>${esc(item.id)}</dd></div><div><dt data-i18n=Verification>Verification</dt><dd>${signed ? "DSSE / Ed25519, verified against a trusted project key" : "A record from an actor authorized by project policy"}</dd></div>${item.required_verifier_id ? `<div><dt>Required verifier</dt><dd>${esc(item.required_verifier_id)}</dd></div>` : ""}${item.required_verified_level ? `<div><dt>Required level</dt><dd>${esc(item.required_verified_level)}</dd></div>` : ""}<div><dt>Source prefix</dt><dd>${esc(item.required_provenance_prefix || "No prefix restriction configured")}</dd></div></dl></details></li>`;
  }).join("")}</ul>`;
}

async function openGovernanceReview(reviewId, claimId) {
  const project = state.activeProject;
  const claim = project?.claims.find(item => item.id === claimId);
  if (!claim || !governanceClaimReviews(project, claim).some(item => item.id === reviewId)) return;
  const origin = { projectId: project.id, claimId, reviewId };
  governanceReviewOrigin = origin;
  const review = await selectReview(reviewId);
  if (!review || governanceReviewOrigin !== origin || state.activeProject?.id !== origin.projectId) return;
  setEvidenceTab("requirements");
  setReviewWorkspaceTab("evidence", { focus: true });
  $("#review-tab-evidence")?.scrollIntoView({ block: "nearest" });
}

function governanceReturnButton(reviewId) {
  const origin = governanceReviewOrigin;
  return origin?.reviewId === reviewId && origin.projectId === state.activeProject?.id
    ? '<button type="button" class="button button-quiet governance-return" data-return-governance-claim>Back to governing claim</button>' : "";
}

function bindGovernanceReturn() {
  $("[data-return-governance-claim]")?.addEventListener("click", () => showGovernance(governanceReviewOrigin?.claimId));
}

function renderTrustRegistry() {
  const project = state.activeProject;
  if (!project) return;
  const roots = project.attestation_trust_roots || [];
  const activeRoots = roots.filter((root) => root.status === "active").length;
  $("#trust-registry-state").textContent = activeRoots
    ? `${plural(activeRoots, "trusted key")} · manage access`
    : "No trusted signing key · signed uploads unavailable";
  const rootHtml = roots.length ? roots.map((root) => {
    const active = root.status === "active";
    const validity = root.valid_until
      ? `${new Date(root.valid_from).toLocaleDateString()} → ${new Date(root.valid_until).toLocaleDateString()}`
      : `${new Date(root.valid_from).toLocaleDateString()} → no scheduled expiry`;
    const lifecycle = active
      ? `Added by ${root.added_by} under ${root.added_under_policy}`
      : `Revoked ${new Date(root.revoked_at).toLocaleString()} by ${root.revoked_by} · ${title(root.revocation_mode)}`;
    const actions = active ? `
      <div class="trust-root-actions">
        <button type="button" class="button button-small rotate-trust-root" data-key-id="${esc(root.key_id)}">Rotate</button>
        <button type="button" class="button button-small button-danger revoke-trust-root" data-key-id="${esc(root.key_id)}">Revoke</button>
      </div>` : "";
    return `
      <article class="trust-root-card" data-status="${esc(root.status)}">
        <div class="trust-root-status"><span></span>${esc(title(root.status))}</div>
        <div class="trust-root-copy">
          <header><strong>${esc(root.key_id)}</strong><code>${esc(root.algorithm)}</code></header>
          <p>${esc(root.verifier_id)}</p>
          <dl><div><dt data-i18n=Evidence%20authority>Evidence authority</dt><dd>${esc(root.authority)}</dd></div><div><dt>Validity</dt><dd>${esc(validity)}</dd></div></dl>
          <small>${esc(lifecycle)}${root.revocation_reason ? ` · ${esc(root.revocation_reason)}` : ""}</small>
        </div>
        ${actions}
      </article>`;
  }).join("") : '<div class="empty-contract">No trusted signing key yet. Add one only when this project needs to accept signed evidence uploads.</div>';
  $("#trust-root-list").innerHTML = rootHtml;
  const eventHtml = state.projectEvents.length ? [...state.projectEvents].reverse().map((event) => `
    <article class="trust-event">
      <header><strong>${esc(title(event.action))}</strong><span>Version ${event.project_version}</span></header>
      <p>${esc(event.reason)}</p>
      <small>${esc(event.actor)} · ${new Date(event.created_at).toLocaleString()}</small>
    </article>`).join("") : '<div class="empty-contract">No trust transition has been recorded.</div>';
  $("#project-event-list").innerHTML = eventHtml;
  document.querySelectorAll(".rotate-trust-root").forEach((node) =>
    node.addEventListener("click", () => openTrustChange("rotate", node.dataset.keyId))
  );
  document.querySelectorAll(".revoke-trust-root").forEach((node) =>
    node.addEventListener("click", () => openTrustChange("revoke", node.dataset.keyId))
  );
}

function intentCandidateDelta(candidate) {
  const delta = candidate.structural_delta;
  return `${delta.path}: ${delta.from_module} → ${delta.to_module}`;
}

function renderIntentRealization(intent) {
  const attempts = intent.realization_attempts || [];
  if (!attempts.length) return "";
  const attempt = attempts[attempts.length - 1];
  const succeeded = attempt.status === "succeeded";
  const discrepancy = attempt.round_trip_discrepancy == null
    ? "—"
    : Number(attempt.round_trip_discrepancy).toFixed(3);
  const coverage = attempt.observable_coverage == null
    ? "—"
    : `${Math.round(Number(attempt.observable_coverage) * 100)}%`;
  const rehydrated = attempt.rehydrated_candidates || [];
  const rehydratedHtml = rehydrated.length ? rehydrated.map((candidate) => {
    const selected = candidate.id === attempt.selected_rehydration_id;
    return `<article class="intent-rehydration" data-selected="${selected}">
      <header><span>${selected ? "Selected observed candidate" : "Observed candidate"}</span><strong>${candidate.confidence == null ? "—" : `${Math.round(candidate.confidence * 100)}%`}</strong></header>
      <code>${esc(intentCandidateDelta(candidate))}</code>
      <small>${(candidate.evidence || []).map((item) => esc(item)).join(" · ") || "No observable evidence was returned"}</small>
    </article>`;
  }).join("") : '<div class="empty-contract">No observable structural candidate was returned.</div>';
  const failures = (attempt.failed_preconditions || []).length
    ? `<div class="intent-realization-alert"><strong>Unmet preconditions</strong><ul>${attempt.failed_preconditions.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>`
    : '<div class="intent-realization-ok">No failed preconditions</div>';
  const unknowns = (attempt.unobservable_relations || []).length
    ? `<div class="intent-realization-alert"><strong>Unobservable state</strong><ul>${attempt.unobservable_relations.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>`
    : '<div class="intent-realization-ok">No unobservable relation in this bounded operation</div>';
  const diff = attempt.artifact_diff
    ? `<details class="intent-realization-diff"><summary>Inspect real artifact diff</summary><pre>${esc(attempt.artifact_diff)}</pre></details>`
    : "";
  return `<details class="intent-realization" data-status="${esc(attempt.status)}"${succeeded?"":" open"}><summary class="intent-report-summary">${I18n.mark("Implementation check")}<span>${I18n.mark(succeeded?"Completed":"Needs attention")}</span></summary>
    <header class="intent-realization-head">
      <div><p class="eyebrow">Round-trip verification</p><h4>Structural proposal realized and independently checked</h4></div>
      <span class="status-pill">${esc(title(attempt.status))}</span>
    </header>
    <div class="intent-realization-metrics">
      <div><span>Realization</span><strong>${succeeded ? "Completed" : "Failed"}</strong></div>
      <div><span>D<sub>rt</sub></span><strong>${discrepancy}</strong></div>
      <div><span>Observable</span><strong>${coverage}</strong></div>
      <div><span>Observed candidates</span><strong>${rehydrated.length}</strong></div>
    </div>
    <div class="intent-realization-body">
      <div class="intent-realization-trace">
        <dl>
          <div><dt>Proposal ref</dt><dd><code>${esc(attempt.git_ref || "not retained")}</code></dd></div>
          <div><dt>Candidate commit</dt><dd><code>${esc(short(attempt.target_ref || "unavailable"))}</code></dd></div>
          <div><dt>Actor</dt><dd>${esc(attempt.actor)}</dd></div>
        </dl>
        ${failures}${unknowns}${diff}
      </div>
      <div class="intent-rehydration-list">${rehydratedHtml}</div>
    </div>
    <footer><span>${esc(attempt.id)}</span></footer>
  </details>`;
}

function renderIntentWorkspace() {
  const list = $("#intent-list");
  if (!list) return;
  $("#intent-count").textContent = state.intents.length;
  if (!state.intents.length) {
    const noPython=IntentModel.repositoryScope(state.projectTree,state.projectTreeLoading).state==='no_python';
    const requestAction=document.body.classList.contains('viewer-mode')?'':`<button type="button" class="button ${noPython?'button-quiet':'button-primary'} button-with-icon" data-workspace-open="new-request">${uiIcon('plus')}<span>${I18n.mark(noPython?'Draft a Python request':'Create first request')}</span></button>`;
    const reviewAction=`<button type="button" class="button ${noPython?'button-primary':'button-quiet'}" data-workspace-open="reviews">${I18n.mark(state.reviews.length?'View existing reviews':'Open reviews')}</button>`;
    list.innerHTML = `<div class="workspace-empty-guide"><span class="workspace-empty-symbol">${uiIcon('file-text')}</span><p class="eyebrow">${I18n.mark("Requests")} · ${esc(state.activeProject.name)}</p><h3>${I18n.mark(noPython?'Start with a code review':'Clarify the change before implementation')}</h3><p>${I18n.mark(noPython?'No Python files were found in this project snapshot. Requests currently handles Python import replacements. Use Reviews to inspect this project’s existing changes and evidence.':'No requests are recorded yet. Describe a Python import change and compare alternatives before selecting an approach.')}</p><div class="workspace-guide-actions">${noPython?reviewAction+requestAction:requestAction+reviewAction}</div><ol class="request-workflow-guide" aria-label="Request workflow guide"><li><span>01</span><h4 data-i18n=Describe>Describe</h4><p data-i18n=State%20the%20import%20change%20and%20what%20must%20stay%20true.>State the import change and what must stay true.</p></li><li><span>02</span><h4 data-i18n=Compare>Compare</h4><p data-i18n=Inspect%20alternative%20replacements%20and%20open%20questions.>Inspect alternative replacements and open questions.</p></li><li><span>03</span><h4 data-i18n=Select%20%26%20review>Select &amp; review</h4><p data-i18n=Record%20a%20choice%2C%20then%20inspect%20its%20implementation.>Record a choice, then inspect its implementation.</p></li></ol></div>`;
    return;
  }
  list.innerHTML = state.intents.map((intent) => {
    const activeCandidates = intent.candidates.filter((candidate) => candidate.status === "active");
    const statusLabel = ({clarification_required: "Open questions", ready_for_selection: "Ready to select", selected: "Selected", realized: "Review created"})[intent.status] || title(intent.status);
    const selectedCandidate = intent.candidates.find((candidate) => candidate.id === intent.selected_candidate_id);
    const latestAttempt = (intent.realization_attempts || []).at(-1);
    const openState = intent.status === "realized" ? "" : " open";
    const candidates = intent.candidates.map((candidate) => {
      const selected = candidate.id === intent.selected_candidate_id;
      const canClarify = intent.status === "clarification_required" && candidate.status === "active";
      const canSelect = IntentModel.canSelect(intent, candidate);
      const canRealize = intent.status === "selected" && selected;
      const uncertainty = candidate.uncertainties.length
        ? `<ul>${candidate.uncertainties.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`
        : '<p class="intent-resolved">No unresolved uncertainty</p>';
      return `<article class="intent-candidate" data-status="${esc(candidate.status)}">
        <header><div><span class="candidate-status">${esc(title(candidate.status))}</span><h4>${esc(candidate.title)}</h4></div>${candidate.confidence == null ? "" : `<strong title="Self-reported model estimate, not verification">Model ${Math.round(candidate.confidence * 100)}%</strong>`}</header>
        <p>${esc(candidate.summary)}</p><code>${esc(intentCandidateDelta(candidate))}</code>${uncertainty}
        <small>Source · ${esc(candidate.provenance)}</small>
        <div class="intent-candidate-actions">
          ${canClarify ? `<button type="button" class="button button-small clarify-intent-button" data-intent="${esc(intent.id)}" data-candidate="${esc(candidate.id)}">Clarify questions</button>` : ""}
          ${IntentModel.canRevise(intent, candidate) ? `<button type="button" class="button button-small button-quiet edit-intent-candidate" data-intent="${esc(intent.id)}" data-candidate="${esc(candidate.id)}" data-i18n=Edit%20proposal>Edit proposal</button>` : ""}
          ${canSelect ? `<button type="button" class="button button-small button-primary select-intent-button" data-intent="${esc(intent.id)}" data-candidate="${esc(candidate.id)}">Select proposal</button>` : ""}
          ${canRealize ? `<button type="button" class="button button-small button-primary realize-intent-button" data-intent="${esc(intent.id)}">Run isolated realization</button>` : ""}
          ${selected ? '<span class="selected-candidate-mark">✓ Selected by human authority</span>' : ""}
        </div>
      </article>`;
    }).join("");
    return `<details class="intent-map-card" data-intent-id="${esc(intent.id)}" data-status="${esc(intent.status)}"${openState}>
      <summary class="intent-map-summary">
        <div class="intent-summary-status"><span class="intent-status-dot" aria-hidden="true"></span><span class="status-pill">${I18n.mark(statusLabel)}</span></div>
        <div class="intent-summary-copy"><h3>${esc(intent.request)}</h3><p>${esc(selectedCandidate ? selectedCandidate.title : intent.context)}</p></div>
        <dl class="intent-summary-metrics">
          <div><dt data-i18n=Revision>Revision</dt><dd>#${intent.revision}</dd></div>
          ${latestAttempt ? `<div><dt>${I18n.mark("Implementation")}</dt><dd>${I18n.mark(latestAttempt.status==="succeeded"?"Checked":"Needs attention")}</dd></div>` : `<div><dt>Interpretations</dt><dd>${intent.candidates.length}</dd></div><div><dt>Open questions</dt><dd>${activeCandidates.reduce((count, candidate) => count + candidate.uncertainties.length, 0)}</dd></div>`}
        </dl>
        <span class="intent-summary-chevron" aria-hidden="true">⌄</span>
      </summary>
      <div class="intent-map-detail">
        <div class="intent-next-action">${intent.realized_review_id?`<span>${I18n.mark("Implementation ready for review")}</span><button type="button" class="button button-small button-primary open-realized-review" data-review-link="${esc(intent.realized_review_id)}">${I18n.mark("Open linked review")} ${uiIcon("arrow-right")}</button>`:`<strong>${I18n.mark("Next step")}</strong>${esc(IntentModel.nextAction(intent))}`}</div>
        ${intent.status === "realized" ? `<details class="intent-interpretations"><summary>${I18n.mark("Selected interpretation")}<span>${esc(selectedCandidate?.title || "")}</span></summary>` : ""}
        <div class="intent-context-line"><span>Request context</span><p>${esc(intent.context)}</p></div>
        <div class="intent-alternatives-toolbar"><h4>Compare interpretations</h4>${IntentModel.canRevise(intent) ? `<button type="button" class="button button-small button-quiet add-intent-candidate" data-intent="${esc(intent.id)}">Add alternative</button>` : ["clarification_required", "ready_for_selection"].includes(intent.status) ? '<small>20-interpretation limit reached, including ruled-out alternatives.</small>' : ""}</div>
        <div class="intent-candidate-grid">${candidates}</div>
        ${intent.status === "realized" ? "</details>" : ""}
        ${renderClarificationHistory(intent)}
        ${renderIntentRealization(intent)}
        <footer><span>Base version ${intent.base_version} · ${esc(short(intent.base_ref))}</span><span>${plural(intent.clarification_history.length, "recorded turn")}</span><span>Created by ${esc(intent.created_by)}</span></footer>
      </div>
    </details>`;
  }).join("");
  document.querySelectorAll(".clarify-intent-button").forEach((button) =>
    button.addEventListener("click", () => openClarification(button.dataset.intent, button.dataset.candidate))
  );
  document.querySelectorAll(".select-intent-button").forEach((button) =>
    button.addEventListener("click", () => openIntentSelection(button.dataset.intent, button.dataset.candidate))
  );
  document.querySelectorAll(".edit-intent-candidate, .add-intent-candidate").forEach((button) =>
    button.addEventListener("click", () => openCandidateRevision(button.dataset.intent, button.dataset.candidate || null))
  );
  document.querySelectorAll(".realize-intent-button").forEach((button) =>
    button.addEventListener("click", () => {
      const intent = state.intents.find((item) => item.id === button.dataset.intent);
      if (intent && window.confirm("Create an isolated Git realization and turn the result into a review?")) {
        realizeIntent(intent.id, intent.revision).catch((error) => toast(error.message));
      }
    })
  );
  document.querySelectorAll(".open-realized-review").forEach((button) =>
    button.addEventListener("click", () => selectReview(button.dataset.reviewLink).catch((error) => toast(error.message)))
  );
}

function candidateChangeMarkup(changes, beforeLabel = "Before", afterLabel = "After") {
  return changes.length ? `<dl class="candidate-change-list">${changes.map(change => `<div><dt>${esc(change.label)}</dt><dd><span>${esc(beforeLabel)}</span><p>${esc(change.before || "None")}</p></dd><dd><span>${esc(afterLabel)}</span><p>${esc(change.after || "None")}</p></dd></div>`).join("")}</dl>` : '<p class="field-hint">No proposal fields changed.</p>';
}

function renderClarificationHistory(intent) {
  const history = intent.clarification_history || [];
  if (!history.length && !intent.selection_actor) return "";
  const turns = history.map((turn) => {
    const eliminated = new Set(turn.eliminated_candidate_ids || []);
    const revised = new Set(turn.revised_candidate_ids || []);
    const outcomes = (turn.before_candidates || []).filter((candidate) => candidate.status === "active").map((candidate) => {
      const resolved = turn.resolved_uncertainties?.[candidate.id] || [];
      const after = (turn.after_candidates || []).find(item => item.id === candidate.id);
      const changes = revised.has(candidate.id) && after ? candidateChangeMarkup(IntentModel.candidateChanges(candidate, after)) : "";
      return `<li><strong>${esc(candidate.title)}</strong><span>${eliminated.has(candidate.id) ? "Ruled out" : revised.has(candidate.id) ? "Revised; kept open" : "Kept open"}</span>${changes}${resolved.length ? `<ul>${resolved.map((item) => `<li>Resolved: ${esc(item)}</li>`).join("")}</ul>` : ""}</li>`;
    }).join("");
    const added = (turn.after_candidates || []).filter(candidate => (turn.added_candidate_ids || []).includes(candidate.id)).map(candidate => `<li><strong>${esc(candidate.title)}</strong><span>Added alternative</span>${candidateChangeMarkup(IntentModel.candidateChanges(null, candidate))}</li>`).join("");
    const isRevision = revised.size || added;
    return `<article class="clarification-turn"><header><strong>Revision ${turn.intent_revision}</strong><span>${esc(turn.actor)}</span><time>${esc(absoluteTime(turn.created_at))}</time></header><dl><dt>${isRevision ? "Change" : "Question"}</dt><dd>${esc(turn.question)}</dd><dt>${isRevision ? "Reason" : "Answer"}</dt><dd>${esc(turn.answer)}</dd></dl><ul class="clarification-outcomes">${outcomes}${added}</ul><details><summary>Inspect before and after</summary><pre>${esc(JSON.stringify({before: turn.before_candidates, after: turn.after_candidates}, null, 2))}</pre></details></article>`;
  }).join("");
  const selection = intent.selection_actor ? `<article class="clarification-turn"><header><strong>Selection recorded</strong><span>${esc(intent.selection_actor)}</span></header><p>${esc(intent.selection_reason)}</p></article>` : "";
  return `<details class="intent-history"><summary><span data-i18n=Decision%20trail>Decision trail</span> <span>${plural(history.length, "recorded turn")}${intent.selection_actor ? " and human selection" : ""}</span></summary>${turns}${selection}</details>`;
}

function plainReviewCheckLabel(check) {
  if (!check) return "Review check";
  const passed = check.status === "pass";
  const labels = {
    base_version: passed ? "Review is based on the current project" : "Project has moved past this review’s base",
    static_analysis: passed ? "Structure analysis completed" : "Structure analysis is incomplete",
    tests: passed ? "Tests passed" : check.summary && /exited/i.test(check.summary) ? "Tests failed" : "Tests have not run",
    critical_findings: passed ? "No critical uncertainty remains" : "Critical finding needs a disposition",
    evidence_obligations: passed ? "Required evidence is present" : "Required evidence is missing",
    evidence_freshness: passed ? "Evidence is up to date" : "Some evidence is stale",
    proposal_conflict: passed ? "No conflicting review" : "Overlaps another open proposal",
    human_authority: passed ? "Human decision recorded" : "Human decision required",
  };
  return labels[check.key] || check.label;
}

function plainReviewCheckSummary(check) {
  if (!check) return "";
  const passed = check.status === "pass";
  const passedSummaries = {
    base_version: "Compared with the latest recorded project version.",
    static_analysis: "Structure analysis completed with no unresolved claims.",
    tests: "The configured test command completed successfully.",
    critical_findings: "No critical findings remain open.",
    evidence_obligations: "No required evidence is missing.",
    evidence_freshness: "All recorded evidence is current.",
    proposal_conflict: "No conflicting review prevents this decision.",
    human_authority: "The final decision has been recorded.",
  };
  if (passed) return passedSummaries[check.key] || check.summary;
  if (check.key === "human_authority") return "An authorized project owner must record the final decision.";
  if (check.key === "tests" && (!check.summary || /missing|allowlisted|not run/i.test(check.summary))) {
    return "No test command is configured for this project.";
  }
  const detail = plainVersion(check.summary || "").trim();
  return detail ? `${sentence(detail).replace(/\.$/, "")}.` : check.label;
}

function reviewStatusLabel(status) {
  return ({
    open: "Open",
    committed: "Approved",
    rebase_required: "Update requested",
    rejected: "Rejected",
    rolled_back: "Rolled back",
  })[status] || title(status);
}

function rememberReviewLocation() {
  if (state.activeReview && state.activeProject) {
    reviewNavigation.remember(state.activeProject.id, state.activeReview.id, reviewWorkspaceTab);
  }
}

function leaveReview() {
  rememberReviewLocation();
  closeReviewOperations();
  state.reviewSelectionVersion += 1;
  state.reviewListExpanded = false;
  if (state.viewMode === "review") state.filePanelPreference = state.filePanelOpen;
  state.activeReview = null;
  state.manifest = null;
  state.contractGraph = null;
  state.events = [];
  destroyContractGraph();
  setFilePanelOpen(false);
}

function setViewParam(view, reviewId = null) {
  const url = new URL(window.location.href);
  if (view === "canvas") url.searchParams.delete("view");
  else url.searchParams.set("view", view);
  if (reviewId) url.searchParams.set("review", reviewId);
  else url.searchParams.delete("review");
  if (state.activeProject) {
    if (url.searchParams.get("project") !== state.activeProject.id) url.searchParams.delete("meaning");
    url.searchParams.set("project", state.activeProject.id);
  }
  if (url.href === window.location.href) return;
  const method = workspaceNavigationReady && !restoringWorkspaceHistory ? "pushState" : "replaceState";
  window.history[method]({}, "", url);
}

function showProjectCanvas() {
  if (!state.activeProject) return;
  leaveReview();
  state.viewMode = "canvas";
  setViewParam("canvas");
  renderWorkspace();
  window.scrollTo({ top: 0, behavior: "instant" });
}

function showGovernance(claimId = null) {
  if (!state.activeProject) return;
  destroyProjectCanvas();
  leaveReview();
  state.viewMode = "governance";
  setViewParam("governance");
  renderWorkspace();
  ReviewMotion.enter($("#governance-view"), "panel");
  ReviewMotion.disclosures($("#governance-view"));
  const claim = typeof claimId === "string" ? [...document.querySelectorAll("[data-governance-claim]")].find(node => node.dataset.governanceClaim === claimId) : null;
  if (claim) {
    claim.open = true;
    claim.querySelector(":scope > summary")?.focus({ preventScroll: true });
    claim.scrollIntoView({ block: "start" });
  } else window.scrollTo({ top: 0, behavior: "instant" });
}

function showIntents(intentId = null) {
  if (!state.activeProject) return;
  destroyProjectCanvas();
  leaveReview();
  state.viewMode = "intents";
  setViewParam("intents");
  renderWorkspace();
  ReviewMotion.enter($("#intents-view"), "panel");
  ReviewMotion.disclosures($("#intents-view"));
  const card = [...document.querySelectorAll("[data-intent-id]")].find((item) => item.dataset.intentId === intentId);
  if (card) {
    card.open = true;
    card.querySelector("summary")?.focus();
    card.scrollIntoView({ block: "start" });
  } else window.scrollTo({ top: 0 });
}

function showReviews() {
  if (!state.activeProject) return;
  if (state.activeReview) return;
  const preferred = reviewNavigation.restore(state.activeProject.id, matchingReviewList());
  if (preferred) {
    selectReview(preferred.review.id, state.selectionVersion, { section: preferred.section });
    return;
  }
  destroyProjectCanvas();
  leaveReview();
  state.viewMode = "review";
  setViewParam("review");
  renderWorkspace();
}

function setProjectView(view) {
  if (view === "canvas") return showProjectCanvas();
  if (view === "governance") return showGovernance();
  if (view === "intents") return showIntents();
  return showReviews();
}

function destroyProjectCanvas() {
  projectCanvasResizeObserver?.disconnect();
  projectCanvasResizeObserver = null;
  if (projectCanvasInstance) {
    projectCanvasInstance.nodes().stop(true, false);
    projectCanvasInstance.destroy();
  }
  projectCanvasInstance = null;
}

function canvasReviewTone(review) {
  return CanvasModel.reviewTone(review);
}

function projectCanvasElements() {
  const graph=CanvasModel.build(state.activeProject, state.reviews, state.intents);
  return canvasState.filesExpanded?graph:CanvasModel.directoryOverview(graph);
}

function projectCanvasStyles() {
  const palette = graphPalette();
  const sans = "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif";
  return [
    { selector: "node", style: { "background-color": palette.panel, "border-color": palette.line, "border-width": 1.25, color: palette.ink, label:node=>I18n.canvasLabel(node.data()), "font-family": sans, "font-size": 11.5, "font-weight": 500, "line-height": 1.3, "text-wrap": "wrap", "text-max-width": 156, "text-valign": "center", "text-halign": "center", shape: "round-rectangle", width: 176, height: 62, "overlay-opacity": 0 } },
    { selector: 'node[type = "state"]', style: { width: 194, height: 78, "border-color": palette.ink, "border-width": 2, "background-color": palette.panelSubtle, "font-size": 13, "font-weight": 600 } },
    { selector: 'node[type = "intent"]', style: { width: 238, height: 94, "text-max-width": 212, "border-style": "dashed", "border-color": palette.cyan, "background-color": palette.panel, "font-size": 14 } },
    { selector: 'node[type = "claim"]', style: { "border-color": palette.cyan, "border-width": 1.5, "background-color": palette.cyanBg, width: 218, height: 84, "text-max-width": 196, "font-size": 13, color: palette.cyan, "font-weight": 500 } },
    { selector: 'node[type = "review"]', style: { width: 238, height: 100, "border-width": 1.5, "text-max-width": 212, "font-size": 14.5, "font-weight": 500 } },
    { selector: 'node[type = "review"][tone = "open"]', style: { "border-color": palette.accent, "background-color": palette.panel } },
    { selector: 'node[type = "review"][tone = "attention"]', style: { "border-color": palette.orange, "background-color": palette.orangeBg } },
    { selector: 'node[type = "review"][tone = "committed"]', style: { "border-color": palette.accent, "background-color": palette.accentFaint } },
    { selector: 'node[type = "review"][tone = "rejected"]', style: { "border-color": palette.red, "border-style": "dashed", "background-color": palette.redBg, color: palette.muted } },
    { selector: 'node[type = "review"][tone = "stale"]', style: { "border-color": palette.orange, "border-style": "dashed", "background-color": palette.panel } },
    { selector: 'node[type = "artifact"]', style: { width: 224, height: 60, "text-max-width": 202, "border-color": palette.line, "font-family": "SFMono-Regular, SF Mono, Menlo, monospace", "font-size": 12.5, "font-weight": 400, color: palette.muted, "background-color": palette.panelSubtle } },
    { selector: 'node[type = "directory"]', style: {width:210,height:76,"text-max-width":184,"background-color":palette.panelSubtle,"border-color":palette.line,"border-width":1.25,"font-size":13,"font-weight":500} },
    { selector: "edge", style: { width: 1.3, "line-color": palette.dim, "target-arrow-color": palette.dim, "target-arrow-shape": "triangle", "arrow-scale": .75, "curve-style": "bezier", opacity: 1, "overlay-opacity": 0, label: "data(label)", color: palette.dim, "font-family": sans, "font-size": 12, "text-background-color": palette.panel, "text-background-opacity": 1, "text-background-padding": 3, "text-rotation": "autorotate" } },
    { selector: 'edge[relation = "commits"]', style: { "line-color": palette.accent, "target-arrow-color": palette.accent, width: 2.2 } },
    { selector: 'edge[relation = "proposes"]', style: { "line-color": palette.accent, "target-arrow-color": palette.accent, "line-style": "dashed", width: 1.6 } },
    { selector: 'edge[relation = "changes_in"]', style: {label:"","line-color":palette.dim,"target-arrow-color":palette.dim,"font-size":11.5,"curve-style":"taxi","taxi-direction":"rightward"} },
    { selector: 'edge[relation = "rolls_back"], edge[relation = "rejected"], edge[relation = "contests"]', style: { "line-color": palette.red, "target-arrow-color": palette.red, "line-style": "dashed", width: 1.8 } },
    { selector: 'edge[relation = "inconclusive"]', style: { "line-color": palette.orange, "target-arrow-color": palette.orange, "line-style": "dotted", width: 1.8 } },
    { selector: 'edge[relation = "governs"]', style: { "line-color": palette.cyan, "target-arrow-color": palette.cyan, width: 1.6 } },
    { selector: 'edge[relation = "supports"]', style: { "line-color": palette.accent, "target-arrow-color": palette.accent, width: 1.8 } },
    { selector: ".canvas-muted", style: { opacity: .14 } },
    { selector: "edge.canvas-active", style: { opacity: 1, label:edge=>I18n.t(edge.data('label')), "z-index": 9 } },
    { selector: "node.canvas-active", style: { "border-width": 3, "z-index": 10 } },
    { selector: 'node[type = "review"]:selected', style: { "underlay-color": palette.accent, "underlay-opacity": .18, "underlay-padding": 10 } },
    { selector: ".canvas-filtered", style: { display: "none" } },
    { selector: "edge.canvas-compact", style: { "font-size": 12, "text-rotation": "none" } },
    { selector: 'edge[relation = "changes_in"].canvas-compact', style: { "curve-style":"unbundled-bezier", "control-point-distances":180, "control-point-weights":.5 } },
  ];
}

function canvasCurrentGraph() {
  const file = canvasState.snapshotFile;
  if (!file) return projectCanvasData;
  return {
    nodes: [...projectCanvasData.nodes, {data: {...file, fullLabel: file.path, label: file.path.split("/").slice(-2).join("/")}, position: {x:340,y:0}, classes: "canvas-snapshot"}],
    edges: [...projectCanvasData.edges, {data: {id:`snapshot:${file.path}`,source:"state",target:file.id,relation:"contains",label:"contains"}, classes:"canvas-snapshot"}],
  };
}

function setCanvasMapMode(mode) {
  canvasState.mode = mode;
  canvasState.query = "";
  $("#canvas-search").value = "";
  if (mode === "project") {
    canvasState.selected = null;
    canvasState.snapshotFile = null;
    clearCanvasHighlight();
    renderProjectCanvasDetail(null);
    filterProjectCanvas();
  } else {
    const graph = canvasCurrentGraph();
    const id = graph.nodes.some(node=>node.data.id===canvasState.focusId) ? canvasState.focusId : CanvasModel.preferredFocus(graph);
    if (id) selectCanvasObject(id, canvasState.snapshotFile, { revealDetails: false });
  }
}

function canvasObjectButton(data) {
  const kind = { state: "Current state", claim: "Claim", review: "Review", artifact: "File", intent: "Intent", directory:"Directory" }[data.type];
  const status = data.tone === "attention" ? "Needs attention" : data.tone === "stale" ? "Needs rebase" : sentence(data.status);
  const label = data.type === "claim" || data.type === "state" ? data.fullLabel : data.summary || data.path || data.label;
  return `<button type="button" class="canvas-object" data-canvas-object="${esc(data.id)}" data-tone="${esc(data.tone || data.type)}" aria-pressed="${canvasState.selected === data.id}" title="${esc(data.summary || data.path || data.label)}"><span class="canvas-object-icon" aria-hidden="true">${uiIcon({ review: "shield-check", artifact: "file-text", intent: "file-text", state: "network", claim: "shield-check",directory:"code" }[data.type])}</span><span class="canvas-activity-copy"><strong>${esc(label)}</strong><small>${esc(kind)} · ${esc(status)}</small></span></button>`;
}

function bindCanvasObjects(scope) {
  scope?.querySelectorAll("[data-canvas-object]").forEach((button) => {
    button.addEventListener("click", () => selectCanvasObject(button.dataset.canvasObject));
  });
}

function renderProjectCanvasSide() {
  const reviews = CanvasModel.orderedReviews(state.reviews);
  const attention = reviews.filter((review) => ["attention", "stale"].includes(canvasReviewTone(review)));
  const open = reviews.filter((review) => review.status === "open");
  $("#project-canvas-glance").innerHTML = `<h3>${attention.length ? plural(attention.length, "change needs", "changes need") + " attention" : open.length ? plural(open.length, "open review") : "Project overview"}</h3><p>${attention.length ? "Inspect evidence and open findings before recording a decision." : "A review records a proposed transition, not a merge."}</p>`;
  const next = attention[0] || open[0];
  if (next) {
    $("#project-canvas-glance").insertAdjacentHTML("beforeend", '<button type="button" class="text-button" id="canvas-next-change" data-i18n=Locate%20on%20map%20%E2%86%92>Locate on map →</button>');
    $("#canvas-next-change").onclick = () => selectCanvasObject(`review:${next.id}`);
  }
  const dataOf = (id) => projectCanvasData.nodes.find((node) => node.data.id === id)?.data;
  $("#canvas-activity-meta").textContent = reviews.length ? "Attention first" : "";
  $("#project-canvas-activity").innerHTML = reviews.map((review) => canvasObjectButton(dataOf(`review:${review.id}`))).join("")
    || '<p class="canvas-empty" data-i18n=No%20reviews%20yet.%20Use%20New%20review%20to%20compare%20a%20change%20against%20this%20state.>No reviews yet. Use New review to compare a change against this state.</p>';
  const recordedClaims=[...(state.activeProject.claims || []),...(state.activeProject.commitments || [])];
  $("#canvas-claims-meta").textContent = plural(recordedClaims.length, "commitment");
  $("#project-canvas-claims").innerHTML = [dataOf("state"), ...recordedClaims.map((claim) => dataOf(`claim:${claim.id}`))].map(canvasObjectButton).join("");
  $("#canvas-intents-list").innerHTML = state.intents.map((intent) => canvasObjectButton(dataOf(`intent:${intent.id}`))).join("")
    || '<p class="canvas-empty" data-i18n=Clarify%20an%20ambiguous%20request%20before%20implementing%20it.>Clarify an ambiguous request before implementing it.</p>';
  const directories=projectCanvasData.nodes.filter(node=>node.data.type==='directory');
  $("#canvas-directories-section").hidden=!directories.length;
  $("#canvas-directories").innerHTML=directories.map(node=>canvasObjectButton(node.data)).join('');
  const nodeTypes=new Set(projectCanvasData.nodes.map(node=>node.data.type));
  document.querySelectorAll('.project-canvas-legend [data-node]').forEach(item=>item.hidden=!nodeTypes.has(item.dataset.node));
  bindCanvasObjects($("#canvas-overview"));
  $("#canvas-all-intents").onclick = () => showIntents();
  renderCanvasFiles();
}

function renderCanvasFiles() {
  const panel = $("#canvas-files");
  if (!panel) return;
  if (state.projectTreeLoading) {
    panel.innerHTML = '<p class="canvas-empty" role="status">Reading the project snapshot…</p>';
    return;
  }
  if (!state.projectTree || state.projectTree.error) {
    panel.innerHTML = `<p class="canvas-empty">${esc(state.projectTree?.error || "The project snapshot is unavailable.")}</p><button type="button" class="button" id="canvas-retry-files">Retry files</button>`;
    $("#canvas-retry-files").onclick = async () => {
      const version = state.selectionVersion;
      const projectId = state.activeProject.id;
      state.projectTreeLoading = true;
      renderCanvasFiles();
      try {
        const result = await loadProjectTree(projectId);
        if (version === state.selectionVersion) state.projectTree = result;
      } catch (error) {
        if (version === state.selectionVersion) state.projectTree = { error: error.message, entries: [] };
      } finally {
        if (version === state.selectionVersion) {
          state.projectTreeLoading = false;
          renderCanvasFiles();
          renderProjectTree();
        }
      }
    };
    return;
  }
  const entries = state.projectTree.entries || [];
  panel.innerHTML = `<p class="canvas-file-context"><span data-i18n=Project%20snapshot>Project snapshot</span> <code>${esc(short(state.projectTree.revision))}</code></p><p class="canvas-empty">Select a file to see related reviews. Proposed files also appear on the map.</p><label class="canvas-file-search"><span class="sr-only">Filter snapshot files</span><input type="search" id="canvas-file-search" placeholder="Filter snapshot files"></label><div id="canvas-file-tree" class="project-file-tree"></div><p class="canvas-empty">${state.projectTree.truncated ? "Limited snapshot: not all files are shown." : plural(entries.filter((entry) => entry.kind === "file").length, "tracked file")}</p>`;
  const render = () => {
    const query = $("#canvas-file-search").value.trim().toLowerCase();
    const visible = query ? entries.filter((entry) => entry.kind === "file" && entry.path.toLowerCase().includes(query)) : entries;
    const nodes = buildProjectTree(visible);
    const tree = $("#canvas-file-tree");
    tree.innerHTML = nodes.length ? renderProjectTreeNodes(nodes, new Set(), query ? 0 : 1) : '<p class="canvas-empty">No matching files. Try a shorter name.</p>';
    tree.querySelectorAll("[data-file-path]").forEach((button) => {
      button.onclick = () => selectCanvasObject(`artifact:${button.dataset.filePath}`, { type: "artifact", id: `artifact:${button.dataset.filePath}`, path: button.dataset.filePath, label: button.dataset.filePath, status: "snapshot" });
    });
  };
  $("#canvas-file-search").oninput = render;
  render();
}

function selectCanvasObject(id, fallback = null, { revealDetails = true } = {}) {
  const data = projectCanvasData.nodes.find((node) => node.data.id === id)?.data || fallback;
  if (!data) return;
  const snapshot = !projectCanvasData.nodes.some(node=>node.data.id===id)
    && data.type === "artifact" && state.projectTree?.entries?.some(entry=>entry.kind==="file" && entry.path===data.path);
  canvasState.snapshotFile = snapshot ? data : null;
  canvasState.selected = id;
  canvasState.focusId = id;
  canvasState.mode = "focus";
  canvasState.panelOpen = true;
  filterProjectCanvas();
  highlightCanvasNode(id);
  renderProjectCanvasDetail(data);
  if (revealDetails) {
    $("#canvas-clear-selection")?.focus({ preventScroll: true });
    if (window.matchMedia("(max-width: 1000px)").matches) $("#project-canvas-detail")?.scrollIntoView({ block: "nearest" });
  }
}

function renderProjectCanvasDetail(data) {
  const detail = $("#project-canvas-detail");
  if (!detail) return;
  detail.hidden = !data;
  if (!data) { detail.innerHTML = ""; return; }
  const review = data.type === "review" ? state.reviews.find((item) => item.id === data.reviewId) : null;
  const intent = data.type === "intent" ? state.intents.find((item) => item.id === data.intentId) : null;
  const related = state.reviews.filter((item) => data.type === "claim"
    ? (item.claim_deltas || []).some((delta) => delta.claim_id === data.claimId)
    : data.type === "artifact" ? (item.changed_paths || []).includes(data.path) : data.type==='directory' ? (item.changed_paths || []).some(path=>data.paths.includes(path)) : false);
  const readable = data.type === "artifact" && state.projectTree?.entries?.some(entry => entry.kind === "file" && entry.path === data.path);
  const graph = canvasCurrentGraph();
  const relations = graph.edges.filter(({ data: edge }) => edge.source === data.id || edge.target === data.id);
  const nodeTitle = (id) => {
    const node = graph.nodes.find((item) => item.data.id === id)?.data;
    return node?.summary || node?.path || node?.label || id;
  };
  const status = data.tone === "attention" ? "Needs attention" : sentence(data.status);
  detail.innerHTML = `<button type="button" class="text-button canvas-back" id="canvas-clear-selection">Back to ${canvasState.query.trim() ? "results" : canvasState.panel === "files" ? "files" : "overview"}</button>
    <p class="canvas-selection-type">${esc(sentence(data.type === "artifact" ? "file" : data.type))} · ${esc(status)}</p>
    <h3>${esc(data.type === "claim" ? data.fullLabel : data.summary || data.path || data.label)}</h3>
    ${data.type === "claim" && data.summary ? `<p>${esc(data.summary)}</p>` : ""}
    ${review ? `<dl><div><dt data-i18n=Review>Review</dt><dd>${esc(reviewRef(review))}</dd></div><div><dt data-i18n=Changed%20files>Changed files</dt><dd>${(review.changed_paths || []).length}</dd></div><div><dt>Created</dt><dd>${I18n.mark(relativeTime(review.created_at))}</dd></div>${state.paperMode ? "" : `<div><dt>Proposed by</dt><dd>${esc(review.proposer)}</dd></div>`}</dl><button type="button" class="button button-primary" id="canvas-open-review">Inspect review</button>` : ""}
    ${intent ? '<p class="canvas-empty">Inspect the original request, candidate interpretations, and recorded selection.</p><button type="button" class="button button-primary" id="canvas-open-intent">Open intent</button>' : ""}
    ${readable ? '<button type="button" class="button button-primary" id="canvas-read-file">Read snapshot</button><p class="canvas-empty">Read-only content from the project snapshot, not the proposed patch.</p>' : data.type === "artifact" ? '<p class="canvas-empty">This file is not in the project snapshot. Open a related review to inspect its proposed change.</p>' : ""}
    ${related.length ? `<h4>Related reviews</h4><div class="canvas-related">${related.map((item) => `<button type="button" class="canvas-object" data-canvas-open="${esc(item.id)}"><span class="canvas-activity-copy"><strong>${esc(item.intent_summary || item.summary)}</strong><small>${esc(reviewRef(item))} · ${I18n.mark(reviewStatusLabel(item.status))}</small></span></button>`).join("")}</div>` : data.type === "artifact" ? '<p class="canvas-empty">No review changes this file.</p>' : ""}
    ${relations.length ? `<h4>Relationships</h4><ul class="canvas-relations">${relations.map(({ data: edge }) => `<li><span>${esc(edge.source === data.id ? edge.label : `Incoming · ${edge.label}`)}</span><button type="button" class="text-button" data-canvas-object="${esc(edge.source === data.id ? edge.target : edge.source)}">${esc(nodeTitle(edge.source === data.id ? edge.target : edge.source))}</button></li>`).join("")}</ul>` : ""}`;
  $("#canvas-clear-selection").onclick = () => {
    canvasState.selected = null;
    canvasState.snapshotFile = null;
    canvasState.mode = "project";
    clearCanvasHighlight();
    renderProjectCanvasDetail(null);
    filterProjectCanvas();
    const returnControl = canvasState.query.trim()
      ? [...document.querySelectorAll("#canvas-search-results [data-canvas-object]")].find(button => button.dataset.canvasObject === data.id) || $("#canvas-search")
      : document.querySelector(`[data-canvas-panel="${canvasState.panel}"]`);
    returnControl?.focus();
  };
  if (review) $("#canvas-open-review").onclick = () => selectReview(review.id);
  if (intent) $("#canvas-open-intent").onclick = () => showIntents(intent.id);
  if (readable) $("#canvas-read-file").onclick = () => openSnapshotFile(data.path);
  if(data.type==='directory') {
    const files=data.paths.map(path=>{const exists=state.projectTree?.entries?.some(entry=>entry.kind==='file'&&entry.path===path);return `<li>${exists?`<button type="button" data-canvas-read-path="${esc(path)}" title="Read the current project snapshot">${uiIcon('file-text')}<span>${esc(path)}</span>${uiIcon('arrow-right')}</button>`:`<span>${esc(path)}</span><small>Inspect its proposed patch in a related review.</small>`}</li>`;}).join('');
    detail.insertAdjacentHTML('beforeend',`<section class="canvas-directory-files"><h4 data-i18n=Changed%20files>Changed files</h4><p>Read the current snapshot here; open a related review for its proposed diff.</p><ul>${files}</ul></section>`);
    detail.querySelectorAll('[data-canvas-read-path]').forEach(button=>button.onclick=()=>openSnapshotFile(button.dataset.canvasReadPath));
  }
  ReviewMotion.enter(detail,'panel');
  detail.querySelectorAll("[data-canvas-open]").forEach((button) => { button.onclick = () => selectReview(button.dataset.canvasOpen); });
  bindCanvasObjects(detail);
  document.querySelectorAll("#canvas-overview [data-canvas-object], #canvas-search-results [data-canvas-object]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.canvasObject === data.id)));
}

function highlightCanvasNode(nodeId) {
  if (!projectCanvasInstance) return;
  const node = projectCanvasInstance.getElementById(nodeId);
  projectCanvasInstance.elements().removeClass("canvas-muted canvas-active");
  if (!node || node.empty()) return;
  if (canvasState.mode !== "focus") projectCanvasInstance.elements().addClass("canvas-muted");
  node.addClass("canvas-active");
  node.connectedEdges().removeClass("canvas-muted").addClass("canvas-active");
}

function clearCanvasHighlight() {
  projectCanvasInstance?.elements().removeClass("canvas-muted canvas-active");
}

function updateCanvasPanel() {
  $(".project-canvas")?.classList.toggle("canvas-panel-hidden", !canvasState.panelOpen);
  $("#canvas-side")?.toggleAttribute("hidden", !canvasState.panelOpen);
  const toggle = $("#canvas-panel-toggle");
  toggle?.setAttribute("aria-expanded", String(canvasState.panelOpen));
  if (toggle) toggle.textContent = canvasState.panelOpen ? "Hide panel" : "Show panel";
  const searching = Boolean(canvasState.query.trim());
  $("#canvas-overview")?.toggleAttribute("hidden", Boolean(searching || canvasState.selected || canvasState.panel !== "overview"));
  $("#canvas-files")?.toggleAttribute("hidden", Boolean(searching || canvasState.selected || canvasState.panel !== "files"));
  $("#canvas-search-results")?.toggleAttribute("hidden", !searching || Boolean(canvasState.selected));
  document.querySelectorAll("[data-canvas-panel]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.canvasPanel === canvasState.panel)));
  document.querySelectorAll("#canvas-overview [data-canvas-object], #canvas-search-results [data-canvas-object]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.canvasObject === canvasState.selected)));
}

function fitProjectCanvas({ fitAll = false } = {}) {
  if (!projectCanvasInstance) return;
  const visible = projectCanvasInstance.elements(":visible");
  if (!visible.length) return;
  projectCanvasInstance.resize();
  projectCanvasInstance.fit(visible, window.matchMedia("(max-width: 600px)").matches ? 24 : 46);
  if (projectCanvasInstance.zoom() > 1) {
    projectCanvasInstance.zoom(1);
    projectCanvasInstance.center(visible);
  }
  if (!fitAll && (canvasState.mode === "focus" || canvasState.query.trim())) {
    const minimum = 1;
    if (projectCanvasInstance.zoom() < minimum) {
      projectCanvasInstance.zoom(minimum);
      const node = projectCanvasInstance.getElementById(canvasState.selected || canvasState.focusId);
      projectCanvasInstance.center(node?.visible() ? node : visible.nodes().first());
    }
  }
}

function filterProjectCanvas() {
  const query = canvasState.query.trim();
  const graph = canvasCurrentGraph();
  const matches = CanvasModel.matches(projectCanvasData.nodes, query);
  const compact = window.matchMedia("(max-width: 600px)").matches;
  let view;
  if (canvasState.mode === "focus" && canvasState.focusId) view = CanvasModel.focused(graph, canvasState.focusId, {compact});
  else if (query) {
    const ids = CanvasModel.neighborhood(matches.map(node=>node.data.id), graph.edges);
    if (ids.size) ids.add("state");
    view = CanvasModel.scoped(graph,ids,{compact});
  } else view = compact ? CanvasModel.scoped(graph,new Set(graph.nodes.map(node=>node.data.id)),{compact:true}) : graph;
  $("#project-canvas")?.style.setProperty('--canvas-content-height',`${Math.min(740,Math.max(360,view.nodes.length*116+80))}px`);
  const ids = new Set(view.nodes.map(node=>node.data.id));
  projectCanvasInstance?.batch(() => {
    projectCanvasInstance.elements(".canvas-snapshot").remove();
    if (canvasState.snapshotFile) projectCanvasInstance.add([...graph.nodes,...graph.edges].filter(element=>element.classes==="canvas-snapshot"));
    projectCanvasInstance.nodes().forEach(node=>node.toggleClass("canvas-filtered",!ids.has(node.id())));
    projectCanvasInstance.edges().forEach(edge=>{
      edge.toggleClass("canvas-filtered",!ids.has(edge.source().id())||!ids.has(edge.target().id()));
      edge.toggleClass("canvas-compact",compact);
    });
    view.nodes.forEach(node=>projectCanvasInstance.getElementById(node.data.id).position(node.position));
  });
  $("#canvas-mode-focus")?.setAttribute("aria-pressed",String(canvasState.mode==="focus"));
  $("#canvas-mode-project")?.setAttribute("aria-pressed",String(canvasState.mode==="project"));
  if ($("#canvas-scope-status")) $("#canvas-scope-status").textContent = `${view.nodes.length} of ${graph.nodes.length} objects${query ? " · Search" : ""}`;
  const results = $("#canvas-search-results");
  if (results) {
    results.innerHTML = `<p class="canvas-result-count" role="status">${plural(matches.length, "matching object")}</p>${matches.map((node) => canvasObjectButton(node.data)).join("")}${matches.length ? "" : '<p class="canvas-empty">Try a shorter name, a file path, or a review ID.</p>'}<button type="button" class="text-button" id="canvas-clear-search" data-i18n=Clear%20search>Clear search</button>`;
    bindCanvasObjects(results);
    $("#canvas-clear-search").onclick = () => {
      $("#canvas-search").value = "";
      canvasState.query = "";
      filterProjectCanvas();
      $("#canvas-search").focus();
    };
  }
  updateCanvasPanel();
  fitProjectCanvas();
}

function renderProjectCanvas() {
  const mountPoint = $("#review-canvas");
  const template = $("#project-canvas-template");
  if (!mountPoint || !template || !state.activeProject) return;
  if (!mountPoint.querySelector(".project-canvas")) {
    destroyProjectCanvas();
    mountPoint.innerHTML = "";
    mountPoint.removeAttribute("aria-busy");
    mountPoint.append(template.content.cloneNode(true));
    $("#canvas-search").oninput = (event) => {
      canvasState.query = event.target.value;
      canvasState.selected = null;
      canvasState.mode = "project";
      canvasState.snapshotFile = null;
      canvasState.panel = "overview";
      canvasState.panelOpen = true;
      renderProjectCanvasDetail(null);
      clearCanvasHighlight();
      filterProjectCanvas();
    };
    $("#canvas-fit").onclick = () => fitProjectCanvas({fitAll:true});
    $("#canvas-mode-focus").onclick = () => setCanvasMapMode("focus");
    $("#canvas-mode-project").onclick = () => setCanvasMapMode("project");
    $("#canvas-file-detail").onclick=()=>{
      canvasState.filesExpanded=!canvasState.filesExpanded;
      canvasState.selected=null;canvasState.snapshotFile=null;canvasState.focusId=null;
      renderProjectCanvas();
      ReviewMotion.enter($(".project-canvas-stage"), "panel");
    };
    $("#canvas-panel-toggle").onclick = () => {
      canvasState.panelOpen = !canvasState.panelOpen;
      updateCanvasPanel();
    };
    document.querySelectorAll("[data-canvas-panel]").forEach((button) => {
      button.onclick = () => {
        canvasState.panel = button.dataset.canvasPanel;
        canvasState.selected = null;
        canvasState.query = "";
        $("#canvas-search").value = "";
        renderProjectCanvasDetail(null);
        clearCanvasHighlight();
        filterProjectCanvas();
      };
    });
    const zoom = (factor) => {
      if (!projectCanvasInstance) return;
      const canvas = $("#project-canvas");
      projectCanvasInstance.zoom({ level: projectCanvasInstance.zoom() * factor, renderedPosition: { x: canvas.clientWidth / 2, y: canvas.clientHeight / 2 } });
    };
    document.querySelectorAll("[data-canvas-zoom]").forEach((button) => { button.onclick = () => zoom(button.dataset.canvasZoom === "in" ? 1.2 : 1 / 1.2); });
    $("#project-canvas").onkeydown = (event) => {
      if (!["+", "=", "-", "0", "Escape"].includes(event.key)) return;
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "0") fitProjectCanvas({fitAll:true});
      else if (event.key === "Escape") $("#canvas-clear-selection")?.click();
      else zoom(event.key === "-" ? 1 / 1.2 : 1.2);
    };
  }
  I18n.setText($("#project-canvas-title"),"Project state");
  I18n.setText($('#canvas-file-detail'),canvasState.filesExpanded?'Group files':'Show files');
  $("#canvas-file-detail").setAttribute('aria-pressed',String(canvasState.filesExpanded));
  const ordered = CanvasModel.orderedReviews(state.reviews);
  const attention = ordered.filter(review => ["attention", "stale"].includes(canvasReviewTone(review)));
  const open = ordered.filter(review => review.status === "open");
  const next = attention[0] || open[0];
  const unavailableContext = state.reviewsLoading || Boolean(state.projectLoadError);
  I18n.setText($("#project-canvas-copy"),state.reviewsLoading ? "Loading reviews and requests…"
    : state.projectLoadError ? "Project context is unavailable. Retry below."
    : open.length || attention.length ? "Open reviews: {count} · Agreed commitments: {agreed}"
    : "No open reviews. Start with a pull request or compare local revisions.",{count:open.length,agreed:(state.activeProject.commitments||[]).length});
  const actions = $("#project-canvas-actions");
  $("#project-state-overview").innerHTML=CommitmentUI.projectView(state.activeProject,state.reviews);
  actions.innerHTML = !unavailableContext && next
    ? '<button type="button" class="button button-primary" id="canvas-review-next"><span data-i18n=Review%20next%20change>Review next change</span><span aria-hidden="true"> →</span></button>'
    : !unavailableContext && !document.body.classList.contains("viewer-mode")
      ? '<button type="button" class="button button-primary" id="canvas-start-review"><span data-i18n=New%20review>New review</span><span aria-hidden="true"> →</span></button>' : "";
  $("#canvas-review-next")?.addEventListener("click", () => selectReview(next.id));
  $("#canvas-start-review")?.addEventListener("click", startNewReview);
  $("#canvas-search").value = canvasState.query;
  projectCanvasData = projectCanvasElements();
  if (!state.reviewsLoading && !state.projectLoadError && !canvasState.focusId) {
    canvasState.focusId = CanvasModel.preferredFocus(projectCanvasData);
  }
  renderProjectCanvasSide();
  renderProjectCanvasDetail(canvasState.selected ? projectCanvasData.nodes.find(node=>node.data.id===canvasState.selected)?.data || canvasState.snapshotFile : null);
  updateCanvasPanel();
  const overlay = $("#project-canvas-overlay");
  const canvas = $("#project-canvas");
  mountPoint.setAttribute("aria-busy", String(state.reviewsLoading));
  const unavailable = state.reviewsLoading || Boolean(state.projectLoadError);
  document.querySelectorAll("[data-canvas-zoom], #canvas-fit, #canvas-file-detail, #canvas-search, [data-canvas-panel], [data-canvas-mode]").forEach((control) => { control.disabled = unavailable; });
  if (state.reviewsLoading) {
    destroyProjectCanvas();
    canvas.replaceChildren();
    $("#canvas-overview").hidden = true;
    overlay.classList.remove("hidden");
    overlay.innerHTML = '<strong role="status">Loading project context…</strong><span>Reading reviews and recorded intents.</span>';
    return;
  }
  if (state.projectLoadError) {
    destroyProjectCanvas();
    canvas.replaceChildren();
    overlay.classList.remove("hidden");
    overlay.innerHTML = `<strong role="alert">Couldn’t load this project</strong><span>${esc(state.projectLoadError)}</span><button type="button" class="button" id="canvas-retry-project">Retry project</button>`;
    $("#canvas-overview").hidden = true;
    $("#canvas-retry-project").onclick = () => selectProject(state.activeProject.id);
    return;
  }
  overlay.classList.add("hidden");
  if (typeof window.cytoscape !== "function") {
    destroyProjectCanvas();
    canvas.innerHTML = '<div class="graph-fallback">Interactive rendering is unavailable. Use the panel to inspect every object and its relationships.</div>';
    document.querySelectorAll("[data-canvas-zoom], #canvas-fit").forEach((button) => { button.disabled = true; });
    $("#canvas-zoom").textContent = "—";
    filterProjectCanvas();
    return;
  }
  const signature = JSON.stringify(projectCanvasData);
  if (projectCanvasInstance && canvas.dataset.signature === signature) {
    if (canvasState.selected) selectCanvasObject(canvasState.selected, canvasState.snapshotFile, { revealDetails: false });
    return;
  }
  destroyProjectCanvas();
  canvas.dataset.signature = signature;
  canvas.innerHTML = "";
  projectCanvasInstance = cytoscape({
    container: canvas,
    elements: [...projectCanvasData.nodes.map(node=>({...node,position:{...node.position}})), ...projectCanvasData.edges],
    style: projectCanvasStyles(),
    layout: { name: "preset", fit: false },
    minZoom: .08, maxZoom: 2.2,
    userZoomingEnabled: false,
    boxSelectionEnabled: false,
  });
  projectCanvasInstance.on("tap", "node", (event) => selectCanvasObject(event.target.id()));
  projectCanvasInstance.on("tap", (event) => {
    if (event.target !== projectCanvasInstance) return;
    canvasState.selected = null;
    canvasState.snapshotFile = null;
    canvasState.mode = "project";
    clearCanvasHighlight();
    renderProjectCanvasDetail(null);
    filterProjectCanvas();
  });
  projectCanvasInstance.on("zoom", () => {
    const output = $("#canvas-zoom");
    if (output) output.textContent = `${Math.round(projectCanvasInstance.zoom() * 100)}%`;
  });
  filterProjectCanvas();
  if (canvasState.selected) selectCanvasObject(canvasState.selected, canvasState.snapshotFile, { revealDetails: false });
  if (window.ResizeObserver) {
    const instance = projectCanvasInstance;
    let width = canvas.clientWidth;
    projectCanvasResizeObserver = new ResizeObserver(() => {
      if (projectCanvasInstance !== instance) return;
      instance.resize();
      if (Math.abs(canvas.clientWidth - width) > 4) {
        width = canvas.clientWidth;
        filterProjectCanvas();
      }
    });
    projectCanvasResizeObserver.observe(canvas);
  }
}

function renderReviewGroups(reviews, renderItem) {
  const open = reviews.filter((review) => review.status === "open");
  const decided = reviews.filter((review) => review.status !== "open");
  if (!open.length || !decided.length) return reviews.map(renderItem).join("");
  return `<div class="review-group-label"><span data-i18n=Open>Open</span><span>${open.length}</span></div>${open.map(renderItem).join("")}<div class="review-group-label">${I18n.mark('Decided')}<span>${decided.length}</span></div>${decided.map(renderItem).join("")}`;
}

function matchingReviewList() {
  const query = ($("#review-filter")?.value || "").trim().toLowerCase();
  const ordered = [...state.reviews.filter(review => review.status === "open"), ...state.reviews.filter(review => review.status !== "open")];
  return ordered.filter(review => !query || [review.intent_summary, review.summary, reviewRef(review), review.proposer]
    .filter(Boolean).join(" ").toLowerCase().includes(query));
}

function clearReviewFilter() {
  $("#review-filter").value = "";
  reviewQueries.delete(state.activeProject?.id);
  renderWorkspace();
  const input = $("#review-filter");
  const target = input?.checkVisibility() ? input
    : $('#review-list [aria-current="true"]') || $("#review-list [data-review]") || $('[data-view-tab="review"]');
  target?.focus();
}

function syncReviewList() {
  const toggle = $("#review-list-toggle");
  const content = $("#review-list-content");
  if (!toggle || !content) return;
  const compact = window.matchMedia("(max-width: 820px)").matches;
  const canCollapse = compact && Boolean(state.activeReview);
  const expanded = !canCollapse || state.reviewListExpanded;
  toggle.hidden = !canCollapse;
  toggle.setAttribute("aria-expanded", String(expanded));
  content.hidden = !expanded;
  const ordered = matchingReviewList();
  const index = ordered.findIndex((review) => review.id === state.activeReview?.id);
  $("#review-list-position").textContent = $("#review-filter").value.trim()
    ? plural(ordered.length, "match", "matches")
    : index >= 0 ? `${index + 1} of ${ordered.length}` : plural(ordered.length, "review");
  $(".review-rail")?.classList.toggle("has-review-switcher", canCollapse);
}

async function selectReviewFromList(reviewId) {
  const review = await selectReview(reviewId);
  if (!review) return;
  state.reviewListExpanded = false;
  syncReviewList();
  if (window.matchMedia("(max-width: 820px)").matches) {
    $(".review-intent-title")?.focus({ preventScroll: true });
    $(".review-rail")?.scrollIntoView({ block: "start", behavior: "instant" });
  } else {
    const item = document.querySelector(`#review-list [data-review="${CSS.escape(review.id)}"]`);
    item?.focus({ preventScroll: true });
    item?.scrollIntoView({ block: "nearest" });
  }
}

function renderWorkspace() {
  const hasProject = Boolean(state.activeProject);
  $("#new-project-button")?.classList.toggle("button-primary", !hasProject || !state.reviews.length);
  $("#new-project-button")?.classList.toggle("button-quiet", hasProject && Boolean(state.reviews.length));
  $("#empty-state").classList.toggle("hidden", hasProject);
  $("#workspace").classList.toggle("hidden", !hasProject);
  if (!hasProject) {
    $("#toggle-file-panel-button")?.classList.add("hidden");
    return;
  }
  const project = state.activeProject;
  $("#project-name").textContent = project.name;
  $("#repo-path").textContent = displayRepo(project);
  $("#project-version").textContent = `Version ${project.version}`;
  $("#project-head").textContent = short(project.head_ref);
  $("#toggle-file-panel-button")?.classList.remove("hidden");
  const rootCount = (project.attestation_trust_roots || []).filter((root) => root.status === "active").length;
  $("#project-tools-state").textContent = `${plural((project.claims || []).length, "claim")} · ${plural(rootCount, "trusted key")}`;
  renderProjectClaims();
  renderTrustRegistry();
  renderIntentWorkspace();
  renderProjectTree();
  setFilePanelOpen(state.filePanelOpen);
  setInspectorTab(state.inspectorTab);
  $("#review-count").textContent = state.reviews.length;
  const railTools = $("#review-rail-tools");
  const filter = ($("#review-filter")?.value || "").trim().toLowerCase();
  // An empty value can be an in-progress edit, not a request to close search.
  if (railTools) railTools.classList.toggle("hidden", state.reviews.length < 6 && !filter && !reviewQueries.has(project.id));
  const visibleReviews = matchingReviewList();
  $("#review-filter-feedback").hidden = !filter;
  $("#review-filter-status").textContent = state.reviewsLoading
    ? "Loading reviews…" : `${visibleReviews.length} of ${plural(state.reviews.length, "review")}`;
  const skeleton = '<div class="review-item review-item-skeleton" aria-hidden="true"><span class="loading-skeleton loading-skeleton-short"></span><span class="loading-skeleton"></span><span class="loading-skeleton loading-skeleton-short"></span></div>';
  $("#review-list").innerHTML = state.reviewsLoading && !state.reviews.length
    ? `${skeleton}${skeleton}${skeleton}<span class="sr-only" role="status">Loading reviews</span>`
    : state.reviews.length ? visibleReviews.length ? renderReviewGroups(visibleReviews, (review) => {
    const openFindings = (review.findings || []).filter((item) => item.status === "open");
    const attention = canvasReviewTone(review) === "attention";
    const meta = [plural((review.changed_paths || []).length, "file"), openFindings.length ? plural(openFindings.length, "open finding") : ""].filter(Boolean).join(" · ");
    return `
    <button type="button" class="review-item ${state.activeReview?.id === review.id ? "active" : ""}" data-review="${esc(review.id)}" data-attention="${attention}" data-tone="${esc(canvasReviewTone(review))}"${state.activeReview?.id === review.id ? ' aria-current="true"' : ""} title="${esc(reviewRef(review))} · ${esc(meta)}">
      <p>${esc(review.intent_summary || review.summary)}</p>
      <small><span class="status-pill status-${esc(review.status)}">${I18n.mark(attention ? "Needs attention" : reviewStatusLabel(review.status))}</span><span class="review-item-time">${I18n.mark(relativeTime(review.created_at))}</span></small>
    </button>`;
  }) : '<div class="rail-empty"><p>No review matches this filter.</p><button type="button" class="button button-small" data-clear-review-filter>Clear filter</button></div>'
    : '<div class="rail-empty"><p>No pull requests yet.</p><button type="button" class="text-button" data-create-review>Start a review</button></div>';
  document.querySelectorAll("[data-review]").forEach((node) => {
    node.addEventListener("click", () => selectReviewFromList(node.dataset.review));
  });
  syncReviewList();
  $("[data-clear-review-filter]")?.addEventListener("click", clearReviewFilter);
  $("[data-create-review]")?.addEventListener("click", () => $("#new-review-button")?.click());
  const view = state.activeReview ? "review" : state.viewMode;
  document.body.dataset.view = view;
  document.querySelectorAll("[data-view-tab]").forEach((button) => {
    const active = button.dataset.viewTab === view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const openCount = state.reviews.filter((review) => review.status === "open").length;
  const navCount = $("#view-nav-review-count");
  if (navCount) {
    navCount.textContent = String(openCount);
    navCount.hidden = !openCount;
  }
  $("#view-nav")?.toggleAttribute("hidden", !state.activeProject);
  $("#review-workbench")?.classList.toggle("hidden", ["governance", "intents"].includes(view));
  $("#governance-view")?.toggleAttribute("hidden", view !== "governance");
  $("#intents-view")?.toggleAttribute("hidden", view !== "intents");
  if (!state.activeReview) {
    if (view === "canvas") renderProjectCanvas();
    else if (view === "review") {
      destroyProjectCanvas();
      const noMatches = state.reviews.length && !visibleReviews.length;
      const emptyTitle = noMatches ? "No matching reviews" : state.reviews.length ? "Choose a review" : "No reviews yet";
      const emptyHint = noMatches ? "Change or clear the review filter to see available reviews."
        : state.reviews.length ? "Select one from the list to see what changed, what needs attention, and what to do next."
        : "Start one with New review. It appears here and on the canvas.";
      $("#review-canvas").innerHTML = state.reviewsLoading
        ? '<div class="review-loading" role="status"><div class="loading-skeleton loading-skeleton-title"></div><div class="loading-skeleton"></div></div>'
        : `<div class="detail-empty"><div><h2>${emptyTitle}</h2><p>${emptyHint}</p></div></div>`;
    }
    const assistantPanel = $("#inspector-assistant");
    if (assistantPanel) assistantPanel.innerHTML = '<div class="inspector-empty"><strong data-i18n=Select%20a%20pull%20request>Select a pull request</strong><p data-i18n=Then%20ask%20a%20question%20grounded%20in%20its%20evidence.>Then ask a question grounded in its evidence.</p></div>';
  }
}

async function selectReview(reviewId, expectedVersion = state.selectionVersion, { section = null } = {}) {
  if (expectedVersion !== state.selectionVersion) return;
  rememberReviewLocation();
  closeSnapshotFile(false);
  if (governanceReviewOrigin?.reviewId !== reviewId) governanceReviewOrigin = null;
  closeReviewOperations(reviewId);
  const reviewVersion = ++state.reviewSelectionVersion;
  const syncNotice = reviewSyncNotices.get(reviewId);
  const leavingCanvas = state.viewMode !== "review";
  state.viewMode = "review";
  setViewParam("review", reviewId);
  destroyProjectCanvas();
  if (leavingCanvas && window.matchMedia("(min-width: 1180px)").matches) setFilePanelOpen(state.filePanelPreference);
  renderWorkspace();
  renderReviewLoading(reviewId);
  try {
    const [review, events, manifest, contractGraph] = await Promise.all([
      api(`/api/reviews/${reviewId}`),
      api(`/api/reviews/${reviewId}/events`),
      api(`/api/reviews/${reviewId}/package`),
      api(`/api/reviews/${reviewId}/graph`),
    ]);
    if (expectedVersion !== state.selectionVersion || reviewVersion !== state.reviewSelectionVersion) return;
    if (state.activeReview?.id !== review.id) {
      state.changeMapDirectory = "";
      reviewWorkspaceTab = "overview";
      state.evidenceTab = "requirements";
      state.evidenceQuery = "";
      state.evidenceFilter = "all";
      state.evidenceObligation = "";
    }
    if (state.diffReviewId !== review.id || state.diffRevision !== review.revision) {
      state.diffReviewId = null;
      state.diffRevision = null;
      state.diffRequestVersion += 1;
      state.diffPromise = null;
      state.diffText = null;
      state.diffFiles = [];
      state.diffPath = null;
      state.diffInspection = null;
      state.diffQuery = "";
      state.diffLoading = false;
      state.diffError = null;
    }
    state.activeReview = review;
    if (section) reviewWorkspaceTab = section;
    state.events = events;
    state.manifest = manifest;
    state.contractGraph = contractGraph;
    if (reviewSyncNotices.get(reviewId) === syncNotice) reviewSyncNotices.delete(reviewId);
    renderWorkspace();
    renderReview();
    rememberReviewLocation();
    return review;
  } catch (error) {
    if (expectedVersion !== state.selectionVersion || reviewVersion !== state.reviewSelectionVersion) return;
    renderReviewError(reviewId, error);
    toast(error.message);
  }
}

function renderReviewLoading(reviewId) {
  destroyContractGraph();
  const detail = $("#review-canvas");
  detail.setAttribute("aria-busy", "true");
  detail.innerHTML = `
    <div class="review-loading" role="status" aria-live="polite">
      <div class="loading-skeleton loading-skeleton-title" aria-hidden="true"></div>
      <div class="loading-skeleton" aria-hidden="true"></div>
      <div class="loading-skeleton loading-skeleton-short" aria-hidden="true"></div>
      <span class="sr-only">Loading review ${esc(short(reviewId).toUpperCase())}</span>
    </div>`;
}

function renderReviewError(reviewId, error) {
  const detail = $("#review-canvas");
  detail.removeAttribute("aria-busy");
  detail.innerHTML = `
    <div class="review-error" role="alert">
      <h2>Couldn’t open this pull request</h2>
      <p>${esc(error?.message || "The review service did not return a complete response.")}</p>
      <button type="button" class="button button-primary retry-review-button" data-i18n=Try%20again>Try again</button>
      ${governanceReturnButton(reviewId)}
    </div>`;
  $(".retry-review-button")?.addEventListener("click", () => governanceReviewOrigin?.reviewId === reviewId
    ? openGovernanceReview(reviewId, governanceReviewOrigin.claimId) : selectReviewFromList(reviewId));
  bindGovernanceReturn();
  renderReviewSyncNotice();
}

function renderReviewWorkspaceTabs() {
  const selected = (value) => value === reviewWorkspaceTab
    ? ' aria-selected="true" tabindex="0"'
    : ' aria-selected="false" tabindex="-1"';
  const review = state.activeReview;
  const evidenceCount = (review?.evidence || []).length;
  return `
    <nav class="review-workspace-tabs" role="tablist" aria-label="Review sections">
      <button type="button" role="tab" id="review-tab-overview" data-review-tab="overview" aria-controls="review-panel-overview"${selected("overview")}><span data-i18n=Decision>Decision</span></button>
      <button type="button" role="tab" id="review-tab-changes" data-review-tab="changes" aria-controls="review-panel-changes"${selected("changes")}><span data-i18n=Changes>Changes</span><small>${review?.changed_paths?.length || 0}</small></button>
      <button type="button" role="tab" id="review-tab-evidence" data-review-tab="evidence" aria-controls="review-panel-evidence"${selected("evidence")} data-attention="${Boolean(review?.status === "open" && state.manifest && !state.manifest.committable)}"><span data-i18n=Evidence>Evidence</span><small>${evidenceCount}</small></button>
      <button type="button" role="tab" id="review-tab-audit" data-review-tab="audit" aria-controls="review-panel-audit"${selected("audit")}><span data-i18n=Audit>Audit</span></button>
    </nav>`;
}

function setReviewWorkspaceTab(tab, { focus = false } = {}) {
  const button = document.querySelector(`[data-review-tab="${tab}"]`);
  const panel = document.querySelector(`[data-review-panel="${tab}"]`);
  if (!button || !panel) return;
  const changed = reviewWorkspaceTab !== tab;
  reviewWorkspaceTab = tab;
  rememberReviewLocation();
  document.querySelectorAll("[data-review-tab]").forEach((item) => {
    const selected = item.dataset.reviewTab === tab;
    item.classList.toggle("active", selected);
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll("[data-review-panel]").forEach((item) => {
    item.hidden = item.dataset.reviewPanel !== tab;
  });
  window.requestAnimationFrame(()=>ReviewMotion.indicator($(".review-workspace-tabs"),'[aria-selected="true"]'));
  if (changed) ReviewMotion.enter(panel,"panel");
  if (tab === "changes") ensureDiffLoaded();
  if (tab === "audit") {
    if (!contractGraphInstance) renderContractGraph();
    else {
      window.requestAnimationFrame(() => {
        contractGraphInstance?.resize();
        contractGraphInstance?.fit(contractGraphInstance.elements().not(".lens-hidden"), 46);
      });
    }
  }
  if (focus) button.focus();
}

function returnToDecision() {
  setReviewWorkspaceTab('overview');
  const target = document.querySelector('.decision-bar') || document.querySelector('.review-verdict');
  if (!target) return;
  target.focus({ preventScroll: true });
  target.scrollIntoView({ block: 'nearest', behavior: 'instant' });
}

function handleReviewWorkspaceTabKeydown(event) {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  const tabs = [...document.querySelectorAll("[data-review-tab]")];
  const current = tabs.indexOf(event.currentTarget);
  if (current < 0) return;
  let next = current;
  if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
  if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") next = 0;
  if (event.key === "End") next = tabs.length - 1;
  event.preventDefault();
  setReviewWorkspaceTab(tabs[next].dataset.reviewTab, { focus: true });
}

function handleReviewMoreMenuKeydown(event) {
  if (!["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) return;
  const menu = event.currentTarget.closest(".review-more-menu");
  const items = [...menu.querySelectorAll('[role="menuitem"]')];
  if (!items.length) return;
  event.preventDefault();
  menu.open = true;
  const target = event.key === "ArrowUp" ? items.at(-1) : items[0];
  window.requestAnimationFrame(() => target.focus());
}

function handleReviewActionMenuKeydown(event) {
  const menu = event.currentTarget.closest(".review-more-menu");
  const summary = menu.querySelector("summary");
  if (event.key === "Escape") {
    event.preventDefault();
    menu.open = false;
    summary.focus();
    return;
  }
  if (event.key === "Tab") {
    menu.open = false;
    return;
  }
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const items = [...menu.querySelectorAll('[role="menuitem"]')];
  if (!items.length) return;
  event.preventDefault();
  const current = items.indexOf(document.activeElement);
  let next = current;
  if (event.key === "ArrowDown") next = (current + 1) % items.length;
  if (event.key === "ArrowUp") next = (current - 1 + items.length) % items.length;
  if (event.key === "Home") next = 0;
  if (event.key === "End") next = items.length - 1;
  items[next].focus();
}

function bindReviewMoreMenu() {
  const menu = $(".review-more-menu");
  if (!menu) return;
  const summary = menu.querySelector("summary");
  const actionMenu = menu.querySelector('[role="menu"]');
  menu.addEventListener("toggle", () => {
    summary.setAttribute("aria-expanded", String(menu.open));
  });
  summary.addEventListener("keydown", handleReviewMoreMenuKeydown);
  actionMenu.addEventListener("keydown", handleReviewActionMenuKeydown);
}

function reviewRiskItems(review, manifest) {
  const values = [];
  manifest.admission_checks
    .filter((item) => item.status === "block")
    .forEach((item) => values.push({
      title: plainReviewCheckLabel(item),
      detail: item.summary,
      source: "Required check",
    }));
  review.findings
    .filter((item) => item.status === "open")
    .forEach((item) => values.push({
      title: item.message,
      detail: item.path ? `${item.path}${item.line ? `:${item.line}` : ""}` : title(item.kind),
      source: item.severity === "warning" ? "Risk" : "Finding",
    }));
  const seen = new Set();
  return values.filter((item) => {
    const key = `${item.title}|${item.detail}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 3);
}

function reviewEvidenceState(review, kind) {
  return review.evidence.find((item) => item.kind === kind) || null;
}

function joinClauses(values) {
  const items = values.filter(Boolean);
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items.at(-1)}`;
}

function reviewFacts(review, manifest) {
  const tests = reviewEvidenceState(review, "tests");
  const staticAnalysis = reviewEvidenceState(review, "static_analysis");
  const openFindings = review.findings.filter((item) => effectiveFindingStatus(review, item) === "open");
  const criticalOpen = openFindings.filter((item) => item.severity === "critical").length;
  const structure = criticalOpen
    ? { label: plural(criticalOpen, "critical finding"), tone: "danger" }
    : staticAnalysis?.outcome === "contests"
      ? { label: "Conflict found", tone: "danger" }
      : staticAnalysis?.outcome === "inconclusive" || openFindings.length
        ? { label: `${plural(openFindings.length || 1, "open question")}`, tone: "warn" }
        : DecisionModel.reviewTrace(review, manifest).stages.find(item => item.id === "claims").value === "0"
          ? { label: "No claims linked", tone: "neutral" }
        : staticAnalysis?.status === "pass"
          ? { label: "No structural conflict", tone: "ok" }
          : { label: "Structure not analyzed", tone: "neutral" };
  const testFact = !tests || tests.status === "not_run"
    ? { label: "Tests not run", tone: "warn" }
    : tests.status === "pass"
      ? { label: "Tests passed", tone: "ok" }
      : tests.status === "fail"
        ? { label: "Tests failed", tone: "danger" }
        : { label: "Tests unknown", tone: "warn" };
  const obligations = manifest.obligation_statuses || [];
  const satisfied = obligations.filter((item) => ["satisfied", "waived"].includes(item.status)).length;
  const evidence = obligations.length
    ? { label: `${satisfied} of ${obligations.length} required records`, tone: satisfied === obligations.length ? "ok" : "warn" }
    : { label: `${plural(review.evidence.length, "evidence record")}`, tone: "neutral" };
  return [
    { term: "Files", label: plural(review.changed_paths.length, "file"), tone: review.changed_paths.length ? "neutral" : "warn" },
    { term: "Structure", ...structure },
    { term: "Tests", ...testFact },
    { term: "Evidence", ...evidence },
  ];
}

function verdictTone(review, manifest) {
  if (review.status === "committed") return "ok";
  if (review.status === "rejected" || review.status === "rolled_back") return "danger";
  if (review.status === "rebase_required") return "warn";
  return manifest.committable ? DecisionModel.requirementCoverage(review, manifest).tone : "warn";
}

function renderReviewVerdict(review, manifest) {
  const blockedChecks = manifest.admission_checks.filter((item) => item.status === "block");
  const terminal = review.status !== "open";
  const ready = manifest.committable || terminal;
  const headings = {
    committed: "Approved",
    rebase_required: "Update requested",
    rejected: "Rejected",
    rolled_back: "Approval rolled back",
  };
  const heading = terminal
    ? headings[review.status] || reviewStatusLabel(review.status)
    : ready ? DecisionModel.requirementCoverage(review, manifest).heading : "Not ready to approve";
  const openCritical = review.findings.filter((item) => item.severity === "critical" && effectiveFindingStatus(review, item) === "open").length;
  const missingRecords = (manifest.obligation_statuses || []).filter((item) => !["satisfied", "waived"].includes(item.status)).length;
  const blockerClauses = blockedChecks.map((item) => ({
    base_version: "a stale base",
    critical_findings: plural(openCritical || 1, "open critical finding"),
    evidence_obligations: plural(missingRecords || 1, "missing evidence record"),
    tests: /exited/i.test(item.summary || "") ? "failing tests" : "tests that have not run",
    static_analysis: "incomplete structure analysis",
  })[item.key] || plainReviewCheckLabel(item).toLowerCase());
  const lastDecision = review.decision_records?.at(-1);
  const reason = terminal
    ? lastDecision
      ? `${reviewStatusLabel(review.status)} by ${lastDecision.actor} ${relativeTime(lastDecision.created_at)}${lastDecision.reason ? ` — “${lastDecision.reason}”` : ""}.`
      : `${reviewStatusLabel(review.status)}. No attributed decision record is available in this review.`
    : ready
      ? "Only the configured checks have passed. This is not a guarantee that the change meets every requirement."
      : blockerClauses.length
        ? `Blocked by ${joinClauses(blockerClauses)}.`
        : `${plural(manifest.blockers.length, "blocking check")} must be resolved first.`;
  const facts = reviewFacts(review, manifest);
  const inspection = nextReviewInspection(review, manifest);
  const scope = DecisionModel.reviewScope(review, manifest);
  const coverage = DecisionModel.requirementCoverage(review, manifest);
  const reasonHtml=terminal?esc(reason):ready?I18n.mark("Configured checks passed."):blockerClauses.length
    ? blockerClauses.map(clause=>I18n.mark(clause)).join(' · ')
    : I18n.mark('{count} blocking checks must be resolved first.',{count:manifest.blockers.length});
  return `
    <section class="review-verdict" tabindex="-1" data-ready="${ready}" data-status="${esc(review.status)}" data-tone="${esc(verdictTone(review, manifest))}">
      <div class="verdict-brief">
      <div><h3>${I18n.mark(heading)}</h3><p class="verdict-reason">${reasonHtml}</p></div>
      <div class="review-next-inspection">
        <button type="button" class="button button-primary button-with-icon" id="next-review-inspection">${uiIcon("search")}<span>${I18n.mark(inspection.label)}</span></button>
      </div>
      </div>
      ${!terminal&&coverage.status==='unframed'?`<div class="requirement-coverage" data-coverage="unframed"><strong>${I18n.mark('No commitment linked')}</strong>${!document.body.classList.contains('viewer-mode')?`<button type="button" class="text-button" data-draft-commitment>${I18n.mark('Draft commitment')} ${uiIcon('arrow-right')}</button>`:''}</div>`:''}
      <details class="review-scope-note"><summary data-i18n=Assessment%20details>Assessment details</summary>
      <p class="review-coverage-note" aria-label="Structure check scope"><span data-i18n=Structure%20scope>Structure scope</span><span><b>${scope.pythonFiles}</b> <span data-i18n=Python%20files%20in%20this%20change>Python files in this change</span></span><span><b>${scope.claims}</b> <span data-i18n=linked%20rules>linked rules</span></span></p>
      <dl class="review-facts" aria-label="Review facts">
        ${facts.map((fact) => `<div data-tone="${esc(fact.tone)}"><dt class="sr-only">${I18n.mark(fact.term)}</dt><dd>${I18n.mark(fact.label)}</dd></div>`).join("")}
      </dl>
      <p>${I18n.mark(plainVersion(inspection.detail))}</p>${ready&&!terminal?`<p>${I18n.mark("Only the configured checks have passed. This is not a guarantee that the change meets every requirement.")}</p>`:""}<p data-i18n=Structure%20checks%20inspect%20changed%20Python%20imports%20and%20configured%20project%20rules.%20Tests%20run%20only%20when%20a%20command%20is%20configured.%20This%20does%20not%20prove%20behavioral%20correctness%20or%20replace%20human%20review.>Structure checks inspect changed Python imports and configured project rules. Tests run only when a command is configured. This does not prove behavioral correctness or replace human review.</p><p class="review-deterministic-summary">Recorded summary: ${esc(plainVersion(review.summary))}</p></details>
    </section>`;
}

function nextReviewInspection(review, manifest) {
  return DecisionModel.nextInspection({...review, findings:review.findings.map(item => ({...item,status:effectiveFindingStatus(review,item)}))}, manifest);
}

function inspectNextReviewStep() {
  const review = state.activeReview, manifest = state.manifest;
  if (!review || !manifest) return;
  const step = nextReviewInspection(review, manifest);
  if (step.kind === "finding") return openChangedFile(step.path, step.findingId);
  if (step.kind === "requirements" || step.kind === "records") {
    state.evidenceQuery = ""; state.evidenceFilter = "all"; state.evidenceObligation = "";
    $("#evidence-record-search").value = "";
    $("#evidence-record-filter").value = "all";
    refreshEvidenceRecords();
    setReviewWorkspaceTab("evidence");
    setEvidenceTab(step.kind === "records" ? "records" : "requirements", {focus:true});
    return;
  }
  if (step.kind === "audit" && review.decision_records?.length) {
    const history = document.querySelector(".decision-history");
    if (history) {
      setReviewWorkspaceTab("overview");
      history.open = true;
      const record = history.querySelector(".decision-record:last-child") || history.querySelector("summary");
      record.focus({preventScroll:true});
      record.scrollIntoView({block:"nearest",behavior:"instant"});
      return;
    }
  }
  if (step.kind === "changes" || step.kind === "audit") {
    setReviewWorkspaceTab(step.kind, {focus:true});
    return;
  }
  const check = [...document.querySelectorAll("[data-admission-check]")].find(node => node.dataset.admissionCheck === step.checkKey);
  if (check) {
    for (let parent = check.parentElement; parent; parent = parent.parentElement) if (parent.tagName === "DETAILS") parent.open = true;
    check.open = true;
    check.querySelector("summary").focus();
    check.scrollIntoView({block:"nearest",behavior:"instant"});
  }
}

function reviewPatchMetrics(review) {
  const match = String(review.patch_summary || "").match(
    /(\d+)\s+files? changed(?:,\s*(\d+)\s+insertions?\(\+\))?(?:,\s*(\d+)\s+deletions?\(-\))?/i
  );
  return {
    files: Number(match?.[1] || review.changed_paths?.length || 0),
    additions: Number(match?.[2] || 0),
    deletions: Number(match?.[3] || 0),
  };
}

function changedFileStats(review) {
  const parsed = new Map();
  String(review.patch_summary || "").split("\n").forEach((line) => {
    const match = line.match(/^(.+?)\s+\|\s+(\d+)\s*([+-]*)\s*$/);
    if (!match) return;
    parsed.set(match[1].trim(), {
      lines: Number(match[2]),
      marks: match[3],
    });
  });
  const diffFiles = new Map((state.diffFiles || []).map((file) => [file.path, file]));
  return (review.changed_paths || []).map((path) => {
    const stat = parsed.get(path) || { lines: 0, marks: "" };
    const directory = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "Project root";
    const filename = path.includes("/") ? path.slice(path.lastIndexOf("/") + 1) : path;
    const diffFile = diffFiles.get(path);
    const additions = diffFile ? diffFile.additions : null;
    const deletions = diffFile ? diffFile.deletions : null;
    const changeType = {added:"Added", deleted:"Removed", renamed:"Renamed", modified:"Modified"}[diffFile?.status] || "Changed";
    return { path, directory, filename, changeType, additions, deletions, sizeKnown:Boolean(diffFile || parsed.has(path)), partial:Boolean(diffFile?.partial), ...stat, lines: diffFile ? additions + deletions : stat.lines };
  });
}

function parseUnifiedDiff(text = "") {
  return DiffModel.parse(text);
}

const CODE_KEYWORDS = {
  python: new Set("False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case self cls".split(" ")),
  javascript: new Set("break case catch class const continue debugger default delete do else export extends finally for function if import in instanceof new return super switch this throw try typeof var void while with yield let static async await of null undefined true false from as".split(" ")),
  data: new Set(["true", "false", "null", "yes", "no", "on", "off"]),
  shell: new Set("if then else elif fi for while do done case esac function in export local return exit set".split(" ")),
};

function codeLanguage(path = "") {
  const extension = path.slice(path.lastIndexOf(".") + 1).toLowerCase();
  if (["py", "pyi"].includes(extension)) return "python";
  if (["js", "mjs", "cjs", "ts", "tsx", "jsx"].includes(extension)) return "javascript";
  if (["json", "yaml", "yml", "toml", "ini", "cfg", "env"].includes(extension)) return "data";
  if (["sh", "bash", "zsh"].includes(extension)) return "shell";
  return null;
}

const CODE_PATTERNS = {
  python: /(#.*$)|("{3}[\s\S]*?"{3}|'{3}[\s\S]*?'{3}|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(@[A-Za-z_][\w.]*)|(\b\d[\d_]*(?:\.\d+)?\b)|(\b[A-Za-z_]\w*\b)/g,
  javascript: /(\/\/.*$|\/\*[\s\S]*?\*\/)|(`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(@[A-Za-z_]\w*)|(\b\d[\d_]*(?:\.\d+)?\b)|(\b[A-Za-z_$][\w$]*\b)/g,
  data: /(#.*$)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|()|(\b-?\d+(?:\.\d+)?\b)|(\b[A-Za-z_][\w-]*\b)/g,
  shell: /(#.*$)|("(?:\\.|[^"\\])*"|'[^']*')|(\$[\w{}@#?]+)|(\b\d+\b)|(\b[A-Za-z_][\w-]*\b)/g,
};

function highlightCode(text = "", language = null) {
  const pattern = language ? CODE_PATTERNS[language] : null;
  if (!pattern || !text) return esc(text);
  const keywords = CODE_KEYWORDS[language] || new Set();
  let output = "";
  let last = 0;
  let previous = "";
  text.replace(pattern, (match, comment, string, decorator, number, word, offset) => {
    output += esc(text.slice(last, offset));
    let className = "";
    if (comment) className = "tok-comment";
    else if (string) className = "tok-string";
    else if (decorator) className = "tok-decorator";
    else if (number) className = "tok-number";
    else if (word && keywords.has(word)) className = "tok-keyword";
    else if (word && ["def", "class", "function"].includes(previous)) className = "tok-def";
    else if (word && language === "data" && text.slice(offset + match.length).trimStart().startsWith(":") && /^[\s-]*$/.test(text.slice(0, offset))) className = "tok-key";
    if (word) previous = word;
    output += className ? `<span class="${className}">${esc(match)}</span>` : esc(match);
    last = offset + match.length;
    return match;
  });
  output += esc(text.slice(last));
  return output;
}

function diffFileFindings(review, path) {
  return (review.findings || []).filter((item) => item.path === path);
}

function renderDiffFile(file, review) {
  const findings = DiffModel.annotations(file, review.findings);
  const open = review.status === "open";
  const annotation = (item, unplaced = false) => {
    const status = effectiveFindingStatus(review, item);
    const tone = status !== "open" ? "ok" : item.severity === "critical" ? "danger" : "warn";
    const action = open && status === "open"
      ? `<button type="button" class="button button-small waive-button" data-finding="${esc(item.id)}">Bounded waiver</button>`
      : `<span class="tag" data-tone="${tone}">${esc(sentence(status))}</span>`;
    return `<div class="diff-annotation" data-severity="${esc(item.severity)}" data-finding-location="${esc(item.id)}" tabindex="-1"><div class="diff-annotation-copy"><span class="tag" data-tone="${tone}">${esc(sentence(item.kind))}</span><strong>${esc(item.message)}</strong><small>${item.line ? `Line ${item.line}${unplaced ? " — outside the displayed patch" : ""}` : "File-level finding"}</small><small>Claim: ${esc(item.rule_id)}</small></div>${action}</div>`;
  };
  const language = codeLanguage(file.path);
  const codeRows = file.rows.filter(row => row.kind !== "meta");
  const metadata = file.rows.filter(row => row.kind === "meta");
  const body = file.binary
    ? '<p class="diff-binary">Binary file changed; no textual diff is available.</p>'
    : !codeRows.length
      ? `<p class="diff-binary">${file.partial ? "The available patch is incomplete. Inspect the source repository for the remaining changes." : file.status === "added" ? "Empty file added." : file.status === "deleted" ? "Empty file removed." : "No text changes. Only the file path or metadata changed."}</p>`
      : `<table class="diff-table" aria-label="Diff for ${esc(file.path)}" data-language="${esc(language || "text")}"><tbody>${file.rows.map((row, index) => {
      if (row.kind === "meta") return "";
      if (row.kind === "hunk") return `<tr class="hunk"><td class="diff-ln"></td><td class="diff-ln"></td><td class="diff-sign"></td><td class="diff-code">${esc(row.text)}</td></tr>`;
      if (row.kind === "note") return `<tr class="meta"><td colspan="4" class="diff-code">${esc(row.text)}</td></tr>`;
      const sign = row.kind === "add" ? "+" : row.kind === "del" ? "−" : "";
      const oldNumber = row.kind === "add" ? "" : row.oldLine;
      const newNumber = row.kind === "del" ? "" : row.newLine;
      return `<tr class="${row.kind}"${findings.byRow[index] ? ' data-has-finding="true"' : ""}><td class="diff-ln">${oldNumber ?? ""}</td><td class="diff-ln">${newNumber ?? ""}</td><td class="diff-sign">${sign}</td><td class="diff-code">${highlightCode(row.text, language)}</td></tr>${(findings.byRow[index] || []).map(item => `<tr class="diff-finding-row"><td colspan="4">${annotation(item)}</td></tr>`).join("")}`;
    }).join("")}</tbody></table>`;
  const statusLabel = { added: "Added", deleted: "Removed", renamed: "Renamed", modified: "Modified" }[file.status] || "Changed";
  return `<article class="diff-file" data-path="${esc(file.path)}" aria-label="${esc(file.path)}">
    <header class="diff-file-head"><span class="diff-file-path">${esc(file.path)}${file.oldPath !== file.path ? ` <small>from ${esc(file.oldPath)}</small>` : ""}</span><span class="tag" data-tone="${file.status === "added" ? "ok" : file.status === "deleted" ? "danger" : "neutral"}">${esc(statusLabel)}</span><span class="diff-file-stat"><b class="add">+${file.additions}</b><b class="del">−${file.deletions}</b></span><button type="button" class="diff-copy-path" data-copy-path="${esc(file.path)}" aria-label="Copy path ${esc(file.path)}" data-tooltip="Copy path">${uiIcon("link")}${controlTooltip("Copy path")}</button></header>
    ${findings.unplaced.map(item => annotation(item, true)).join("")}
    ${file.partial && codeRows.length ? '<p class="diff-binary" role="note">This patch is incomplete. File line counts reflect only the displayed portion; inspect the source repository for the remaining changes.</p>' : ""}
    ${body}
    ${metadata.length ? `<details class="diff-metadata"><summary>Patch metadata</summary><pre>${esc(metadata.map(row => row.text).join("\n"))}</pre></details>` : ""}
  </article>`;
}

function renderDiffViewer() {
  const viewer = $("#diff-viewer");
  const review = state.activeReview;
  if (!viewer || !review) return;
  const fileView = DiffModel.fileView(review.changed_paths, state.diffFiles, state.diffPath, state.diffQuery);
  if (fileView.selected) state.diffPath = fileView.selected.path;
  const selectedPath = fileView.selected?.path || "";
  const fileChanged = viewer.dataset.path !== selectedPath;
  viewer.dataset.path = selectedPath;
  renderDiffNavigation(review);
  if (state.diffLoading) {
    viewer.innerHTML = '<p class="diff-status" role="status">Loading the diff for this review…</p>';
    return;
  }
  if (state.diffError) {
    viewer.innerHTML = `<div class="diff-status" role="alert"><strong>Couldn’t load the code changes</strong><p>Check your connection and try again. Your selected file is kept.</p><small>${esc(state.diffError)}</small><button type="button" class="button retry-diff-button" data-i18n=Try%20again>Try again</button></div>`;
    $(".retry-diff-button")?.addEventListener("click", retryReviewDiff);
    return;
  }
  if (!fileView.selected) {
    viewer.innerHTML = `<div class="diff-status" role="status"><strong>${state.diffQuery ? "No matching files" : "No changed files"}</strong><p>${state.diffQuery ? `No path contains “${esc(state.diffQuery)}”.` : "No file changes were recorded for this review."}</p>${state.diffQuery ? '<button type="button" class="button clear-diff-filter">Clear file search</button>' : ""}</div>`;
    $(".clear-diff-filter")?.addEventListener("click", () => { state.diffQuery = ""; renderDiffViewer(); $("#review-file-search")?.focus(); });
    return;
  }
  viewer.innerHTML = fileView.selected.file
    ? renderDiffFile(fileView.selected.file, review)
    : `<div class="diff-status" role="status"><strong>${esc(fileView.selected.path)}</strong><p>${state.diffTruncated ? "This file is outside the available patch. The server limited the diff size; inspect the source repository before deciding." : "No patch was recorded for this file. Inspect the source repository before deciding."}</p></div>`;
  if (fileChanged) viewer.scrollTop = 0;
  viewer.querySelectorAll(".waive-button").forEach((node) => node.addEventListener("click", () => openDecision("waive", node.dataset.finding)));
  viewer.querySelectorAll("[data-copy-path]").forEach((node) => node.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    try {
      await copyText(node.dataset.copyPath);
      toast(`Copied ${node.dataset.copyPath}`, "success");
    } catch {
      toast("Copy failed", "error");
    }
  }));
  renderInspectorChangedFiles();
}

async function retryReviewDiff(event) {
  const review = state.activeReview;
  const path = state.diffPath;
  const inspection = state.diffInspection;
  const button = event.currentTarget;
  const restoreFocus = document.activeElement === button;
  await ensureDiffLoaded(true);
  if (!restoreFocus || state.activeReview?.id !== review?.id || state.activeReview?.revision !== review?.revision
    || state.diffPath !== path || state.diffError || reviewWorkspaceTab !== "changes"
    || ![button, document.body].includes(document.activeElement)) return;
  const finding = inspection?.reviewId === review.id && inspection.revision === review.revision && inspection.path === path
    ? document.querySelector(`[data-finding-location="${CSS.escape(inspection.findingId)}"]`) : null;
  const destination = finding || $("#diff-viewer");
  destination?.focus({preventScroll:true});
  destination?.scrollIntoView({behavior:"instant",block:"nearest"});
}

function renderDiffNavigation(review) {
  const block = $("#changed-files-block");
  if (!block) return;
  const active = block.contains(document.activeElement) ? document.activeElement : null;
  const focusId = active?.id;
  const search = $("#review-file-search");
  if (search) {
    // Keep the input connected while typing, including an in-progress IME
    // composition. Replacing it and restoring focus loses native input state.
    const template = document.createElement("template");
    template.innerHTML = renderChangedFiles(review);
    for (const selector of [".diff-navigation-heading", ".diff-step-controls"]) {
      block.querySelector(selector).replaceWith(template.content.querySelector(selector));
    }
    const select = $("#review-file-select");
    const nextSelect = template.content.querySelector("#review-file-select");
    const optionsKey = node => JSON.stringify([...node.options].map(option => [option.value, option.textContent]));
    if (optionsKey(select) !== optionsKey(nextSelect)) select.innerHTML = nextSelect.innerHTML;
    select.value = nextSelect.value;
    select.disabled = nextSelect.disabled;
    if (search.value !== state.diffQuery) search.value = state.diffQuery;
  } else {
    block.innerHTML = renderChangedFiles(review);
  }
  $("#review-file-search").oninput = (event) => {
    state.diffQuery = event.target.value;
    renderDiffViewer();
  };
  $("#review-file-select").onchange = (event) => {
    state.diffPath = event.target.value;
    renderDiffViewer();
  };
  block.querySelectorAll("[data-diff-step]").forEach(node => node.addEventListener("click", () => {
    state.diffPath = node.dataset.diffStep;
    renderDiffViewer();
  }));
  if (focusId) {
    const target = document.getElementById(focusId);
    if (target !== document.activeElement) (target?.disabled ? $("#review-file-select") : target)?.focus({ preventScroll: true });
  }
}

async function ensureDiffLoaded(force = false) {
  const review = state.activeReview;
  if (!review) return null;
  if (!force && state.diffReviewId === review.id && state.diffRevision === review.revision && state.diffText !== null && !state.diffError) return state.diffText;
  if (state.diffLoading && state.diffReviewId === review.id && state.diffRevision === review.revision && state.diffPromise) return state.diffPromise;
  state.diffReviewId = review.id;
  state.diffRevision = review.revision;
  state.diffLoading = true;
  state.diffError = null;
  renderDiffViewer();
  state.diffPromise = loadDiffText(review, ++state.diffRequestVersion);
  return state.diffPromise;
}

async function loadDiffText(review, requestVersion) {
  const current = () => state.activeReview?.id === review.id && state.activeReview?.revision === review.revision && state.diffRequestVersion === requestVersion;
  try {
    const result = await api(`/api/reviews/${review.id}/diff`);
    if (!current()) return null;
    state.diffText = result.diff || "";
    state.diffTruncated = Boolean(result.truncated);
    state.diffCharacters = result.character_count || state.diffText.length;
    state.diffFiles = parseUnifiedDiff(state.diffText);
    if (state.diffTruncated && state.diffFiles.length) state.diffFiles.at(-1).partial = true;
    const note = $("#diff-note");
    if (note) {
      note.textContent = state.diffTruncated ? "Diff is truncated at the safe display limit." : "";
      note.classList.toggle("hidden", !state.diffTruncated);
    }
    return state.diffText;
  } catch (error) {
    if (current()) state.diffError = error.message;
    return null;
  } finally {
    if (current()) {
      state.diffPromise = null;
      state.diffLoading = false;
      renderDiffViewer();
    }
  }
}

function renderChangedFiles(review) {
  const metrics = reviewPatchMetrics(review);
  const fileView = DiffModel.fileView(review.changed_paths, state.diffFiles, state.diffPath, state.diffQuery);
  return `
    <div class="diff-navigation" role="group" aria-label="Changed files" data-i18n-aria-label=Changed%20files>
      <div class="diff-navigation-heading"><h3>${plural(fileView.total, "changed file")}</h3><span class="diff-file-stat" role="img" aria-label="${metrics.additions} lines added, ${metrics.deletions} removed"><b class="add">+${metrics.additions}</b><b class="del">−${metrics.deletions}</b></span><span class="diff-position" role="status">${state.diffQuery ? `${fileView.matches.length} of ${fileView.total} match` : `File ${fileView.position} of ${fileView.total}`}</span></div>
      <div class="diff-navigation-controls">
        <label class="diff-search"><span class="sr-only">Find changed file</span><input type="search" id="review-file-search" value="${esc(state.diffQuery)}" placeholder="Find file…" autocomplete="off" spellcheck="false"></label>
        <label class="diff-select"><span class="sr-only">Current changed file</span><select id="review-file-select" aria-controls="diff-viewer"${fileView.matches.length ? "" : " disabled"}>${fileView.matches.length ? fileView.matches.map(item => {
          const findings = diffFileFindings(review, item.path).filter(item => effectiveFindingStatus(review, item) === "open").length;
          return `<option value="${esc(item.path)}"${item.path === fileView.selected?.path ? " selected" : ""}>${esc(item.path)}${findings ? ` (${plural(findings, "open finding")})` : ""}</option>`;
        }).join("") : '<option data-i18n=No%20matching%20files>No matching files</option>'}</select></label>
        <div class="diff-step-controls"><button type="button" id="diff-previous" class="button" data-diff-step="${esc(fileView.previous || "")}" aria-label="Previous file"${fileView.previous ? "" : " disabled"}>${uiIcon("chevron-left")}</button><button type="button" id="diff-next" class="button" data-diff-step="${esc(fileView.next || "")}" aria-label="Next file"${fileView.next ? "" : " disabled"}>${uiIcon("chevron-right")}</button></div>
      </div>
    </div>`;
}

function renderEvidenceBrief(review, manifest) {
  const { pending } = EvidenceModel.requirements(review, manifest);
  const findings = (review.findings || []).filter(item => effectiveFindingStatus(review, item) === "open");
  const total = pending.length + findings.length;
  const blocked = review.status === "open" && manifest.committable === false;
  const heading = review.status !== "open" ? "Evidence for this decision"
    : total ? "{count} items need attention" : blocked ? "Not ready to approve" : "No outstanding evidence items";
  return `<section class="evidence-brief module" data-attention="${review.status === "open" && (total > 0 || blocked)}">
    <div><h3>${I18n.mark(heading,{count:total})}</h3><p>${I18n.mark(total ? "{requirements} requirements · {findings} findings" : blocked ? "Other checks need attention. Return to Decision." : "Approval is recorded separately.",{requirements:pending.length,findings:findings.length})}</p></div>
  </section>`;
}

function renderEvidenceWorkspace(review, manifest) {
  const { pending, covered } = EvidenceModel.requirements(review, manifest);
  const unresolved = (review.findings || []).filter(item => effectiveFindingStatus(review, item) === "open");
  const resolved = (review.findings || []).filter(item => effectiveFindingStatus(review, item) !== "open");
  const panel = (key) => `role="tabpanel" id="evidence-panel-${key}" aria-labelledby="evidence-tab-${key}" data-evidence-panel="${key}"${state.evidenceTab === key ? "" : " hidden"}`;
  return `<div class="evidence-workbench">
    <header class="evidence-workspace-header">${renderEvidenceBrief(review, manifest)}<button type="button" class="text-button" data-return-to-decision>${uiIcon("chevron-left")}${I18n.mark("Back to decision")}</button></header>
    <div class="evidence-view-tabs" role="tablist" aria-label="Evidence views">${[
      ["requirements", review.status === "open" ? "To resolve" : "Coverage", pending.length + unresolved.length],
      ["records", "Records", review.evidence.length],
      ["claims", "Claims", review.claim_deltas.length],
    ].map(([key,label,count]) => `<button type="button" role="tab" id="evidence-tab-${key}" data-evidence-tab="${key}" aria-controls="evidence-panel-${key}" aria-selected="${state.evidenceTab === key}" tabindex="${state.evidenceTab === key ? 0 : -1}">${I18n.mark(label)}<span>${count}</span></button>`).join("")}</div>
    <section ${panel("requirements")}>
      <section id="required-evidence" class="evidence-section"><header class="section-heading"><h3 data-i18n=Evidence%20to%20collect>Evidence to collect</h3>${I18n.mark(pending.length===1?'{count} requirement':'{count} requirements',{count:pending.length})}</header>
        ${pending.length ? renderEvidenceObligations(review, manifest, pending) : '<p class="evidence-empty" data-i18n=No%20outstanding%20requirements.>No outstanding requirements.</p>'}
      </section>
      <section id="review-findings" class="evidence-section"><header class="section-heading"><h3 data-i18n=Findings%20to%20review>Findings to review</h3>${I18n.mark(unresolved.length===1?'{count} finding':'{count} findings',{count:unresolved.length})}</header>
        ${unresolved.length ? renderFindings({...review, findings:unresolved}) : '<p class="evidence-empty" data-i18n=No%20open%20findings.>No open findings.</p>'}
      </section>
      ${covered.length ? `<details class="review-disclosure evidence-covered"><summary><span data-i18n=Covered%20requirements>Covered requirements</span><small>${covered.length}</small></summary>${renderEvidenceObligations(review, manifest, covered)}</details>` : ""}
      ${resolved.length ? `<details class="review-disclosure evidence-covered"><summary><span data-i18n=Resolved%20or%20waived%20findings>Resolved or waived findings</span><small>${resolved.length}</small></summary>${renderFindings({...review, findings:resolved})}</details>` : ""}
    </section>
    <section ${panel("records")}>
      <div class="evidence-record-tools"><label><span class="sr-only" data-i18n=Search%20evidence%20records>Search evidence records</span><input type="search" id="evidence-record-search" value="${esc(state.evidenceQuery)}" placeholder="Find a record or source…" autocomplete="off" data-i18n-placeholder=Find%20a%20record%20or%20source%E2%80%A6></label><label><span class="sr-only" data-i18n=Filter%20evidence%20records>Filter evidence records</span><select id="evidence-record-filter"><option value="all"${state.evidenceFilter === "all" ? " selected" : ""} data-i18n=All%20records>All records</option><option value="attention"${state.evidenceFilter === "attention" ? " selected" : ""} data-i18n=Needs%20attention>Needs attention</option></select></label></div>
      <div id="evidence-record-scope"></div><div class="evidence-record-status"><p id="evidence-record-count" class="evidence-record-count" role="status"></p><button type="button" class="button button-quiet" id="refresh-evidence-records" data-i18n=Refresh%20records>Refresh records</button></div>
      <div id="evidence-record-list">${renderEvidence(review)}</div>
    </section>
    <section ${panel("claims")}><p class="evidence-view-copy" data-i18n=The%20project%20rules%20this%20change%20affects.%20These%20observations%20are%20not%20automatically%20accepted%20changes%20to%20those%20rules.>The project rules this change affects. These observations are not automatically accepted changes to those rules.</p>${renderClaimDeltas(review)}</section>
  </div>`;
}

function setEvidenceTab(tab, { focus = false } = {}) {
  const button = document.querySelector(`[data-evidence-tab="${tab}"]`);
  if (!button) return;
  state.evidenceTab = tab;
  document.querySelectorAll("[data-evidence-tab]").forEach(item => {
    const selected = item.dataset.evidenceTab === tab;
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll("[data-evidence-panel]").forEach(item => { item.hidden = item.dataset.evidencePanel !== tab; });
  if (focus) button.focus();
}

function refreshEvidenceRecords() {
  const review = state.activeReview;
  const list = $("#evidence-record-list");
  if (!review || !list) return;
  list.innerHTML = renderEvidence(review);
  const count = EvidenceModel.recordView(review.evidence, review.target_ref, state.evidenceQuery, state.evidenceFilter, state.evidenceObligation, state.manifest?.invalidated_evidence_ids).length;
  $("#evidence-record-count").textContent = `${count} of ${plural(review.evidence.length, "record")}`;
  const obligation = review.evidence_obligations?.find(item => item.id === state.evidenceObligation);
  $("#evidence-record-scope").innerHTML = obligation
    ? `<div class="evidence-scope">${I18n.mark('Linked to: {title}',{title:EvidenceModel.obligationContext(review,obligation,state.activeProject?.claims||[]).title})}<button type="button" class="button button-quiet" data-clear-evidence-filters data-i18n=Show%20all%20records>Show all records</button></div>` : "";
}

function focusEvidenceObligation(obligationId) {
  state.evidenceQuery = '';
  state.evidenceFilter = 'all';
  state.evidenceObligation = obligationId;
  const search = $('#evidence-record-search'), filter = $('#evidence-record-filter');
  if (search) search.value = '';
  if (filter) filter.value = 'all';
  refreshEvidenceRecords();
  setReviewWorkspaceTab('evidence');
  setEvidenceTab('requirements');
  document.querySelectorAll('[data-obligation-card]').forEach(card=>{
    const selected = card.dataset.obligationCard === obligationId;
    card.dataset.focused = String(selected);
    if (!selected) return;
    const disclosure = card.closest('details');
    if (disclosure) disclosure.open = true;
    const plan = card.querySelector('.obligation-plan');
    if (plan) plan.open = true;
    card.focus({preventScroll:true});
    card.scrollIntoView({block:'center',behavior:'instant'});
  });
}

function bindEvidenceWorkspace() {
  const root = $(".evidence-workbench");
  if (!root) return;
  root.querySelectorAll("[data-evidence-tab]").forEach(node => {
    node.addEventListener("click", () => setEvidenceTab(node.dataset.evidenceTab));
    node.addEventListener("keydown", event => {
      if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
      const tabs = [...root.querySelectorAll("[data-evidence-tab]")];
      const current = tabs.indexOf(node);
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
        : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      event.preventDefault();
      setEvidenceTab(tabs[next].dataset.evidenceTab, {focus:true});
    });
  });
  $("#evidence-record-search").addEventListener("input", event => {
    state.evidenceQuery = event.currentTarget.value;
    refreshEvidenceRecords();
  });
  $("#evidence-record-filter").addEventListener("change", event => {
    state.evidenceFilter = event.currentTarget.value;
    refreshEvidenceRecords();
  });
  $("#refresh-evidence-records").addEventListener("click", async event => {
    const button = event.currentTarget;
    setBusy(button, true, "Refreshing…");
    try {
      const review = await selectReview(state.activeReview.id);
      if (review && state.activeReview?.id === review.id) {
        toast("Evidence refreshed");
        if (state.evidenceTab === "records" && reviewWorkspaceTab === "evidence") $("#refresh-evidence-records")?.focus();
      }
    } finally {
      setBusy(button, false);
    }
  });
  root.addEventListener("click", event => {
    const linked = event.target.closest("[data-evidence-obligation]");
    const clear = event.target.closest("[data-clear-evidence-filters]");
    if (!linked && !clear) return;
    state.evidenceObligation = linked?.dataset.evidenceObligation || "";
    state.evidenceQuery = "";
    state.evidenceFilter = "all";
    $("#evidence-record-search").value = "";
    $("#evidence-record-filter").value = "all";
    refreshEvidenceRecords();
    if (linked) setEvidenceTab("records", {focus:true});
    else $("#evidence-record-search").focus();
  });
  refreshEvidenceRecords();
}

function evidenceErrorMessage(error) {
  if (error?.name === "TypeError") return "The connection failed and attachment could not be confirmed. Your draft is kept in this tab. Use Refresh records in Records before retrying to avoid a duplicate.";
  return `${error.message || "The record could not be attached."} Your draft is unchanged; correct the issue and try again.`;
}

function findingSymbol(item) {
  if (item.kind === "unobservable") return "?";
  if (item.severity === "warning" || item.kind === "overlap") return "◆";
  return "×";
}

function renderClaimDeltas(review) {
  if (!review.claim_deltas.length) return '<div class="empty-contract">No structural claim delta was inferred for this artifact change.</div>';
  return review.claim_deltas.map((delta) => {
    const claim = state.activeProject.claims.find((item) => item.id === delta.claim_id);
    const anchors = delta.artifact_anchors.map((anchor) => `
      <span class="anchor-chip">${esc(anchor.relation)} · ${esc(anchor.path)}${anchor.line ? `:${anchor.line}` : ""}</span>`).join("");
    return `
      <article class="delta-card" data-status="${esc(delta.status)}">
        <header><div><span class="delta-source">Inferred from ${esc(title(delta.source))}</span><h4>${esc(delta.claim_id)}</h4></div><span class="status-pill">${esc(title(delta.status))}</span></header>
        <p class="delta-summary">${esc(delta.summary)}</p>
        <dl>
          <div><dt>Committed claim</dt><dd>${esc(delta.before || claim?.title || "Not recorded")}</dd></div>
          <div><dt>Rehydrated observation</dt><dd>${esc(delta.after || "No candidate observation")}</dd></div>
          <div><dt>Scope / authority</dt><dd>${esc(delta.affected_scope || claim?.scope || "unspecified")} · ${esc(claim?.authority || "authority not assigned")}</dd></div>
        </dl>
        <div class="anchor-list">${anchors || '<span class="anchor-chip empty">No artifact anchor</span>'}</div>
      </article>`;
  }).join("");
}

function renderEvidence(review) {
  if (!review.evidence.length) return '<div class="evidence-empty"><strong>No records yet</strong><p>Evidence will appear here after checks run or an authorized record is attached.</p></div>';
  const records = EvidenceModel.recordView(review.evidence, review.target_ref, state.evidenceQuery, state.evidenceFilter, state.evidenceObligation, state.manifest?.invalidated_evidence_ids);
  if (!records.length) return '<div class="evidence-empty"><strong>No matching records</strong><p>Try another term or clear the filters.</p><button type="button" class="button" data-clear-evidence-filters>Clear filters</button></div>';
  return records.map((item) => {
    const assessment = EvidenceModel.assessRecord(item, review.target_ref, state.manifest?.invalidated_evidence_ids);
    const fields = [["Record ID",item.id],["Source",item.provenance || "Not recorded"],["Revision",item.artifact_ref || "Not recorded"],["Run result",sentence(item.status)],["Claim outcome",sentence(item.outcome)],["Stored freshness",sentence(item.freshness)]];
    if (item.recorded_by) fields.push(["Recorded by",item.recorded_by]);
    if (item.authority) fields.push(["Authority",item.authority]);
    if (item.details?.signature_verified) fields.push(["Verified signing key",item.details.key_id]);
    if (item.invalidated_reason) fields.push(["Invalidated because",item.invalidated_reason]);
    if (item.claim_ids?.length) fields.push(["Claims",item.claim_ids.join(", ")]);
    if (item.obligation_ids?.length) fields.push(["Requirements",item.obligation_ids.join(", ")]);
    return `<article class="evidence-card" data-outcome="${esc(item.outcome)}" data-freshness="${esc(item.freshness)}" data-attention="${assessment.attention}">
      <header><span>${esc(sentence(item.kind))}</span><b>${assessment.label}</b></header>
      <p>${esc(plainVersion(item.summary))}</p>
      <small>Run: ${esc(sentence(item.status))}${item.artifact_ref ? ` · revision <code>${esc(short(item.artifact_ref))}</code>` : ""}${assessment.label === "Invalidated" ? " · Signing trust was revoked retroactively. This record cannot establish coverage." : ""}</small>
      <details class="evidence-record-details"><summary>Record details</summary><dl>${fields.map(([label,value]) => `<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl></details>
    </article>`;
  }).join("");
}

function renderEvidenceObligations(review, manifest, entries = null) {
  const obligations = review.evidence_obligations || [];
  if (!obligations.length) {
    return '<div class="empty-contract" data-i18n=No%20claim-level%20evidence%20obligation%20is%20declared%20for%20this%20proposal.>No claim-level evidence obligation is declared for this proposal.</div>';
  }
  const groups = EvidenceModel.requirements(review, manifest);
  const symbols = { satisfied: "●", waived: "◆", missing: "○", contested: "!", stale: "?" };
  return `<div class="obligation-list">${(entries || [...groups.pending, ...groups.covered]).map(({obligation, status}) => {
    const signed = obligation.verification === "dsse_ed25519";
    const requiredSource = signed
      ? `Signed VSA · ${obligation.required_verifier_id} · ${obligation.required_verified_level}`
      : obligation.required_provenance_prefix
      ? `Source must begin ${obligation.required_provenance_prefix}`
      : "Any authorized attestation source";
    const actions = obligationActions(review, manifest, obligation, status);
    const context = EvidenceModel.obligationContext(review, obligation, state.activeProject?.claims || []);
    const explanation = {
      missing: "No qualifying record supports this requirement for the target revision.",
      stale: "Linked evidence is outdated or invalidated. Collect fresh evidence for the current target revision.",
      contested: "Linked evidence conflicts with this requirement. Investigate the result before attaching new evidence.",
      satisfied: "Qualifying evidence covers the target revision. This is not an approval of the review.",
      waived: "A time-limited waiver covers this requirement. It is not verified evidence.",
      unknown: "Coverage status is unavailable. Refresh the review before relying on this requirement.",
    }[status.status] || "Coverage status is unavailable. Check Decision before continuing.";
    const linked = (review.evidence || []).filter(item => (item.obligation_ids || []).includes(obligation.id)).length;
    return `
      <article class="obligation-card" data-status="${esc(status.status)}" data-obligation-card="${esc(obligation.id)}" data-focused="${state.evidenceObligation === obligation.id}" tabindex="-1">
        <div class="obligation-state" aria-hidden="true">${symbols[status.status] || "?"}</div>
        <div class="obligation-copy"><header><b>${I18n.mark(status.status === "missing" ? "Needs verification" : status.status === "unknown" ? "Unknown" : sentence(status.status))}</b><span>${I18n.mark(signed ? "Signed verification" : "Authorized record")}</span></header><h4>${esc(context.title)}</h4>
        <div class="obligation-footer"><details class="evidence-record-details"${state.evidenceObligation===obligation.id?' open':''}><summary data-i18n=Verification%20details>Verification details</summary>${context.statement?`<p class="obligation-claim">${esc(context.statement)}</p>`:''}<p class="obligation-explanation">${I18n.mark(explanation)}</p><div class="obligation-plan"><strong>${I18n.mark('Verification plan')}</strong><ol>${context.plan.split(/\n+/).filter(Boolean).map(line=>`<li>${esc(line)}</li>`).join('')}</ol></div><dl><div><dt data-i18n=Requirement%20ID>Requirement ID</dt><dd>${esc(obligation.id)}</dd></div><div><dt data-i18n=Claim%20ID>Claim ID</dt><dd>${esc(obligation.claim_id)}</dd></div><div><dt data-i18n=Target%20revision>Target revision</dt><dd>${esc(review.target_ref)}</dd></div><div><dt data-i18n=Accepted%20source>Accepted source</dt><dd>${I18n.mark(requiredSource)}</dd></div><div><dt data-i18n=Exception%20policy>Exception policy</dt><dd>${I18n.mark(obligation.waivable ? "An authorized, bounded waiver is allowed." : "Mandatory. A waiver is not allowed.")}</dd></div>${status.evidence_ids?.length ? `<div><dt data-i18n=Evidence%20IDs>Evidence IDs</dt><dd>${esc(status.evidence_ids.join(", "))}</dd></div>` : ""}${status.waiver_ids?.length ? `<div><dt data-i18n=Waiver%20IDs>Waiver IDs</dt><dd>${esc(status.waiver_ids.join(", "))}</dd></div>` : ""}</dl></details><div class="obligation-actions">${actions}</div></div>
        ${linked || status.evidence_ids?.length ? `<button type="button" class="button button-quiet" data-evidence-obligation="${esc(obligation.id)}">View linked records${linked ? ` (${linked})` : ""}</button>` : ""}</div>
      </article>`;
  }).join("")}</div>`;
}

function effectiveFindingStatus(review, finding) {
  if (finding.status !== "waived") return finding.status;
  const active = (review.waivers || []).some((waiver) =>
    (waiver.finding_ids || []).includes(finding.id) && Date.parse(waiver.expires_at) > Date.now()
  );
  return active ? "waived" : "open";
}

function renderFindings(review) {
  const open = review.status === "open";
  if (!review.findings.length) return '<div class="empty-contract">No unresolved or conflicting relation was recorded.</div>';
  return review.findings.map((item) => {
    const effectiveStatus = effectiveFindingStatus(review, item);
    const expired = item.status === "waived" && effectiveStatus === "open";
    return `
    <article class="finding ${esc(effectiveStatus)}" data-kind="${esc(item.kind)}">
      <div class="finding-kind"><span class="tag" data-tone="${effectiveStatus !== "open" ? "neutral" : item.severity === "critical" ? "danger" : "warn"}">${esc(sentence(item.kind))}</span></div>
      <div><p>${esc(item.message)}</p><code>${esc(item.path || "project")}${item.line ? `:${item.line}` : ""} · ${esc(item.rule_id)}${expired ? " · prior waiver expired" : ""}</code></div>
      <div class="obligation-actions">${item.path ? `<button type="button" class="button button-small button-quiet" data-open-changed-file="${esc(item.path)}" data-open-finding="${esc(item.id)}">Show in diff</button>` : ""}${open && effectiveStatus === "open" ? `<button type="button" class="button button-small waive-button" data-finding="${esc(item.id)}">${expired ? "Renew waiver" : "Bounded waiver"}</button>` : `<span class="status-pill">${esc(effectiveStatus)}</span>`}</div>
    </article>`;
  }).join("");
}

function obligationActions(review, manifest, obligation, status) {
  const open = review.status === "open";
  if (!open || status.status === "satisfied") return "";
  const roots = state.activeProject?.attestation_trust_roots || [];
  const signed = obligation.verification === "dsse_ed25519";
  const now = Date.now();
  const hasEligibleRoot = !signed || roots.some((root) => {
    const validFrom = Date.parse(root.valid_from);
    const validUntil = root.valid_until ? Date.parse(root.valid_until) : null;
    return root.status === "active"
      && Number.isFinite(validFrom)
      && validFrom <= now
      && (validUntil === null || Number.isFinite(validUntil) && validUntil >= now)
      && root.verifier_id === obligation.required_verifier_id
      && (root.predicate_types || []).includes("https://slsa.dev/verification_summary/v1")
      && (review.required_authorities || []).includes(root.authority);
  });
  const attach = signed
    ? hasEligibleRoot
      ? `<button type="button" class="button button-small import-dsse-button" data-obligation="${esc(obligation.id)}">Import verification</button>`
      : `<button type="button" class="button button-small trust-root-required" disabled title="Add an active trust root matching this verifier and authority">Add eligible trust root</button>`
    : `<button type="button" class="button button-small attach-evidence-button" data-obligation="${esc(obligation.id)}" data-i18n=Attach%20evidence>Attach evidence</button>`;
  const waive = obligation.waivable && !["satisfied", "waived"].includes(status.status)
    ? `<button type="button" class="button button-small button-quiet waive-obligation-button" data-obligation="${esc(obligation.id)}" data-i18n=Waive>Waive</button>`
    : "";
  return `${attach}${waive}`;
}

function renderCheckResolution(item, review, manifest) {
  if (item.status === "pass" || review.status !== "open") return "";
  if (item.key === "critical_findings") {
    const findings = review.findings.filter((finding) => finding.severity === "critical" && effectiveFindingStatus(review, finding) === "open");
    if (!findings.length) return "";
    return `<ul class="check-items">${findings.map((finding) => `
      <li class="check-item"><div><strong>${esc(finding.message)}</strong><small>${finding.path ? `<code>${esc(finding.path)}${finding.line ? `:${finding.line}` : ""}</code>` : ""}</small></div><div class="check-item-actions">${finding.path ? `<button type="button" class="button button-small button-quiet" data-open-changed-file="${esc(finding.path)}" data-open-finding="${esc(finding.id)}">Show in diff</button>` : ""}<button type="button" class="button button-small waive-button" data-finding="${esc(finding.id)}">Waive</button></div></li>`).join("")}</ul>`;
  }
  if (item.key === "evidence_obligations") {
    const statuses = new Map((manifest.obligation_statuses || []).map((status) => [status.obligation_id, status]));
    const pending = (review.evidence_obligations || []).filter((obligation) => {
      const status = statuses.get(obligation.id);
      return !status || !["satisfied", "waived"].includes(status.status);
    });
    if (!pending.length) return "";
    return `<ul class="check-items">${pending.map((obligation) => {
      const status = statuses.get(obligation.id) || { status: "missing" };
      return `<li class="check-item"><div><strong>${esc(sentence(obligation.label))}</strong><small>${esc(obligation.claim_id)}</small></div><div class="check-item-actions">${obligationActions(review, manifest, obligation, status)}</div></li>`;
    }).join("")}</ul>`;
  }
  if (item.key === "tests") {
    return `<div class="check-actions"><button type="button" class="button button-small button-primary" data-configure-tests>${state.activeProject?.test_command?.length ? "Run tests" : "Configure and run tests"}</button></div>`;
  }
  if (item.key === "base_version") {
    return '<div class="check-actions"><button type="button" class="button button-small decision-button" data-action="rebase" data-i18n=Request%20an%20update>Request an update</button></div>';
  }
  if (item.key === "evidence_freshness" || item.key === "proposal_conflict") {
    return '<div class="check-actions"><button type="button" class="button button-small" data-open-review-tab="evidence">Inspect evidence</button></div>';
  }
  return "";
}

function renderAdmission(manifest) {
  const review = state.activeReview;
  const order = { block: 0, unknown: 1, pass: 2 };
  const items = [...manifest.admission_checks].sort((a, b) => (order[a.status] ?? 1) - (order[b.status] ?? 1));
  const passedItems = items.filter((item) => item.status === "pass");
  const attentionItems = items.filter((item) => item.status !== "pass" && !(item.key === "human_authority" && review?.status === "open"));
  const blocked = attentionItems.filter((item) => item.status === "block").length;
  const glyph = (status) => status === "pass" ? "✓" : status === "block" ? "!" : "·";
  const checkMeta = (item) => {
    if (item.status === "pass" || !review) return "";
    if (item.key === "base_version") return `<span class="check-meta"><span class="tag">based on v${review.base_version}</span><span class="tag" data-tone="warn">project is at v${state.activeProject?.version ?? review.current_project_version}</span></span>`;
    if (item.key === "evidence_freshness") {
      const stale = review.evidence.filter((record) => record.freshness === "stale").length;
      return `<span class="check-meta"><span class="tag" data-tone="warn">${plural(stale || 1, "stale record")}</span></span>`;
    }
    return "";
  };
  const checkRow = (item, index) => {
    const resolution = review ? renderCheckResolution(item, review, manifest) : "";
    const hasItems = resolution.includes('class="check-items"');
    const meta = hasItems ? "" : checkMeta(item);
    if (item.status !== "pass") return `<li class="check-disclosure-row" data-status="${esc(item.status)}"><details class="admission-check" data-admission-check="${esc(item.key)}"${index === 0 ? " open" : ""}>
      <summary><span class="check-state" aria-label="${item.status === "block" ? "Blocking" : "Needs attention"}">${glyph(item.status)}</span><strong>${I18n.mark(plainReviewCheckLabel(item))}</strong><span class="check-disclosure-status">${item.status === "block" ? "Blocking" : "Attention"}</span></summary>
      <div class="check-body"><div class="check-copy">${meta}${hasItems ? "" : `<small>${esc(plainReviewCheckSummary(item))}</small>`}</div>${resolution}</div>
    </details></li>`;
    return `
    <li data-status="${esc(item.status)}"><span class="check-state" aria-label="${item.status === "pass" ? "Passed" : item.status === "block" ? "Blocking" : "Required"}">${glyph(item.status)}</span><div class="check-body"><div class="check-copy"><strong>${I18n.mark(plainReviewCheckLabel(item))}</strong>${meta}${hasItems || meta ? "" : `<small>${esc(plainReviewCheckSummary(item))}</small>`}</div>${resolution}</div></li>`;
  };
  if (!attentionItems.length && !passedItems.length) return "";
  return `
    <section class="review-checks module" data-committable="${manifest.committable}" data-gate-state="${esc(manifest.gate_state)}">
      ${attentionItems.length ? `<header class="module-head"><h3>${blocked ? "What blocks approval" : "Still required"}</h3><span>${blocked ? plural(blocked, "blocked check") : plural(attentionItems.length, "item")}</span></header>
      <ul>${attentionItems.map(checkRow).join("")}</ul>` : ""}
      ${passedItems.length ? `<details class="passed-checks"${attentionItems.length ? "" : " open"}><summary>${plural(passedItems.length, "passed check")}</summary><ul>${passedItems.map(checkRow).join("")}</ul></details>` : ""}
    </section>`;
}

function renderDecisionRecords(review) {
  if (!review.decision_records?.length) {
    return "";
  }
  const actionLabels = { commit: "Approved", waive: "Waiver recorded", rebase: "Update requested", reject: "Rejected", rollback: "Rolled back" };
  return review.decision_records.map((record) => `
    <article class="decision-record" tabindex="-1">
      <header><span>${esc(actionLabels[record.action] || sentence(record.action))}</span><b>${esc(record.authority)} · ${I18n.mark(relativeTime(record.created_at))}</b></header>
      <dl>
        <div><dt>Actor</dt><dd>${esc(record.actor)}</dd></div>
        <div><dt data-i18n=Policy>Policy</dt><dd>${esc(record.policy_id)}</dd></div>
        <div><dt>Rationale</dt><dd>${esc(record.reason || "No rationale recorded")}</dd></div>
        <div><dt>Provenance</dt><dd>${esc(title(record.provenance))}</dd></div>
      </dl>
    </article>`).join("");
}

function renderClaimContext() {
  const claims = state.activeProject.claims || [];
  if (!claims.length) return "";
  return claims.map((claim) => {
    const obligations = (claim.evidence_obligations || []).map((item) =>
      typeof item === "string" ? item : item.label
    ).filter(Boolean);
    return `
    <article class="claim-context">
      <header><span>${esc(claim.id)}</span><b>${esc(title(claim.status))}</b></header>
      <h4>${esc(claim.title)}</h4>
      <p>${esc(claim.rationale || "No rationale recorded")}</p>
      <dl><div><dt>Validity</dt><dd>Version ${claim.introduced_version}${claim.superseded_version ? `–${claim.superseded_version}` : "–present"}</dd></div><div><dt data-i18n=Authority>Authority</dt><dd>${esc(claim.authority || "not assigned")}</dd></div></dl>
      <small>Evidence obligation: ${esc(obligations.join("; ") || "not recorded")}</small>
    </article>`;
  }).join("");
}

function destroyContractGraph() {
  document.querySelector(".control-grid")?.classList.remove("graph-focus");
  contractGraphResizeObserver?.disconnect();
  contractGraphResizeObserver = null;
  contractGraphInstance?.destroy();
  contractGraphInstance = null;
}

function toggleContractGraphFocus() {
  const grid = document.querySelector(".control-grid");
  const button = $("#contract-graph-expand");
  if (!grid || !button) return;
  const expanded = grid.classList.toggle("graph-focus");
  button.textContent = expanded ? "Back to review" : "Focus graph";
  button.setAttribute("aria-pressed", String(expanded));
  window.requestAnimationFrame(() => {
    contractGraphInstance?.resize();
    contractGraphInstance?.fit(contractGraphInstance.elements().not(".lens-hidden"), 58);
  });
}

function defaultContractGraphLens() {
  if (state.paperMode) return "full";
  return state.activeReview?.status === "open" ? "evidence" : "decision";
}

function contractGraphLensNodes(graph, lens) {
  if (lens === "full") return new Set(graph.nodes.map((node) => node.id));
  const types = lens === "evidence"
    ? new Set(["base_state", "proposal", "artifact", "evidence", "finding", "claim", "current_state"])
    : new Set(["base_state", "proposal", "artifact", "claim", "authority", "decision", "current_state"]);
  return new Set(graph.nodes
    .filter((node) => types.has(node.type))
    .filter((node) => lens !== "decision" || node.type !== "artifact" || node.metadata?.changed)
    .map((node) => node.id));
}

function contractGraphLensEdges(graph, visibleIds) {
  return graph.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
}

function contractGraphPositions(graph, lens = "full") {
  const laneOrders = {
    decision: [
      ["base_state", "proposal"],
      ["artifact"],
      ["claim"],
      ["authority", "decision"],
      ["current_state"],
    ],
    evidence: [
      ["base_state", "proposal"],
      ["artifact"],
      ["evidence", "finding"],
      ["claim"],
      ["current_state"],
    ],
    full: [
      ["base_state", "proposal"],
      ["artifact"],
      ["evidence", "finding"],
      ["claim"],
      ["authority", "decision"],
      ["current_state"],
    ],
  };
  const laneOrder = laneOrders[lens] || laneOrders.full;
  const positions = {};
  laneOrder.forEach((types, laneIndex) => {
    const laneNodes = graph.nodes
      .filter((node) => types.includes(node.type))
      .sort((left, right) => left.type.localeCompare(right.type) || left.id.localeCompare(right.id));
    laneNodes.forEach((node, index) => {
      positions[node.id] = {
        x: 110 + laneIndex * 184,
        y: 290 + (index - (laneNodes.length - 1) / 2) * 98,
      };
    });
  });
  return positions;
}

function themeToken(name, fallback) {
  const value = getComputedStyle(document.body).getPropertyValue(name).trim();
  return value || fallback;
}

function graphPalette() {
  const paper = state.paperMode;
  const light = paper || document.documentElement.dataset.theme === "light";
  return {
    light,
    ink: themeToken("--ink", "#17201b"),
    muted: themeToken("--muted", "#4f5b54"),
    dim: themeToken("--dim", "#5f6a64"),
    panel: themeToken("--panel", "#ffffff"),
    panelSubtle: themeToken("--panel-subtle", "#f7f8f6"),
    line: themeToken("--line-strong", "#b9c1bb"),
    accent: themeToken("--accent", "#1f6b4e"),
    accentFaint: themeToken("--accent-faint", "#eaf4ee"),
    red: themeToken("--red", "#9c3f37"),
    redBg: themeToken("--red-bg", "#faefec"),
    orange: themeToken("--orange", "#8a5b18"),
    orangeBg: themeToken("--orange-bg", "#fbf3e3"),
    cyan: themeToken("--cyan", "#3f6878"),
    cyanBg: themeToken("--cyan-bg", "#eaf2f5"),
  };
}

function contractGraphStyles() {
  const palette = graphPalette();
  const paper = state.paperMode;
  return [
    {
      selector: "node",
      style: {
        "background-color": palette.panel,
        "border-color": palette.line,
        "border-width": 1.5,
        color: palette.ink,
        label: "data(display_label)",
        "font-family": "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif",
        "font-size": 10.5,
        "font-weight": 600,
        "text-wrap": "wrap",
        "text-max-width": 132,
        "text-valign": "center",
        "text-halign": "center",
        width: 150,
        height: 58,
        shape: "round-rectangle",
        "overlay-opacity": 0,
        "transition-property": "opacity, border-width, border-color, background-color",
        "transition-duration": "180ms",
      },
    },
    { selector: 'node[type = "base_state"]', style: { "border-color": palette.line, "border-style": "dashed", width: 104, "background-color": palette.panelSubtle, color: palette.muted } },
    { selector: 'node[type = "proposal"]', style: { "border-color": palette.accent, "border-width": 2, width: 178, height: 72, "background-color": palette.accentFaint } },
    { selector: 'node[type = "current_state"]', style: { "border-color": palette.ink, "border-width": 2.5, width: 108, "background-color": palette.panelSubtle } },
    { selector: 'node[type = "claim"]', style: { "border-color": palette.cyan, "border-width": 2, width: 182, height: 72, "background-color": palette.cyanBg } },
    { selector: 'node[type = "artifact"]', style: { "border-color": palette.line, width: 166, "background-color": palette.panel, "font-family": "SFMono-Regular, SF Mono, Menlo, monospace", "font-size": 10 } },
    { selector: 'node[type = "evidence"]', style: { "border-color": palette.accent, width: 142, "background-color": palette.panel } },
    { selector: 'node[type = "finding"]', style: { "border-color": palette.red, "border-width": 2, shape: "round-hexagon", width: 142, color: palette.red, "background-color": palette.redBg } },
    { selector: 'node[type = "authority"]', style: { "border-color": palette.orange, "border-width": 2, width: 154, "background-color": palette.orangeBg } },
    { selector: 'node[type = "decision"]', style: { "border-color": palette.accent, "border-width": 2.5, shape: "round-diamond", width: 128, height: 78, "background-color": palette.accentFaint } },
    {
      selector: "edge",
      style: {
        width: 1.4,
        "line-color": palette.line,
        "target-arrow-color": palette.line,
        "target-arrow-shape": "triangle",
        "curve-style": "taxi",
        "taxi-direction": "rightward",
        "taxi-turn": 22,
        label: paper ? "data(label)" : "",
        color: palette.dim,
        "font-family": "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif",
        "font-size": 8,
        "text-background-color": palette.panel,
        "text-background-opacity": .92,
        "text-background-padding": 2,
        "text-rotation": "autorotate",
        "arrow-scale": .8,
        "overlay-opacity": 0,
        opacity: paper ? .75 : .55,
      },
    },
    { selector: 'edge[relation = "supports"]', style: { "line-color": palette.accent, "target-arrow-color": palette.accent, width: 2 } },
    { selector: 'edge[relation = "contests"]', style: { "line-color": palette.red, "target-arrow-color": palette.red, "line-style": "dashed", width: 2 } },
    { selector: 'edge[relation = "inconclusive"]', style: { "line-color": palette.orange, "target-arrow-color": palette.orange, "line-style": "dotted", width: 1.8 } },
    { selector: 'edge[relation = "authorizes"]', style: { "line-color": palette.orange, "target-arrow-color": palette.orange, width: 2 } },
    { selector: 'edge[relation = "governs"]', style: { "line-color": palette.cyan, "target-arrow-color": palette.cyan, width: 1.8 } },
    { selector: 'edge[relation = "commits"], edge[relation = "rolls_back"]', style: { "line-color": palette.ink, "target-arrow-color": palette.ink, width: 2.4 } },
    { selector: ".graph-muted", style: { opacity: .12 } },
    { selector: "edge.graph-active", style: { label: "data(label)", opacity: 1, width: 2.4, "z-index": 9 } },
    { selector: "node.graph-active", style: { opacity: 1, "border-width": 3, "z-index": 10 } },
    { selector: ".lens-hidden", style: { display: "none" } },
    { selector: ".graph-search-match", style: { "underlay-color": palette.accent, "underlay-opacity": .18, "underlay-padding": 12 } },
    { selector: ":selected", style: { "underlay-color": palette.accent, "underlay-opacity": .22, "underlay-padding": 11, "border-width": 3.5 } },
  ];
}

function graphMetadataRows(metadata = {}) {
  return Object.entries(metadata)
    .filter(([, value]) => value !== null && value !== "" && (!Array.isArray(value) || value.length))
    .map(([key, value]) => {
      const display = Array.isArray(value) ? value.join(", ") : String(value);
      return `<div><dt>${esc(title(key))}</dt><dd>${esc(display)}</dd></div>`;
    }).join("");
}

function contractGraphDisplayLabels(graph) {
  const groups = new Map();
  graph.nodes.forEach((node) => {
    const key = `${node.type}:${node.label}`;
    groups.set(key, [...(groups.get(key) || []), node]);
  });
  const labels = new Map();
  groups.forEach((nodes) => {
    nodes.sort((left, right) => left.id.localeCompare(right.id)).forEach((node, index) => {
      labels.set(node.id, nodes.length > 1 ? `${node.label} · ${index + 1}` : node.label);
    });
  });
  return labels;
}

function graphConnectionRows(nodeId) {
  const graph = state.contractGraph;
  if (!graph) return '<p class="graph-no-connections">No connected relation is recorded.</p>';
  const labels = contractGraphDisplayLabels(graph);
  const rows = graph.edges
    .filter((edge) => edge.source === nodeId || edge.target === nodeId)
    .sort((left, right) => left.relation.localeCompare(right.relation) || left.id.localeCompare(right.id))
    .map((edge) => {
      const outgoing = edge.source === nodeId;
      const otherId = outgoing ? edge.target : edge.source;
      return `<li><span class="graph-relation-direction">${outgoing ? "OUT" : "IN"}</span><span data-relation="${esc(edge.relation)}">${esc(edge.label)}</span><button type="button" data-graph-node="${esc(otherId)}">${esc(labels.get(otherId) || otherId)}</button></li>`;
    }).join("");
  return rows ? `<ul>${rows}</ul>` : '<p class="graph-no-connections">No connected relation is recorded.</p>';
}

function bindContractGraphDetailActions() {
  $("#contract-graph-selection-clear")?.addEventListener("click", clearContractGraphSelection);
  document.querySelectorAll("#contract-graph-detail [data-graph-node]").forEach((button) => {
    button.addEventListener("click", () => selectContractGraphNode(button.dataset.graphNode));
  });
}

function clearContractGraphSelection() {
  if (contractGraphInstance) {
    contractGraphInstance.elements().removeClass("graph-muted graph-active graph-search-match");
    contractGraphInstance.$(":selected").unselect();
  }
  document.querySelectorAll(".graph-node-link").forEach((button) => button.classList.remove("active"));
  const detail = $("#contract-graph-detail");
  if (!detail) return;
  detail.hidden = true;
  detail.innerHTML = `
    <div class="graph-detail-intro"><p class="eyebrow" data-i18n=Selected%20element>Selected element</p><h4 data-i18n=Explore%20the%20decision%20path>Explore the decision path</h4><span class="graph-detail-status" data-i18n=Ready>Ready</span><button type="button" class="graph-selection-clear" id="contract-graph-selection-clear" data-i18n=Show%20all>Show all</button></div>
    <div class="graph-detail-copy"><p data-i18n=Select%20an%20element%20to%20isolate%20its%20immediate%20relations%2C%20status%2C%20and%20provenance.>Select an element to isolate its immediate relations, status, and provenance.</p></div>
    <div class="graph-connection-list"><p class="eyebrow" data-i18n=Connected%20records>Connected records</p><p data-i18n=No%20element%20selected.>No element selected.</p></div>`;
  bindContractGraphDetailActions();
}

function selectContractGraphNode(nodeId) {
  const graph = state.contractGraph;
  const node = graph?.nodes.find((item) => item.id === nodeId);
  if (!node) return;
  const displayLabel = contractGraphDisplayLabels(graph).get(nodeId) || node.label;
  if (!contractGraphLensNodes(graph, contractGraphLens).has(nodeId)) setContractGraphLens("full");
  const detail = $("#contract-graph-detail");
  detail.hidden = false;
  detail.innerHTML = `
    <div class="graph-detail-intro"><p class="eyebrow">${esc(title(node.type))}</p><h4>${esc(displayLabel)}</h4><span class="graph-detail-status">${esc(title(node.status))}</span><button type="button" class="graph-selection-clear" id="contract-graph-selection-clear" data-i18n=Show%20all>Show all</button></div>
    <div class="graph-detail-copy"><p>${esc(node.summary || "No additional summary is recorded for this element.")}</p><dl>${graphMetadataRows(node.metadata)}</dl></div>
    <div class="graph-connection-list"><p class="eyebrow" data-i18n=Connected%20records>Connected records</p>${graphConnectionRows(nodeId)}</div>`;
  bindContractGraphDetailActions();
  if (contractGraphInstance) {
    contractGraphInstance.elements().removeClass("graph-muted graph-active graph-search-match");
    contractGraphInstance.elements().addClass("graph-muted");
    contractGraphInstance.$(":selected").unselect();
    const selected = contractGraphInstance.getElementById(nodeId);
    const connectedEdges = contractGraphInstance.edges().filter((edge) => edge.source().id() === nodeId || edge.target().id() === nodeId);
    const connectedNodes = connectedEdges.connectedNodes();
    selected.add(connectedEdges).add(connectedNodes).removeClass("graph-muted").addClass("graph-active");
    selected.select();
  }
  document.querySelectorAll(".graph-node-link").forEach((button) => {
    button.classList.toggle("active", button.dataset.graphNode === nodeId);
  });
}

function renderContractGraphTable(graph, lens = contractGraphLens) {
  const visibleIds = contractGraphLensNodes(graph, lens);
  const visibleEdges = contractGraphLensEdges(graph, visibleIds);
  const labels = contractGraphDisplayLabels(graph);
  const rows = visibleEdges.map((edge) => `
    <tr>
      <td><button type="button" class="graph-node-link" data-graph-node="${esc(edge.source)}">${esc(labels.get(edge.source) || edge.source)}</button></td>
      <td><span data-relation="${esc(edge.relation)}">${esc(edge.label)}</span></td>
      <td><button type="button" class="graph-node-link" data-graph-node="${esc(edge.target)}">${esc(labels.get(edge.target) || edge.target)}</button></td>
    </tr>`).join("");
  $("#contract-graph-table").innerHTML = `
    <table>
      <caption>${plural(visibleIds.size, "element")} and ${plural(visibleEdges.length, "relation")} in ${esc(title(lens))} lens</caption>
      <thead><tr><th data-i18n=Source>Source</th><th>Relation</th><th data-i18n=Target>Target</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  document.querySelectorAll(".graph-node-link").forEach((button) => {
    button.addEventListener("click", () => selectContractGraphNode(button.dataset.graphNode));
  });
}

function contractGraphStory(lens) {
  const stories = {
    decision: ["Decision trail", "Follow the proposal through changed artifacts, governed claims, authority, and the recorded disposition."],
    evidence: ["Evidence coverage", "Inspect which sources support, contest, or leave the governed claim inconclusive."],
    full: ["Full audit", "Audit every recorded element and relation without collapsing the evidence or decision path."],
  };
  return stories[lens] || stories.full;
}

function contractGraphLaneLabels(lens) {
  const labels = {
    decision: ["PROPOSAL", "ARTIFACTS", "CONTRACT", "AUTHORITY", "STATE"],
    evidence: ["PROPOSAL", "ARTIFACTS", "EVIDENCE", "CONTRACT", "STATE"],
    full: ["PROPOSAL", "ARTIFACTS", "EVIDENCE", "CONTRACT", "AUTHORITY", "STATE"],
  };
  return labels[lens] || labels.full;
}

function setContractGraphLens(lens) {
  const graph = state.contractGraph;
  if (!graph || !["decision", "evidence", "full"].includes(lens)) return;
  contractGraphLens = lens;
  const visibleIds = contractGraphLensNodes(graph, lens);
  const visibleEdges = contractGraphLensEdges(graph, visibleIds);
  document.querySelectorAll("[data-graph-lens]").forEach((button) => {
    const active = button.dataset.graphLens === lens;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const [storyLabel, storyCopy] = contractGraphStory(lens);
  $("#contract-graph-story-label").textContent = storyLabel;
  $("#contract-graph-story-copy").textContent = storyCopy;
  $("#contract-graph-metrics").innerHTML = `
    <span><strong>${visibleIds.size}</strong> elements</span>
    <span><strong>${visibleEdges.length}</strong> relations</span>
    <span data-tone="${state.manifest?.committable ? "ready" : state.activeReview?.status || "blocked"}">${esc(state.activeReview?.status === "open" ? state.manifest?.committable ? "ready" : plural(state.manifest?.blockers?.length || 0, "blocker") : title(state.activeReview?.status || "unknown"))}</span>`;
  const viewport = $(".contract-graph-viewport");
  viewport.dataset.lens = lens;
  $(".graph-lane-labels").innerHTML = contractGraphLaneLabels(lens).map((label) => `<span>${label}</span>`).join("");
  renderContractGraphTable(graph, lens);
  clearContractGraphSelection();
  if (!contractGraphInstance) return;
  const filteredGraph = { nodes: graph.nodes.filter((node) => visibleIds.has(node.id)) };
  const positions = contractGraphPositions(filteredGraph, lens);
  contractGraphInstance.batch(() => {
    contractGraphInstance.elements().addClass("lens-hidden");
    contractGraphInstance.nodes().forEach((element) => {
      if (!visibleIds.has(element.id())) return;
      element.removeClass("lens-hidden");
      element.position(positions[element.id()]);
    });
    contractGraphInstance.edges().forEach((element) => {
      if (visibleIds.has(element.source().id()) && visibleIds.has(element.target().id())) element.removeClass("lens-hidden");
    });
  });
  if (contractGraphView === "graph") {
    window.requestAnimationFrame(() => {
      contractGraphInstance.resize();
      contractGraphInstance.fit(contractGraphInstance.elements().not(".lens-hidden"), 58);
    });
  }
}

function updateContractGraphZoomLabel() {
  if (!contractGraphInstance || !$("#contract-graph-zoom-label")) return;
  $("#contract-graph-zoom-label").textContent = `${Math.round(contractGraphInstance.zoom() * 100)}%`;
}

function zoomContractGraph(delta) {
  if (!contractGraphInstance || contractGraphView !== "graph") return;
  const zoom = Math.min(2.5, Math.max(.4, contractGraphInstance.zoom() + delta));
  contractGraphInstance.animate({ zoom, center: { eles: contractGraphInstance.elements().not(".lens-hidden") } }, { duration: 180 });
}

function searchContractGraph(query) {
  const graph = state.contractGraph;
  const source = String(query || "").trim().toLowerCase();
  const status = $("#contract-graph-search-status");
  if (!graph || !source) {
    if (status) status.textContent = "Type a file, evidence source, claim, or decision";
    return;
  }
  const displayLabels = contractGraphDisplayLabels(graph);
  const match = graph.nodes.find((node) => displayLabels.get(node.id)?.toLowerCase() === source)
    || graph.nodes.find((node) => [displayLabels.get(node.id), node.label, node.id, node.type, node.status].some((value) => String(value).toLowerCase().includes(source)));
  if (!match) {
    status.textContent = `No contract element matches “${query}”`;
    return;
  }
  if (!contractGraphLensNodes(graph, contractGraphLens).has(match.id)) setContractGraphLens("full");
  setContractGraphView("graph");
  selectContractGraphNode(match.id);
  status.textContent = `${title(match.type)} · ${displayLabels.get(match.id) || match.label}`;
  if (contractGraphInstance) {
    const element = contractGraphInstance.getElementById(match.id);
    element.addClass("graph-search-match");
    contractGraphInstance.animate({ center: { eles: element }, zoom: Math.max(.9, contractGraphInstance.zoom()) }, { duration: 240 });
    window.setTimeout(() => element.removeClass("graph-search-match"), 1500);
  }
}

function setContractGraphView(view) {
  const table = view === "table";
  contractGraphView = view;
  $("#contract-graph-canvas").classList.toggle("hidden", table);
  $("#contract-graph-table").classList.toggle("hidden", !table);
  $(".contract-graph-viewport").classList.toggle("table-view", table);
  ["#contract-graph-fit", "#contract-graph-zoom-in", "#contract-graph-zoom-out"].forEach((selector) => {
    $(selector).disabled = table || !contractGraphInstance;
  });
  document.querySelectorAll(".graph-view-button").forEach((button) => {
    const active = button.dataset.graphView === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (!table && contractGraphInstance) {
    window.requestAnimationFrame(() => {
      contractGraphInstance.resize();
      contractGraphInstance.fit(contractGraphInstance.elements().not(".lens-hidden"), 58);
    });
  }
}

function renderContractGraph() {
  const graph = state.contractGraph;
  const mount = $("#contract-graph-mount");
  const template = $("#contract-graph-template");
  if (!graph || !mount || !template) return;
  destroyContractGraph();
  mount.replaceChildren(template.content.cloneNode(true));
  contractGraphLens = defaultContractGraphLens();
  contractGraphView = "graph";
  renderContractGraphTable(graph, contractGraphLens);
  const canvas = $("#contract-graph-canvas");
  canvas.setAttribute(
    "aria-label",
    `Interactive governance relation graph with ${graph.nodes.length} nodes and ${graph.edges.length} relations`,
  );
  $("#contract-graph-export").addEventListener("click", downloadContractGraphSvg);
  $("#contract-graph-expand").addEventListener("click", toggleContractGraphFocus);
  $("#contract-graph-selection-clear").addEventListener("click", clearContractGraphSelection);
  document.querySelectorAll("[data-graph-lens]").forEach((button) => {
    button.addEventListener("click", () => setContractGraphLens(button.dataset.graphLens));
  });
  document.querySelectorAll(".graph-view-button").forEach((button) => {
    button.addEventListener("click", () => setContractGraphView(button.dataset.graphView));
  });
  $("#contract-graph-search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    searchContractGraph($("#contract-graph-search").value);
  });
  $("#contract-graph-search").addEventListener("search", (event) => {
    if (!event.currentTarget.value) clearContractGraphSelection();
  });
  const displayLabels = contractGraphDisplayLabels(graph);
  $("#contract-graph-search-options").innerHTML = graph.nodes
    .slice()
    .sort((left, right) => left.type.localeCompare(right.type) || left.label.localeCompare(right.label))
    .map((node) => `<option value="${esc(displayLabels.get(node.id) || node.label)}">${esc(title(node.type))}</option>`).join("");
  if (typeof window.cytoscape !== "function") {
    canvas.innerHTML = '<div class="graph-fallback">Interactive rendering is unavailable. The complete relation table remains available.</div>';
    setContractGraphView("table");
    return;
  }
  const elements = [
    ...graph.nodes.map((node) => ({ data: { ...node, display_label: displayLabels.get(node.id) || node.label } })),
    ...graph.edges.map((edge) => ({ data: edge })),
  ];
  contractGraphInstance = cytoscape({
    container: canvas,
    elements,
    style: contractGraphStyles(),
    layout: { name: "preset", fit: false },
    minZoom: .4,
    maxZoom: 2.5,
    boxSelectionEnabled: false,
    autounselectify: false,
  });
  contractGraphInstance.on("tap", "node", (event) => {
    selectContractGraphNode(event.target.id());
  });
  contractGraphInstance.on("tap", (event) => {
    if (event.target === contractGraphInstance) clearContractGraphSelection();
  });
  contractGraphInstance.on("zoom", updateContractGraphZoomLabel);
  $("#contract-graph-zoom-in").addEventListener("click", () => zoomContractGraph(.18));
  $("#contract-graph-zoom-out").addEventListener("click", () => zoomContractGraph(-.18));
  $("#contract-graph-fit").addEventListener("click", () => {
    contractGraphInstance.fit(contractGraphInstance.elements().not(".lens-hidden"), 58);
  });
  if (window.ResizeObserver) {
    contractGraphResizeObserver = new ResizeObserver(() => contractGraphInstance?.resize());
    contractGraphResizeObserver.observe(canvas);
  }
  setContractGraphLens(contractGraphLens);
  updateContractGraphZoomLabel();
}

function xmlEsc(value = "") {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&apos;", '"': "&quot;",
  }[char]));
}

function wrapGraphLabel(value, maxLength = 22) {
  const source = String(value);
  const tokens = source.split(/\s+|(?=[./_-])/).filter(Boolean);
  const lines = [];
  let line = "";
  tokens.forEach((token) => {
    if (!line) line = token;
    else if (`${line}${token}`.length <= maxLength) line += token;
    else {
      lines.push(line);
      line = token;
    }
  });
  if (line) lines.push(line);
  return lines.slice(0, 3);
}

function buildContractGraphSvg(graph) {
  const positions = contractGraphPositions(graph);
  const displayLabels = contractGraphDisplayLabels(graph);
  const maxY = Math.max(...Object.values(positions).map((point) => point.y), 360);
  const height = Math.max(620, Math.ceil(maxY + 150));
  const edgeColor = {
    supports: "#1f6b4e",
    contests: "#9c3f37",
    inconclusive: "#8a5b18",
    authorizes: "#8a5b18",
    governs: "#3f6878",
    commits: "#17201b",
    rolls_back: "#9c3f37",
  };
  const nodeColor = {
    base_state: ["#f7f8f6", "#b9c1bb"],
    proposal: ["#eaf4ee", "#1f6b4e"],
    current_state: ["#f7f8f6", "#17201b"],
    claim: ["#eaf2f5", "#3f6878"],
    artifact: ["#ffffff", "#b9c1bb"],
    evidence: ["#ffffff", "#1f6b4e"],
    finding: ["#faefec", "#9c3f37"],
    authority: ["#fbf3e3", "#8a5b18"],
    decision: ["#eaf4ee", "#1f6b4e"],
  };
  const edges = graph.edges.map((edge) => {
    const source = positions[edge.source];
    const target = positions[edge.target];
    if (!source || !target) return "";
    const color = edgeColor[edge.relation] || "#8da1a7";
    const dash = ["contests", "inconclusive"].includes(edge.relation) ? ' stroke-dasharray="6 5"' : "";
    const middleX = (source.x + target.x) / 2;
    const middleY = (source.y + target.y) / 2 - 6;
    return `<g><line x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" stroke="${color}" stroke-width="1.5"${dash} marker-end="url(#arrow)"/><text x="${middleX}" y="${middleY}" text-anchor="middle" fill="#60777f" font-size="9">${xmlEsc(edge.label)}</text></g>`;
  }).join("");
  const nodes = graph.nodes.map((node) => {
    const point = positions[node.id];
    if (!point) return "";
    const [fill, stroke] = nodeColor[node.type] || ["#ffffff", "#8da1a7"];
    const width = ["claim", "artifact"].includes(node.type) ? 174 : 146;
    const lines = wrapGraphLabel(displayLabels.get(node.id) || node.label);
    const textY = point.y - ((lines.length - 1) * 7);
    const tspans = lines.map((line, index) => `<tspan x="${point.x}" y="${textY + index * 14}">${xmlEsc(line)}</tspan>`).join("");
    return `<g><rect x="${point.x - width / 2}" y="${point.y - 35}" width="${width}" height="70" rx="8" fill="${fill}" stroke="${stroke}" stroke-width="2"/><text x="${point.x}" y="${textY}" text-anchor="middle" fill="#20323a" font-size="10" font-weight="600">${tspans}</text><text x="${point.x}" y="${point.y + 27}" text-anchor="middle" fill="#71858b" font-size="7" letter-spacing=".7">${xmlEsc(node.type.toUpperCase())} · ${xmlEsc(node.status.toUpperCase())}</text></g>`;
  }).join("");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="${height}" viewBox="0 0 1600 ${height}" role="img" aria-labelledby="title desc"><title id="title">AgenticConsensus audit graph</title><desc id="desc">${xmlEsc(graph.review_id)} at project version ${graph.project_version}, status ${xmlEsc(graph.review_status)}</desc><rect width="1600" height="${height}" fill="#ffffff"/><text x="34" y="38" fill="#20323a" font-family="Georgia, serif" font-size="22" data-i18n=Audit%20graph>Audit graph</text><text x="34" y="58" fill="#71858b" font-family="monospace" font-size="9">${xmlEsc(graph.review_id)} · version ${graph.project_version} · ${xmlEsc(graph.review_status)}</text><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#71858b"/></marker></defs>${edges}${nodes}</svg>`;
}

function downloadContractGraphSvg() {
  if (!state.contractGraph) return;
  const svg = buildContractGraphSvg(state.contractGraph);
  const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${state.contractGraph.review_id.replace(/[^a-zA-Z0-9_-]/g, "-")}-contract-graph.svg`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  toast("Audit graph exported");
}

function renderReviewCopilot() {
  const template = $("#review-copilot-template");
  return template ? template.innerHTML : "";
}

function upsertAIRun(run, { select = true } = {}) {
  const index = state.aiRuns.findIndex((item) => item.id === run.id);
  if (index >= 0) state.aiRuns[index] = run;
  else state.aiRuns.unshift(run);
  if (select) state.activeCopilotRun = run;
}

function currentCopilotDraft() {
  return copilotSession.get(state.activeReview, state.activeProject);
}

function copilotDraftVisible(draft) {
  return copilotSession.owns(draft) && currentCopilotDraft() === draft
    && !document.body.classList.contains("auth-locked")
    && state.viewMode === "review"
    && $("#review-canvas")?.getAttribute("aria-busy") !== "true";
}

function renderCopilotControls() {
  const draft = currentCopilotDraft();
  const form = $("#review-copilot-form");
  if (!draft || !form) return;
  const readonly = document.body.classList.contains("viewer-mode");
  const pending = draft.pending;
  const submit = form.querySelector('[type="submit"]');
  submit.disabled = readonly || Boolean(pending);
  submit.textContent = pending?.kind === "ask" ? "Reviewing…" : state.runtime?.configured ? "Ask assistant" : "Explain from records";
  if (pending?.kind === "ask") submit.setAttribute("aria-busy", "true");
  else submit.removeAttribute("aria-busy");
  const plan = $("#evidence-gaps-button");
  plan.disabled = readonly || Boolean(pending);
  plan.textContent = pending?.kind === "plan" ? "Finding gaps…" : "Find recorded gaps";
  if (pending?.kind === "plan") plan.setAttribute("aria-busy", "true");
  else plan.removeAttribute("aria-busy");
  form.elements.deliberate.disabled = readonly || Boolean(pending) || !state.runtime?.configured;
  document.querySelectorAll("[data-copilot-prompt], [data-ai-feedback]").forEach(button => {
    button.disabled = readonly || Boolean(pending);
  });
  document.querySelectorAll("[data-ai-feedback-editor] button").forEach(button => { button.disabled = readonly || Boolean(pending); });
  const feedbackInput = $("#copilot-feedback-note");
  if (feedbackInput) feedbackInput.readOnly = readonly || Boolean(pending);
  $("#copilot-answer-history")?.toggleAttribute("disabled", Boolean(pending));
  let message = draft.message, status = draft.state;
  if (pending && !AssistantModel.contextMatches(pending, state.activeReview, state.activeProject)) {
    message = "An earlier version’s request is still running. Its answer will be checked against the current review context.";
  } else if (!pending && state.activeCopilotRun && !AssistantModel.isCurrent(state.activeCopilotRun, state.activeReview, state.activeProject)) {
    message = "This saved answer uses an earlier review or project version. Ask again for the current context; your question is kept.";
    status = "warning";
  }
  setReviewCopilotStatus(readonly ? "Read-only view. You can inspect saved answers and sources; ask an operator to generate new advice." : message, readonly ? "idle" : status);
}

function renderCopilotHistory() {
  const root = $("#copilot-history");
  if (!root) return;
  const runs = state.aiRuns.filter(item => item.project_id === state.activeProject?.id && item.review_id === state.activeReview?.id
    && ["review_copilot", "evidence_gap_planner"].includes(item.feature));
  root.hidden = runs.length === 0 || (runs.length === 1 && AssistantModel.isCurrent(runs[0], state.activeReview, state.activeProject));
  if (root.hidden) { root.replaceChildren(); return; }
  const selected = state.activeCopilotRun?.id;
  root.innerHTML = `<label for="copilot-answer-history">Saved answers (${runs.length})</label><select id="copilot-answer-history">${selected ? "" : '<option value="">Choose a saved answer</option>'}${runs.map(run => `<option value="${esc(run.id)}" title="${esc(run.request)}"${run.id === selected ? " selected" : ""}>${AssistantModel.isCurrent(run, state.activeReview, state.activeProject) ? "" : "Earlier version: "}${esc(run.feature === "evidence_gap_planner" ? "Local gap plan" : run.request)}</option>`).join("")}</select>`;
  root.querySelector("select").addEventListener("change", event => {
    const draft = currentCopilotDraft();
    if (!draft || draft.pending) return;
    const run = runs.find(item => item.id === event.currentTarget.value);
    if (!run) return;
    draft.runId = run.id;
    state.activeCopilotRun = run;
    renderReviewCopilotOutput(run);
    renderCopilotControls();
  });
}

function restoreCopilotDraft() {
  const draft = currentCopilotDraft();
  const form = $("#review-copilot-form");
  if (!draft || !form) return;
  form.elements.question.value = draft.question;
  form.elements.deliberate.checked = draft.deliberate;
  form.querySelector(".copilot-settings").open = draft.optionsOpen;
  form.elements.question.addEventListener("input", () => { if (copilotSession.owns(draft)) draft.question = form.elements.question.value; });
  form.elements.deliberate.addEventListener("change", () => { if (copilotSession.owns(draft)) draft.deliberate = form.elements.deliberate.checked; });
  form.querySelector(".copilot-settings").addEventListener("toggle", event => { if (copilotSession.owns(draft)) draft.optionsOpen = event.currentTarget.open; });
  $("#copilot-review-context").textContent = state.activeReview.intent_summary || "Selected review";
  $("#copilot-review-version").textContent = `${reviewRef(state.activeReview)} · revision ${state.activeReview.revision} · project v${state.activeProject.version} · target ${short(state.activeReview.target_ref)}`;
  $("#copilot-provider-state").textContent = state.runtime?.configured ? `Configured model: ${state.runtime.model || state.runtime.provider || "Connected"}` : "No model configured. Explanations use local recorded rules.";
  $("#copilot-data-note").textContent = state.runtime?.configured
    ? "Your question and this review’s records, including a bounded diff, go to the configured model provider."
    : "Uses local review records only. No question or code is sent to a model provider.";
  renderCopilotControls();
}

function formatAIPercent(value) {
  return Number.isFinite(Number(value)) ? `${Math.round(Number(value) * 100)}%` : "—";
}

function setReviewCopilotStatus(message = "", stateName = "idle") {
  const status = $("#review-copilot-status");
  const output = $("#review-copilot-output");
  if (!status) return;
  status.textContent = message;
  status.dataset.state = stateName;
  status.setAttribute("role", stateName === "error" ? "alert" : "status");
  if (output) {
    if (stateName === "pending") output.setAttribute("aria-busy", "true");
    else output.removeAttribute("aria-busy");
  }
}

function renderAIEvalStrip() {
  const metrics = state.aiEvals;
  if (!metrics) return;
  $("#ai-eval-runs").textContent = String(metrics.runs || 0);
  $("#ai-grounded-rate").textContent = formatAIPercent(metrics.grounded_rate);
  $("#ai-citation-precision").textContent = formatAIPercent(metrics.mean_citation_precision);
  $("#ai-latency").textContent = `${Math.round(metrics.average_latency_ms || 0)} ms`;
  const feedback = metrics.feedback || {};
  $("#ai-feedback-count").textContent = String((feedback.accepted || 0) + (feedback.edited || 0) + (feedback.rejected || 0));
}

function renderReviewCopilotOutput(run = state.activeCopilotRun) {
  renderCopilotHistory();
  const output = $("#review-copilot-output");
  if (!output) return;
  if (!run || run.review_id !== state.activeReview?.id) {
    output.innerHTML = '<p class="copilot-empty">Understand the blockers, compare the risks, or inspect missing records.</p>';
    return;
  }
  if (!AssistantModel.isCurrent(run, state.activeReview, state.activeProject)) {
    output.innerHTML = '<p class="copilot-empty">This advisory answer belongs to an earlier review or project version. Ask again to use the current evidence.</p>';
    return;
  }
  const citations = (run.citations || []).map((citation) => {
    const target = AssistantModel.sourceTarget(citation, state.activeReview, state.activeProject, state.manifest);
    return `<li><strong>${esc(sentence(citation.label))}</strong><small>${esc(sentence(citation.kind || citation.id.split(":")[0]))}</small><p>${esc(citation.excerpt)}</p>${target ? `<button type="button" class="button button-quiet" data-copilot-source="${esc(citation.id)}">${target.kind === "obligation" ? "Open requirements" : target.kind === "admission" || target.kind === "review" || target.kind === "decision" ? "Open decision" : target.kind === "claim" ? "Open claim context" : "Inspect source"}</button>` : ""}</li>`;
  }).join("");
  const disagreements = (run.result.disagreements || []).map((item) => `<li>${esc(item)}</li>`).join("");
  const uncertainties = (run.uncertainties || []).map((item) => `<li>${esc(item)}</li>`).join("");
  const checks = (run.suggested_checks || []).map((item) => `<li>${esc(item)}</li>`).join("");
  const gaps = (run.result.gaps || []).map((gap) => `
    <article class="copilot-gap"><span>${esc(title(gap.kind))}</span><strong>${esc(gap.suggested_check)}</strong><p>${esc(gap.reason)}</p></article>`).join("");
  const feedback = run.feedback;
  const localPlan = run.feature === "evidence_gap_planner";
  const originalAnswer = run.feature === "evidence_gap_planner" ? run.result.summary : run.result.answer;
  const editedAnswer = feedback?.verdict === "edited" ? feedback.edited_response?.trim() : "";
  const answer = editedAnswer || originalAnswer;
  const semanticSupportNote = (run.quality_flags || []).includes("semantic_support_unverified")
    ? '<p class="copilot-authority-boundary">The source records exist. Check whether they actually support this answer; this has not been independently verified.</p>'
    : "";
  output.innerHTML = `
    <article class="copilot-answer" data-source="${esc(run.source)}">
      <header><h4>${esc(localPlan ? "Local gap plan" : run.request)}</h4><small>${esc(localPlan ? "Local records · no model call" : run.source === "model" ? `${run.model || run.provider}` : run.source === "hybrid" ? `${run.model || run.provider} + local checks` : "Local record explanation")} · ${(run.latency_ms / 1000).toFixed(1)} s</small></header>
      ${editedAnswer ? '<p class="copilot-authority-boundary"><strong>Human-edited advice.</strong> Sources belong to the original answer; edits are not independently verified.</p>' : ""}
      ${!localPlan && run.source === "deterministic" && state.runtime?.configured ? `<p class="copilot-authority-boundary copilot-fallback-note">The configured model did not return a usable answer${(run.quality_flags || []).length ? ` (${esc((run.quality_flags || []).map((flag) => title(flag)).join(", "))})` : ""}. This explanation uses local recorded rules, not model reasoning.</p>` : ""}
      <div class="copilot-answer-copy">${plainVersion(answer || "No advisory answer was produced.").split(/\n{2,}|\n(?=\s*(?:\(\d+\)|\d+[.)]|[-•]) )/).map((part) => part.trim()).filter(Boolean).map((part) => `<p>${esc(part)}</p>`).join("")}</div>
      ${editedAnswer ? `<details class="copilot-original"><summary>Original ${run.source === "model" ? "model" : "advisory"} answer</summary><p class="copilot-answer-copy">${esc(plainVersion(originalAnswer || "No original answer recorded."))}</p></details>` : ""}
      ${gaps ? `<div class="copilot-gap-list">${gaps}</div>` : ""}
      ${disagreements ? `<details open><summary>Disagreement</summary><ul>${disagreements}</ul></details>` : ""}
      ${uncertainties && run.uncertainties.length ? `<details><summary>${plural(run.uncertainties.length, "uncertainty", "uncertainties")}</summary><ul>${uncertainties}</ul></details>` : ""}
      ${checks && run.suggested_checks.length ? `<details><summary>${plural(run.suggested_checks.length, "suggested check")}</summary><ul>${checks}</ul></details>` : ""}
      <details class="copilot-sources"><summary>${plural(run.citations?.length || 0, "source")} · inspect records</summary><ol class="copilot-citations">${citations || "<li>No source resolved.</li>"}</ol></details>
      ${semanticSupportNote}

      <footer class="copilot-feedback">
        <button type="button" class="copilot-copy-answer" data-copy-answer aria-label="Copy this answer">${uiIcon("file-text")}<span data-i18n=Copy>Copy</span></button>
        ${feedback
          ? `<span>${esc(feedback.verdict === "edited" ? "Edited advice kept" : feedback.verdict === "accepted" ? "Marked helpful" : "Marked unhelpful")} by ${esc(feedback.actor)}</span>`
          : `<span>Was AI advice useful?</span><button type="button" class="icon-feedback-button" aria-label="Mark AI answer helpful" data-tooltip="Helpful" data-ai-feedback="accepted">${uiIcon("thumbs-up")}${controlTooltip("Helpful")}</button><button type="button" data-ai-feedback="edited">Edit & keep</button><button type="button" class="icon-feedback-button" aria-label="Mark AI answer unhelpful" data-tooltip="Not helpful" data-ai-feedback="rejected">${uiIcon("thumbs-down")}${controlTooltip("Not helpful")}</button>`}
      </footer>
    </article>`;
  document.querySelectorAll("[data-ai-feedback]").forEach((button) => {
    button.addEventListener("click", recordAIFeedback);
  });
  document.querySelectorAll("[data-copilot-source]").forEach(button => button.addEventListener("click", () => openCopilotSource(button.dataset.copilotSource, run)));
  $("[data-copy-answer]")?.addEventListener("click", async () => {
    try {
      await copyText(plainVersion(answer || ""));
      toast("Answer copied", "success");
    } catch {
      toast("Copy failed", "error");
    }
  });
  if (!run.feedback && currentCopilotDraft()?.feedbackDrafts?.has(run.id)) showAIFeedbackEditor(currentCopilotDraft().feedbackDrafts.get(run.id).verdict);
}

function openCopilotSource(id, run) {
  if (!AssistantModel.isCurrent(run, state.activeReview, state.activeProject)) return;
  const citation = run.citations.find(item => item.id === id);
  const target = AssistantModel.sourceTarget(citation, state.activeReview, state.activeProject, state.manifest);
  if (!target) return;
  if (target.kind === "finding") return openChangedFile(target.path, target.id);
  if (window.innerWidth <= 960) setFilePanelOpen(false);
  if (target.kind === "evidence") {
    setReviewWorkspaceTab("evidence", {focus:true});
    state.evidenceQuery = target.id;
    state.evidenceFilter = "all";
    state.evidenceObligation = "";
    $("#evidence-record-search").value = target.id;
    $("#evidence-record-filter").value = "all";
    refreshEvidenceRecords();
    setEvidenceTab("records", {focus:true});
  } else if (target.kind === "obligation") {
    setReviewWorkspaceTab("evidence", {focus:true});
    setEvidenceTab("requirements", {focus:true});
  } else if (target.kind === "claim") {
    setReviewWorkspaceTab("changes", {focus:true});
    const claims = $(".diff-claims");
    if (claims) {
      claims.open = true;
      claims.querySelector("summary").focus({preventScroll:true});
      claims.scrollIntoView({behavior:"instant",block:"nearest"});
    }
  } else setReviewWorkspaceTab(target.kind === "diff" ? "changes" : "overview", {focus:true});
}

async function refreshAIEvals(projectId = state.activeProject?.id) {
  if (!projectId) return;
  const userId = state.auth?.user?.id, csrf = state.csrfToken;
  const metrics = await api(`/api/projects/${projectId}/ai/evals`);
  if (state.activeProject?.id !== projectId || state.auth?.user?.id !== userId || state.csrfToken !== csrf) return;
  state.aiEvals = metrics;
  if ($("#ai-eval-runs")) renderAIEvalStrip();
}

async function askReviewCopilot(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const draft = currentCopilotDraft();
  if (!draft || draft.pending) return;
  draft.question = form.elements.question.value;
  draft.deliberate = form.elements.deliberate.checked;
  if (!draft.question.trim()) {
    draft.message = "Write a question, or choose a suggested question above.";
    draft.state = "error";
    renderCopilotControls();
    form.elements.question.focus();
    return;
  }
  await runReviewAssistant("ask");
}

async function planEvidenceGaps() {
  await runReviewAssistant("plan");
}

async function runReviewAssistant(kind) {
  const draft = currentCopilotDraft();
  if (!draft || document.body.classList.contains("viewer-mode") || document.body.classList.contains("auth-locked")) return;
  const operation = copilotSession.begin(draft, state.activeReview, state.activeProject, kind);
  if (!operation) return;
  draft.message = kind === "plan" ? "Inspecting recorded gaps locally. No checks are being run."
    : !state.runtime?.configured ? "Reading local review records…"
      : draft.deliberate ? "Asking the model, then challenging and synthesizing its answer. You can keep reviewing; the answer stays with this review."
        : "Asking the model with this review’s records. You can keep reviewing; the answer stays with this review.";
  draft.state = "pending";
  renderCopilotControls();
  try {
    const run = await api(`/api/reviews/${operation.reviewId}/ai/${kind === "plan" ? "evidence-gaps" : "copilot"}`, {
      method:"POST",
      ...(kind === "ask" ? {body:JSON.stringify({question:draft.question.trim(), deliberate:draft.deliberate})} : {}),
    });
    if (!copilotSession.owns(draft)) return;
    if (!AssistantModel.isCurrent(run, {id:operation.reviewId,revision:operation.reviewRevision}, {id:operation.projectId,version:operation.projectVersion})) {
      const error = new Error("The answer does not match the submitted review context.");
      error.status = 409;
      throw error;
    }
    draft.runId = run.id;
    const visible = copilotDraftVisible(draft);
    if (state.activeProject?.id === operation.projectId) upsertAIRun(run, {select:visible});
    const modelAnswer = run.source === "model" || run.source === "hybrid";
    const message = kind === "plan" ? `${plural(run.result.gaps?.length || 0, "recorded gap")} found. Suggested checks have not been run.`
      : modelAnswer ? `Answer ready. ${plural(run.citations.length, "source")} linked; inspect them before deciding.`
        : "Local record explanation ready. This is not a model answer.";
    copilotSession.finish(operation, message, !modelAnswer && kind === "ask" && state.runtime?.configured ? "warning" : "success");
    if (visible) {
      renderReviewCopilotOutput(run);
      renderCopilotControls();
    }
    // The answer is already available. Statistics failure must not misreport it
    // as a failed question or turn a late result into another project's state.
    try { await refreshAIEvals(operation.projectId); } catch { /* Optional metrics remain at their last successful snapshot. */ }
  } catch (error) {
    const visible = copilotDraftVisible(draft);
    if (copilotSession.finish(operation, AssistantModel.errorMessage(error), "error") && visible) renderCopilotControls();
  } finally {
    if (copilotSession.owns(draft) && draft.pending === operation) copilotSession.finish(operation, draft.message, draft.state);
    if (copilotDraftVisible(draft)) renderCopilotControls();
  }
}

function showAIFeedbackEditor(verdict, {focus = false} = {}) {
  const run = state.activeCopilotRun;
  const draft = currentCopilotDraft();
  if (!run || !draft || document.body.classList.contains("viewer-mode")) return;
  const footer = document.querySelector(".copilot-feedback");
  if (!footer) return;
  const editing = verdict === "edited";
  draft.feedbackDrafts ||= new Map();
  let editor = draft.feedbackDrafts.get(run.id);
  if (!editor || editor.verdict !== verdict) {
    editor = {verdict, text:editing ? (run.result.answer || run.result.summary || "") : ""};
    draft.feedbackDrafts.set(run.id, editor);
  }
  footer.innerHTML = `
    <form class="copilot-feedback-editor" data-ai-feedback-editor="${esc(verdict)}" data-ai-run="${esc(run.id)}">
      <label for="copilot-feedback-note">${editing ? "Edit the advisory answer" : "Why was this advice unhelpful?"}</label>
      <textarea class="copilot-feedback-note" id="copilot-feedback-note" name="feedback_note" rows="4" ${editing ? "required" : ""}>${esc(editor.text)}</textarea>
      <div class="copilot-feedback-actions"><button type="submit">${editing ? "Keep edited answer" : "Record feedback"}</button><button type="button" data-ai-feedback-cancel data-i18n=Cancel>Cancel</button></div>
    </form>`;
  const form = footer.querySelector("[data-ai-feedback-editor]");
  form.addEventListener("submit", submitAIFeedback);
  form.elements.feedback_note.addEventListener("input", () => { if (copilotSession.owns(draft)) editor.text = form.elements.feedback_note.value; });
  form.querySelector("[data-ai-feedback-cancel]").addEventListener("click", () => {
    if (draft.pending) return;
    draft.feedbackDrafts.delete(run.id);
    renderReviewCopilotOutput(run);
    document.querySelector(`[data-ai-feedback="${CSS.escape(verdict)}"]`)?.focus();
  });
  renderCopilotControls();
  if (focus) {
    form.elements.feedback_note.focus();
    if (editing) form.elements.feedback_note.select();
  }
}

async function submitAIFeedback(event) {
  event.preventDefault();
  const run = state.activeCopilotRun;
  if (!run) return;
  const form = event.currentTarget;
  if (form.dataset.aiRun !== run.id || currentCopilotDraft()?.pending) return;
  const verdict = form.dataset.aiFeedbackEditor;
  const value = form.elements.feedback_note.value.trim();
  const button = event.submitter || form.querySelector('[type="submit"]');
  setBusy(button, true, "Recording…");
  await persistAIFeedback(run, verdict, verdict === "rejected" ? value : "", verdict === "edited" ? value : null, button);
}

async function persistAIFeedback(run, verdict, note = "", editedResponse = null, button = null) {
  const draft = currentCopilotDraft();
  if (!draft || !AssistantModel.isCurrent(run, state.activeReview, state.activeProject)
    || document.body.classList.contains("viewer-mode")) { setBusy(button, false); return; }
  const operation = copilotSession.begin(draft, state.activeReview, state.activeProject, "feedback");
  if (!operation) { setBusy(button, false); return; }
  draft.message = "Recording feedback about this answer. No review decision is being changed.";
  draft.state = "pending";
  renderCopilotControls();
  try {
    const updated = await api(`/api/ai/runs/${run.id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ verdict, note, edited_response: editedResponse }),
    });
    if (!copilotSession.owns(draft)) return;
    if (updated.id !== run.id || updated.review_id !== operation.reviewId || updated.project_id !== operation.projectId) {
      const error = new Error("The feedback response did not match this answer."); error.status = 409; throw error;
    }
    const visible = copilotDraftVisible(draft);
    draft.feedbackDrafts?.delete(run.id);
    if (state.activeProject?.id === operation.projectId) upsertAIRun(updated, {select:visible});
    copilotSession.finish(operation, `Feedback recorded as ${verdict}. No review decision was changed.`, "success");
    if (visible) { renderReviewCopilotOutput(updated); renderCopilotControls(); }
    try { await refreshAIEvals(operation.projectId); } catch { /* Feedback has already been recorded. */ }
  } catch (error) {
    const visible = copilotDraftVisible(draft);
    if (copilotSession.finish(operation, `${AssistantModel.errorMessage(error)} Feedback was not recorded.`, "error") && visible) renderCopilotControls();
  } finally {
    setBusy(button, false);
    if (copilotDraftVisible(draft)) renderCopilotControls();
  }
}

async function recordAIFeedback(event) {
  const run = state.activeCopilotRun;
  if (!run || currentCopilotDraft()?.pending) return;
  const verdict = event.currentTarget.dataset.aiFeedback;
  if (verdict === "edited" || verdict === "rejected") {
    showAIFeedbackEditor(verdict, {focus:true});
    return;
  }
  setBusy(event.currentTarget, true, "Recording…");
  await persistAIFeedback(run, verdict, "", null, event.currentTarget);
}

function reviewDecisionBoundary(review, manifest) {
  if (review.status !== "open") return review.status === "committed" ? I18n.mark("Rolling back restores the previous project state.") : "";
  if (document.body.classList.contains("viewer-mode")) return I18n.mark("Read-only view. Share findings with an operator to record the decision.");
  const blocker = manifest.admission_checks.find((item) => item.status === "block");
  if (blocker) return I18n.mark("Approval requires all blocking checks to pass.");
  const authorities = (manifest.required_authorities || []).join(" or ");
  return authorities
    ? I18n.mark("Recorded as {authorities} under {policy}.", {authorities, policy:manifest.governing_policy})
    : I18n.mark("Recorded under {policy}.", {policy:manifest.governing_policy});
}

function renderReviewTrace(review, manifest) {
  const trace = DecisionModel.reviewTrace(review, manifest);
  return `<section class="review-trace" aria-labelledby="review-trace-title">
    <header><h3 id="review-trace-title" data-i18n=Review%20trace>Review trace</h3><span data-i18n=Links%20recorded%20in%20this%20review>Links recorded in this review</span></header>
    <ol>${trace.stages.map((stage, index) => `<li data-tone="${esc(stage.tone)}"><button type="button" ${stage.tab ? `data-open-review-tab="${esc(stage.tab)}"` : `data-open-project-view="${esc(stage.view)}"`}${stage.id === 'evidence' ? ' data-open-evidence-records' : ''} aria-label="${esc(`${stage.label}: ${stage.value}. ${stage.detail}. Inspect ${stage.label.toLowerCase()}.`)}"><span class="trace-label"><span class="trace-marker" aria-hidden="true">${index + 1}</span>${I18n.mark(stage.label)}</span><strong>${I18n.mark(stage.value)}</strong><small>${I18n.mark(stage.detail)}</small></button></li>`).join("")}</ol>
  </section>`;
}

function renderReviewChangeMap(review, manifest) {
  const map = DecisionModel.changeMap(review, changedFileStats(review));
  const groups = state.changeMapDirectory ? map.groups.filter(group => group.directory === state.changeMapDirectory) : map.groups;
  const colors = new Map(map.groups.map((group,index) => [group.directory,index % 3]));
  const boxes = DecisionModel.partitionMap(groups, {x:0,y:0,width:1000,height:440});
  const records = review.evidence || [];
  const results = records.filter(record => ["pass","fail"].includes(record.status)).length;
  const labels = {git:"Git revisions",static_analysis:"Python analysis",tests:"Tests",policy:"Policy",attestation:"Attestation"};
  const assessed = records.map(record => {
    const assessment = EvidenceModel.assessRecord(record, review.target_ref, manifest.invalidated_evidence_ids);
    const unscoped = record.kind === "static_analysis" && !record.claim_ids?.length && !review.claim_deltas?.length;
    return {record, label:record.status === "not_run" ? "Not run" : unscoped && record.status === "pass" ? "Run only" : assessment.label,
      tone:unscoped && record.status === "pass" ? "neutral" : assessment.attention ? "attention" : "ok"};
  });
  const trace = DecisionModel.reviewTrace(review, manifest);
  const claims = trace.stages.find(stage => stage.id === "claims");
  return `<section class="review-change-map module" aria-labelledby="change-map-title">
    <header class="change-map-head"><div><h3 id="change-map-title">Change map</h3><p>${plural(review.changed_paths.length, "file")}${map.totalLines !== null ? ` · ${map.totalLines.toLocaleString("en-US")} changed lines` : ""}</p></div><div><label class="sr-only" for="change-map-directory">Directory shown in change map</label><select id="change-map-directory"><option value="">All directories</option>${map.groups.map(group => `<option value="${esc(group.directory)}"${state.changeMapDirectory === group.directory ? " selected" : ""}>${esc(group.directory)}</option>`).join("")}</select><button type="button" class="button button-quiet button-with-icon" data-open-review-tab="audit">${uiIcon("network")}<span data-i18n=Relations>Relations</span></button></div></header>
    <div class="change-map-body"><div class="change-map-main"><div class="change-map-canvas" role="group" aria-label="Changed files, grouped by directory and sized by ${map.scale === "lines" ? "recorded changed lines" : "file count"}">
    ${boxes.length ? boxes.map(box => {
      const tiles = DecisionModel.partitionMap(box.files,{x:0,y:0,width:box.width,height:Math.max(1,box.height-34)});
      return `<section class="map-directory" data-map-directory="${esc(box.directory)}" data-map-color="${colors.get(box.directory)}" style="left:${box.x / 10}%;top:${box.y / 4.4}%;width:${box.width / 10}%;height:${box.height / 4.4}%;" aria-label="${esc(box.directory)}"><header><span>${esc(box.directory)}</span><small>${box.files.length}</small></header><div class="map-directory-tiles">${tiles.map(tile => `<button type="button" class="map-file-tile" data-open-changed-file="${esc(tile.path)}" data-map-lines="${tile.lines === null ? 'unknown' : tile.lines}" data-map-dense="${tile.width < 100 || tile.height < 70}" data-map-major="${tile.width * tile.height > 45000}" data-selected="${state.diffPath === tile.path}" style="left:${tile.x / box.width * 100}%;top:${tile.y / Math.max(1,box.height-34) * 100}%;width:calc(${tile.width / box.width * 100}% - 4px);height:calc(${tile.height / Math.max(1,box.height-34) * 100}% - 4px);" title="${esc(tile.path)}${tile.lines !== null ? ` · ${plural(tile.lines,'changed line')}` : ' · Size unavailable'}" aria-label="${esc(`Open diff for ${tile.path}${tile.lines !== null ? `, ${plural(tile.lines,'changed line')}` : ', size unavailable'}`)}"><span class="map-file-name">${esc(tile.filename)}</span><small>${tile.lines !== null ? tile.lines.toLocaleString("en-US") : "—"}</small>${uiIcon("arrow-right")}</button>`).join("")}</div></section>`;
    }).join("") : '<div class="change-map-empty">No changed files recorded.</div>'}</div>
    <footer class="change-map-legend"><div>${map.groups.map(group => `<span data-map-color="${colors.get(group.directory)}"><i aria-hidden="true"></i>${esc(group.directory)}</span>`).join("")}</div><span>${map.scale === "lines" ? `Area = changed lines${map.groups.some(group=>group.files.some(file=>file.lines===0)) ? '; path-only files use a minimum tile.' : ''}` : "Equal file sizing · line counts unavailable or incomplete."}</span><button type="button" class="text-button" data-open-review-tab="changes">${I18n.mark("All files")} ${uiIcon("arrow-right")}</button></footer></div>
    <aside class="change-map-evidence" aria-label="Evidence and missing links"><h4 data-i18n=Evidence>Evidence</h4><div class="map-evidence-glance"><svg class="map-evidence-ring" viewBox="0 0 100 100" role="img" aria-label="${results} of ${records.length} records have a pass or fail result"><circle class="ring-track" cx="50" cy="50" r="38" pathLength="100"></circle>${assessed.map((item,index) => `<circle data-tone="${item.tone}" cx="50" cy="50" r="38" pathLength="100" stroke-dasharray="${Math.max(0,100 / records.length - 2)} ${100 - Math.max(0,100 / records.length - 2)}" stroke-dashoffset="${-index * 100 / records.length}" transform="rotate(-90 50 50)"></circle>`).join("")}</svg><div><strong>${results}<span> / ${records.length}</span></strong><small>with results</small></div></div>
      <div class="map-evidence-sources">${assessed.map(item => `<button type="button" data-map-evidence="${esc(item.record.id)}" data-tone="${item.tone}" title="${esc(item.record.summary)}"><span class="map-record-icon">${uiIcon(item.tone === "ok" ? "check-circle" : item.tone === "attention" ? "minus" : "code")}</span><span>${esc(labels[item.record.kind] || sentence(item.record.kind))}</span><small>${esc(item.label)}</small></button>`).join("") || '<p>No source records.</p>'}</div>
      <div class="map-missing-links"><h4>Recorded links</h4><button type="button" data-open-project-view="intents">${uiIcon("file-text")}<span>Intent map</span><small>${review.intent_id ? "Linked" : "Unlinked"}</small></button><button type="button" data-open-project-view="governance">${uiIcon("shield-check")}<span data-i18n=Claims>Claims</span><small>${claims.value} linked</small></button></div>
    </aside></div>
  </section>`;
}

function bindReviewChangeMap() {
  $("#change-map-directory")?.addEventListener("change", event => {
    const before=ReviewMotion.capture($(".change-map-canvas"));
    state.changeMapDirectory = event.target.value;
    $(".review-change-map").outerHTML = renderReviewChangeMap(state.activeReview,state.manifest);
    bindReviewChangeMap();
    ReviewMotion.reflow($(".change-map-canvas"),before);
    $("#change-map-directory")?.focus({preventScroll:true});
  });
  document.querySelectorAll(".review-change-map [data-open-changed-file]").forEach(node => node.addEventListener("click",()=>openChangedFile(node.dataset.openChangedFile)));
  document.querySelectorAll(".review-change-map [data-open-review-tab]").forEach(node => node.addEventListener("click",()=>setReviewWorkspaceTab(node.dataset.openReviewTab,{focus:true})));
  document.querySelectorAll(".review-change-map [data-open-project-view]").forEach(node => node.addEventListener("click",()=>setProjectView(node.dataset.openProjectView)));
  document.querySelectorAll("[data-map-evidence]").forEach(node => node.addEventListener("click",()=> {
    state.evidenceQuery = node.dataset.mapEvidence;
    state.evidenceFilter = "all"; state.evidenceObligation = "";
    $("#evidence-record-search").value = state.evidenceQuery;
    $("#evidence-record-filter").value = "all";
    refreshEvidenceRecords(); setEvidenceTab("records"); setReviewWorkspaceTab("evidence",{focus:true});
  }));
}

function renderRevisionContext(review) {
  const children=state.reviews.filter(item=>item.predecessor_review_id===review.id);
  if(!review.predecessor_review_id && review.status!=='rebase_required' && !children.length)return '';
  const context=review.revision_context||{};
  const canFollowUp=review.status==='rebase_required' && review.base_version===state.activeProject?.version
    && !children.some(child=>['open','committed'].includes(child.status));
  const versionNotice=review.status==='open'
    ? 'Requirements carried forward. Evidence and approval must be collected again for this target.'
    : 'This review has its own evidence and decision records. Previous-version notes remain historical.';
  return `<section class="review-continuation" aria-label="${I18n.t('Revision history')}">
    ${review.predecessor_review_id?`<details class="revision-summary"><summary>${uiIcon('history')}<span>${I18n.mark('Revision history')}</span><small>${I18n.mark('Follow-up')}</small></summary><div class="revision-summary-body"><button class="text-button" type="button" data-followup-review="${esc(review.predecessor_review_id)}">${I18n.mark('Open previous review')} ${uiIcon('arrow-right')}</button><p>${esc(context.reason||'')}</p><p>${I18n.mark(versionNotice)}</p>${context.findings?.length||context.source_readings?.length?`<details><summary>${I18n.mark('Questions from the previous version · not current findings')}</summary><ul>${(context.findings||[]).map(f=>`<li>${esc(f.path||'')} ${esc(f.message)}</li>`).join('')}${(context.source_readings||[]).map(n=>`<li><code>${esc(n.path)}:${n.start_line} @${esc(n.version_ref.slice(0,8))}</code> ${esc(n.summary)}</li>`).join('')}</ul></details>`:''}</div></details>`:''}
    ${canFollowUp?`<div class="revision-next"><span>${I18n.mark('Update requested')}</span>${!document.body.classList.contains('viewer-mode')?`<button type="button" class="button button-small" data-review-revision>${I18n.mark('Review revised version')} ${uiIcon('arrow-right')}</button>`:''}</div>`:''}
    ${review.status==='rebase_required'&&!canFollowUp&&!children.length?`<p>${I18n.mark('The baseline has advanced. Start a new review against the current project version.')}</p>`:''}
    ${children.map(child=>`<button type="button" class="text-button" data-followup-review="${esc(child.id)}">${I18n.mark('Open follow-up review')} · ${esc(short(child.target_ref))} · ${I18n.mark(reviewStatusLabel(child.status))} ${uiIcon('arrow-right')}</button>`).join('')}
  </section>`;
}

function renderReview() {
  const review = state.activeReview;
  const manifest = state.manifest;
  if (!review || !manifest) return;
  const open = review.status === "open";
  const events = state.events.map((event) => `<div class="event"><strong>${esc(title(event.action))}</strong><span>${esc(event.actor)}</span><small>${new Date(event.created_at).toLocaleString()}</small>${event.reason ? `<p>${esc(event.reason)}</p>` : ""}</div>`).join("");
  const claimContext = renderClaimContext();
  const commitButton = open
    ? `<button type="button" class="button button-with-icon ${manifest.committable ? "button-primary" : "button-muted-gate"} decision-button" data-action="commit" aria-label="Record approval" ${manifest.committable ? "" : 'disabled title="Resolve blocking checks before recording approval" data-i18n-title=Resolve%20blocking%20checks%20before%20recording%20approval'} data-i18n-aria-label=Record%20approval>${manifest.committable ? uiIcon("check-circle") : uiIcon("lock")}<span data-i18n=Approve>Approve</span></button>`
    : "";
  const showDecisionOptions = !document.body.classList.contains("viewer-mode") && (open || review.status === "committed");
  const externalUrl = safeHttpUrl(review.external_url);
  const externalAction = externalUrl
    ? `<a class="button button-quiet button-with-icon external-review-link" href="${esc(externalUrl)}" target="_blank" rel="noopener noreferrer" role="menuitem" tabindex="-1">${uiIcon("github")}<span data-i18n=Open%20on%20GitHub>Open on GitHub</span></a>`
    : "";
  const records = renderDecisionRecords(review);
  destroyContractGraph();
  const detail = $("#review-canvas");
  detail.removeAttribute("aria-busy");
  detail.innerHTML = `
    ${governanceReturnButton(review.id)}
    <div class="detail-head">
      <div class="detail-title"><p class="review-meta"><span class="status-pill status-${esc(review.status)}">${I18n.mark(reviewStatusLabel(review.status))}</span><span>${esc(reviewRef(review))}</span><span title="${esc(absoluteTime(review.created_at))}">${I18n.mark(relativeTime(review.created_at))}</span>${externalUrl ? `<a class="review-meta-link" href="${esc(externalUrl)}" target="_blank" rel="noopener noreferrer">${uiIcon("github")}<span>${esc(review.external_label || "Open on GitHub")}</span></a>` : ""}${review.intent_id ? '<span class="review-meta-note">from an intent map</span>' : ""}</p><h2 class="review-intent-title" tabindex="-1" title="${esc(review.intent_summary || reviewStatusLabel(review.status))}">${esc(review.intent_summary || reviewStatusLabel(review.status))}</h2><p class="proposer-line"><b>${esc(review.proposer.replace(/^github:/, ""))}</b><span title="${esc(review.base_ref)} → ${esc(review.target_ref)}">${I18n.mark("{count} files changed",{count:review.changed_paths.length})}</span></p></div>
      <div class="detail-actions">
        <button type="button" class="button button-with-icon open-files-inspector-button" aria-label="Open changed files" data-i18n-aria-label=Open%20changed%20files>${uiIcon("panel-right")}<span data-i18n=Files>Files</span></button>
        <button type="button" class="button button-with-icon open-ai-inspector-button" aria-label="Ask AI about this review" data-i18n-aria-label=Ask%20AI%20about%20this%20review>${uiIcon("message-square")}<span data-i18n=Ask%20AI>Ask AI</span></button>
        <details class="review-more-menu"><summary class="button icon-tool-button" id="review-more-button" role="button" aria-label="More review actions" aria-haspopup="menu" aria-expanded="false" aria-controls="review-actions-menu" data-tooltip="More actions" data-i18n-aria-label=More%20review%20actions data-i18n-data-tooltip=More%20actions>${uiIcon("more-horizontal")}${controlTooltip("More actions")}</summary><div id="review-actions-menu" role="menu" aria-labelledby="review-more-button">${externalAction}<button type="button" class="button button-quiet button-with-icon copy-link-button" role="menuitem" tabindex="-1" aria-label="Copy review link" data-i18n-aria-label=Copy%20review%20link>${uiIcon("link")}<span data-i18n=Copy%20review%20link>Copy review link</span></button><button type="button" class="button button-quiet button-with-icon summarize-button" role="menuitem" tabindex="-1" aria-label="Refresh review summary" data-i18n-aria-label=Refresh%20review%20summary>${uiIcon("refresh")}<span data-i18n=Refresh%20summary>Refresh summary</span></button><button type="button" class="button button-quiet button-with-icon copy-brief-button" role="menuitem" tabindex="-1">${uiIcon("file-text")}<span data-i18n=Copy%20summary>Copy summary</span></button><a class="button button-quiet button-with-icon export-link" href="/api/reviews/${esc(review.id)}/export" download role="menuitem" tabindex="-1">${uiIcon("download")}<span data-i18n=Export%20JSON>Export JSON</span></a></div></details>
      </div>
    </div>
    <div class="review-revision-band" aria-label="Source revisions" data-i18n-aria-label=Source%20revisions><span>${uiIcon("github")}<span>${esc(displayRepo(state.activeProject))}</span></span><span class="revision-comparison"><span><span data-i18n=base>base</span> <code title="${esc(review.base_ref)}">${esc(short(review.base_ref))}</code></span>${uiIcon("arrow-right")}<span><span data-i18n=target>target</span> <code title="${esc(review.target_ref)}">${esc(short(review.target_ref))}</code></span></span></div>
    ${renderRevisionContext(review)}
    ${renderReviewWorkspaceTabs()}
    ${document.body.classList.contains("viewer-mode") ? '<div class="permission-notice" role="note"><strong data-i18n=Read-only%20access>Read-only access</strong><span data-i18n=You%20can%20inspect%20this%20review%20and%20its%20evidence%2C%20but%20only%20an%20operator%20can%20change%20the%20recorded%20decision.>You can inspect this review and its evidence, but only an operator can change the recorded decision.</span></div>' : ""}
    <div class="review-workspace-panels">
      <section role="tabpanel" id="review-panel-overview" aria-labelledby="review-tab-overview" data-review-panel="overview"${reviewWorkspaceTab === "overview" ? "" : " hidden"}>
        <section class="decision-hero module" data-tone="${esc(verdictTone(review, manifest))}">
        ${renderReviewVerdict(review, manifest)}
        ${showDecisionOptions ? `<div class="decision-bar" tabindex="-1" role="group" aria-label="${I18n.t('Decision options')}" data-i18n-aria-label=Decision%20options>
          <span class="decision-bar-copy"><strong>${I18n.mark('Your decision')}</strong><small>${reviewDecisionBoundary(review, manifest)}</small></span>
          ${open ? `<button type="button" class="button button-with-icon decision-button" data-action="rebase">${uiIcon("git-rebase")}<span data-i18n=Request%20update>Request update</span></button><button type="button" class="button button-with-icon button-danger decision-button" data-action="reject">${uiIcon("x-circle")}<span data-i18n=Reject>Reject</span></button>` : ""}
          ${commitButton}
          ${review.status === "committed" ? `<button type="button" class="button button-with-icon button-danger decision-button" data-action="rollback">${uiIcon("refresh")}<span data-i18n=Roll%20back%20approval>Roll back approval</span></button>` : ""}
        </div>` : ""}
        </section>
        ${CommitmentUI.reviewView(review,manifest)}
        ${CommitmentUI.riskView(review)}
        <details class="visual-review-detail review-policy-detail"><summary><span data-i18n=Policy%20checks>Policy checks</span><small>${I18n.mark("{count} blocking checks",{count:manifest.admission_checks.filter(item=>item.status==="block").length})}</small></summary>${renderAdmission(manifest)}</details>
        ${records ? `<details class="review-disclosure decision-history module"${open ? "" : " open"}><summary><span data-i18n=Recorded%20decision>Recorded decision</span><small>${plural(review.decision_records.length, "record")}</small></summary>${records}</details>` : ""}
      </section>

      <section role="tabpanel" id="review-panel-evidence" aria-labelledby="review-tab-evidence" data-review-panel="evidence"${reviewWorkspaceTab === "evidence" ? "" : " hidden"}>
        ${renderEvidenceWorkspace(review, manifest)}
      </section>

      <section role="tabpanel" id="review-panel-changes" aria-labelledby="review-tab-changes" data-review-panel="changes"${reviewWorkspaceTab === "changes" ? "" : " hidden"}>
        <div class="review-return-row"><button type="button" class="text-button" data-return-to-decision>${uiIcon('chevron-left')}${I18n.mark('Back to decision')}</button></div>
        <details class="visual-review-detail commitment-file-map"><summary><span data-i18n=Explore%20the%20code%20changes>Explore the code changes</span><small>${I18n.mark("{count} files · paths and change volume",{count:review.changed_paths.length})}</small></summary>${renderReviewChangeMap(review, manifest)}</details>
        <div class="detail-body review-changes-panel">
          <div id="changed-files-block">${renderChangedFiles(review)}</div>
          <p class="diff-note hidden" id="diff-note" role="note"></p>
          <div id="diff-viewer" class="diff-viewer" role="region" tabindex="0" aria-label="Selected file diff"></div>
          <div class="diff-toolbar"><span data-i18n=Raw%20unified%20patch>Raw unified patch</span><div class="diff-toolbar-actions"><button type="button" class="button button-small button-quiet load-diff-button" aria-controls="unified-diff" aria-expanded="false" data-i18n=Open%20full%20diff>Open full diff</button></div></div>
          <pre class="unified-diff hidden" id="unified-diff"></pre>
          ${claimContext ? `<details class="review-disclosure diff-claims"><summary><span data-i18n=Governing%20claims>Governing claims</span><small>${plural(state.activeProject.claims.length, "claim")}</small></summary>${claimContext}</details>` : ""}
        </div>
      </section>

      <section role="tabpanel" id="review-panel-audit" aria-labelledby="review-tab-audit" aria-label="Decision provenance" data-review-panel="audit"${reviewWorkspaceTab === "audit" ? "" : " hidden"} data-i18n-aria-label=Decision%20provenance>
        <div class="review-return-row"><button type="button" class="text-button" data-return-to-decision>${uiIcon('chevron-left')}${I18n.mark('Back to decision')}</button></div>
        <details class="visual-review-detail review-linkage-detail"><summary><span data-i18n=Request-to-decision%20links>Request-to-decision links</span><small data-i18n=Inspect%20recorded%20correspondence>Inspect recorded correspondence</small></summary>${renderReviewTrace(review, manifest)}</details>
        <div class="detail-body review-audit-panel">
          <div id="contract-graph-mount" class="module module-flush"></div>
          <details class="review-disclosure audit-events module"><summary><span data-i18n=Recorded%20events>Recorded events</span><small>${plural(state.events.length, "event")}</small></summary><div class="timeline">${events || '<div class="empty-contract" data-i18n=No%20recorded%20events%20yet.>No recorded events yet.</div>'}</div></details>
        </div>
      </section>
    </div>
  `;
  bindGovernanceReturn();
  document.querySelectorAll('[data-return-to-decision]').forEach(button => button.addEventListener('click', returnToDecision));
  $("#next-review-inspection")?.addEventListener("click", inspectNextReviewStep);
  $("#review-actions-menu")?.insertAdjacentHTML("afterbegin", `<button type="button" class="button button-quiet button-with-icon" role="menuitem" tabindex="-1" data-open-inspector="files">${uiIcon("panel-right")}<span data-i18n=Files>Files</span></button><button type="button" class="button button-quiet button-with-icon" role="menuitem" tabindex="-1" data-open-inspector="assistant">${uiIcon("message-square")}<span data-i18n=Ask%20AI>Ask AI</span></button>`);
  const assistantPanel = $("#inspector-assistant");
  if (assistantPanel) assistantPanel.innerHTML = renderReviewCopilot();
  document.querySelectorAll(".waive-button").forEach((node) => node.addEventListener("click", () => openDecision("waive", node.dataset.finding)));
  document.querySelectorAll(".waive-obligation-button").forEach((node) => node.addEventListener("click", () => openDecision("waive", "", node.dataset.obligation)));
  document.querySelectorAll(".attach-evidence-button").forEach((node) => node.addEventListener("click", () => openEvidence(node.dataset.obligation)));
  document.querySelectorAll(".import-dsse-button").forEach((node) => node.addEventListener("click", () => openDsseAttestation(node.dataset.obligation)));
  document.querySelectorAll(".decision-button:not(:disabled)").forEach((node) => node.addEventListener("click", () => openDecision(node.dataset.action)));
  document.querySelector('[data-review-revision]')?.addEventListener('click',()=>openCompareDialog(review));
  document.querySelectorAll('[data-followup-review]').forEach(button=>button.addEventListener('click',()=>selectReview(button.dataset.followupReview).catch(error=>toast(error.message))));
  $(".summarize-button")?.addEventListener("click", (event) => summarizeReview(event.currentTarget));
  $(".load-diff-button")?.addEventListener("click", (event) => loadDiff(event.currentTarget));
  document.querySelectorAll("[data-configure-tests]").forEach((node) => node.addEventListener("click", openTestConfiguration));
  document.querySelectorAll("[data-open-review-tab]:not(.review-change-map *)").forEach((node) => node.addEventListener("click", () => {
    if (node.hasAttribute("data-open-evidence-records")) {
      state.evidenceQuery = ""; state.evidenceFilter = "all"; state.evidenceObligation = "";
      $("#evidence-record-search").value = ""; $("#evidence-record-filter").value = "all";
      refreshEvidenceRecords(); setEvidenceTab("records");
    }
    setReviewWorkspaceTab(node.dataset.openReviewTab, { focus: true });
  }));
  document.querySelectorAll("[data-open-project-view]:not(.review-change-map *)").forEach((node) => node.addEventListener("click", () => setProjectView(node.dataset.openProjectView)));
  $(".copy-link-button")?.addEventListener("click", copyReviewLink);
  $(".open-files-inspector-button")?.addEventListener("click", () => setInspectorTab("files", { open: true, focus: true }));
  $(".open-ai-inspector-button")?.addEventListener("click", () => setInspectorTab("assistant", { open: true, focus: true }));
  document.querySelectorAll(".copy-brief-button").forEach(button=>button.addEventListener("click",copyReviewBrief));
  $(".review-more-menu .export-link")?.addEventListener("click", async (event) => {
    event.currentTarget.closest("details").open = false;
    if (document.documentElement.dataset.paperDemo !== "true") return;
    event.preventDefault();
    try {
      const record = await api(`/api/reviews/${encodeURIComponent(review.id)}/export`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], {type: "application/json"}));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${review.id}.json`;
      anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { toast(error.message); }
  });
  bindReviewMoreMenu();
  document.querySelectorAll("[data-open-inspector]").forEach(node => node.addEventListener("click", () => {
    const menu = node.closest(".review-more-menu");
    menu.open = false;
    menu.querySelector("summary")?.focus({preventScroll:true});
    setInspectorTab(node.dataset.openInspector,{open:true,focus:true});
  }));
  bindEvidenceWorkspace();
  document.querySelectorAll("[data-review-tab]").forEach((node) => {
    node.addEventListener("click", () => setReviewWorkspaceTab(node.dataset.reviewTab));
    node.addEventListener("keydown", handleReviewWorkspaceTabKeydown);
  });
  $("#review-copilot-form")?.addEventListener("submit", askReviewCopilot);
  $("#review-copilot-question")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      const form = $("#review-copilot-form");
      form?.requestSubmit(form.querySelector('[type="submit"]'));
    }
  });
  $("#evidence-gaps-button")?.addEventListener("click", planEvidenceGaps);
  document.querySelectorAll("[data-copilot-prompt]").forEach((node) => {
    node.addEventListener("click", () => {
      const question = $("#review-copilot-question");
      if (!question) return;
      question.value = node.dataset.copilotPrompt;
      question.dispatchEvent(new Event("input", {bubbles:true}));
      question.focus();
    });
  });
  document.querySelectorAll("[data-changed-file]").forEach((node) => {
    node.addEventListener("click", () => openChangedFile(node.dataset.changedFile));
  });
  document.querySelectorAll("[data-open-changed-file]:not(.review-change-map *)").forEach((node) => {
    node.addEventListener("click", () => openChangedFile(node.dataset.openChangedFile, node.dataset.openFinding));
  });
  bindReviewChangeMap();
  ReviewMotion.disclosures(detail);
  detail.querySelectorAll('.map-file-tile').forEach((node,index)=>ReviewMotion.enter(node,"tile",index));
  renderDiffNavigation(review);
  if (state.diffReviewId === review.id && state.diffText !== null) renderDiffViewer();
  const recentCopilotRun = state.aiRuns.find((item) => (
    item.review_id === review.id
    && ["review_copilot", "evidence_gap_planner"].includes(item.feature)
    && item.review_revision === review.revision
    && item.project_version === state.activeProject?.version
    && !(item.quality_flags || []).includes("legacy_unversioned_context")
  ));
  const copilotDraft = currentCopilotDraft();
  state.activeCopilotRun = state.aiRuns.find(item => item.id === copilotDraft?.runId && item.review_id === review.id) || recentCopilotRun || null;
  renderAIEvalStrip();
  renderReviewCopilotOutput();
  restoreCopilotDraft();
  setInspectorTab(state.inspectorTab);
  setReviewWorkspaceTab(reviewWorkspaceTab);
  renderReviewSyncNotice();
}

function renderReviewSyncNotice() {
  $("#review-sync-notice")?.remove();
  const notice = reviewSyncNotices.get(state.activeReview?.id);
  const detail = $("#review-canvas");
  if (!notice || notice.userId !== state.auth?.user?.id || notice.projectId !== state.activeProject?.id
      || detail.getAttribute("aria-busy") === "true") return;
  const node = document.createElement("div");
  node.id = "review-sync-notice";
  node.className = "review-sync-notice";
  node.setAttribute("role", "status");
  node.innerHTML = `<div><strong>${esc(notice.message)}</strong><p>${notice.pending ? "Saved. Updating the review…" : "Saved, but this view has not refreshed. Refresh to see the latest state; do not submit the record again."}</p></div><button type="button" class="button"${notice.pending ? ' disabled aria-busy="true"' : ""}>Refresh review</button>`;
  (detail.querySelector(".review-workspace-tabs, .review-error") || detail.firstElementChild)?.before(node);
  node.querySelector("button").onclick = async () => {
    notice.pending = true;
    renderReviewSyncNotice();
    try {
      await refreshCurrentProject(notice.reviewId);
    } catch {
      // The write already succeeded. Recovery retries reads only.
    } finally {
      notice.pending = false;
      renderReviewSyncNotice();
      if (state.activeReview?.id === notice.reviewId) {
        ($("#review-sync-notice button") || $(".review-intent-title"))?.focus({ preventScroll: true });
      }
    }
  };
}

async function completeReviewOperation(form, context, message) {
  finishReviewOperation(form, context);
  if (context.userId !== state.auth?.user?.id || document.body.classList.contains("auth-locked")) return;
  const notice = { ...context, message, pending: reviewOperationIsCurrent(context) };
  reviewSyncNotices.set(context.reviewId, notice);
  renderReviewSyncNotice();
  try {
    await refreshCurrentProject(context.reviewId, context);
  } catch {
    // Keep a persistent, review-scoped receipt when the follow-up read fails.
  } finally {
    notice.pending = false;
    renderReviewSyncNotice();
  }
  if (context.userId !== state.auth?.user?.id || document.body.classList.contains("auth-locked")) return;
  if (reviewSyncNotices.get(context.reviewId) === notice && reviewOperationIsCurrent(context)
      && !document.querySelector("dialog[open]")) {
    $("#review-sync-notice")?.scrollIntoView({ block: "center", behavior: "instant" });
    $("#review-sync-notice button")?.focus({ preventScroll: true });
  }
  if (!reviewSyncNotices.has(context.reviewId)) toast(message);
  else if (state.activeReview?.id !== context.reviewId) toast(`${message} — ${context.reviewTitle}`);
}

function closeReviewOperations(nextReviewId = null) {
  comparisonContext = null;
  if ($("#review-source-dialog").open) $("#review-source-dialog").close();
  if ($("#review-dialog").open) $("#review-dialog").close();
  reviewOperationDialogs.forEach(id => {
    const dialog = $(`#${id}`);
    const context = reviewOperations.get(dialog.querySelector("form"));
    if (dialog.open && context?.reviewId !== nextReviewId) dialog.close();
  });
}

function reviewOperationIsCurrent(context) {
  return Boolean(context && !document.body.classList.contains("auth-locked")
    && context.userId === state.auth?.user?.id
    && context.projectId === state.activeProject?.id
    && context.reviewId === state.activeReview?.id
    && context.targetRef === state.activeReview?.target_ref
    && context.revision === state.activeReview?.revision
    && context.selectionVersion === state.selectionVersion
    && context.reviewSelectionVersion === state.reviewSelectionVersion);
}

function requireReviewOperation(form) {
  const context = reviewOperations.get(form);
  if (!form.closest("dialog").open || !reviewOperationIsCurrent(context)) {
    throw new Error("This review has changed. Reopen the action from the review you want to update. Your input has not been submitted.");
  }
  return context;
}

function finishReviewOperation(form, context) {
  // A later opening of the same form owns its own input and must not be cleared.
  if (reviewOperations.get(form) !== context) return;
  form.closest("dialog").close();
  form.reset();
  delete form.dataset.draftKey;
  reviewOperations.delete(form);
}

function showDialog(id) {
  const dialog = $(id);
  if (reviewOperationDialogs.includes(dialog.id)) {
    if (!state.activeReview || !state.activeProject) return toast("Open a review before continuing.");
    const form = dialog.querySelector("form");
    reviewOperations.set(form, {
      userId: state.auth?.user?.id, projectId: state.activeProject.id,
      reviewId: state.activeReview.id, targetRef: state.activeReview.target_ref,
      reviewTitle: state.activeReview.intent_summary || state.activeReview.summary,
      revision: state.activeReview.revision, selectionVersion: state.selectionVersion,
      reviewSelectionVersion: state.reviewSelectionVersion,
    });
    let context = form.querySelector(".operation-context");
    if (!context) {
      context = document.createElement("div");
      context.className = "operation-context";
      form.querySelector(".dialog-head").after(context);
    }
    context.innerHTML = `<span data-i18n=This%20review>This review</span><strong>${esc(state.activeReview.intent_summary || state.activeReview.summary)}</strong><small><span>${esc(state.activeProject.name)}</span><span><span data-i18n=Target%20revision>Target revision</span> <code>${esc(short(state.activeReview.target_ref))}</code></span></small>`;
  }
  if (!dialog.open) {dialog.showModal();ReviewMotion.enter(dialog,"dialog");}
  window.requestAnimationFrame(() => {
    const field = dialog.querySelector('[autofocus]');
    field?.focus({ preventScroll: true });
    // Reveal the whole field above sticky form actions, not just its first line.
    (field?.closest('label') || field)?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
  });
}

function replaceIntent(updated) {
  if (updated.project_id !== state.activeProject?.id) return;
  const index = state.intents.findIndex((item) => item.id === updated.id);
  if (index >= 0) state.intents[index] = updated;
  else state.intents.unshift(updated);
  renderIntentWorkspace();
  $("#project-canvas")?.removeAttribute("data-signature");
}

const candidateRevisionDrafts = new Map();
let candidateRevisionDraft = null;

function clearCandidateRevisionDrafts() {
  CommitmentUI.clear();
  candidateRevisionDrafts.clear();
  candidateRevisionDraft = null;
  $("#candidate-revision-dialog").close();
  $("#candidate-revision-form").reset();
  $("#candidate-revision-changes").replaceChildren();
  $("#candidate-revision-latest-content").replaceChildren();
}

function candidateRevisionIsOwned(draft, token = state.csrfToken) {
  return draft.ownerId === state.auth?.user?.id && token === state.csrfToken && state.auth?.user?.role !== "viewer";
}

function captureCandidateRevisionDraft() {
  const draft = candidateRevisionDraft;
  if (!draft || draft.saving || draft.checking) return;
  const form = $("#candidate-revision-form");
  draft.values = Object.fromEntries(["title", "summary", "path", "from_module", "to_module", "uncertainties"].map(field => [field, form.elements[field].value]));
  draft.reason = form.elements.reason.value;
}

function populateCandidateRevisionDraft() {
  const form = $("#candidate-revision-form"), draft = candidateRevisionDraft;
  for (const [field, value] of Object.entries(draft.values)) form.elements[field].value = value;
  form.elements.reason.value = draft.reason;
  form.querySelectorAll("input, textarea").forEach(input => input.setCustomValidity(""));
}

function renderCandidateRevisionState() {
  const draft = candidateRevisionDraft;
  if (!draft) return;
  const original = draft.snapshot.candidates.find(candidate => candidate.id === draft.candidateId);
  const candidate = IntentModel.editCandidate(original || {provenance: "human-authored/added-alternative", confidence: null, status: "active"}, draft.values);
  const changes = IntentModel.candidateChanges(original, candidate);
  $("#candidate-revision-title").textContent = draft.candidateId ? "Edit proposal" : "Add an alternative";
  $("#candidate-revision-context").textContent = `${state.activeProject?.id === draft.projectId ? state.activeProject.name : "Request"} · Revision ${draft.snapshot.revision}`;
  $("#candidate-revision-request").textContent = draft.snapshot.request;
  $("#candidate-revision-constraints").textContent = draft.snapshot.context;
  $("#candidate-revision-changes").innerHTML = candidateChangeMarkup(changes, "Saved", "Your draft");
  $("#candidate-revision-change-count").textContent = `(${changes.length})`;
  const impact = `${draft.candidateId ? plural(changes.length, "field") + " changed" : "1 alternative added"}; all ${draft.snapshot.candidates.filter(item => item.status === "active").length} active interpretations stay open.`;
  if ($("#candidate-revision-impact").textContent !== impact) $("#candidate-revision-impact").textContent = impact;
  $("#candidate-revision-error").textContent = draft.error || "";
  const busy = draft.saving || draft.checking;
  const button = $("#candidate-revision-submit");
  // setBusy retains its first idle label; restore it before setting mode-specific text.
  if (button.getAttribute("aria-busy") === "true") setBusy(button, false);
  button.textContent = draft.candidateId ? "Save proposal changes" : "Record alternative";
  if (busy) setBusy(button, true, draft.saving ? "Saving…" : "Checking latest…");
  button.disabled = Boolean(busy || draft.needsReview || draft.locked);
  $("#candidate-revision-form .intent-composer-body").inert = Boolean(busy);
  $("#candidate-revision-latest").hidden = !draft.needsReview;
  $("#candidate-revision-latest").disabled = Boolean(busy);
  $("#candidate-revision-draft-note").textContent = draft.saving ? "Saving this exact version. Closing the panel will not cancel the save." : "Draft stays here while this page is open. Nothing is selected or executed.";
  $("#candidate-revision-conflict").hidden = !draft.latest;
  $("#candidate-revision-rebase").hidden = !draft.latest || draft.locked;
  if (draft.latest) {
    const latestCandidate = draft.latest.candidates.find(item => item.id === draft.candidateId);
    $("#candidate-revision-conflict-copy").textContent = draft.locked ? "This proposal can no longer be edited. Your draft is kept for reference; close the panel to inspect the recorded decision." : `Latest revision ${draft.latest.revision} is shown below. Applying your edits keeps fields you did not change from the latest version; it does not save anything.`;
    const proposed = draft.candidateId && latestCandidate ? IntentModel.editCandidate(latestCandidate, IntentModel.rebaseCandidate(original, latestCandidate, draft.values)) : candidate;
    $("#candidate-revision-latest-content").innerHTML = latestCandidate ? `<h4>Changes since your draft</h4>${candidateChangeMarkup(IntentModel.candidateChanges(original, latestCandidate), "When you started", "Latest saved version")}<h4>Your edits to apply</h4>${candidateChangeMarkup(IntentModel.candidateChanges(latestCandidate, proposed), "Latest", "After applying your edits")}` : `<p class="field-hint">${draft.candidateId ? "The original proposal is no longer available." : `${draft.latest.candidates.length} interpretations are recorded. Your new alternative remains a draft.`}</p>`;
  }
}

function openCandidateRevision(intentId, candidateId = null) {
  const intent = state.intents.find(item => item.id === intentId);
  const candidate = candidateId ? intent?.candidates.find(item => item.id === candidateId) : null;
  if (!intent || !state.auth?.user || state.auth.user.role === "viewer" || !IntentModel.canRevise(intent, candidate) || (candidateId && !candidate)) return toast("This proposal is no longer editable. Reload the request to inspect its current state.");
  const key = `${intent.project_id}/${intent.id}/${candidateId || "new"}`;
  let draft = candidateRevisionDrafts.get(key);
  if (!draft) {
    draft = {key, projectId: intent.project_id, ownerId: state.auth.user.id, candidateId, snapshot: structuredClone(intent), values: candidate ? IntentModel.candidateValues(candidate) : {title: "", summary: "", path: "", from_module: "", to_module: "", uncertainties: ""}, reason: "", error: ""};
    candidateRevisionDrafts.set(key, draft);
  }
  if (draft.snapshot.revision !== intent.revision && !draft.saving) {
    draft.needsReview = true;
    draft.error = "The request changed while this draft was closed. Review the latest revision before saving. Your edits are kept.";
  }
  candidateRevisionDraft = draft;
  populateCandidateRevisionDraft();
  $("#candidate-revision-files").innerHTML = (state.projectTree?.entries || []).filter(entry => entry.kind === "file" && entry.path.endsWith(".py")).map(entry => `<option value="${esc(entry.path)}"></option>`).join("");
  $("#candidate-revision-preview").open = false;
  renderCandidateRevisionState();
  showDialog("#candidate-revision-dialog");
  $("#candidate-revision-form .intent-composer-body").scrollTop = 0;
}

function finishCandidateRevision(draft, updated) {
  replaceIntent(updated);
  candidateRevisionDrafts.delete(draft.key);
  if (candidateRevisionDraft === draft) {
    $("#candidate-revision-dialog").close();
    candidateRevisionDraft = null;
    $("#candidate-revision-form").reset();
    const candidateId = draft.candidateId || updated.clarification_history.at(-1)?.added_candidate_ids[0];
    window.requestAnimationFrame(() => document.querySelector(`.edit-intent-candidate[data-intent="${CSS.escape(updated.id)}"][data-candidate="${CSS.escape(candidateId || "")}"]`)?.focus());
  }
  if (state.activeProject?.id === draft.projectId) toast(draft.candidateId ? "Proposal changes saved. Other interpretations stay open; nothing was selected or executed." : "Alternative recorded. Nothing was selected or executed.");
}

async function reviewLatestCandidateRevision() {
  const draft = candidateRevisionDraft;
  if (!draft || draft.saving || draft.checking || !candidateRevisionIsOwned(draft)) return;
  captureCandidateRevisionDraft();
  const token = state.csrfToken;
  draft.checking = true;
  renderCandidateRevisionState();
  try {
    const latest = await api(`/api/intents/${draft.snapshot.id}`);
    if (!candidateRevisionIsOwned(draft, token)) return;
    if (draft.uncertain && draft.payload && IntentModel.recordedRevision(latest, draft.payload, draft.actor)) {
      finishCandidateRevision(draft, latest);
      return;
    }
    replaceIntent(latest);
    draft.latest = latest;
    const candidate = draft.candidateId ? latest.candidates.find(item => item.id === draft.candidateId) : null;
    draft.locked = !IntentModel.canRevise(latest, candidate) || (draft.candidateId && !candidate);
    draft.error = draft.uncertain ? "The attempted save was not found in the latest record. Compare below before continuing." : "Compare the latest record with your edits below before continuing.";
    if (candidateRevisionDraft === draft && $("#candidate-revision-dialog").open) window.requestAnimationFrame(() => $("#candidate-revision-conflict").focus());
  } catch (error) {
    if (candidateRevisionIsOwned(draft, token)) draft.error = `${error.message} Could not check the latest version. Your draft is kept; try reviewing again.`;
  } finally {
    draft.checking = false;
    if (candidateRevisionDraft === draft && candidateRevisionIsOwned(draft, token)) renderCandidateRevisionState();
  }
}

$("#candidate-revision-form").addEventListener("input", event => {
  event.target.setCustomValidity?.("");
  captureCandidateRevisionDraft();
  if (candidateRevisionDraft && !candidateRevisionDraft.needsReview) candidateRevisionDraft.error = "";
  renderCandidateRevisionState();
});
$("#candidate-revision-latest").addEventListener("click", reviewLatestCandidateRevision);
$("#candidate-revision-rebase").addEventListener("click", () => {
  const draft = candidateRevisionDraft;
  if (!draft?.latest || draft.locked || draft.saving || draft.checking || !candidateRevisionIsOwned(draft)) return;
  captureCandidateRevisionDraft();
  if (draft.candidateId) draft.values = IntentModel.rebaseCandidate(draft.snapshot.candidates.find(item => item.id === draft.candidateId), draft.latest.candidates.find(item => item.id === draft.candidateId), draft.values);
  draft.snapshot = structuredClone(draft.latest);
  draft.latest = null;
  draft.needsReview = false;
  draft.uncertain = false;
  draft.error = "";
  populateCandidateRevisionDraft();
  renderCandidateRevisionState();
  $("#candidate-revision-preview").open = true;
  $("#candidate-revision-form").elements.title.focus();
});
$("#candidate-revision-form").addEventListener("submit", async event => {
  event.preventDefault();
  const draft = candidateRevisionDraft;
  if (!draft || draft.saving || draft.checking || draft.needsReview || draft.locked || !candidateRevisionIsOwned(draft) || state.activeProject?.id !== draft.projectId) return;
  captureCandidateRevisionDraft();
  try {
    draft.payload = IntentModel.revisionPayload(draft.snapshot, {candidateId: draft.candidateId, values: draft.values, reason: draft.reason});
  } catch (error) {
    draft.error = error.message;
    renderCandidateRevisionState();
    const field = event.currentTarget.elements[error.field];
    if (field) {field.setCustomValidity(error.message); field.reportValidity();}
    return;
  }
  const token = state.csrfToken;
  draft.actor = state.auth.user.actor;
  draft.error = "";
  draft.saving = true;
  renderCandidateRevisionState();
  try {
    const updated = await api(`/api/intents/${draft.snapshot.id}/clarifications`, {method: "POST", body: JSON.stringify(draft.payload)});
    if (!candidateRevisionIsOwned(draft, token)) return;
    if (updated.id !== draft.snapshot.id || updated.project_id !== draft.projectId || !IntentModel.recordedRevision(updated, draft.payload, draft.actor)) throw new Error("The saved response could not be matched to this edit.");
    finishCandidateRevision(draft, updated);
  } catch (error) {
    if (!candidateRevisionIsOwned(draft, token)) return;
    draft.uncertain = !error.status || error.status >= 500;
    draft.needsReview = draft.uncertain || error.status === 409 || error.status === 404;
    draft.error = draft.uncertain ? "The save result is uncertain. Review the latest revision before retrying to avoid recording it twice. Your draft is kept." : `${error.message} Your draft is kept.${draft.needsReview ? " Review the latest revision before saving." : " Correct the proposal and try again."}`;
  } finally {
    draft.saving = false;
    if (candidateRevisionDraft === draft && candidateRevisionIsOwned(draft, token)) renderCandidateRevisionState();
  }
});

let clarificationSnapshot = null;

function openClarification(intentId, candidateId) {
  const intent = state.intents.find((item) => item.id === intentId);
  const candidate = intent?.candidates.find((item) => item.id === candidateId && item.status === "active");
  if (!intent || !candidate) return toast("The candidate is no longer available for clarification");
  const form = $("#clarification-form");
  form.reset();
  $("#clarification-error").textContent = "";
  form.elements.intent_id.value = intent.id;
  form.elements.candidate_id.value = candidate.id;
  form.elements.expected_revision.value = intent.revision;
  clarificationSnapshot = structuredClone(intent);
  $("#clarification-candidate").textContent = intent.request;
  $("#clarification-choices").innerHTML = `<h3>Keep the interpretations that are still possible</h3><p class="field-hint">Unchecking an interpretation records it as ruled out. Nothing is selected or realized here.</p>${intent.candidates.filter((item) => item.status === "active").map((item) => `<fieldset class="clarification-choice" data-candidate="${esc(item.id)}"><legend>${esc(item.title)}</legend><label class="clarification-check"><input type="checkbox" name="retained" value="${esc(item.id)}" checked><span>Keep this interpretation</span></label><div class="clarification-questions"><p class="field-hint">${item.uncertainties.length ? "This answer resolves (optional)" : "No unresolved questions."}</p>${item.uncertainties.map((question, index) => `<label class="clarification-check"><input type="checkbox" data-resolved-index="${index}" value="${esc(item.id)}"><span>${esc(question)}</span></label>`).join("")}</div></fieldset>`).join("")}`;
  $("#clarification-choices").onchange = updateClarificationImpact;
  updateClarificationImpact();
  showDialog("#clarification-dialog");
}

function clarificationValues() {
  const form = $("#clarification-form");
  const retained = [...form.querySelectorAll('[name="retained"]:checked')].map((input) => input.value);
  const resolved = {};
  form.querySelectorAll("[data-resolved-index]:checked:not(:disabled)").forEach((input) => {
    (resolved[input.value] ||= []).push(Number(input.dataset.resolvedIndex));
  });
  return {question: form.elements.question.value, answer: form.elements.answer.value, retained, resolved};
}

function updateClarificationImpact() {
  const form = $("#clarification-form");
  form.querySelectorAll(".clarification-choice").forEach((group) => {
    const retained = group.querySelector('[name="retained"]').checked;
    group.querySelectorAll("[data-resolved-index]").forEach((input) => { input.disabled = !retained; });
    group.classList.toggle("ruled-out", !retained);
  });
  const values = clarificationValues();
  const total = form.querySelectorAll('[name="retained"]').length;
  const resolved = Object.values(values.resolved).reduce((sum, items) => sum + items.length, 0);
  $("#clarification-impact").textContent = `${values.retained.length} kept open, ${total - values.retained.length} ruled out, ${plural(resolved, "question")} resolved. Unchecked questions remain unresolved.`;
}

function openIntentSelection(intentId, candidateId) {
  const intent = state.intents.find((item) => item.id === intentId);
  const candidate = intent?.candidates.find((item) => item.id === candidateId && item.status === "active");
  if (!intent || !candidate) return toast("The candidate is no longer available for selection");
  const form = $("#selection-form");
  form.reset();
  $("#selection-error").textContent = "";
  form.elements.intent_id.value = intent.id;
  form.elements.candidate_id.value = candidate.id;
  form.elements.expected_revision.value = intent.revision;
  $("#selection-candidate").textContent = `${candidate.title} · ${intentCandidateDelta(candidate)}`;
  showDialog("#selection-dialog");
}

async function selectIntentCandidate(intentId, candidateId, reason, expectedRevision) {
  const updated = await api(`/api/intents/${intentId}/selection`, {
    method: "POST",
    body: JSON.stringify({
      candidate_id: candidateId,
      reason,
      expected_revision: Number(expectedRevision),
    }),
  });
  replaceIntent(updated);
  return updated;
}

async function realizeIntent(intentId, expectedRevision) {
  const updated = await api(`/api/intents/${intentId}/realization`, {
    method: "POST",
    body: JSON.stringify({ expected_revision: Number(expectedRevision) }),
  });
  replaceIntent(updated);
  if (state.activeProject) {
    state.reviews = await api(`/api/projects/${state.activeProject.id}/reviews`);
    renderWorkspace();
  }
  if (updated.realized_review_id) await selectReview(updated.realized_review_id);
  toast(updated.status === "realized" ? "Round-trip verification completed" : "Realization preconditions recorded");
  return updated;
}

function openDecision(action, findingId = "", obligationId = "") {
  const form = $("#decision-form");
  form.reset();
  $("#decision-error").textContent = "";
  form.elements.action.value = action;
  form.elements.finding_ids.value = findingId;
  form.elements.obligation_ids.value = obligationId;
  form.elements.reason.required = true;
  form.elements.policy_id.value = state.manifest?.governing_policy || "";
  const authorities = state.manifest?.required_authorities || [];
  form.elements.authority.innerHTML = authorities.map((value) =>
    `<option value="${esc(value)}">${esc(value)}</option>`
  ).join("");
  const waiver = action === "waive";
  $("#waiver-fields").classList.toggle("hidden", !waiver);
  form.elements.scope.disabled = !waiver;
  form.elements.expires_at.disabled = !waiver;
  form.elements.scope.required = waiver;
  form.elements.expires_at.required = waiver;
  const titles = {
    commit: "Approve and record this change",
    waive: "Record a bounded waiver",
    rebase: "Request an update",
    reject: "Reject this change",
    rollback: "Roll back the approval",
  };
  const copy = {
    commit: "Approval records this change in the local project ledger under the policy and authority below. Repository branches are not changed.",
    waive: "A waiver keeps the item visible while lifting the block for a bounded scope and time. It is recorded under your identity and expires automatically.",
    rebase: "Record that this proposal needs an update. It leaves the open-review queue and keeps its history; analyze the revised commits as a new review. Share the review brief with the proposer separately — this action sends no notification.",
    reject: "Rejection closes this review without changing the project state. The record stays auditable.",
    rollback: "Rollback restores the prior project state and marks evidence that depended on this approval as invalid.",
  };
  $("#decision-title").textContent = titles[action] || `${sentence(action)} this change`;
  const decisionCopy = $("#decision-copy");
  if (decisionCopy) decisionCopy.textContent = copy[action] || "";
  const finding = (state.activeReview?.findings || []).find((item) => item.id === findingId);
  const obligation = (state.activeReview?.evidence_obligations || []).find((item) => item.id === obligationId);
  const contextText = finding
    ? `Finding · ${finding.message}${finding.path ? ` · ${finding.path}${finding.line ? `:${finding.line}` : ""}` : ""}`
    : obligation
      ? `Required evidence · ${obligation.label} · ${obligation.claim_id}`
      : "";
  const context = $("#decision-context");
  if (context) {
    context.textContent = contextText;
    context.classList.toggle("hidden", !contextText);
  }
  if (waiver) {
    const expires = new Date(Date.now() + 7 * 86400000);
    expires.setMinutes(expires.getMinutes() - expires.getTimezoneOffset());
    form.elements.expires_at.value = expires.toISOString().slice(0, 16);
    form.elements.scope.value = finding?.path
      ? finding.path.includes("/") ? `${finding.path.slice(0, finding.path.lastIndexOf("/"))}.*` : finding.path
      : obligation?.claim_id || "";
  }
  showDialog("#decision-dialog");
}

function openEvidence(obligationId) {
  const form = $("#evidence-form");
  const obligation = (state.activeReview?.evidence_obligations || []).find((item) => item.id === obligationId);
  if (!obligation) return toast("Evidence obligation is no longer available");
  const draftKey = JSON.stringify([state.auth?.user?.id, state.activeReview.id, state.activeReview.target_ref, obligationId]);
  if (form.dataset.draftKey !== draftKey) form.reset();
  form.dataset.draftKey = draftKey;
  const draftAuthority = form.elements.authority.value;
  $("#evidence-error").textContent = "";
  form.elements.obligation_ids.value = obligation.id;
  form.elements.policy_id.value = state.manifest?.governing_policy || "";
  const authorities = state.manifest?.required_authorities || [];
  form.elements.authority.innerHTML = authorities.map((value) =>
    `<option value="${esc(value)}">${esc(value)}</option>`
  ).join("");
  if (authorities.includes(draftAuthority)) form.elements.authority.value = draftAuthority;
  const context = EvidenceModel.obligationContext(state.activeReview, obligation, state.activeProject?.claims || []);
  $("#evidence-obligation-label").textContent = context.title;
  $("#evidence-target-hint").textContent = context.statement;
  $("#evidence-target-hint").hidden = !context.statement;
  $("#evidence-verification-plan").innerHTML = context.plan.split(/\n+/).filter(Boolean).map(line=>`<li>${esc(line)}</li>`).join('');
  I18n.setText($("#evidence-provenance-hint"), obligation.required_provenance_prefix
    ? 'Cite a retrievable run, report, or trace. The source must start with {prefix}.'
    : 'Cite a retrievable run, report, or trace so another reviewer can verify the observation.',
    {prefix:obligation.required_provenance_prefix||''});
  showDialog("#evidence-dialog");
}

function openDsseAttestation(obligationId) {
  const form = $("#dsse-form");
  const obligation = (state.activeReview?.evidence_obligations || []).find((item) => item.id === obligationId);
  if (!obligation) return toast("Evidence obligation is no longer available");
  const draftKey = JSON.stringify([state.auth?.user?.id, state.activeReview.id, state.activeReview.target_ref, obligationId]);
  if (form.dataset.draftKey !== draftKey) form.reset();
  form.dataset.draftKey = draftKey;
  $("#dsse-error").textContent = "";
  form.elements.obligation_ids.value = obligation.id;
  $("#dsse-obligation-label").textContent = sentence(obligation.label);
  $("#dsse-contract").textContent = `Import a DSSE-wrapped SLSA verification summary (VSA) produced by ${obligation.required_verifier_id}. It must assert ${obligation.required_verified_level} and bind both subject and resource URI to target ${short(state.activeReview.target_ref)}. The server verifies its signature and policy before attaching it; import does not run the verifier.`;
  showDialog("#dsse-dialog");
}

function setTrustFieldMode(container, enabled) {
  container.classList.toggle("hidden", !enabled);
  container.querySelectorAll("input, select, textarea").forEach((field) => {
    field.disabled = !enabled;
  });
}

function updateRetroactiveConfirmation() {
  const form = $("#trust-form");
  const destructive = ["revoke", "rotate"].includes(form.elements.action.value)
    && form.elements.revocation_mode.value === "retroactive";
  $("#retroactive-confirm").classList.toggle("hidden", !destructive);
  form.elements.confirm_retroactive.required = destructive;
  if (!destructive) form.elements.confirm_retroactive.checked = false;
  const button = $("#trust-submit-button");
  button.classList.toggle("button-danger", destructive);
  button.classList.toggle("button-primary", !destructive);
}

function buildTrustRootFromForm(form) {
  const validFrom = new Date(form.elements.valid_from.value);
  const validUntil = form.elements.valid_until.value
    ? new Date(form.elements.valid_until.value)
    : null;
  if (Number.isNaN(validFrom.getTime()) || (validUntil && Number.isNaN(validUntil.getTime()))) {
    throw new Error("Choose a valid trust-root validity window");
  }
  return {
    key_id: form.elements.new_key_id.value,
    algorithm: "ed25519",
    public_key_base64: form.elements.new_public_key_base64.value.replace(/\s+/g, ""),
    verifier_id: form.elements.new_verifier_id.value,
    authority: form.elements.new_authority.value,
    resource_uri_prefix: form.elements.new_resource_uri_prefix.value,
    predicate_types: ["https://slsa.dev/verification_summary/v1"],
    valid_from: validFrom.toISOString(),
    valid_until: validUntil ? validUntil.toISOString() : null,
  };
}

function downloadTrustSigningPackage() {
  if (!trustSigningPackage) return;
  const keyId = String(trustSigningPackage.contract.key_id).replace(/[^a-zA-Z0-9._-]/g, "_");
  const blob = new Blob([`${JSON.stringify(trustSigningPackage, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `agentic-consensus-${keyId}-possession-signing-package.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function openTrustChange(action, keyId = "") {
  const project = state.activeProject;
  if (!project) return;
  const form = $("#trust-form");
  form.reset();
  $("#trust-error").textContent = "";
  $("#trust-proof-contract").textContent = "Build a template to see the required policy, verified level, target, and signing bytes.";
  $("#trust-signing-input").value = "";
  $("#copy-trust-signing-input").disabled = true;
  $("#trust-proof-download-button").disabled = true;
  trustSigningPackage = null;
  form.elements.action.value = action;
  form.elements.expected_project_version.value = project.version;
  form.elements.policy_id.value = project.policy_id;
  form.elements.authority.value = project.default_authority;
  form.elements.new_authority.value = project.default_authority;
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  form.elements.valid_from.value = now.toISOString().slice(0, 16);
  const needsExisting = action !== "add";
  const needsNew = action !== "revoke";
  setTrustFieldMode($("#trust-existing-fields"), needsExisting);
  setTrustFieldMode($("#trust-new-fields"), needsNew);
  const activeRoots = (project.attestation_trust_roots || []).filter((root) => root.status === "active");
  form.elements.key_id.innerHTML = activeRoots.map((root) =>
    `<option value="${esc(root.key_id)}" ${root.key_id === keyId ? "selected" : ""}>${esc(root.key_id)} · ${esc(root.verifier_id)}</option>`
  ).join("");
  form.elements.key_id.required = needsExisting;
  ["new_key_id", "new_authority", "new_public_key_base64", "new_verifier_id", "new_resource_uri_prefix", "new_key_proof_json"].forEach((name) => {
    form.elements[name].required = needsNew;
  });
  const labels = {
    add: ["Add attestation trust root", "The new key must prove possession with a signed VSA bound to the current governed head."],
    rotate: ["Rotate attestation trust root", "The old key remains in history. The replacement must prove possession before both changes commit atomically."],
    revoke: ["Revoke attestation trust root", "Prospective revocation blocks future imports. Retroactive revocation also marks prior evidence stale."],
  };
  $("#trust-title").textContent = labels[action][0];
  $("#trust-contract").textContent = `Version ${project.version} · ${labels[action][1]}`;
  updateRetroactiveConfirmation();
  showDialog("#trust-dialog");
}

async function summarizeReview(button) {
  if (!state.activeReview) return;
  setBusy(button, true, "Summarizing…");
  try {
    const result = await api(`/api/reviews/${state.activeReview.id}/summary`, { method: "POST" });
    toast(`Advisory summary refreshed · ${result.source}`);
    await selectReview(state.activeReview.id);
  } catch (error) {
    toast(error.message);
  } finally {
    if (button.isConnected) setBusy(button, false);
  }
}

async function loadDiff(button) {
  if (!state.activeReview) return;
  const output = $("#unified-diff");
  const note = $("#diff-note");
  if (button.dataset.loaded === "true") {
    const show = output.classList.contains("hidden");
    output.classList.toggle("hidden", !show);
    note.classList.toggle("hidden", !show && !state.diffTruncated);
    button.dataset.idleLabel = show ? "Hide unified diff" : "Show unified diff";
    button.textContent = button.dataset.idleLabel;
    button.setAttribute("aria-expanded", String(show));
    button.focus({ preventScroll: true });
    return;
  }
  setBusy(button, true, "Loading diff…");
  try {
    const text = await ensureDiffLoaded();
    if (text === null) throw new Error(state.diffError || "The diff could not be loaded.");
    output.textContent = text || "No textual diff.";
    output.classList.remove("hidden");
    note.textContent = state.diffTruncated ? "Diff is truncated at the safe display limit." : `${state.diffCharacters} characters loaded.`;
    note.classList.remove("hidden");
    button.dataset.loaded = "true";
    button.dataset.idleLabel = "Hide unified diff";
    button.dataset.idleHtml = "Hide unified diff";
    button.setAttribute("aria-expanded", "true");
  } catch (error) {
    toast(error.message);
  } finally {
    if (button.isConnected) {
      setBusy(button, false);
      button.focus({ preventScroll: true });
    }
  }
}

function openTestConfiguration() {
  if (!state.activeProject || !state.activeReview) return;
  const form = $("#test-command-form");
  const command = state.activeProject.test_command || [];
  const configured = command.length > 0;
  form.reset();
  $("#test-command-error").textContent = "";
  form.elements.test_command.value = command.join(" ");
  form.elements.test_command.readOnly = configured;
  $("#test-command-dialog-title").textContent = configured
    ? "Run configured tests"
    : "Configure this test run";
  $("#test-command-hint").textContent = configured
    ? "This project command is fixed by intake and cannot be replaced during a review."
    : "This one-time command is recorded in the review audit trail and does not change project configuration.";
  showDialog("#test-command-dialog");
}

async function rerunReviewTests(event) {
  event.preventDefault();
  if (!state.activeReview) return;
  const form = event.currentTarget;
  const button = event.submitter;
  $("#test-command-error").textContent = "";
  let testCommand;
  try {
    testCommand = parseCommand(form.elements.test_command.value);
  } catch (error) {
    $("#test-command-error").textContent = error.message;
    form.elements.test_command.focus();
    return;
  }
  if (!testCommand.length) {
    $("#test-command-error").textContent = "Enter the command that runs this repository’s test suite.";
    form.elements.test_command.focus();
    return;
  }
  setBusy(button, true, "Running tests…");
  let operation;
  try {
    operation = requireReviewOperation(form);
    const { reviewId } = operation;
    await api(`/api/reviews/${reviewId}/tests`, {
      method: "POST",
      body: JSON.stringify({ test_command: testCommand }),
    });
    await completeReviewOperation(form, operation, "Test evidence refreshed for this review");
  } catch (error) {
    if (!operation || reviewOperations.get(form) === operation) $("#test-command-error").textContent = error.message;
  } finally {
    if (button.isConnected) setBusy(button, false);
  }
}

async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
    return;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    if (!copied) throw new Error("browser denied clipboard access");
  }
}

async function copyReviewLink(event) {
  const button = event.currentTarget;
  try {
    await copyText(window.location.href);
    setIconButtonFeedback(button, {
      label: "Review link copied",
      tooltip: "Copied",
      iconName: "check-circle",
    });
    toast("Reviewer link copied");
  } catch {
    toast("Copy failed; use the current address bar URL");
  }
}

async function copyReviewBrief(event) {
  if (!state.activeReview || !state.manifest) return;
  const review = state.activeReview;
  const brief = DecisionModel.handoffBrief({...review,findings:review.findings.map(finding=>({...finding,status:effectiveFindingStatus(review,finding)}))},state.manifest,state.activeProject,window.location.href);
  try {
    await copyText(brief);
    event?.currentTarget?.closest("details")?.removeAttribute("open");
    toast("Review brief copied — ready to share with the proposer");
  } catch {
    toast("Copy failed; export the review JSON instead");
  }
}

async function refreshCurrentProject(reviewId = state.activeReview?.id, operation = null) {
  if (operation && !reviewOperationIsCurrent(operation)) return;
  if (reviewId && reviewId !== state.activeReview?.id) return;
  const projectId = state.activeProject?.id;
  const selectionVersion = state.selectionVersion;
  const reviewVersion = state.reviewSelectionVersion;
  const stillCurrent = () => projectId === state.activeProject?.id
    && selectionVersion === state.selectionVersion && reviewVersion === state.reviewSelectionVersion;
  const projects = await api("/api/projects");
  if (!stillCurrent()) return;
  state.projects = projects;
  state.activeProject = projects.find((project) => project.id === projectId) || null;
  renderProjects();
  if (!state.activeProject) {
    state.reviews = [];
    state.projectEvents = [];
    state.activeReview = null;
    state.manifest = null;
    renderWorkspace();
    return;
  }
  // A background refresh keeps the existing tree usable while reads are pending.
  const [reviews, projectEvents, projectTree] = await Promise.all([
    api(`/api/projects/${projectId}/reviews`),
    api(`/api/projects/${projectId}/events`),
    loadProjectTree(projectId).catch((error) => ({ error: error.message, entries: [] })),
  ]);
  if (!stillCurrent()) return;
  state.reviews = reviews;
  state.projectEvents = projectEvents;
  state.projectTree = projectTree;
  state.projectTreeLoading = false;
  if (state.viewMode === "canvas") $("#project-canvas")?.removeAttribute("data-signature");
  renderWorkspace();
  if (reviewId) await selectReview(reviewId);
}

const intentDrafts = new Map();
let intentDraft = null;
let intentDraftOwner = null;

function captureIntentDraft() {
  if (!intentDraft) return;
  const form = $("#intent-form");
  intentDraft.request = form.elements.request.value;
  intentDraft.context = form.elements.context.value;
  intentDraft.base_ref = form.elements.base_ref.value;
  form.querySelectorAll("[data-editor-index]").forEach((editor) => {
    const index = Number(editor.dataset.editorIndex);
    const values = Object.fromEntries([...editor.querySelectorAll("[data-field]")].map((input) => [input.dataset.field, input.value]));
    intentDraft.candidates[index] = IntentModel.editCandidate(intentDraft.candidates[index], values);
  });
}

function renderIntentEditors() {
  $("#intent-candidate-editors").innerHTML = intentDraft.candidates.map((candidate, index) => {
    const delta = candidate.structural_delta;
    const input = (field, label, value, max, placeholder = "") => `<label>${label}<input data-field="${field}" name="candidate_${index}_${field}" value="${esc(value)}" required maxlength="${max}" placeholder="${esc(placeholder)}"${field === "path" ? ' list="intent-python-files"' : ""}></label>`;
    return `<fieldset class="intent-candidate-editor" data-editor-index="${index}"><legend>Interpretation ${index + 1}</legend>${input("title", "Name the approach", candidate.title, 240, index ? "Use a compatibility adapter" : "Use the reviewed module")}<label><span data-i18n=Why%20this%20approach%3F>Why this approach?</span><textarea data-field="summary" name="candidate_${index}_summary" rows="2" required maxlength="2000">${esc(candidate.summary)}</textarea></label>${input("path", "Python file", delta.path, 1000, "checkout.py")}<div class="form-pair">${input("from_module", "Current import", delta.from_module, 500, "legacy.billing")}${input("to_module", "Replace with", delta.to_module, 500, "billing.pricing")}</div><label><span data-i18n=Open%20questions%20(optional)>Open questions (optional)</span><textarea data-field="uncertainties" name="candidate_${index}_uncertainties" rows="3" placeholder="One question per line. Leave blank only if this interpretation has no unresolved uncertainty.">${esc(candidate.uncertainties.join("\n"))}</textarea></label><small class="intent-source">Source: ${esc(candidate.provenance)}</small></fieldset>`;
  }).join("");
  $("#intent-python-files").innerHTML = (state.projectTree?.entries || []).filter((entry) => entry.kind === "file" && entry.path.endsWith(".py")).map((entry) => `<option value="${esc(entry.path)}"></option>`).join("");
}

function setIntentComposerStep(step, focus = true) {
  intentDraft.step = step;
  $("#intent-dialog").dataset.step = step;
  $("#intent-request-step").hidden = step !== "request";
  $("#intent-candidates-step").hidden = step !== "candidates";
  $("#intent-composer-back").hidden = step === "request";
  $("#intent-ai-suggest-button").hidden = step !== "request";
  $("#intent-composer-submit").textContent = step === "request" ? (intentDraft.candidates.length ? "Review alternatives" : "Write alternatives") : "Record interpretations";
  $("#intent-dialog-title").textContent = step === "request" ? "What should change?" : "Check the interpretations";
  $("#intent-request-recap").textContent = intentDraft.request;
  $("#intent-base-label").textContent = short(intentDraft.base_ref);
  $("#intent-error").textContent = "";
  $(".intent-composer-body").scrollTop = 0;
  if (focus) window.requestAnimationFrame(() => $(step === "request" ? '#intent-form [name="request"]' : '#intent-candidate-editors input')?.focus());
}

function validateIntentStep(step) {
  const section = $(step === "request" ? "#intent-request-step" : "#intent-candidates-step");
  for (const input of section.querySelectorAll("input, textarea")) {
    input.setCustomValidity("");
    if (input.required && !input.value.trim()) input.setCustomValidity("Add a value for this field.");
    if (!input.checkValidity()) {
      const details = input.closest("details");
      if (details) details.open = true;
      input.reportValidity();
      return false;
    }
  }
  return true;
}

function openIntentComposer() {
  if (!state.activeProject) return openProject();
  const project = state.activeProject;
  intentDraft = intentDrafts.get(project.id);
  if (!intentDraft) {
    intentDraft = {projectId: project.id, ownerId: state.auth?.user?.id, request: "", context: "", base_ref: project.head_ref, candidates: [], step: "request", version: 0, busy: false, aiStatus: ""};
    intentDrafts.set(project.id, intentDraft);
  }
  const form = $("#intent-form");
  for (const field of ["request", "context", "base_ref"]) form.elements[field].value = intentDraft[field];
  form.querySelectorAll("input, textarea").forEach((input) => input.setCustomValidity(""));
  $("#intent-project-label").textContent = project.name;
  const noPython=IntentModel.repositoryScope(state.projectTree,state.projectTreeLoading).state==='no_python';
  $("#intent-composer-scope").textContent=noPython
    ? "This project snapshot has no Python files. This workflow needs a Python import change and at least two alternatives. Choose an appropriate base revision, or use Reviews for existing code changes."
    : "This workflow compares Python import replacements. Each request needs at least two alternatives.";
  $("#intent-ai-status").textContent = intentDraft.aiStatus || (state.runtime?.enabled && state.runtime?.configured ? "Draft with AI sends the request and repository context to your configured provider. You review the result before recording it." : "AI is not configured. The interpreter can still offer local rule-based drafts, or you can write alternatives yourself.");
  renderIntentEditors();
  showDialog("#intent-dialog");
  setIntentComposerStep(intentDraft.step);
  setBusy($("#intent-ai-suggest-button"), intentDraft.busy, "Interpreting…");
  setIntentSaving(Boolean(intentDraft.saving));
}

function setIntentSaving(saving) {
  $("#intent-form .intent-composer-body").inert = saving;
  $("#intent-composer-back").disabled = saving;
  const button = $("#intent-composer-submit");
  if (saving && button.getAttribute("aria-busy") !== "true") setBusy(button, true, "Recording…");
  if (!saving && button.getAttribute("aria-busy") === "true") setBusy(button, false);
  $("#intent-draft-note").textContent = saving ? "Recording this version. You can close this panel; saving will continue." : "Draft stays here while this page is open.";
}

async function suggestIntentCandidates(event) {
  if (!intentDraft || intentDraft.busy || intentDraft.saving || !validateIntentStep("request")) return;
  captureIntentDraft();
  if (intentDraft.candidates.length && !window.confirm("Replace the current alternatives with new drafts? Your request and context will stay.")) return;
  const draft = intentDraft;
  const version = draft.version;
  const button = event.currentTarget;
  const status = $("#intent-ai-status");
  const {request, context, base_ref} = draft;
  draft.busy = true;
  setBusy(button, true, "Interpreting…");
  status.textContent = "Drafting alternatives. You can continue editing; a late result will not overwrite your changes.";
  try {
    const run = await api(`/api/projects/${draft.projectId}/ai/interpret-intent`, {
      method: "POST",
      body: JSON.stringify({ request, context, base_ref }),
    });
    if (draft.ownerId === state.auth?.user?.id && state.activeProject?.id === draft.projectId) upsertAIRun(run);
    if (intentDraft !== draft || draft.version !== version || state.activeProject?.id !== draft.projectId || !$("#intent-dialog").open) {
      draft.aiStatus = "Drafting finished after the request changed or closed. Your edits were kept; ask again for fresh alternatives.";
    } else {
      draft.candidates = IntentModel.fromAIRun(run);
      draft.aiStatus = `Drafted by ${run.source}. Review every alternative before recording it.`;
      renderIntentEditors();
      setIntentComposerStep("candidates");
    }
  } catch (error) {
    draft.aiStatus = `${error.message} Your input is kept. Retry drafting or write alternatives yourself.`;
  } finally {
    draft.busy = false;
    if (intentDraft === draft) {
      status.textContent = draft.aiStatus;
      setBusy(button, false);
    }
  }
}

$("#intent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!intentDraft || intentDraft.projectId !== state.activeProject?.id) return;
  const form = event.currentTarget;
  const button = $("#intent-composer-submit");
  if (button.disabled) return;
  if (!validateIntentStep(intentDraft.step)) return;
  captureIntentDraft();
  if (intentDraft.step === "request") {
    intentDraft.version += 1;
    if (!intentDraft.candidates.length) {
      intentDraft.candidates = [0, 1].map((index) => ({title: "", summary: "", structural_delta: {kind: "python_import_substitution", path: "", from_module: "", to_module: ""}, uncertainties: [], provenance: `human-authored/interpretation-${index + 1}`, confidence: null}));
      renderIntentEditors();
    }
    setIntentComposerStep("candidates");
    return;
  }
  const draft = intentDraft;
  $("#intent-error").textContent = "";
  draft.saving = true;
  setIntentSaving(true);
  try {
    for (const [index, candidate] of draft.candidates.entries()) {
      if (candidate.uncertainties.length > 20) throw new Error(`Interpretation ${index + 1}: keep at most 20 open questions, one per line.`);
      if (candidate.structural_delta.from_module === candidate.structural_delta.to_module) throw new Error(`Interpretation ${index + 1}: the replacement must differ from the current import.`);
    }
    const projectId = draft.projectId;
    const intent = await api(`/api/projects/${projectId}/intents`, {
      method: "POST",
      body: JSON.stringify({
        request: draft.request,
        context: draft.context,
        base_ref: draft.base_ref,
        candidates: draft.candidates,
      }),
    });
    replaceIntent(intent);
    if (intentDrafts.get(draft.projectId) === draft) intentDrafts.delete(draft.projectId);
    if (intentDraft === draft) {
      $("#intent-dialog").close();
      intentDraft = null;
      form.reset();
    }
    toast("Interpretations recorded. Clarify open questions, then select a proposal.");
  } catch (error) {
    if (intentDraft === draft) $("#intent-error").textContent = `${error.message} Your draft is kept.`;
  } finally {
    draft.saving = false;
    if (intentDraft === draft || !intentDraft) setIntentSaving(false);
  }
});

$("#clarification-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#clarification-error").textContent = "";
  setBusy(button, true, "Applying…");
  try {
    const data = Object.fromEntries(new FormData(form));
    const intentId = data.intent_id;
    if (!clarificationSnapshot || clarificationSnapshot.id !== intentId) throw new Error("The intent changed; reopen clarification");
    const payload = IntentModel.clarificationPayload(clarificationSnapshot, clarificationValues());
    const updated = await api(`/api/intents/${intentId}/clarifications`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    replaceIntent(updated);
    form.reset();
    $("#clarification-dialog").close();
    toast("Clarification lineage recorded");
  } catch (error) {
    $("#clarification-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

$("#selection-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#selection-error").textContent = "";
  setBusy(button, true, "Selecting…");
  try {
    const data = Object.fromEntries(new FormData(form));
    await selectIntentCandidate(
      data.intent_id,
      data.candidate_id,
      data.reason,
      data.expected_revision,
    );
    form.reset();
    $("#selection-dialog").close();
    toast("Structural proposal selected");
  } catch (error) {
    $("#selection-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

$("#project-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!$("#project-dialog").open || document.body.classList.contains("auth-locked")) return;
  if (intakeIsOwned(intakeOperation) && ["pending", "saved", "uncertain"].includes(intakeOperation.status)) return;
  const form = event.currentTarget;
  const repositorySource = state.github.source;
  let operation = null;
  $("#project-error").textContent = "";
  try {
    const data = Object.fromEntries(new FormData(form));
    const modules = data.forbidden_modules.split(",").map((value) => value.trim()).filter(Boolean);
    const obligations = data.evidence_obligations.split(",").map((value) => value.trim()).filter(Boolean);
    const signedObligationLabel = data.signed_obligation_label.trim();
    const defaultAuthority = data.default_authority.trim();
    const authorizedActors = data.authorized_actors.split(",").map((value) => value.trim()).filter(Boolean);
    if (!authorizedActors.length) throw new Error("Add at least one authorized decision identity");
    const claimAuthority = data.claim_authority.trim() || defaultAuthority;
    const signedFields = {
      key_id: data.attestation_key_id.trim(),
      public_key_base64: data.attestation_public_key_base64.replace(/\s+/g, ""),
      verifier_id: data.attestation_verifier_id.trim(),
      resource_uri_prefix: data.attestation_resource_uri_prefix.trim(),
      required_level: data.attestation_required_level.trim(),
    };
    if (signedObligationLabel && !modules.length) throw new Error("Add a structural claim before requiring signed evidence");
    if (signedObligationLabel && Object.values(signedFields).some((value) => !value)) {
      throw new Error("Complete every signed CI evidence field");
    }
    if (!signedObligationLabel && Object.values(signedFields).some((value, index) => index !== 4 && value)) {
      throw new Error("Add a signed obligation label or clear the signed CI evidence fields");
    }
    if (signedObligationLabel) obligations.push({
      label: signedObligationLabel,
      verification: "dsse_ed25519",
      required_verifier_id: signedFields.verifier_id,
      required_verified_level: signedFields.required_level,
      required_provenance_prefix: "dsse-ed25519:",
    });
    const claims = modules.length ? [{
      id: data.claim_id || "architecture.boundary",
      title: data.claim_title || "Declared architecture boundary",
      scope: data.claim_scope || "",
      authority: claimAuthority,
      forbidden_modules: modules,
      evidence_obligations: obligations,
    }] : [];
    const payload = {
      name: data.name,
      test_command: parseCommand(data.test_command),
      claims,
      policy_id: data.policy_id,
      default_authority: defaultAuthority,
      authority_grants: [...new Set([defaultAuthority, ...(modules.length ? [claimAuthority] : [])])].map((authority) => ({
        authority,
        actors: authorizedActors,
        actions: ["commit", "waive", "rebase", "reject", "rollback", "attest", "manage_trust"],
      })),
      attestation_trust_roots: signedObligationLabel ? [{
        key_id: signedFields.key_id,
        algorithm: "ed25519",
        public_key_base64: signedFields.public_key_base64,
        verifier_id: signedFields.verifier_id,
        authority: claimAuthority,
        resource_uri_prefix: signedFields.resource_uri_prefix,
        predicate_types: ["https://slsa.dev/verification_summary/v1"],
      }] : [],
    };
    let project;
    let githubReview = null;
    if (repositorySource === "github") {
      const selected = state.github.repositories.find(
        (repository) => repository.id === state.github.selectedRepositoryId
      );
      if (!selected) throw new Error("Select a GitHub repository to import");
      const selectedPull = state.github.pullRequests.find(
        (pullRequest) => pullRequest.number === state.github.selectedPullNumber
      );
      if (!selectedPull) throw new Error("Select an open pull request to analyze");
      if (selectedPull.draft) throw new Error("Mark this draft ready on GitHub before analysis.");
      operation = beginIntakeOperation(repositorySource, {
        label: `${selected.full_name} · PR #${selectedPull.number}`, title: selectedPull.title,
        repositoryId: selected.id, installationId: selected.installation_id,
        pullUrl: selectedPull.html_url, baseRef: selectedPull.base_sha, targetRef: selectedPull.head_sha,
      });
      const result = await api(`/api/github/repositories/${selected.id}/pulls/${selectedPull.number}/analyze`, {
        method: "POST",
        body: JSON.stringify({ ...payload, installation_id: selected.installation_id }),
      });
      project = result.project;
      githubReview = result.review;
    } else {
      operation = beginIntakeOperation(repositorySource, { label: data.repo_path.trim(), title: data.name.trim(), repoPath: data.repo_path.trim() });
      project = await api("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          ...payload,
          repo_path: data.repo_path,
          repo_label: data.repo_label || null,
          head_ref: data.head_ref,
        }),
      });
    }
    if (!intakeIsOwned(operation)) return;
    rememberIntakeResult(operation, { project, review: githubReview });
    if (intakeViewIsCurrent(operation) && operation.selectionVersion === state.selectionVersion && operation.startedUrl === location.href) await openIntakeResult();
  } catch (error) {
    if (operation) {
      if (!intakeIsOwned(operation)) return;
      const uncertain = !error.status || error.status >= 500;
      operation.status = uncertain ? "uncertain" : "failed";
      operation.error = uncertain ? "The request may have finished, but its response was interrupted. Check the workspace before submitting again." : error.message;
      renderIntakeOperation();
    } else {
      if (intakeIsOwned(intakeOperation) && intakeOperation.status === "failed") intakeOperation.error = error.message;
      $("#project-error").textContent = error.message;
    }
    if ($("#project-dialog").open) $("#project-error").focus();
  }
});

$("#review-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const context = comparisonContext;
  if (!comparisonIsCurrent(context)) return;
  const draft = context.draft;
  if (draft.pending || draft.review) return;
  rememberComparisonInput();
  const data = Object.fromEntries(Object.entries(draft.fields).map(([key,value]) => [key,value.trim()]));
  if (draft.predecessor ? !data.target_ref : Object.values(data).some(value => !value)) {
    draft.error = draft.predecessor ? "Enter the revised target before analyzing." : "Enter the target, change intent, baseline and proposer before analyzing.";
    renderComparisonStatus();
    $("#review-error").focus();
    return;
  }
  draft.pending = true;
  draft.error = "";
  renderComparisonStatus();
  try {
    localStorage.setItem("consensus-proposer", data.proposer);
    const review = await api(draft.predecessor?`/api/reviews/${draft.predecessor.id}/revisions`:`/api/projects/${draft.projectId}/reviews`, { method: "POST", body: JSON.stringify(draft.predecessor?{target_ref:data.target_ref,expected_revision:draft.predecessor.revision}:data) });
    if (!comparisonIsOwned(draft)) return;
    draft.review = review;
    if (state.activeProject?.id === draft.projectId) {
      state.reviews = [review, ...state.reviews.filter(item => item.id !== review.id)];
      renderWorkspace();
    }
    if (comparisonIsCurrent(context)) {
      $("#review-dialog").close();
      const opened = await selectReview(review.id, context.selectionVersion);
      if (!comparisonIsOwned(draft)) return;
      if (opened) comparisonDrafts.delete(draft.storageKey||draft.projectId);
      else draft.error = "The review was created, but its details could not be loaded. Open the saved review to try again.";
    } else if (comparisonContext?.draft === draft && $("#review-dialog").open) {
      renderComparisonStatus();
      $("#review-created-receipt").focus();
    } else toast(`Review created in ${draft.projectName}: ${data.intent_summary}`);
  } catch (error) {
    if (!comparisonIsOwned(draft)) return;
    draft.error = error?.name === "TypeError"
      ? "The connection was interrupted. Your draft is kept. Check Reviews before trying again: creation may have completed."
      : error.message;
  } finally {
    draft.pending = false;
    if (comparisonContext?.draft === draft && comparisonIsOwned(draft)) {
      renderComparisonStatus();
      if (draft.error && $("#review-dialog").open) $("#review-error").focus();
    }
  }
});

$("#test-command-form").addEventListener("submit", rerunReviewTests);

$("#decision-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#decision-error").textContent = "";
  setBusy(button, true, "Recording…");
  let operation;
  try {
    operation = requireReviewOperation(form);
    const { reviewId } = operation;
    const data = Object.fromEntries(new FormData(form));
    const payload = {
      action: data.action,
      actor: state.auth.user.actor,
      authority: data.authority,
      policy_id: data.policy_id,
      reason: data.reason || null,
      finding_ids: data.finding_ids ? [data.finding_ids] : [],
      obligation_ids: data.obligation_ids ? [data.obligation_ids] : [],
    };
    if (data.action === "waive") {
      const expiresAt = new Date(data.expires_at);
      if (!data.expires_at || Number.isNaN(expiresAt.getTime())) throw new Error("Choose a valid waiver expiry date");
      payload.scope = data.scope;
      payload.expires_at = expiresAt.toISOString();
    }
    await api(`/api/reviews/${reviewId}/decisions`, { method: "POST", body: JSON.stringify(payload) });
    await completeReviewOperation(form, operation, ({
      commit: "Approval recorded",
      waive: "Bounded waiver recorded",
      rebase: "Update requested",
      reject: "Rejection recorded",
      rollback: "Approval rolled back",
    })[data.action] || `${sentence(data.action)} recorded`);
  } catch (error) {
    if (!operation || reviewOperations.get(form) === operation) $("#decision-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

$("#evidence-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#evidence-error").textContent = "";
  setBusy(button, true, "Attaching…");
  let operation;
  try {
    operation = requireReviewOperation(form);
    const { reviewId } = operation;
    const data = Object.fromEntries(new FormData(form));
    const payload = {
      actor: state.auth.user.actor,
      authority: data.authority,
      policy_id: data.policy_id,
      obligation_ids: [data.obligation_ids],
      summary: data.summary,
      provenance: data.provenance,
    };
    await api(`/api/reviews/${reviewId}/evidence`, { method: "POST", body: JSON.stringify(payload) });
    await completeReviewOperation(form, operation, "Evidence attached to the target revision");
  } catch (error) {
    if (!operation || reviewOperations.get(form) === operation) $("#evidence-error").textContent = evidenceErrorMessage(error);
  } finally {
    setBusy(button, false);
  }
});

$("#dsse-form").elements.envelope_file.addEventListener("change", async (event) => {
  const file = event.currentTarget.files?.[0];
  if (!file) return;
  $("#dsse-error").textContent = "";
  if (file.size > 2_700_000) {
    event.currentTarget.value = "";
    $("#dsse-error").textContent = "DSSE envelope file exceeds the 2.7 MB intake limit";
    return;
  }
  try {
    $("#dsse-form").elements.envelope_json.value = await file.text();
  } catch {
    $("#dsse-error").textContent = "Could not read the selected envelope file";
  }
});

$("#dsse-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#dsse-error").textContent = "";
  setBusy(button, true, "Verifying…");
  let operation;
  try {
    operation = requireReviewOperation(form);
    const { reviewId } = operation;
    let envelope;
    try {
      envelope = JSON.parse(form.elements.envelope_json.value);
    } catch {
      throw new Error("DSSE envelope must be valid JSON");
    }
    if (!envelope || Array.isArray(envelope) || typeof envelope !== "object") {
      throw new Error("DSSE envelope must be a JSON object");
    }
    await api(`/api/reviews/${reviewId}/attestations/dsse`, {
      method: "POST",
      body: JSON.stringify({ obligation_ids: [form.elements.obligation_ids.value], envelope }),
    });
    await completeReviewOperation(form, operation, "Signed VSA verified and attached");
  } catch (error) {
    if (!operation || reviewOperations.get(form) === operation) $("#dsse-error").textContent = evidenceErrorMessage(error);
  } finally {
    setBusy(button, false);
  }
});

$("#trust-form").elements.new_key_proof_file.addEventListener("change", async (event) => {
  const file = event.currentTarget.files?.[0];
  if (!file) return;
  $("#trust-error").textContent = "";
  if (file.size > 2_700_000) {
    event.currentTarget.value = "";
    $("#trust-error").textContent = "Signed proof file exceeds the 2.7 MB intake limit";
    return;
  }
  try {
    $("#trust-form").elements.new_key_proof_json.value = await file.text();
  } catch {
    $("#trust-error").textContent = "Could not read the selected proof file";
  }
});

$("#trust-form").elements.revocation_mode.addEventListener("change", updateRetroactiveConfirmation);

$("#trust-proof-template-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const form = $("#trust-form");
  $("#trust-error").textContent = "";
  setBusy(button, true, "Building…");
  try {
    const newRoot = buildTrustRootFromForm(form);
    const result = await api(
      `/api/projects/${state.activeProject.id}/trust-roots/possession-template`,
      {
        method: "POST",
        body: JSON.stringify({ new_root: newRoot }),
      },
    );
    form.elements.new_key_proof_json.value = JSON.stringify(result.envelope, null, 2);
    trustSigningPackage = result;
    $("#trust-signing-input").value = result.signing_input_base64;
    $("#copy-trust-signing-input").disabled = false;
    $("#trust-proof-download-button").disabled = false;
    $("#trust-proof-contract").textContent = `Version ${result.contract.project_version} · ${result.contract.policy_uri} · ${result.contract.required_verified_level} · ${result.contract.resource_uri}`;
    toast("Signing template built; replace the signature placeholder after external signing");
  } catch (error) {
    $("#trust-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

$("#copy-trust-signing-input").addEventListener("click", async () => {
  try {
    await copyText($("#trust-signing-input").value);
    toast("Base64 signing input copied");
  } catch {
    toast("Copy failed; select the signing input manually");
  }
});

$("#trust-proof-download-button").addEventListener("click", () => {
  downloadTrustSigningPackage();
  toast("Offline signing package downloaded");
});

$("#trust-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#trust-error").textContent = "";
  setBusy(button, true, "Applying…");
  try {
    const action = form.elements.action.value;
    const payload = {
      action,
      actor: state.auth.user.actor,
      authority: form.elements.authority.value,
      policy_id: form.elements.policy_id.value,
      reason: form.elements.reason.value,
      expected_project_version: Number(form.elements.expected_project_version.value),
    };
    if (action !== "add") {
      payload.key_id = form.elements.key_id.value;
      payload.revocation_mode = form.elements.revocation_mode.value;
      if (payload.revocation_mode === "retroactive" && !form.elements.confirm_retroactive.checked) {
        throw new Error("Confirm the retroactive invalidation of prior evidence");
      }
      payload.confirm_retroactive = payload.revocation_mode === "retroactive"
        && form.elements.confirm_retroactive.checked;
    }
    if (action !== "revoke") {
      let proof;
      try {
        proof = JSON.parse(form.elements.new_key_proof_json.value);
      } catch {
        throw new Error("New-key possession proof must be valid JSON");
      }
      if (!proof || Array.isArray(proof) || typeof proof !== "object") {
        throw new Error("New-key possession proof must be a JSON object");
      }
      payload.new_root = buildTrustRootFromForm(form);
      payload.new_key_proof = proof;
    }
    const projectId = state.activeProject.id;
    const reviewId = state.activeReview?.id;
    await api(`/api/projects/${projectId}/trust-roots/changes`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("#trust-dialog").close();
    form.reset();
    await refreshCurrentProject(reviewId);
    toast(`${title(action)} trust transition recorded`);
  } catch (error) {
    $("#trust-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

function authEventDetails(event) {
  const details = [
    new Date(event.created_at).toLocaleString(),
    event.payload.target_actor,
    event.payload.target_role,
  ];
  if (event.payload.operator) details.push(`host operator ${event.payload.operator}`);
  if (event.payload.revoked_sessions) {
    details.push(`${event.payload.revoked_sessions} session(s) revoked`);
  }
  if (event.payload.reason) details.push(event.payload.reason);
  return details.map((detail) => esc(detail)).join(" · ");
}

function renderUsers() {
  const currentUserId = state.auth?.user?.id;
  $("#user-list").innerHTML = state.users.map((user) => `
    <article class="user-card ${user.password_change_required ? "password-required" : ""}" data-disabled="${user.disabled}">
      <div><strong>${esc(user.actor)}</strong><span>${esc(user.username)} · ${esc(user.role)}</span></div>
      <div class="user-actions">
        <small>${user.disabled ? "disabled" : user.password_change_required ? "password change required" : "active"}</small>
        ${user.id === currentUserId || user.disabled ? "" : `<button type="button" class="button button-small user-reset-password" data-user-id="${esc(user.id)}">Reset password</button>`}
        ${user.id === currentUserId ? "" : `<button type="button" class="button button-small user-toggle" data-user-id="${esc(user.id)}" data-disabled="${user.disabled}">${user.disabled ? "Enable" : "Disable"}</button>`}
      </div>
    </article>`).join("");
  document.querySelectorAll(".user-reset-password").forEach((button) => {
    button.addEventListener("click", () => {
      const user = state.users.find((item) => item.id === button.dataset.userId);
      if (!user) return;
      state.resetUser = user;
      $("#reset-password-form").reset();
      $("#reset-password-error").textContent = "";
      $("#reset-password-actor").textContent = user.actor;
      $("#users-dialog").close();
      showDialog("#reset-password-dialog");
    });
  });
  document.querySelectorAll(".user-toggle").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      $("#user-error").textContent = "";
      try {
        await api(`/api/users/${button.dataset.userId}`, {
          method: "PATCH",
          body: JSON.stringify({ disabled: button.dataset.disabled !== "true" }),
        });
        await loadUsers();
      } catch (error) {
        $("#user-error").textContent = error.message;
        button.disabled = false;
      }
    });
  });
  $("#auth-event-list").innerHTML = state.authEvents.slice().reverse().map((event) => `
    <div class="auth-event">
      <strong>${esc(title(event.action))}</strong><span>${esc(event.actor)}</span>
      <small>${authEventDetails(event)}</small>
    </div>`).join("");
}

async function loadUsers() {
  [state.users, state.authEvents] = await Promise.all([
    api("/api/users"),
    api("/api/auth/events"),
  ]);
  renderUsers();
}

async function loadControlPlane() {
  const [health, runtime, projects] = await Promise.all([
    api("/api/health"), api("/api/runtime"), api("/api/projects"),
  ]);
  $("#health-label").textContent = `${plural(health.projects, "PROJECT")} · ${plural(health.reviews, "REVIEW")}`;
  state.runtime = runtime;
  const systemStatus = $("#health-label").closest(".system-status");
  setControlTooltip(systemStatus, runtimeLabel(runtime));
  systemStatus.setAttribute("aria-label", `${$("#health-label").textContent} · ${runtimeLabel(runtime)}`);
  state.projects = projects;
  renderProjects();
  const requestedProject = new URLSearchParams(window.location.search).get("project");
  const selected = projects.find((item) => item.id === requestedProject) || projects[0];
  if (selected) await selectProject(selected.id);
  else renderWorkspace();
  workspaceNavigationReady = true;
}

window.addEventListener("popstate", async () => {
  if (!state.auth?.authenticated || document.body.classList.contains("auth-locked")) return;
  const params = new URLSearchParams(window.location.search);
  const projectId = params.get("project") || state.activeProject?.id;
  restoringWorkspaceHistory = true;
  try {
    if (projectId !== state.activeProject?.id) await selectProject(projectId);
    else if (params.get("review")) await selectReview(params.get("review"));
    else setProjectView(params.get("view") || "canvas");
    document.querySelector('[data-view-tab][aria-current="page"]')?.focus({ preventScroll: true });
  } finally {
    restoringWorkspaceHistory = false;
  }
});

async function completeAuthentication(auth) {
  window.PaperDemo.configure(auth.csrf_token);
  renderAuthenticatedUser(auth);
  $("#bootstrap-form").reset();
  $("#login-form").reset();
  $("#signup-form").reset();
  if (auth.user.password_change_required) {
    showForcedPasswordGate(auth);
    return;
  }
  $("#forced-password-form").reset();
  await loadControlPlane();
  const githubResult = new URLSearchParams(window.location.search).get("github");
  const searchParams = new URLSearchParams(window.location.search);
  const githubInstallationReturn = Boolean(searchParams.get("installation_id"))
    && searchParams.get("setup_action") === "install";
  if (["connected", "installed"].includes(githubResult) || githubInstallationReturn) {
    const url = new URL(window.location.href);
    url.searchParams.delete("github");
    url.searchParams.delete("installation_id");
    url.searchParams.delete("setup_action");
    window.history.replaceState({}, "", url);
    await openProject("github");
    toast(githubResult === "installed" || githubInstallationReturn
      ? "Repository access updated. Select a pull request to analyze."
      : "GitHub connected. Select a pull request to analyze.");
  }
}

function passwordChangePayload(form) {
  const currentPassword = form.elements.current_password.value;
  const newPassword = form.elements.new_password.value;
  const confirmation = form.elements.confirm_password.value;
  if (newPassword !== confirmation) throw new Error("New password confirmation does not match");
  return { current_password: currentPassword, new_password: newPassword };
}

async function submitPasswordChange(form, errorNode, button, dialog = null) {
  errorNode.textContent = "";
  setBusy(button, true, "Changing…");
  try {
    const auth = await api("/api/auth/password", {
      method: "POST",
      body: JSON.stringify(passwordChangePayload(form)),
    });
    form.reset();
    if (dialog?.open) dialog.close();
    await completeAuthentication(auth);
    toast("Password changed; other sessions signed out");
  } catch (error) {
    errorNode.textContent = error.message;
  } finally {
    setBusy(button, false);
  }
}

$("#bootstrap-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#bootstrap-error").textContent = "";
  setBusy(button, true, "Creating…");
  try {
    const data = Object.fromEntries(new FormData(form));
    if (data.password !== data.confirm_password) {
      throw new Error("Password confirmation does not match");
    }
    delete data.confirm_password;
    const auth = await api("/api/auth/bootstrap", {
      method: "POST",
      body: JSON.stringify(data),
    });
    await completeAuthentication(auth);
    toast("First administrator created");
  } catch (error) {
    $("#bootstrap-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

document.querySelectorAll("[data-auth-mode]").forEach((button) => {
  button.addEventListener("click", () => setAuthMode(button.dataset.authMode));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const mode = event.key === "ArrowLeft" || event.key === "Home" ? "signin" : "signup";
    setAuthMode(mode, false);
    document.querySelector(`[data-auth-mode="${mode}"]`)?.focus();
  });
});

$("#signup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#signup-error").textContent = "";
  setBusy(button, true, "Creating…");
  try {
    const data = Object.fromEntries(new FormData(form));
    if (data.password !== data.confirm_password) {
      throw new Error("Password confirmation does not match");
    }
    delete data.confirm_password;
    const auth = await api("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(data),
    });
    await completeAuthentication(auth);
    toast("Operator account created");
  } catch (error) {
    $("#signup-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#login-error").textContent = "";
  setBusy(button, true, "Signing in…");
  try {
    const data = Object.fromEntries(new FormData(form));
    const auth = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    });
    await completeAuthentication(auth);
  } catch (error) {
    $("#login-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

$("#forced-password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitPasswordChange(
    event.currentTarget,
    $("#forced-password-error"),
    event.submitter,
  );
});

$("#password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitPasswordChange(
    event.currentTarget,
    $("#password-error"),
    event.submitter,
    $("#password-dialog"),
  );
});

$("#password-button").addEventListener("click", () => {
  $("#password-form").reset();
  $("#password-error").textContent = "";
  $("#session-control-note").textContent = "Keep this browser signed in.";
  showDialog("#password-dialog");
});

$("#more-actions-button").addEventListener("click", (event) => {
  event.stopPropagation();
  setSecondaryActionsOpen($("#more-actions-button").getAttribute("aria-expanded") !== "true");
});

$("#mobile-project-select").addEventListener("change", (event) => {
  if (event.currentTarget.value) selectProject(event.currentTarget.value);
});

$("#secondary-actions").addEventListener("click", () => setSecondaryActionsOpen(false));
$("#secondary-actions").addEventListener("keydown", handleSecondaryActionsKeydown);

document.addEventListener("click", (event) => {
  if (!event.target.closest(".topbar-actions")) setSecondaryActionsOpen(false);
  document.querySelectorAll(".review-more-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    const wasOpen = $("#more-actions-button").getAttribute("aria-expanded") === "true";
    setSecondaryActionsOpen(false);
    if (wasOpen) $("#more-actions-button").focus();
    const reviewMenu = $(".review-more-menu[open]");
    if (reviewMenu) {
      reviewMenu.open = false;
      reviewMenu.querySelector("summary")?.focus();
    }
  }
  if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    const activeTag = document.activeElement?.tagName;
    const search = $("#contract-graph-search");
    if (search && !["INPUT", "TEXTAREA", "SELECT"].includes(activeTag)) {
      event.preventDefault();
      search.focus();
      search.select();
    }
  }
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  if (typing || document.querySelector("dialog[open]") || event.metaKey || event.ctrlKey || event.altKey || document.body.classList.contains("auth-locked")) return;
  if ((event.key === "j" || event.key === "k") && state.reviews.length > 1) {
    event.preventDefault();
    stepReview(event.key === "j" ? 1 : -1);
  }
  if (event.key === "0" && state.activeProject) {
    event.preventDefault();
    showProjectCanvas();
  }
  const sectionIndex = ["1", "2", "3", "4"].indexOf(event.key);
  if (sectionIndex >= 0 && state.activeReview && $("[data-review-tab]")) {
    event.preventDefault();
    setReviewWorkspaceTab(["overview", "changes", "evidence", "audit"][sectionIndex], { focus: true });
  }
});

function stepReview(delta) {
  const reviews = matchingReviewList();
  if (!reviews.length) return;
  const index = reviews.findIndex((item) => item.id === state.activeReview?.id);
  const next = index < 0 ? reviews[delta > 0 ? 0 : reviews.length - 1] : reviews[(index + delta + reviews.length) % reviews.length];
  if (!next || next.id === state.activeReview?.id) return;
  selectReviewFromList(next.id).catch((error) => toast(error.message));
}

$("#review-filter")?.addEventListener("input", (event) => {
  if (state.activeProject) reviewQueries.set(state.activeProject.id, event.currentTarget.value);
  renderWorkspace();
});
$("#clear-review-filter")?.addEventListener("click", clearReviewFilter);
$("#review-list-toggle")?.addEventListener("click", () => {
  state.reviewListExpanded = !state.reviewListExpanded;
  syncReviewList();
});
$(".review-rail")?.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !state.reviewListExpanded || $("#review-list-toggle")?.hidden) return;
  event.preventDefault();
  event.stopPropagation();
  state.reviewListExpanded = false;
  syncReviewList();
  $("#review-list-toggle")?.focus();
});
window.matchMedia("(max-width: 820px)").addEventListener("change", () => {
  const focusWasInList = $("#review-list-content")?.contains(document.activeElement);
  const focusWasToggle = document.activeElement === $("#review-list-toggle");
  state.reviewListExpanded = false;
  syncReviewList();
  if (focusWasInList && $("#review-list-content")?.hidden) $("#review-list-toggle")?.focus({ preventScroll: true });
  if (focusWasToggle && $("#review-list-toggle")?.hidden) $("#review-list [aria-current=true]")?.focus({ preventScroll: true });
});
document.querySelectorAll("[data-view-tab]").forEach((button) => {
  button.addEventListener("click", () => setProjectView(button.dataset.viewTab));
});

function commandItems() {
  const items = [];
  const review = state.activeReview;
  const manifest = state.manifest;
  const viewer = document.body.classList.contains("viewer-mode");
  state.reviews.forEach((item) => items.push({
    group: "Reviews",
    label: item.intent_summary || item.summary,
    hint: `${reviewRef(item)} · ${reviewStatusLabel(item.status)}`,
    keywords: `${reviewRef(item)} ${item.proposer}`,
    run: () => selectReview(item.id),
  }));
  if (review) {
    [["overview", "Decision"], ["changes", "Changes"], ["evidence", "Evidence"], ["audit", "Audit"]].forEach(([tab, label], index) => items.push({
      group: "Sections", label: `Go to ${label}`, hint: `${index + 1}`, keywords: `tab section ${label}`, run: () => setReviewWorkspaceTab(tab, { focus: true }),
    }));
    if (review.status === "open" && !viewer) {
      if (manifest?.committable) items.push({ group: "Actions", label: "Approve and record this change", hint: "Decision", keywords: "commit approve", run: () => openDecision("commit") });
      items.push({ group: "Actions", label: "Request an update", hint: "Decision", keywords: "rebase", run: () => openDecision("rebase") });
      items.push({ group: "Actions", label: "Reject this change", hint: "Decision", keywords: "reject", run: () => openDecision("reject") });
      items.push({ group: "Actions", label: state.activeProject?.test_command?.length ? "Run tests" : "Configure and run tests", hint: "Evidence", keywords: "tests", run: openTestConfiguration });
    }
    if (review.status === "committed" && !viewer) items.push({ group: "Actions", label: "Roll back the approval", hint: "Decision", keywords: "rollback", run: () => openDecision("rollback") });
    if (safeHttpUrl(review.external_url)) items.push({ group: "Actions", label: "Open on GitHub", hint: "External", keywords: "github pr", run: () => window.open(safeHttpUrl(review.external_url), "_blank", "noopener") });
    items.push({ group: "Actions", label: "Copy review link", hint: "Clipboard", keywords: "share url", run: () => copyReviewLink() });
    items.push({ group: "Actions", label: "Copy review brief", hint: "Clipboard", keywords: "summary handoff", run: () => copyReviewBrief() });
    items.push({ group: "Actions", label: "Ask the review assistant", hint: "Inspector", keywords: "ai copilot question", run: () => setInspectorTab("assistant", { open: true, focus: true }) });
  }
  if (state.activeProject && state.viewMode !== "canvas") items.push({ group: "Workspace", label: "Canvas", hint: "0", keywords: "home overview graph project", run: showProjectCanvas });
  if (state.activeProject && state.viewMode !== "intents") items.push({ group: "Workspace", label: "Requests", hint: "Project", keywords: "clarify interpretations request intent maps", run: () => showIntents() });
  if (state.activeProject && state.viewMode !== "governance") items.push({ group: "Workspace", label: "Rules", hint: "Project", keywords: "governance claims trust keys policy", run: showGovernance });
  if (state.activeProject && !state.activeReview) items.push({ group: "Workspace", label: "Reviews", hint: "Project", keywords: "list open decided", run: showReviews });
  if (state.activeProject && state.activeReview) items.push({ group: "Workspace", label: state.filePanelOpen ? "Hide inspector" : "Show inspector", hint: "Layout", keywords: "panel files", run: () => setFilePanelOpen(!state.filePanelOpen, { focus: true }) });
  items.push({ group: "Workspace", label: document.documentElement.dataset.theme === "dark" ? "Switch to light theme" : "Switch to dark theme", hint: "Appearance", keywords: "theme dark light", run: () => $("#theme-mode-button")?.click() });
  items.push({ group: "Workspace", label: state.paperMode ? "Exit presentation view" : "Presentation view", hint: "Appearance", keywords: "paper screenshot", run: () => $("#paper-mode-button")?.click() });
  if (!viewer) items.push({ group: "Workspace", label: "New review", hint: state.activeProject?.source?.provider === "github" ? "Pull request" : "Compare revisions", keywords: "new review compare pull request", run: startNewReview });
  if (!viewer) items.push({ group: "Workspace", label: "Analyze a GitHub pull request", hint: "Import", keywords: "new github import", run: () => openProject("github") });
  if (!viewer) items.push({ group: "Workspace", label: "Register a local repository", hint: "Import", keywords: "local path", run: () => openProject("local") });
  items.push({ group: "Workspace", label: "Keyboard shortcuts", hint: "?", keywords: "help keys", run: () => showDialog("#shortcuts-dialog") });
  if (document.documentElement.dataset.paperDemo === "true") {
    const unavailable = new Set(["New review", "Analyze a GitHub pull request", "Register a local repository", "Requests", "Ask the review assistant", "Copy review link"]);
    return items.filter(item => !unavailable.has(item.label));
  }
  return items;
}

let commandSelection = 0;
function renderCommandResults() {
  const input = $("#command-input");
  const results = $("#command-results");
  if (!input || !results) return;
  const query = input.value.trim().toLowerCase();
  const terms = query.split(/\s+/).filter(Boolean);
  const matches = commandItems().filter((item) => !terms.length || terms.every((term) => `${item.label} ${item.hint} ${item.keywords} ${item.group} ${item.group==='Reviews'?item.label:I18n.t(item.label)} ${I18n.t(item.hint)} ${I18n.t(item.group)}`.toLowerCase().includes(term)));
  commandSelection = Math.min(commandSelection, Math.max(0, matches.length - 1));
  let lastGroup = "";
  results.innerHTML = matches.length ? matches.map((item, index) => {
    const heading = item.group !== lastGroup ? `<div class="command-group">${I18n.mark(item.group)}</div>` : "";
    lastGroup = item.group;
    return `${heading}<button type="button" class="command-item${index === commandSelection ? " active" : ""}" role="option" aria-selected="${index === commandSelection}" data-command-index="${index}"><span>${item.group==='Reviews'?esc(item.label):I18n.mark(item.label)}</span><small>${I18n.mark(item.hint)}</small></button>`;
  }).join("") : '<div class="command-empty" data-i18n=No%20matching%20command.>No matching command.</div>';
  results.querySelectorAll("[data-command-index]").forEach((node) => {
    node.addEventListener("click", () => runCommand(matches[Number(node.dataset.commandIndex)]));
    node.addEventListener("mousemove", () => {
      if (commandSelection === Number(node.dataset.commandIndex)) return;
      commandSelection = Number(node.dataset.commandIndex);
      results.querySelectorAll(".command-item").forEach((item) => {
        const active = Number(item.dataset.commandIndex) === commandSelection;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", String(active));
      });
    });
  });
  results.querySelector(".command-item.active")?.scrollIntoView({ block: "nearest" });
  $("#command-input")?.setAttribute("aria-activedescendant", "");
  renderCommandResults.matches = matches;
}

function runCommand(item) {
  if (!item) return;
  $("#command-dialog")?.close();
  Promise.resolve(item.run()).catch((error) => toast(error.message, "error"));
}

function openCommandPalette() {
  const dialog = $("#command-dialog");
  const input = $("#command-input");
  if (!dialog || !input || document.body.classList.contains("auth-locked")) return;
  closeSnapshotFile(false);
  document.querySelectorAll("dialog[open]").forEach((open) => { if (open !== dialog) open.close(); });
  input.value = "";
  commandSelection = 0;
  renderCommandResults();
  if (!dialog.open) dialog.showModal();
  window.requestAnimationFrame(() => input.focus());
}

$("#command-input")?.addEventListener("input", () => { commandSelection = 0; renderCommandResults(); });
$("#command-input")?.addEventListener("keydown", (event) => {
  const matches = renderCommandResults.matches || [];
  if (event.key === "ArrowDown") { event.preventDefault(); commandSelection = (commandSelection + 1) % Math.max(1, matches.length); renderCommandResults(); }
  if (event.key === "ArrowUp") { event.preventDefault(); commandSelection = (commandSelection - 1 + Math.max(1, matches.length)) % Math.max(1, matches.length); renderCommandResults(); }
  if (event.key === "Enter") { event.preventDefault(); runCommand(matches[commandSelection]); }
});
$("#command-button")?.addEventListener("click", openCommandPalette);
$("#shortcuts-button")?.addEventListener("click", () => showDialog("#shortcuts-dialog"));
$("#command-dialog")?.addEventListener("click", (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); });
$("#project-menu-button")?.addEventListener("click", (event) => {
  event.stopPropagation();
  setProjectMenuOpen($("#project-menu-button").getAttribute("aria-expanded") !== "true");
});
$("#project-menu")?.addEventListener("keydown", (event) => {
  if (event.key === "Escape") { setProjectMenuOpen(false); $("#project-menu-button")?.focus(); return; }
  if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
  const items = [...$("#project-menu").querySelectorAll("button")];
  const index = items.indexOf(document.activeElement);
  event.preventDefault();
  items[(index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
});
document.addEventListener("click", (event) => {
  if (!event.target.closest("#project-context")) setProjectMenuOpen(false);
});
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    openCommandPalette();
    return;
  }
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  if (event.key === "?" && !typing && !document.querySelector("dialog[open]") && !document.body.classList.contains("auth-locked")) {
    event.preventDefault();
    showDialog("#shortcuts-dialog");
  }
});
$("#project-file-search")?.addEventListener("input", () => renderProjectTree());

function initInspectorResizer() {
  const handle = $("#inspector-resizer");
  const grid = $("#review-workbench");
  if (!handle || !grid) return;
  const STORAGE_KEY = "agentic-consensus-inspector-width";
  const MIN = 280;
  const MAX = 560;
  const DEFAULT = 324;
  const current = () => parseInt(grid.style.getPropertyValue("--inspector-width"), 10) || DEFAULT;
  const apply = (width, persist = true) => {
    const next = Math.round(Math.min(MAX, Math.max(MIN, width)));
    grid.style.setProperty("--inspector-width", `${next}px`);
    handle.setAttribute("aria-valuenow", String(next));
    if (persist) {
      try { localStorage.setItem(STORAGE_KEY, String(next)); } catch (_) {}
    }
  };
  try {
    const stored = Number(localStorage.getItem(STORAGE_KEY));
    if (stored) apply(stored, false);
  } catch (_) {}
  let dragging = false;
  handle.addEventListener("pointerdown", (event) => {
    if (!window.matchMedia("(min-width: 1180px)").matches) return;
    dragging = true;
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add("is-resizing-inspector");
    event.preventDefault();
  });
  handle.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    apply(grid.getBoundingClientRect().right - event.clientX, false);
  });
  const stop = () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("is-resizing-inspector");
    apply(current());
    contractGraphInstance?.resize();
  };
  handle.addEventListener("pointerup", stop);
  handle.addEventListener("pointercancel", stop);
  handle.addEventListener("dblclick", () => apply(DEFAULT));
  handle.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") { event.preventDefault(); apply(current() + 16); }
    if (event.key === "ArrowRight") { event.preventDefault(); apply(current() - 16); }
    if (event.key === "Home") { event.preventDefault(); apply(DEFAULT); }
  });
}
initInspectorResizer();

$("#revoke-sessions-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  setBusy(button, true, "Revoking…");
  $("#password-error").textContent = "";
  try {
    const result = await api("/api/auth/sessions/revoke-others", { method: "POST" });
    $("#session-control-note").textContent = `${result.revoked_sessions} other session(s) signed out.`;
    toast("Other sessions signed out");
  } catch (error) {
    $("#password-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

$("#logout-button").addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (error) {
    return toast(error.message);
  }
  state.auth = null;
  state.csrfToken = null;
  window.PaperDemo.clear();
  state.projects = [];
  state.activeProject = null;
  state.activeReview = null;
  $("#current-user").classList.add("hidden");
  intentDrafts.clear();
  intentDraft = null;
  intentDraftOwner = null;
  clarificationSnapshot = null;
  $("#intent-form").reset();
  $("#intent-candidate-editors").replaceChildren();
  clearCandidateRevisionDrafts();
  $("#password-button").classList.add("hidden");
  $("#github-account-button").classList.add("hidden");
  $("#logout-button").classList.add("hidden");
  $("#manage-users-button").classList.add("hidden");
  showAuthGate(false);
});

$("#manage-users-button").addEventListener("click", async () => {
  $("#user-error").textContent = "";
  try {
    await loadUsers();
    showDialog("#users-dialog");
  } catch (error) {
    toast(error.message);
  }
});

$("#user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#user-error").textContent = "";
  setBusy(button, true, "Adding…");
  try {
    const data = Object.fromEntries(new FormData(form));
    await api("/api/users", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    await loadUsers();
    toast("Identity added; password change required");
  } catch (error) {
    $("#user-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

$("#reset-password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  $("#reset-password-error").textContent = "";
  if (!state.resetUser) return;
  setBusy(button, true, "Resetting…");
  try {
    if (form.elements.new_password.value !== form.elements.confirm_password.value) {
      throw new Error("Temporary password confirmation does not match");
    }
    await api(`/api/users/${state.resetUser.id}/password`, {
      method: "POST",
      body: JSON.stringify({ new_password: form.elements.new_password.value }),
    });
    form.reset();
    state.resetUser = null;
    $("#reset-password-dialog").close();
    await loadUsers();
    showDialog("#users-dialog");
    toast("Password reset; target sessions revoked");
  } catch (error) {
    $("#reset-password-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => {
    const dialog = button.closest("dialog");
    if (dialog?.id === "snapshot-file-dialog") closeSnapshotFile();
    else if (dialog?.open) dialog.close();
  });
});

async function openProject(source = "github") {
  intakeVersion += 1;
  if (intakeIsOwned(intakeOperation)) {
    showDialog("#project-dialog");
    renderIntakeOperation();
    $(intakeOperation.status === "failed" ? "#project-error" : "#intake-operation").focus();
    return;
  }
  $("#project-error").textContent = "";
  showDialog("#project-dialog");
  try {
    document.querySelectorAll("#project-form .intake-disclosure").forEach((details) => {
      details.open = false;
    });
    const actorField = $("#project-form").elements.namedItem("authorized_actors");
    if (!actorField.value.trim() && state.auth?.user?.actor) {
      actorField.value = state.auth.user.actor;
    }
    state.github.selectedRepositoryId = null;
    state.github.pullRequests = [];
    state.github.selectedPullNumber = null;
    $("#github-repository-search").value = "";
    $("#github-pull-request-step").classList.add("hidden");
    setRepositorySource(source);
    renderIntakeOperation();
    focusProjectIntake(source);
    if (source === "github") await loadGitHubStatus({ loadRepositories: true });
  } catch (error) {
    $("#project-error").textContent = error.message;
  }
}

function submitGitHubAppManifest(setup) {
  const form = document.createElement("form");
  form.method = "post";
  form.action = setup.registration_url;
  const manifest = document.createElement("input");
  manifest.type = "hidden";
  manifest.name = "manifest";
  manifest.value = JSON.stringify(setup.manifest);
  form.append(manifest);
  document.body.append(form);
  form.submit();
}

function comparisonIsOwned(draft) {
  return Boolean(draft && draft.ownerId === state.auth?.user?.id
    && comparisonDrafts.get(draft.storageKey||draft.projectId) === draft && !document.body.classList.contains("auth-locked"));
}

function comparisonIsCurrent(context) {
  return Boolean(context && comparisonContext === context && comparisonIsOwned(context.draft)
    && context.draft.projectId === state.activeProject?.id
    && context.selectionVersion === state.selectionVersion && $("#review-dialog").open);
}

function rememberComparisonInput() {
  const draft = comparisonContext?.draft;
  if (!comparisonIsOwned(draft) || draft.pending || draft.review) return;
  const form = $("#review-form");
  comparisonFields.forEach(name => { draft.fields[name] = form.elements[name].value; });
  renderComparisonStatus();
}

function renderComparisonStatus() {
  const draft = comparisonContext?.draft;
  if (!comparisonIsOwned(draft)) return;
  const form = $("#review-form");
  const saved = Boolean(draft.review);
  $("#review-create-fields").disabled = draft.pending || saved;
  $("#review-create-fields").hidden = saved;
  $("#review-created-receipt").hidden = !saved;
  $("#review-created-title").textContent = draft.review?.intent_summary || draft.fields.intent_summary;
  $("#review-error").textContent = draft.error;
  $("#review-base-summary").textContent = short(draft.fields.base_ref);
  $("#review-draft-note").textContent = saved ? "Saved in this project."
    : draft.pending ? "Analyzing this version. You can close this panel; analysis will continue."
    : "Draft kept for this project until reload or sign-out.";
  $("#discard-review-draft").hidden = saved || !comparisonFields.some(name => draft.fields[name] !== draft.defaults[name]);
  $("#discard-review-draft").disabled = draft.pending;
  $("#close-comparison-button").textContent = draft.pending || saved ? "Close" : "Cancel";
  const submit = form.querySelector('[type="submit"]');
  submit.hidden = saved;
  setBusy(submit, draft.pending, "Analyzing…");
  $("#open-created-review").hidden = !saved;
}

function openCompareDialog(predecessor=null) {
  if (!state.activeProject) return openProject("local");
  if(predecessor?.status!=='rebase_required')predecessor=null;
  const project = state.activeProject;
  const storageKey=predecessor?`${project.id}:${predecessor.id}`:project.id;
  let draft = comparisonDrafts.get(storageKey);
  if (!comparisonIsOwned(draft)) {
    const defaults = {intent_summary: predecessor?.intent_summary||"", target_ref: predecessor && document.documentElement.dataset.paperDemo === "true" ? "4e965bd23deb04643662ea4f3aef5dacab83cde9" : "", base_ref: predecessor?.base_ref||project.head_ref,
      proposer: predecessor?.proposer||localStorage.getItem("consensus-proposer") || "coding-agent"};
    draft = {projectId: project.id, projectName: project.name, ownerId: state.auth?.user?.id,
      storageKey,predecessor,defaults, fields: {...defaults}, pending: false, error: "", review: null};
    comparisonDrafts.set(storageKey, draft);
  }
  comparisonContext = {draft, selectionVersion: state.selectionVersion};
  const form = $("#review-form");
  comparisonFields.forEach(name => { form.elements[name].value = draft.fields[name]; });
  form.elements.target_ref.readOnly = Boolean(predecessor && document.documentElement.dataset.paperDemo === "true");
  const followup=Boolean(draft.predecessor);
  I18n.setText($('#review-dialog-title'),followup?'Review revised version':'Compare two revisions');
  form.elements.intent_summary.required=!followup;
  form.elements.intent_summary.closest('label').hidden=followup;
  $('#review-compare-options').hidden=followup;
  $('#switch-to-github-intake').hidden=followup;
  $('#revision-comparison-context').hidden=!followup;
  $('#revision-comparison-context').textContent=followup?I18n.t('Requirements carried forward. Evidence and approval must be collected again for this target.')+' '+draft.predecessor.intent_summary:'';
  $("#review-project-context").textContent = project.name;
  $("#review-compare-options").open = false;
  renderComparisonStatus();
  showDialog("#review-dialog");
  if (draft.review) $("#review-created-receipt").focus();
}

$("#review-form").addEventListener("input", rememberComparisonInput);
$("#review-form .comparison-body").addEventListener("focusin", event => {
  // Native textarea focus can expose only its first line. Keep the whole field
  // in the form's scroll area, which ends above the independent action footer.
  event.target.scrollIntoView({block: "nearest", inline: "nearest", behavior: "instant"});
});
$("#review-form").addEventListener("invalid", event => {
  const details = event.target.closest("details");
  if (details) details.open = true;
}, true);
$("#review-dialog").addEventListener("close", () => {
  if (!$("#review-dialog").open) comparisonContext = null;
});
$("#discard-review-draft").addEventListener("click", () => {
  if (!comparisonIsCurrent(comparisonContext) || comparisonContext.draft.pending) return;
  if (!window.confirm("Discard this project's comparison draft?")) return;
  const predecessor=comparisonContext.draft.predecessor;
  comparisonDrafts.delete(comparisonContext.draft.storageKey||comparisonContext.draft.projectId);
  openCompareDialog(predecessor);
});
$("#new-comparison-button").addEventListener("click", () => {
  if (!comparisonIsCurrent(comparisonContext) || !comparisonContext.draft.review) return;
  comparisonDrafts.delete(comparisonContext.draft.storageKey||comparisonContext.draft.projectId);
  openCompareDialog();
});
$("#open-created-review").addEventListener("click", async () => {
  const context = comparisonContext;
  if (!comparisonIsCurrent(context) || !context.draft.review) return;
  const opened = await selectReview(context.draft.review.id, context.selectionVersion);
  if (opened && comparisonIsOwned(context.draft)) comparisonDrafts.delete(context.draft.storageKey||context.draft.projectId);
});

function startNewReview() {
  if (!state.activeProject) return openProject("github");
  if (state.activeProject.source?.provider === "github") return openProject("github");
  const draft = comparisonDrafts.get(state.activeProject.id);
  if (comparisonIsOwned(draft) && (draft.pending || draft.review)) return openCompareDialog();
  $("#review-source-project").textContent = state.activeProject.name;
  showDialog("#review-source-dialog");
}

$("#new-project-button").addEventListener("click", startNewReview);
$("#review-source-local").addEventListener("click", () => {
  $("#review-source-dialog").close();
  openCompareDialog();
});
$("#review-source-github").addEventListener("click", () => {
  $("#review-source-dialog").close();
  openProject("github");
});
$("#switch-to-github-intake")?.addEventListener("click", () => {
  $("#review-dialog")?.close();
  openProject("github");
});
$("#empty-register-button").addEventListener("click", () => openProject("github"));
$("#empty-local-button").addEventListener("click", () => openProject("local"));
$("#github-account-button").addEventListener("click", () => openProject("github"));
$("#toggle-file-panel-button").addEventListener("click", () => {
  setFilePanelOpen(!state.filePanelOpen, { focus: !state.filePanelOpen });
});
$("#close-file-panel-button").addEventListener("click", () => {
  closeReviewInspector();
});
document.querySelectorAll("[data-inspector-tab]").forEach((node) => {
  node.addEventListener("click", () => setInspectorTab(node.dataset.inspectorTab));
  node.addEventListener("keydown", handleInspectorTabKeydown);
});
window.addEventListener("resize", () => {
  const filePanelIsWide = window.matchMedia("(min-width: 1180px)").matches;
  if (filePanelWasWide && !filePanelIsWide && state.filePanelOpen) setFilePanelOpen(false);
  filePanelWasWide = filePanelIsWide;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.filePanelOpen && window.matchMedia("(max-width: 1360px)").matches) {
    closeReviewInspector();
  }
});
$("#github-source-tab").addEventListener("click", () => {
  setRepositorySource("github");
  focusProjectIntake("github");
  loadGitHubStatus({ loadRepositories: true });
});
$("#local-source-tab").addEventListener("click", () => {
  setRepositorySource("local");
  focusProjectIntake("local");
});
$("#github-source-tab").addEventListener("keydown", handleRepositorySourceTabKeydown);
$("#local-source-tab").addEventListener("keydown", handleRepositorySourceTabKeydown);
$("#github-repository-search").addEventListener("input", renderGitHubRepositories);
$("#intake-status-button").addEventListener("click", () => openProject(intakeOperation?.source || "github"));
$("#intake-open-result").addEventListener("click", openIntakeResult);
$("#intake-check-workspace").addEventListener("click", checkIntakeWorkspace);
$("#intake-edit-settings").addEventListener("click", () => {
  if (!intakeIsOwned(intakeOperation) || intakeOperation.status !== "uncertain" || intakeOperation.checking) return;
  if (!window.confirm("The previous request may have finished. Returning to settings can lead to another submission. Check the workspace first if you are unsure.")) return;
  intakeOperation = null;
  renderIntakeOperation();
  focusProjectIntake();
});
$("#github-pull-request-search").addEventListener("input", () => {
  const repository = state.github.repositories.find(item => item.id === state.github.selectedRepositoryId);
  if (repository && !state.github.pullsLoading) renderGitHubPullRequests(repository);
});
$("#github-change-repository").addEventListener("click", () => {
  githubRequests.pulls += 1;
  state.github.selectedRepositoryId = null;
  state.github.selectedPullNumber = null;
  state.github.pullRequests = [];
  state.github.pullsLoading = false;
  renderGitHubRepositories();
  focusProjectIntake();
});
$("#github-status-retry-button").addEventListener("click", () => loadGitHubStatus({ loadRepositories: true }));
$("#project-dialog").addEventListener("close", () => {
  if (!$("#project-dialog").open) intakeVersion += 1;
});
$("#project-form").addEventListener("focusin", event => {
  // Pointer focus must not move a partially visible row between down and up.
  // Keyboard focus still reveals the control above the independent footer.
  if (event.target.matches(":focus-visible") && event.target.closest(".project-intake-layout")) {
    event.target.scrollIntoView({ block: "nearest", behavior: "instant" });
  }
});
$("#project-form").addEventListener("invalid", event => {
  for (let parent = event.target.parentElement; parent && parent !== event.currentTarget; parent = parent.parentElement) {
    if (parent.tagName === "DETAILS") parent.open = true;
  }
}, true);
$("#project-form").querySelector('[name="repo_path"]').addEventListener("input", updateProjectIntakeReadiness);
$("#github-connect-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  $("#project-error").textContent = "";
  setBusy(button, true, "Opening GitHub…");
  try {
    if (state.github.status?.setup_required) {
      const setup = await api("/api/github/app/setup/start", {
        method: "POST",
        body: JSON.stringify({ origin: window.location.origin }),
      });
      submitGitHubAppManifest(setup);
      return;
    }
    const started = await api("/api/github/oauth/start", {
      method: "POST",
      body: JSON.stringify({
        redirect_uri: `${window.location.origin}/api/github/oauth/callback`,
      }),
    });
    window.location.assign(started.authorization_url);
  } catch (error) {
    $("#project-error").textContent = error.message;
    setBusy(button, false);
  }
});
$("#github-disconnect-button").addEventListener("click", async (event) => {
  if (!window.confirm("Disconnect this GitHub account? Imported repositories remain available locally.")) return;
  const button = event.currentTarget;
  setBusy(button, true, "Disconnecting…");
  $("#project-error").textContent = "";
  try {
    const result = await api("/api/github/connection", { method: "DELETE" });
    state.github.repositories = [];
    state.github.selectedRepositoryId = null;
    state.github.pullRequests = [];
    state.github.selectedPullNumber = null;
    await loadGitHubStatus();
    if (result.remote_token_revoked) {
      toast("GitHub disconnected; local governed repositories were preserved");
    } else {
      toast("Disconnected locally. Revoke the token in GitHub settings to finish.", "warning");
    }
  } catch (error) {
    $("#project-error").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});
$("#new-intent-button").addEventListener("click", openIntentComposer);
$("#intent-ai-suggest-button").addEventListener("click", suggestIntentCandidates);
$("#intent-form").addEventListener("input", (event) => {
  event.target.setCustomValidity?.("");
  if (!intentDraft) return;
  intentDraft.version += 1;
  captureIntentDraft();
  $("#intent-base-label").textContent = short(intentDraft.base_ref);
});
$("#intent-composer-back").addEventListener("click", () => {
  captureIntentDraft();
  setIntentComposerStep("request");
});
$("#intent-dialog").addEventListener("close", () => {
  if (intentDraft) intentDraft.version += 1;
});
$("#add-trust-root-button").addEventListener("click", () => openTrustChange("add"));
$("#new-review-button").addEventListener("click", startNewReview);
$("#paper-mode-button").addEventListener("click", () => {
  state.paperMode = !state.paperMode;
  const url = new URL(window.location.href);
  if (state.paperMode) url.searchParams.set("paper", "1");
  else url.searchParams.delete("paper");
  window.history.replaceState({}, "", url);
  applyPaperMode();
});
$(".skip-link")?.addEventListener("click", () => {
  window.requestAnimationFrame(() => $("#main-content").focus({ preventScroll: true }));
});
document.querySelectorAll("[data-theme-cycle]").forEach((button) => {
  button.addEventListener("click", () => {
    const current = document.documentElement.dataset.themePreference || "light";
    const next = THEME_PREFERENCES[(THEME_PREFERENCES.indexOf(current) + 1) % THEME_PREFERENCES.length];
    applyThemePreference(next);
    restyleContractGraph();
  });
});

function runtimeLabel(runtime) {
  if (!runtime.enabled) return "Model off · Deterministic evidence";
  if (!runtime.configured) return "Model not configured";
  return `${String(runtime.api_style).toUpperCase()} · ${runtime.model}`;
}

async function boot() {
  applyThemePreference(document.documentElement.dataset.themePreference || "light", false);
  applyPaperMode();
  try {
    const auth = await api("/api/auth/state");
    state.signupAllowed = Boolean(auth.signup_allowed);
    if (!auth.authenticated) {
      window.PaperDemo.clear();
      showAuthGate(auth.setup_required);
      window.EntryGate?.ready();
      return;
    }
    await completeAuthentication(auth);
    window.EntryGate?.ready();
  } catch (error) {
    $("#health-label").textContent = "Service offline";
    window.EntryGate?.fail("We couldn’t connect to this workspace. Check that the service is running, then try again. No project data has been changed.");
    toast(error.message);
  }
}

document.addEventListener('click',event=>{
  const control=event.target.closest('[data-workspace-open]');if(!control)return;
  if(control.dataset.workspaceOpen==='new-request') $("#new-intent-button")?.click();
  else if(control.dataset.workspaceOpen==='reviews') setProjectView('review');
});
window.addEventListener("resize",()=>window.requestAnimationFrame(()=>{
  ReviewMotion.indicator($(".review-workspace-tabs"),'[aria-selected="true"]');
}));
window.addEventListener("unhandledrejection", (event) => {
  const message = event.reason?.message || "Unexpected operation failure";
  toast(message);
});

CommitmentUI.bind();
document.addEventListener('languagechange',()=>{
  // Repaint labels only: language changes must not reset graph focus, pan or zoom.
  projectCanvasInstance?.style(projectCanvasStyles()).update();
  if($('#command-dialog')?.open)renderCommandResults();
  requestAnimationFrame(() => {
    ReviewMotion.indicator($('.review-workspace-tabs'), '[aria-selected="true"]');
  });
});
boot();
