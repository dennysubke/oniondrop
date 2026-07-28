const LANGUAGES = {
  en: { label: "English", short: "EN", flag: "/static/flags/gb.svg" },
  de: { label: "Deutsch", short: "DE", flag: "/static/flags/de.svg" },
  es: { label: "Español", short: "ES", flag: "/static/flags/es.svg" },
  it: { label: "Italiano", short: "IT", flag: "/static/flags/it.svg" },
  fr: { label: "Français", short: "FR", flag: "/static/flags/fr.svg" },
  zh: { label: "中文", short: "ZH", flag: "/static/flags/cn.svg" },
  ja: { label: "日本語", short: "JA", flag: "/static/flags/jp.svg" },
  ru: { label: "Русский", short: "RU", flag: "/static/flags/ru.svg" },
};

const state = {
  locale: "en",
  translations: {},
  bootstrap: null,
  inboxes: [],
  files: [],
  selectedFiles: new Set(),
  selectedInbox: null,
  currentView: "inboxes",
  appLoaded: false,
  torTimer: null,
  refreshTimer: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
}[char]));

function t(key, values = {}) {
  let value = state.translations[key] || key;
  Object.entries(values).forEach(([name, replacement]) => {
    value = value.replaceAll(`{${name}}`, String(replacement));
  });
  return value;
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(state.locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusLabel(status) {
  return t(`status_${String(status).replaceAll("-", "_")}`);
}

function languageOptionMarkup(code, meta) {
  return `<img src="${meta.flag}" alt="" aria-hidden="true"><span>${escapeHtml(meta.label)}</span>`;
}

function ensureLanguagePickers() {
  $$(".language-select").forEach((select) => {
    if (!select.options.length) {
      Object.entries(LANGUAGES).forEach(([code, meta]) => select.add(new Option(meta.label, code)));
    }
    if (select.closest(".language-picker")) return;

    const wrapper = document.createElement("span");
    wrapper.className = `language-picker${select.classList.contains("compact") ? " compact" : ""}`;
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);
    select.classList.add("language-select-native");

    const button = document.createElement("button");
    button.type = "button";
    button.className = "language-picker-button";
    button.dataset.languageToggle = "true";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");

    const menu = document.createElement("span");
    menu.className = "language-picker-menu";
    menu.setAttribute("role", "listbox");
    Object.entries(LANGUAGES).forEach(([code, meta]) => {
      const option = document.createElement("button");
      option.type = "button";
      option.className = "language-picker-option";
      option.dataset.languageOption = code;
      option.setAttribute("role", "option");
      option.innerHTML = languageOptionMarkup(code, meta);
      menu.appendChild(option);
    });

    wrapper.append(button, menu);
  });
}

function updateLanguagePickers() {
  $$(".language-select").forEach((select) => {
    const wrapper = select.closest(".language-picker");
    if (!wrapper) return;
    const meta = LANGUAGES[select.value] || LANGUAGES.en;
    const button = $(".language-picker-button", wrapper);
    button.innerHTML = `<img src="${meta.flag}" alt="" aria-hidden="true"><span class="language-picker-name">${escapeHtml(meta.label)}</span><span class="language-picker-code">${meta.short}</span><i aria-hidden="true">⌄</i>`;
    button.setAttribute("aria-label", meta.label);
    $$("[data-language-option]", wrapper).forEach((option) => {
      const active = option.dataset.languageOption === select.value;
      option.classList.toggle("active", active);
      option.setAttribute("aria-selected", String(active));
    });
  });
}

function closeLanguagePickers(except = null) {
  $$(".language-picker.open").forEach((picker) => {
    if (picker === except) return;
    picker.classList.remove("open");
    $(".language-picker-button", picker)?.setAttribute("aria-expanded", "false");
  });
}

function applyTranslations() {
  document.documentElement.lang = state.locale;
  $$('[data-i18n]').forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  $$('[data-i18n-placeholder]').forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  $$('[data-i18n-title]').forEach((element) => {
    element.title = t(element.dataset.i18nTitle);
  });
  ensureLanguagePickers();
  $$(".language-select").forEach((select) => { select.value = state.locale; });
  updateLanguagePickers();
  renderDynamicViews();
}

async function setLocale(locale, persist = true) {
  const normalized = LANGUAGES[locale] ? locale : "en";
  const response = await fetch(`/static/i18n/${normalized}.json?v=${document.body.dataset.version}`, { cache: "no-store" });
  if (!response.ok) throw new Error("translation_load_failed");
  state.locale = normalized;
  state.translations = await response.json();
  if (persist) localStorage.setItem("oniondrop-language", normalized);
  applyTranslations();
}

function initialLocale() {
  const stored = localStorage.getItem("oniondrop-language");
  if (stored && LANGUAGES[stored]) return stored;
  const browser = (navigator.language || "en").toLowerCase().split("-")[0];
  return LANGUAGES[browser] ? browser : "en";
}

async function api(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    options.body = JSON.stringify(options.json);
    delete options.json;
  }
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && state.bootstrap?.csrf_token) {
    headers.set("X-CSRF-Token", state.bootstrap.csrf_token);
  }
  const response = await fetch(url, { ...options, method, headers });
  let data = {};
  try { data = await response.json(); } catch { /* file or empty response */ }
  if (!response.ok) {
    if (response.status === 401 && !url.endsWith("/login")) {
      await refreshBootstrap();
    }
    const error = new Error(data.code || data.error || `request_${response.status}`);
    error.code = data.code || data.error;
    error.detail = data.detail;
    throw error;
  }
  return data;
}

