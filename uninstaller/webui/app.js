/* =====================================================================
   Linux Uninstaller — premium web UI logic
   ===================================================================== */
"use strict";

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = {
  managers: [],
  packages: [],
  selected: null,       // {name, manager}
  leftovers: [],
  orphans: [],
  reclaimed: 0,
};

/* =====================================================================
   API
   ===================================================================== */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

/* =====================================================================
   UI helpers
   ===================================================================== */
function toast(kind, title, msg = "", ms = 4200) {
  const ico = {
    ok:   '<svg viewBox="0 0 24 24" stroke="currentColor"><path d="M20 6L9 17l-5-5"/></svg>',
    err:  '<svg viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>',
    info: '<svg viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
  }[kind] || "";
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `
    <div class="toast-ico">${ico}</div>
    <div class="toast-body">
      <div class="toast-title">${esc(title)}</div>
      ${msg ? `<div class="toast-msg">${esc(msg)}</div>` : ""}
    </div>`;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 320); }, ms);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function busy(on) {
  $("#topbar").classList.toggle("on", on);
  document.body.style.cursor = on ? "progress" : "";
}

function human(n) {
  if (!n) return "0 B";
  const u = ["B", "KiB", "MiB", "GiB", "TiB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${i === 0 ? n : n.toFixed(1)} ${u[i]}`;
}

/* modal — returns a Promise<boolean> */
function confirmModal({ title, msg, paths = [], okText = "Confirm", danger = true }) {
  return new Promise(resolve => {
    const root = $("#modalRoot");
    root.innerHTML = `
      <div class="modal-backdrop">
        <div class="modal glass">
          <h2>${esc(title)}</h2>
          <p class="msg">${esc(msg)}</p>
          ${paths.length ? `<div class="modal-paths">${paths.map(p => esc(p)).join("<br>")}</div>` : ""}
          <div class="modal-actions">
            <button class="btn ghost" data-act="cancel">Cancel</button>
            <button class="btn ${danger ? "danger" : "primary"}" data-act="ok">${esc(okText)}</button>
          </div>
        </div>
      </div>`;
    const close = val => { root.innerHTML = ""; resolve(val); };
    root.querySelector('[data-act="cancel"]').onclick = () => close(false);
    root.querySelector('[data-act="ok"]').onclick = () => close(true);
    root.querySelector(".modal-backdrop").onclick = e => {
      if (e.target.classList.contains("modal-backdrop")) close(false);
    };
    root.querySelector('[data-act="ok"]').focus();
  });
}

/* =====================================================================
   Navigation
   ===================================================================== */
function gotoPage(name, push = true) {
  $$(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.page === name));
  $$(".page").forEach(p => p.classList.toggle("active", p.id === `page-${name}`));
  if (push && location.hash !== `#${name}`) location.hash = name;
  if (name === "cleaner") loadCleanSizes();
  if (name === "about") updateAboutStats();
}

/* =====================================================================
   APPS PAGE
   ===================================================================== */
async function loadPackages() {
  busy(true);
  try {
    const q = $("#search").value.trim();
    const mgr = $("#mgrFilter").value;
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (mgr) params.set("manager", mgr);
    const data = await api(`/api/packages?${params}`);
    state.packages = data.packages;
    renderLimit = 250;
    renderPackages();
    $("#pkgCount").textContent = `${data.count} applications installed`;
  } catch (e) {
    toast("err", "Failed to load packages", e.message);
  } finally { busy(false); }
}

let renderLimit = 250;

function renderPackages() {
  const body = $("#pkgBody");
  if (!state.packages.length) {
    body.innerHTML = `<tr><td colspan="4"><div class="empty-state slim"><p>No applications match</p></div></td></tr>`;
    return;
  }
  const slice = state.packages.slice(0, renderLimit);
  let html = slice.map((p, i) => `
    <tr data-i="${i}" class="${state.selected && state.selected.name === p.name ? "sel" : ""}">
      <td class="pkg-name">${esc(p.name)}</td>
      <td class="mono">${esc(p.version)}</td>
      <td class="r">${esc(p.size_h)}</td>
      <td><span class="chip ${esc(p.manager)}">${esc(p.manager)}</span></td>
    </tr>`).join("");
  if (state.packages.length > renderLimit) {
    html += `<tr class="more-row"><td colspan="4" class="more-cell">
      Showing ${renderLimit.toLocaleString()} of ${state.packages.length.toLocaleString()} — scroll for more</td></tr>`;
  }
  body.innerHTML = html;

  $$("#pkgBody tr[data-i]").forEach(tr => {
    tr.onclick = () => selectPackage(state.packages[+tr.dataset.i]);
  });
}