function humanError(error) {
  const code = error?.code || error?.message || "unknown";
  const translated = t(`error_${code}`);
  return translated.startsWith("error_") ? (error?.detail || code) : translated;
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.classList.add("show");
  clearTimeout(element._timer);
  element._timer = setTimeout(() => element.classList.remove("show"), 3000);
}

function legacyCopy(value) {
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.setAttribute("aria-hidden", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  let copied = false;
  try { copied = document.execCommand("copy"); } catch { copied = false; }
  textarea.remove();
  return copied;
}

async function copyText(value) {
  if (!value) return;
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(value);
    else if (!legacyCopy(value)) throw new Error("copy_failed");
    toast(t("copied"));
  } catch {
    if (legacyCopy(value)) toast(t("copied"));
    else toast(t("copy_failed"), true);
  }
}

function showAuth(mode) {
  if (state.torTimer) clearInterval(state.torTimer);
  if (state.refreshTimer) clearInterval(state.refreshTimer);
  state.torTimer = null;
  state.refreshTimer = null;
  $("#appShell").classList.add("hidden");
  $("#authScreen").classList.remove("hidden");
  $("#setupForm").classList.toggle("hidden", mode !== "setup");
  $("#loginForm").classList.toggle("hidden", mode !== "login");
  if (mode === "login" && state.bootstrap?.username) {
    $("#loginForm [name=username]").value = state.bootstrap.username;
  }
}

async function showApp() {
  $("#authScreen").classList.add("hidden");
  $("#appShell").classList.remove("hidden");
  $("#logoutButton").classList.toggle("hidden", !state.bootstrap.auth_enabled);
  if (!state.appLoaded) state.appLoaded = true;
  await loadInboxes();
  await refreshTorStatus();
  if (!state.torTimer) state.torTimer = setInterval(refreshTorStatus, 3000);
  if (!state.refreshTimer) state.refreshTimer = setInterval(loadInboxes, 8000);
  loadSettingsForm();
}

async function refreshBootstrap() {
  const response = await fetch("/api/bootstrap", { cache: "no-store" });
  state.bootstrap = await response.json();
  if (!localStorage.getItem("oniondrop-language") && state.bootstrap.default_language && state.bootstrap.default_language !== state.locale) {
    await setLocale(state.bootstrap.default_language, false);
  }
  if (!state.bootstrap.configured) showAuth("setup");
  else if (state.bootstrap.auth_enabled && !state.bootstrap.authenticated) showAuth("login");
  else await showApp();
}

function switchView(view) {
  state.currentView = view;
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $$(".view").forEach((section) => section.classList.toggle("active", section.id === `${view}View`));
  $("#viewEyebrow").textContent = t({
    inboxes: "private_file_intake",
    files: "local_storage",
    settings: "configuration",
    about: "about_oniondrop",
  }[view] || "private_file_intake");
  const showInboxActions = view === "inboxes";
  $("#importButton").classList.toggle("hidden", !showInboxActions);
  $("#createButton").classList.toggle("hidden", !showInboxActions);
  if (view === "files") refreshFiles();
  if (view === "settings") loadSettingsForm();
}