/* infinite scroll: grow the rendered slice near the bottom */
function initPkgScroll() {
  const wrap = $("#pkgBody").closest(".table-wrap");
  wrap.addEventListener("scroll", () => {
    if (wrap.scrollTop + wrap.clientHeight >= wrap.scrollHeight - 220 &&
        renderLimit < state.packages.length) {
      renderLimit += 250;
      renderPackages();
    }
  });
}

async function selectPackage(pkg) {
  state.selected = pkg;
  state.leftovers = [];
  $$("#pkgBody tr").forEach(tr => tr.classList.remove("sel"));
  const row = $(`#pkgBody tr[data-i="${state.packages.indexOf(pkg)}"]`);
  if (row) row.classList.add("sel");

  $("#selName").textContent = pkg.name;
  $("#selMeta").textContent = `${pkg.version} · via ${pkg.manager} · scanning leftovers…`;
  $("#uninstallBtn").disabled = true;
  const list = $("#leftoverList");
  list.innerHTML = `<div class="empty-state"><p>Scanning for leftover files…</p></div>`;

  try {
    const data = await api(`/api/leftovers?name=${encodeURIComponent(pkg.name)}`);
    if (!state.selected || state.selected.name !== pkg.name) return; // stale
    state.leftovers = data.items;
    $("#selMeta").textContent =
      `${pkg.version} · via ${pkg.manager} · ${data.count} leftover item(s) · ${data.total_h}`;
    $("#uninstallBtn").disabled = false;
    if (!data.items.length) {
      list.innerHTML = `<div class="empty-state"><p>✓ No leftover files found</p></div>`;
      return;
    }
    list.innerHTML = data.items.map((it, i) => `
      <div class="lo-item" style="animation-delay:${Math.min(i * 22, 400)}ms">
        <span class="lo-kind ${esc(it.kind)}">${esc(it.kind)}</span>
        <span class="lo-path mono" title="${esc(it.path)}">${esc(it.path)}</span>
        <span class="lo-size">${esc(it.size_h)}</span>
      </div>`).join("");
  } catch (e) {
    list.innerHTML = `<div class="empty-state"><p>Scan failed: ${esc(e.message)}</p></div>`;
    toast("err", "Leftover scan failed", e.message);
  }
}

async function doUninstall() {
  const pkg = state.selected;
  if (!pkg) return;
  const total = state.leftovers.reduce((s, i) => s + i.size, 0);
  const paths = state.leftovers.slice(0, 30).map(i => `${i.path}  (${i.size_h})`);
  if (state.leftovers.length > 30)
    paths.push(`… and ${state.leftovers.length - 30} more`);

  const ok = await confirmModal({
    title: `Uninstall “${pkg.name}”?`,
    msg: state.leftovers.length
      ? `This removes the package via ${pkg.manager} AND deletes ${state.leftovers.length} leftover item(s) (${human(total)}). This cannot be undone.`
      : `This removes the package via ${pkg.manager}. No leftover files were found.`,
    paths,
    okText: "Uninstall & Clean",
  });
  if (!ok) return;

  busy(true);
  $("#uninstallBtn").disabled = true;
  try {
    const r = await api("/api/uninstall", {
      method: "POST",
      body: { name: pkg.name, manager: pkg.manager, clean: true },
    });
    if (r.success) {
      addReclaimed(r.freed);
      toast("ok", "Uninstalled", `${r.message}${r.cleaned ? ` · freed ${r.freed_h}` : ""}`, 6000);
      state.selected = null;
      $("#selName").textContent = "Select an app";
      $("#selMeta").textContent = "Leftover files will appear here";
      $("#leftoverList").innerHTML =
        `<div class="empty-state"><svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg><p>Pick an app to scan for leftover files</p></div>`;
      await loadPackages();
    } else {
      toast("err", "Uninstall failed", r.message, 7000);
      $("#uninstallBtn").disabled = false;
    }
  } catch (e) {
    toast("err", "Uninstall failed", e.message, 7000);
    $("#uninstallBtn").disabled = false;
  } finally { busy(false); }
}

/* =====================================================================
   ORPHANS PAGE
   ===================================================================== */