async function loadInboxes() {
  try {
    const data = await api("/api/inboxes");
    state.inboxes = data.inboxes || [];
    if (!state.selectedInbox && state.inboxes.length) state.selectedInbox = state.inboxes[0].id;
    if (state.selectedInbox && !state.inboxes.some((inbox) => inbox.id === state.selectedInbox)) {
      state.selectedInbox = state.inboxes[0]?.id || null;
    }
    renderInboxes();
    populateInboxSelect();
    if (state.currentView === "files") await refreshFiles();
  } catch (error) {
    if (error.code !== "authentication_required") toast(humanError(error), true);
  }
}

function renderInboxes() {
  const grid = $("#inboxGrid");
  const empty = $("#emptyState");
  const active = state.inboxes.filter((item) => item.status === "online").length;
  const fileCount = state.inboxes.reduce((sum, item) => sum + Number(item.file_count || 0), 0);
  const bytes = state.inboxes.reduce((sum, item) => sum + Number(item.bytes_used || 0), 0);
  $("#activeCount").textContent = active;
  $("#fileCount").textContent = fileCount;
  $("#storageUsed").textContent = formatBytes(bytes);
  empty.classList.toggle("hidden", state.inboxes.length > 0);
  grid.innerHTML = state.inboxes.map((inbox) => {
    const address = inbox.url || t("waiting_for_address");
    const action = inbox.running
      ? `<button class="button ghost" data-action="stop" data-id="${inbox.id}">${escapeHtml(t("stop"))}</button>`
      : `<button class="button primary" data-action="start" data-id="${inbox.id}">${escapeHtml(t("start"))}</button>`;
    return `<article class="inbox-card">
      <div class="card-head">
        <div class="card-title"><img class="mini-logo" src="/static/logo.svg" alt=""><div><h3>${escapeHtml(inbox.name)}</h3><p>${escapeHtml(inbox.description || t("private_onion_inbox"))}</p></div></div>
        <span class="status ${escapeHtml(inbox.status)}">${escapeHtml(statusLabel(inbox.status))}</span>
      </div>
      <div class="address-box"><div class="address-label">${escapeHtml(t("onion_address"))}</div><div class="address-row"><code>${escapeHtml(address)}</code><button type="button" class="copy-button" data-copy-inbox="${inbox.id}" data-copy-field="url" title="${escapeHtml(t("copy"))}">⧉</button></div></div>
      <div class="card-meta"><span>↓ ${inbox.file_count || 0} ${escapeHtml(t("files_lower"))}</span><span>◫ ${formatBytes(inbox.bytes_used || 0)}</span><span>◇ ${inbox.public ? escapeHtml(t("public")) : escapeHtml(t("private"))}</span></div>
      <div class="card-actions">${action}<button class="button ghost" data-action="details" data-id="${inbox.id}">${escapeHtml(t("details"))}</button></div>
    </article>`;
  }).join("");
}

function populateInboxSelect() {
  const select = $("#fileInboxSelect");
  const current = state.selectedInbox;
  select.innerHTML = state.inboxes.map((inbox) => `<option value="${inbox.id}">${escapeHtml(inbox.name)}</option>`).join("");
  if (current) select.value = current;
}

async function inboxAction(action, inboxId) {
  try {
    if (action === "start" || action === "stop") {
      await api(`/api/inboxes/${inboxId}/${action}`, { method: "POST" });
      toast(t(action === "start" ? "service_starting" : "service_stopped"));
      await loadInboxes();
      await refreshTorStatus();
    } else if (action === "details") {
      await openDetails(inboxId);
    }
  } catch (error) { toast(humanError(error), true); }
}

function invitation(inbox) {
  return inbox.private_key
    ? t("invitation_private", { url: inbox.url || "", key: inbox.private_key })
    : t("invitation_public", { url: inbox.url || "" });
}