async function scanOrphans() {
  busy(true);
  $("#scanBtn").disabled = true;
  $("#orphanInfo").textContent = "Scanning (this can take a minute)…";
  try {
    const data = await api("/api/orphans");
    state.orphans = data.apps;
    renderOrphans();
    $("#orphanInfo").textContent =
      `Found ${data.apps.length} orphaned app(s), total ${data.total_h}`;
    const badge = $("#orphanBadge");
    if (data.apps.length) {
      badge.textContent = data.apps.length;
      badge.hidden = false;
    } else badge.hidden = true;
    toast("ok", "Scan complete",
      data.apps.length ? `${data.apps.length} orphans · ${data.total_h}` : "No orphans found");
  } catch (e) {
    toast("err", "Scan failed", e.message);
    $("#orphanInfo").textContent = "Scan failed";
  } finally {
    busy(false);
    $("#scanBtn").disabled = false;
  }
}

function renderOrphans() {
  const body = $("#orphanBody");
  if (!state.orphans.length) {
    body.innerHTML = `<tr><td colspan="4"><div class="empty-state slim"><p>✓ No orphaned app data found</p></div></td></tr>`;
    $("#cleanOrphansBtn").disabled = true;
    return;
  }
  body.innerHTML = state.orphans.map((a, i) => `
    <tr data-i="${i}">
      <td class="c"><input type="checkbox" data-check="${i}"></td>
      <td class="pkg-name">${esc(a.name)}</td>
      <td class="r">${esc(a.size_h)}</td>
      <td class="r">${a.items.length}</td>
    </tr>`).join("");

  $$("#orphanBody input[type=checkbox]").forEach(cb => {
    cb.onchange = () => {
      const rows = $$("#orphanBody input[type=checkbox]:checked");
      $("#cleanOrphansBtn").disabled = !rows.length;
      showOrphanPaths(rows.map(c => +c.dataset.check));
    };
  });
  $("#orphanAll").checked = false;
  $("#cleanOrphansBtn").disabled = true;
  $("#orphanPaths").innerHTML = "";
}

function showOrphanPaths(idxs) {
  const box = $("#orphanPaths");
  if (!idxs.length) {
    box.innerHTML = "";
    $("#orphanPathInfo").textContent = "Select rows to preview";
    return;
  }
  const total = idxs.reduce((s, i) => s + state.orphans[i].size, 0);
  $("#orphanPathInfo").textContent = `${idxs.length} selected · ${human(total)}`;
  box.innerHTML = idxs.map(i => {
    const a = state.orphans[i];
    return `<div class="lo-item" style="margin-bottom:7px">
      <span class="lo-kind data">${a.items.length}</span>
      <span class="lo-path mono" title="${esc(a.name)}">${esc(a.name)}</span>
      <span class="lo-size">${esc(a.size_h)}</span>
    </div>` +
      a.items.slice(0, 8).map(it => `
      <div class="lo-item" style="margin-left:16px;opacity:.85">
        <span class="lo-kind ${esc(it.kind)}">${esc(it.kind)}</span>
        <span class="lo-path mono" title="${esc(it.path)}">${esc(it.path)}</span>
        <span class="lo-size">${esc(it.size_h)}</span>
      </div>`).join("") +
      (a.items.length > 8 ? `<div class="lo-item" style="margin-left:16px"><span class="lo-path" style="color:var(--muted)">… and ${a.items.length - 8} more</span></div>` : "");
  }).join("");
}

async function cleanSelectedOrphans() {
  const idxs = $$("#orphanBody input[type=checkbox]:checked").map(c => +c.dataset.check);
  if (!idxs.length) return;
  const names = idxs.map(i => state.orphans[i].name);
  const total = idxs.reduce((s, i) => s + state.orphans[i].size, 0);

  const ok = await confirmModal({
    title: `Delete ${names.length} orphaned app(s)?`,
    msg: `ALL leftover data for these apps will be permanently deleted (${human(total)}).\n\n${names.slice(0, 8).join(", ")}${names.length > 8 ? " …" : ""}`,
    okText: "Delete permanently",
  });
  if (!ok) return;

  busy(true);
  try {
    const r = await api("/api/clean-orphans", { method: "POST", body: { names } });
    addReclaimed(r.freed);
    toast("ok", "Cleanup complete", `Removed ${r.removed} item(s) · freed ${r.freed_h}`, 6000);
    // remove cleaned rows
    state.orphans = state.orphans.filter((_, i) => !idxs.includes(i));
    renderOrphans();
    $("#orphanInfo").textContent =
      state.orphans.length
        ? `${state.orphans.length} orphaned app(s) remaining`
        : "✓ All orphans cleaned";
    if (!state.orphans.length) $("#orphanBadge").hidden = true;
    $("#orphanPaths").innerHTML = "";
  } catch (e) {
    toast("err", "Cleanup failed", e.message);
  } finally { busy(false); }
}