async function openDetails(inboxId) {
  const inbox = state.inboxes.find((item) => item.id === inboxId);
  if (!inbox) return;
  let logs = "";
  try { logs = (await api(`/api/inboxes/${inboxId}/logs`)).logs || ""; } catch { /* optional */ }
  $("#detailsContent").innerHTML = `
    <div class="modal-head"><div><p class="eyebrow">${escapeHtml(t("onion_service"))}</p><h2>${escapeHtml(inbox.name)}</h2></div><button type="button" class="close" data-close>×</button></div>
    <p class="modal-copy">${escapeHtml(inbox.description || t("private_onion_inbox"))}</p>
    <div class="details-address">
      <div class="detail-line"><label>${escapeHtml(t("onion_address"))}</label><div><code>${escapeHtml(inbox.url || t("waiting_for_address"))}</code><button type="button" class="copy-button" data-copy-inbox="${inbox.id}" data-copy-field="url" title="${escapeHtml(t("copy"))}">⧉</button></div></div>
      ${inbox.private_key ? `<div class="detail-line"><label>${escapeHtml(t("private_key"))}</label><div><code>${escapeHtml(inbox.private_key)}</code><button type="button" class="copy-button" data-copy-inbox="${inbox.id}" data-copy-field="private_key" title="${escapeHtml(t("copy"))}">⧉</button></div></div>` : ""}
    </div>
    <p class="detail-warning">${escapeHtml(t("untrusted_warning"))}</p>
    <div class="details-buttons">
      <button class="button ghost" data-detail-action="copy-invite" data-id="${inbox.id}">${escapeHtml(t("copy_invitation"))}</button>
      ${inbox.url ? `<button class="button ghost" data-detail-action="qr-url" data-id="${inbox.id}">${escapeHtml(t("address_qr"))}</button>` : ""}
      ${inbox.private_key ? `<button class="button ghost" data-detail-action="qr-key" data-id="${inbox.id}">${escapeHtml(t("key_qr"))}</button>` : ""}
      <a class="button ghost" href="/api/inboxes/${inbox.id}/export">${escapeHtml(t("export_config"))}</a>
      <button class="button danger" data-detail-action="delete" data-id="${inbox.id}">${escapeHtml(t("delete_inbox"))}</button>
    </div>
    ${logs ? `<pre class="log-box">${escapeHtml(logs)}</pre>` : ""}`;
  $("#detailsDialog").showModal();
}

async function detailAction(action, inboxId) {
  const inbox = state.inboxes.find((item) => item.id === inboxId);
  if (!inbox) return;
  if (action === "copy-invite") return copyText(invitation(inbox));
  if (action === "qr-url") return openQr(inbox, "url");
  if (action === "qr-key") return openQr(inbox, "key");
  if (action === "delete") {
    if (!window.confirm(t("confirm_delete_inbox"))) return;
    try {
      await api(`/api/inboxes/${inboxId}`, { method: "DELETE" });
      $("#detailsDialog").close();
      toast(t("inbox_deleted"));
      await loadInboxes();
      await refreshTorStatus();
    } catch (error) { toast(humanError(error), true); }
  }
}

function openQr(inbox, kind) {
  const value = kind === "key" ? inbox.private_key : inbox.url;
  $("#qrLabel").textContent = t(kind === "key" ? "private_key" : "onion_address");
  $("#qrValue").textContent = value;
  $("#qrImage").src = `/api/inboxes/${inbox.id}/qr?kind=${kind}&format=svg`;
  $("#qrDownload").href = `/api/inboxes/${inbox.id}/qr?kind=${kind}&format=png&download=true`;
  $("#qrDownload").download = `oniondrop-${inbox.id}-${kind}.png`;
  $("#qrDialog").showModal();
}

async function refreshTorStatus() {
  if (!state.appLoaded) return;
  try {
    const data = await api("/api/tor/status");
    renderTorStatus(data.tor);
  } catch { /* status is secondary */ }
}

function renderTorStatus(tor) {
  const className = `tor-${tor.state}`;
  [$("#torPill"), $("#engineCard"), $("#torStatusPanel")].forEach((element) => {
    element.classList.remove("tor-connected", "tor-connecting", "tor-idle", "tor-error");
    element.classList.add(className);
  });
  const labelKey = `tor_${tor.state}`;
  $("#torPillText").textContent = t(labelKey);
  $("#sidebarTorText").textContent = t(labelKey);
  $("#torStatusTitle").textContent = t(`tor_${tor.state}_title`);
  $("#torStatusDescription").textContent = t(`tor_${tor.state}_description`);
  $("#torProgress").textContent = `${tor.progress || 0}%`;
  $("#torActiveServices").textContent = tor.active_services || 0;
  $("#torVersion").textContent = tor.tor_version || "—";
}