/* =====================================================================
   CLEANER PAGE
   ===================================================================== */
async function loadCleanSizes() {
  try {
    const d = await api("/api/clean-sizes");
    Object.entries(d).forEach(([k, v]) => {
      const el = $(`[data-size="${k}"]`);
      if (el) el.textContent = v.h;
    });
  } catch (e) {
    console.error(e);
  }
}

async function doClean(kind, label) {
  const ok = await confirmModal({
    title: `Clean ${label}?`,
    msg: kind === "trash"
      ? "Everything in the trash will be permanently deleted."
      : `Cached and temporary files for ${label} will be removed. Apps will rebuild their caches as needed.`,
    okText: "Clean now",
  });
  if (!ok) return;

  busy(true);
  try {
    const r = await api("/api/clean", { method: "POST", body: { kind } });
    addReclaimed(r.freed);
    if (kind === "syscache") toast("ok", "Package caches cleared");
    else toast("ok", "Cleaned", `Removed ${r.removed} item(s) · freed ${r.freed_h}`, 6000);
    await loadCleanSizes();
  } catch (e) {
    toast("err", "Clean failed", e.message);
  } finally { busy(false); }
}

/* =====================================================================
   About
   ===================================================================== */
function updateAboutStats() {
  $("#statPkgs").textContent = state.packages.length
    ? state.packages.length.toLocaleString() : "—";
  $("#statMgrs").textContent = state.managers.length || "—";
  $("#statFreed").textContent = human(state.reclaimed);
  const list = $("#mgrList");
  list.innerHTML = state.managers.map(m => `
    <div class="mgr-row">
      <span class="mgr-dot"></span>
      <span class="mono">${esc(m.name)}</span>
      <span class="sub">${esc(m.display_name)}</span>
    </div>`).join("") || `<p class="sub">None detected</p>`;
}

/* =====================================================================
   Reclaimed counter
   ===================================================================== */
function addReclaimed(bytes) {
  state.reclaimed += bytes || 0;
  $("#reclaimed").textContent = human(state.reclaimed);
  $("#statFreed").textContent = human(state.reclaimed);
}

/* =====================================================================
   Init
   ===================================================================== */
async function init() {
  // nav
  $$(".nav-item").forEach(b => b.onclick = () => gotoPage(b.dataset.page));

  // apps
  $("#search").addEventListener("input", debounce(loadPackages, 260));
  $("#mgrFilter").addEventListener("change", loadPackages);
  $("#refreshBtn").onclick = loadPackages;
  $("#uninstallBtn").onclick = doUninstall;

  // orphans
  $("#scanBtn").onclick = scanOrphans;
  $("#cleanOrphansBtn").onclick = cleanSelectedOrphans;
  $("#orphanAll").onchange = e => {
    $$("#orphanBody input[type=checkbox]").forEach(cb => { cb.checked = e.target.checked; });
    const rows = $$("#orphanBody input[type=checkbox]:checked");
    $("#cleanOrphansBtn").disabled = !rows.length;
    showOrphanPaths(rows.map(c => +c.dataset.check));
  };

  // cleaner
  $$("[data-clean]").forEach(btn => {
    const labels = { cache: "the user cache", trash: "the trash",
                     temp: "temp files", syscache: "package caches" };
    btn.onclick = () => doClean(btn.dataset.clean, labels[btn.dataset.clean]);
  });

  initPkgScroll();

  // status
  busy(true);
  try {
    const st = await api("/api/status");
    state.managers = st.managers;
    $("#brandVersion").textContent = `v${st.version}`;
    $("#aboutVer").textContent = `Version ${st.version}`;
    const sel = $("#mgrFilter");
    st.managers.forEach(m => {
      const o = document.createElement("option");
      o.value = m.name; o.textContent = m.display_name;
      sel.appendChild(o);
    });
    await loadPackages();
  } catch (e) {
    toast("err", "Cannot reach backend", e.message);
  } finally { busy(false); }

  // deep links: #apps | #orphans | #cleaner | #about
  window.addEventListener("hashchange", () => {
    const p = location.hash.slice(1);
    if (["apps", "orphans", "cleaner", "about"].includes(p)) gotoPage(p, false);
  });
  const initial = location.hash.slice(1);
  if (["apps", "orphans", "cleaner", "about"].includes(initial))
    gotoPage(initial, false);
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

init();