async function refreshFiles() {
  if (!state.selectedInbox) {
    state.files = [];
    renderFiles();
    return;
  }
  try {
    const data = await api(`/api/inboxes/${state.selectedInbox}/files`);
    state.files = data.files || [];
    state.selectedFiles = new Set([...state.selectedFiles].filter((path) => state.files.some((file) => file.path === path)));
    renderFiles();
    calculateMissingChecksums();
  } catch (error) { toast(humanError(error), true); }
}

function fileExtension(name) {
  const parts = name.split(".");
  return parts.length > 1 ? parts.pop().slice(0, 4) : "file";
}

function renderFiles() {
  const list = $("#fileList");
  $("#noFiles").classList.toggle("hidden", state.files.length > 0);
  list.innerHTML = state.files.map((file) => `
    <div class="file-row" data-path="${escapeHtml(file.path)}">
      <input class="file-check" type="checkbox" data-path="${escapeHtml(file.path)}" ${state.selectedFiles.has(file.path) ? "checked" : ""}>
      <div class="file-name"><span class="file-icon">${escapeHtml(fileExtension(file.name))}</span><span title="${escapeHtml(file.path)}">${escapeHtml(file.name)}</span></div>
      <span>${escapeHtml(formatDate(file.modified_at))}</span>
      <span>${escapeHtml(formatBytes(file.size))}</span>
      <div class="checksum ${file.sha256 ? "" : "pending"}"><code title="${escapeHtml(file.sha256 || t("calculating"))}">${escapeHtml(file.sha256 || t("calculating"))}</code>${file.sha256 ? `<button class="copy-button" data-copy="${file.sha256}">⧉</button>` : ""}</div>
      <div class="file-actions">
        ${file.previewable ? `<button data-file-action="preview" data-path="${escapeHtml(file.path)}" title="${escapeHtml(t("preview"))}">◫</button>` : ""}
        <a href="/api/inboxes/${state.selectedInbox}/files/download?path=${encodeURIComponent(file.path)}" download title="${escapeHtml(t("download_file"))}">↓</a>
        <button data-file-action="delete" data-path="${escapeHtml(file.path)}" title="${escapeHtml(t("delete"))}">×</button>
      </div>
    </div>`).join("");
  updateFileSelection();
}

async function calculateMissingChecksums() {
  const inboxId = state.selectedInbox;
  if (!inboxId) return;
  const queue = state.files.filter((file) => !file.sha256).map((file) => file.path);
  const worker = async () => {
    while (queue.length) {
      const path = queue.shift();
      try {
        const data = await api(`/api/inboxes/${inboxId}/files/sha256?path=${encodeURIComponent(path)}`);
        if (state.selectedInbox !== inboxId) continue;
        const file = state.files.find((item) => item.path === path);
        if (file) file.sha256 = data.sha256;
        const row = $$(".file-row").find((element) => element.dataset.path === path);
        if (row) {
          const checksum = $(".checksum", row);
          checksum.classList.remove("pending");
          checksum.innerHTML = `<code title="${data.sha256}">${data.sha256}</code><button class="copy-button" data-copy="${data.sha256}">⧉</button>`;
        }
      } catch { /* file may have changed while hashing */ }
    }
  };
  await Promise.all([worker(), worker()]);
}

function updateFileSelection() {
  const count = state.selectedFiles.size;
  $("#selectedFileCount").textContent = count ? t("files_selected", { count }) : t("no_files_selected");
  $("#downloadZipButton").disabled = count === 0;
  $("#selectAllFiles").checked = state.files.length > 0 && count === state.files.length;
  $("#selectAllFiles").indeterminate = count > 0 && count < state.files.length;
}

async function downloadSelectedZip() {
  if (!state.selectedFiles.size) return;
  try {
    const headers = new Headers({ "Content-Type": "application/json", "X-CSRF-Token": state.bootstrap.csrf_token });
    const response = await fetch(`/api/inboxes/${state.selectedInbox}/files/zip`, {
      method: "POST", headers, body: JSON.stringify({ paths: [...state.selectedFiles] }),
    });
    if (!response.ok) {
      const data = await response.json();
      const error = new Error(data.code || data.error);
      error.code = data.code || data.error;
      throw error;
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename\*?=(?:UTF-8''|\")?([^";]+)/i);
    const filename = match ? decodeURIComponent(match[1].replaceAll('"', "")) : "oniondrop-files.zip";
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    toast(t("zip_ready"));
  } catch (error) { toast(humanError(error), true); }
}

async function fileAction(action, path) {
  if (action === "preview") return openPreview(path);
  if (action === "delete") {
    if (!window.confirm(t("confirm_delete_file"))) return;
    try {
      await api(`/api/inboxes/${state.selectedInbox}/files?path=${encodeURIComponent(path)}`, { method: "DELETE" });
      state.selectedFiles.delete(path);
      toast(t("file_deleted"));
      await refreshFiles();
      await loadInboxes();
    } catch (error) { toast(humanError(error), true); }
  }
}

function makeTextPreview(content) {
  const pre = document.createElement("pre");
  pre.className = "preview-text";
  pre.textContent = content || "";
  return pre;
}

function makeTable(rows) {
  const wrap = document.createElement("div");
  wrap.className = "preview-table-wrap";
  const table = document.createElement("table");
  table.className = "preview-table";
  (rows || []).forEach((row, index) => {
    const tr = document.createElement("tr");
    (row || []).forEach((value) => {
      const cell = document.createElement(index === 0 ? "th" : "td");
      cell.textContent = value;
      tr.appendChild(cell);
    });
    table.appendChild(tr);
  });
  wrap.appendChild(table);
  return wrap;
}

async function openPreview(path) {
  try {
    const data = await api(`/api/inboxes/${state.selectedInbox}/files/preview?path=${encodeURIComponent(path)}`);
    const preview = data.preview;
    $("#previewTitle").textContent = preview.name;
    $("#previewMeta").textContent = `${preview.format || preview.mime} · ${formatBytes(preview.size)}`;
    $("#previewDownload").href = `/api/inboxes/${state.selectedInbox}/files/download?path=${encodeURIComponent(path)}`;
    $("#previewDownload").download = preview.name;
    const body = $("#previewBody");
    body.innerHTML = "";

    if (["image", "video", "audio", "pdf"].includes(preview.kind)) {
      const media = document.createElement("div");
      media.className = "preview-media";
      if (preview.kind === "image") {
        const image = document.createElement("img"); image.src = preview.inline_url; image.alt = preview.name; media.appendChild(image);
      } else if (preview.kind === "video") {
        const video = document.createElement("video"); video.src = preview.inline_url; video.controls = true; video.preload = "metadata"; media.appendChild(video);
      } else if (preview.kind === "audio") {
        const audio = document.createElement("audio"); audio.src = preview.inline_url; audio.controls = true; audio.preload = "metadata"; media.appendChild(audio);
      } else {
        const frame = document.createElement("iframe"); frame.src = preview.inline_url; frame.title = preview.name; media.appendChild(frame);
      }
      body.appendChild(media);
    } else if (["text", "document"].includes(preview.kind)) {
      body.appendChild(makeTextPreview(preview.content));
    } else if (preview.kind === "email") {
      const header = [
        `${t("subject")}: ${preview.metadata?.subject || ""}`,
        `${t("from")}: ${preview.metadata?.from || ""}`,
        `${t("to")}: ${preview.metadata?.to || ""}`,
        `${t("date")}: ${preview.metadata?.date || ""}`,
        "",
      ].join("\n");
      body.appendChild(makeTextPreview(header + (preview.content || "")));
    } else if (preview.kind === "table") {
      body.appendChild(makeTable(preview.rows));
    } else if (preview.kind === "spreadsheet") {
      const tabs = document.createElement("div"); tabs.className = "preview-tabs";
      const content = document.createElement("div");
      const showSheet = (index) => {
        content.innerHTML = "";
        content.appendChild(makeTable(preview.tables[index]?.rows || []));
        [...tabs.children].forEach((button, buttonIndex) => button.classList.toggle("active", buttonIndex === index));
      };
      (preview.tables || []).forEach((sheet, index) => {
        const button = document.createElement("button"); button.type = "button"; button.textContent = sheet.name;
        button.addEventListener("click", () => showSheet(index)); tabs.appendChild(button);
      });
      body.append(tabs, content); showSheet(0);
    } else if (preview.kind === "archive") {
      const list = document.createElement("ul"); list.className = "archive-list";
      (preview.items || []).forEach((item) => {
        const li = document.createElement("li");
        const name = document.createElement("span"); name.textContent = `${item.directory ? "▸ " : ""}${item.name}`;
        const size = document.createElement("span"); size.textContent = item.directory ? "" : formatBytes(item.size);
        li.append(name, size); list.appendChild(li);
      });
      body.appendChild(list);
    } else {
      const empty = document.createElement("div"); empty.className = "preview-empty"; empty.textContent = t("preview_not_available"); body.appendChild(empty);
    }
    $("#previewDialog").showModal();
  } catch (error) { toast(humanError(error), true); }
}

function loadSettingsForm() {
  if (!state.bootstrap) return;
  const form = $("#settingsForm");
  form.auth_enabled.checked = Boolean(state.bootstrap.auth_enabled);
  form.username.value = state.bootstrap.username || "admin";
  form.default_language.value = state.bootstrap.default_language || state.locale;
  form.new_password.value = "";
  form.current_password.value = "";
  $("#currentPasswordLabel").classList.toggle("hidden", !state.bootstrap.auth_enabled);
  updateLanguagePickers();
}

async function saveSettings(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const data = await api("/api/settings", {
      method: "PATCH",
      json: {
        auth_enabled: form.auth_enabled.checked,
        username: form.username.value,
        new_password: form.new_password.value,
        current_password: form.current_password.value,
        default_language: form.default_language.value,
      },
    });
    Object.assign(state.bootstrap, data.settings);
    $("#logoutButton").classList.toggle("hidden", !state.bootstrap.auth_enabled);
    toast(t("settings_saved"));
    await setLocale(data.settings.default_language);
    if (state.bootstrap.auth_enabled && !state.bootstrap.authenticated) await refreshBootstrap();
    loadSettingsForm();
  } catch (error) { toast(humanError(error), true); }
}

function renderDynamicViews() {
  if (!state.appLoaded) return;
  renderInboxes();
  renderFiles();
  if (state.currentView) switchView(state.currentView);
}

function bindEvents() {
  document.addEventListener("change", async (event) => {
    if (event.target.matches(".language-select")) {
      await setLocale(event.target.value);
      $$(".language-select").forEach((select) => { select.value = event.target.value; });
    }
    if (event.target.matches("#setupForm [name=auth_enabled]")) {
      $("#setupCredentials").classList.toggle("hidden", !event.target.checked);
      $("#setupForm [name=password]").required = event.target.checked;
    }
    if (event.target.matches("#fileInboxSelect")) {
      state.selectedInbox = event.target.value;
      state.selectedFiles.clear();
      await refreshFiles();
    }
    if (event.target.matches(".file-check")) {
      if (event.target.checked) state.selectedFiles.add(event.target.dataset.path);
      else state.selectedFiles.delete(event.target.dataset.path);
      updateFileSelection();
    }
    if (event.target.matches("#selectAllFiles")) {
      state.selectedFiles = event.target.checked ? new Set(state.files.map((file) => file.path)) : new Set();
      renderFiles();
    }
    if (event.target.matches("#settingsForm [name=auth_enabled]")) {
      $("#currentPasswordLabel").classList.toggle("hidden", !state.bootstrap.auth_enabled);
    }
  });

  document.addEventListener("click", async (event) => {
    const languageOption = event.target.closest("[data-language-option]");
    if (languageOption) {
      const picker = languageOption.closest(".language-picker");
      const select = $(".language-select", picker);
      select.value = languageOption.dataset.languageOption;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      closeLanguagePickers();
      return;
    }
    const languageToggle = event.target.closest("[data-language-toggle]");
    if (languageToggle) {
      const picker = languageToggle.closest(".language-picker");
      const opening = !picker.classList.contains("open");
      closeLanguagePickers(picker);
      picker.classList.toggle("open", opening);
      languageToggle.setAttribute("aria-expanded", String(opening));
      return;
    }
    if (!event.target.closest(".language-picker")) closeLanguagePickers();

    const nav = event.target.closest(".nav-item");
    if (nav) return switchView(nav.dataset.view);
    if (event.target.closest("[data-create]") || event.target.closest("#createButton")) return $("#createDialog").showModal();
    if (event.target.closest("#importButton")) return $("#importDialog").showModal();
    const close = event.target.closest("[data-close]");
    if (close) return close.closest("dialog")?.close();
    const copy = event.target.closest("[data-copy], [data-copy-inbox]");
    if (copy) {
      let value = copy.dataset.copy || "";
      if (copy.dataset.copyInbox) {
        const inbox = state.inboxes.find((item) => item.id === copy.dataset.copyInbox);
        const field = copy.dataset.copyField;
        if (inbox && ["url", "private_key"].includes(field)) value = inbox[field] || "";
      }
      return copyText(value);
    }
    const action = event.target.closest("[data-action]");
    if (action) return inboxAction(action.dataset.action, action.dataset.id);
    const detail = event.target.closest("[data-detail-action]");
    if (detail) return detailAction(detail.dataset.detailAction, detail.dataset.id);
    const file = event.target.closest("[data-file-action]");
    if (file) return fileAction(file.dataset.fileAction, file.dataset.path);
    if (event.target.closest("#refreshButton")) { await loadInboxes(); await refreshTorStatus(); }
    if (event.target.closest("#downloadZipButton")) await downloadSelectedZip();
    if (event.target.closest("#logoutButton")) {
      try {
        const data = await api("/api/logout", { method: "POST" });
        state.bootstrap.csrf_token = data.csrf_token;
        state.bootstrap.authenticated = false;
        showAuth("login");
      } catch (error) { toast(humanError(error), true); }
    }
    if (event.target.closest(".brand")) { event.preventDefault(); switchView("inboxes"); }
  });

  $("#setupForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const data = await api("/api/setup", {
        method: "POST",
        json: {
          auth_enabled: form.auth_enabled.checked,
          username: form.username.value || "admin",
          password: form.password.value,
          default_language: form.default_language.value,
        },
      });
      state.bootstrap.csrf_token = data.csrf_token;
      toast(t("setup_complete"));
      await refreshBootstrap();
    } catch (error) { toast(humanError(error), true); }
  });

  $("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const data = await api("/api/login", { method: "POST", json: { username: form.username.value, password: form.password.value } });
      state.bootstrap.csrf_token = data.csrf_token;
      form.password.value = "";
      await refreshBootstrap();
    } catch (error) { toast(humanError(error), true); }
  });

  $("#createForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await api("/api/inboxes", {
        method: "POST",
        json: {
          name: form.name.value,
          description: form.description.value,
          allow_files: form.allow_files.checked,
          allow_text: form.allow_text.checked,
          public: !form.private.checked,
          autostart: form.autostart.checked,
          expires_hours: form.expires_hours.value,
          quota_mb: form.quota_mb.value,
          start_now: true,
        },
      });
      form.reset();
      form.allow_files.checked = true;
      form.allow_text.checked = true;
      form.private.checked = true;
      form.autostart.checked = true;
      $("#createDialog").close();
      toast(t("inbox_created"));
      await loadInboxes();
      await refreshTorStatus();
    } catch (error) { toast(humanError(error), true); }
  });

  $("#importForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const body = new FormData(form);
    body.set("autostart", "true");
    try {
      await api("/api/import", { method: "POST", body });
      form.reset();
      $("#importDialog").close();
      toast(t("service_imported"));
      await loadInboxes();
      await refreshTorStatus();
    } catch (error) { toast(humanError(error), true); }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeLanguagePickers();
  });

  $("#settingsForm").addEventListener("submit", saveSettings);
}

async function init() {
  try {
    await setLocale(initialLocale(), false);
    bindEvents();
    await refreshBootstrap();
  } catch (error) {
    console.error(error);
    document.body.textContent = "OnionDrop could not start.";
  }
}

document.addEventListener("DOMContentLoaded", init);
