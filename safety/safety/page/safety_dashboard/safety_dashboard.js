frappe.pages["safety-dashboard"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: "Safety Dashboard",
    single_column: true
  });

  inject_css(wrapper);

  const root = document.createElement("div");
  root.className = "isd-wrap";
  page.main[0].appendChild(root);

  let lastData = null;

  page.add_inner_button(__("Export PNG"), () => export_png(root), __("Export"));
  page.add_inner_button(__("Export Excel"), () => export_excel(), __("Export"));

  // ---------------------------
  // On-the-hour refresh helpers
  // ---------------------------
  let refreshTimer = null;

  function ms_until_next_hour() {
    const now = new Date();
    const next = new Date(now);
    next.setMinutes(0, 0, 0);
    next.setHours(now.getHours() + 1);
    return Math.max(0, next.getTime() - now.getTime());
  }

  function schedule_on_the_hour_refresh(loadFn) {
    // Clear any existing timer(s)
    if (refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }

    const wait = ms_until_next_hour();

    // First tick aligns to next whole hour,
    // then we re-schedule again so it stays aligned even if load time varies.
    refreshTimer = setTimeout(async () => {
      try {
        await loadFn();
      } finally {
        schedule_on_the_hour_refresh(loadFn);
      }
    }, wait);
  }

  async function load() {
    root.innerHTML = `<div class="isd-loading">Loading…</div>`;

    const r = await frappe.call({
      method: "safety.safety.report.site_safe_days.site_safe_days.get_today_snapshot",
      args: { filters: {} }
    });

    const payload = r.message || {};
    lastData = payload;
    const rows = payload.rows || {};
    const complexBySite = payload.complex_by_site || {};
    const colorBySite = payload.color_by_site || {};
    const companyColor = (payload.company_colour || "").trim();

    const companyRow = rows["Company"] || null;

    // Group sites by complex
    const groups = {};
    Object.keys(rows)
      .filter(site => site && site !== "Company")
      .forEach(site => {
        const complex = (complexBySite[site] || "Other").toString().trim() || "Other";
        if (!groups[complex]) groups[complex] = [];
        groups[complex].push(site);
      });

    // Stable ordering
    const complexNames = Object.keys(groups).sort((a, b) => a.localeCompare(b));
    complexNames.forEach(c => groups[c].sort((a, b) => a.localeCompare(b)));

    // Render
    root.innerHTML = "";

    const top = document.createElement("div");
    top.className = "isd-top";
    top.appendChild(render_company_card(companyRow, companyColor));
    root.appendChild(top);

    const grid = document.createElement("div");
    grid.className = "isd-grid-2";
    root.appendChild(grid);

    const left = document.createElement("div");
    left.className = "isd-col";
    const right = document.createElement("div");
    right.className = "isd-col";

    complexNames.forEach((complex, idx) => {
      const col = (idx % 2 === 0) ? left : right;
      col.appendChild(render_heading(complex.toUpperCase()));

      (groups[complex] || []).forEach(site => {
        const row = rows[site] || {};
        const siteColor = (colorBySite[site] || "").trim();
        col.appendChild(render_site_card(site, row, siteColor));
      });
    });

    grid.appendChild(left);
    grid.appendChild(render_divider());
    grid.appendChild(right);

    if (!left.children.length || !right.children.length) {
      grid.classList.add("isd-no-divider");
    }
  }

  // Initial load immediately
  load();

  // Refresh exactly on the hour (e.g., 10:00, 11:00, 12:00...)
  schedule_on_the_hour_refresh(load);

  // Optional: clean up timers when navigating away
  if (page && page.wrapper) {
    $(page.wrapper).on("page-change", function () {
      if (refreshTimer) clearTimeout(refreshTimer);
    });
  }
};


// ---------------------------
// Rendering helpers
// ---------------------------
function render_heading(text) {
  const h = document.createElement("div");
  h.className = "isd-heading";
  h.innerText = text;
  return h;
}

function render_divider() {
  const d = document.createElement("div");
  d.className = "isd-divider";
  return d;
}

function render_company_card(row, companyColor) {
  const card = document.createElement("div");
  card.className = "isd-card isd-company";

  const accent = (companyColor && is_valid_hex(companyColor)) ? companyColor : "#ef4444";
  card.style.borderTopColor = accent;

  const ltifrTarget = row?.ltifr_target ?? "";
  const ltifrActual = (row?.ltifr ?? "—");
  const scratchFree = row?.tif_days ?? "—";

  const ltiFree = row?.lti_free_days ?? "";
  const mtcFree = row?.mtc_days ?? "";
  const facFree = row?.fac_days ?? "";
  const pdiFree = row?.pdi_days ?? "";

  card.innerHTML = build_card_html(
    "Isambane Mining",
    ltifrTarget,
    ltifrActual,
    scratchFree,
    ltiFree,
    mtcFree,
    facFree,
    pdiFree
  );
  return card;
}

function render_site_card(site, row, siteColor) {
  const card = document.createElement("div");
  card.className = "isd-card";

  const accent = (siteColor && is_valid_hex(siteColor)) ? siteColor : "#3b82f6";
  card.style.borderTopColor = accent;

  const ltifrTarget = row?.ltifr_target ?? "";
  const ltifrActual = (row?.ltifr ?? "—");
  const scratchFree = row?.tif_days ?? "—";

  const ltiFree = row?.lti_free_days ?? "";
  const mtcFree = row?.mtc_days ?? "";
  const facFree = row?.fac_days ?? "";
  const pdiFree = row?.pdi_days ?? "";

  card.innerHTML = build_card_html(
    site,
    ltifrTarget,
    ltifrActual,
    scratchFree,
    ltiFree,
    mtcFree,
    facFree,
    pdiFree
  );
  return card;
}

function ltifr_tone(target, actual) {
  const t = Number(target);
  const a = Number(actual);
  if (!Number.isFinite(t) || !Number.isFinite(a) || target === "" || actual === "" || actual === "—") {
    return "isd-kpi--neutral";
  }
  return a <= t ? "isd-kpi--good" : "isd-kpi--bad";
}

function build_card_html(siteName, ltifrTarget, ltifrActual, scratchFree, ltiFree, mtcFree, facFree, pdiFree) {
  const actualTone = ltifr_tone(ltifrTarget, ltifrActual);

  return `
    <div class="isd-card-inner">

      <div class="isd-sitebar">
        <div class="isd-eyebrow">Site</div>
        <div class="isd-site-name">${frappe.utils.escape_html(siteName)}</div>
      </div>

      <div class="isd-kpi-row">
        <div class="isd-kpi isd-kpi--neutral">
          <div class="isd-kpi-label">LTIFR Target</div>
          <div class="isd-kpi-val">${ltifrTarget}</div>
        </div>
        <div class="isd-kpi ${actualTone}">
          <div class="isd-kpi-label">LTIFR Actual</div>
          <div class="isd-kpi-val">${ltifrActual}</div>
        </div>
        <div class="isd-kpi isd-kpi--neutral">
          <div class="isd-kpi-label">Scratch Free Days</div>
          <div class="isd-kpi-val">${scratchFree}</div>
        </div>
      </div>

      <div class="isd-safe-title">Safe Days</div>

      <div class="isd-safe-row">
        <div class="isd-safe-tile">
          <div class="isd-safe-h">LTI</div>
          <div class="isd-safe-v">${ltiFree}</div>
        </div>
        <div class="isd-safe-tile">
          <div class="isd-safe-h">MTC</div>
          <div class="isd-safe-v">${mtcFree}</div>
        </div>
        <div class="isd-safe-tile">
          <div class="isd-safe-h">FA</div>
          <div class="isd-safe-v">${facFree}</div>
        </div>
        <div class="isd-safe-tile">
          <div class="isd-safe-h">Property Damage - TMM</div>
          <div class="isd-safe-v">${pdiFree}</div>
        </div>
      </div>

    </div>
  `;
}

function is_valid_hex(s) {
  return /^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/.test(s);
}


// ---------------------------
// PNG export (html2canvas)
// ---------------------------
async function ensure_html2canvas() {
  if (window.html2canvas) {
    return;
  }

  await frappe.require("/assets/safety/js/vendor/html2canvas.min.js");

  if (!window.html2canvas) {
    throw new Error(__("html2canvas could not be loaded."));
  }
}

async function export_png(root) {
  if (!root || !root.children.length) {
    frappe.msgprint(__("Wait for the dashboard to finish loading before exporting."));
    return;
  }

  // .isd-wrap paints its own opaque page background (var(--isd-page-bg)) for
  // the on-screen view - html2canvas's backgroundColor:null option only
  // controls the canvas's own base fill, it doesn't override a background
  // the captured element itself sets. So the page background is dropped for
  // the duration of the capture only, then restored.
  const previousBackground = root.style.background;
  root.style.background = "transparent";

  try {
    await ensure_html2canvas();
    const canvas = await window.html2canvas(root, {
      backgroundColor: null,
      scale: 2,
      useCORS: true,
      logging: false,
    });
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error(__("PNG creation failed.")))), "image/png");
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `Safety-Dashboard-${frappe.datetime.now_date()}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    frappe.msgprint({ title: __("Export failed"), message: error.message, indicator: "red" });
  } finally {
    root.style.background = previousBackground;
  }
}


// ---------------------------
// Excel export
// ---------------------------
function export_excel() {
  window.open(
    "/api/method/safety.safety.page.safety_dashboard.safety_dashboard.download_snapshot_xlsx",
    "_blank"
  );
}


// ---------------------------
// CSS Injection
// ---------------------------
function inject_css(wrapper) {
  const style = document.createElement("style");
  style.textContent = `
    :root{
      --isd-page-bg: #f5f2f2;
      --isd-ink: #172033;
      --isd-muted: #64748b;
      --isd-border: #d7dee8;
      --isd-tile-bg: #f8fafc;
      --isd-radius: 10px;
    }

    .isd-wrap, .isd-wrap * {
      font-family: "Segoe UI", Inter, Roboto, Arial, system-ui, -apple-system;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      text-rendering: geometricPrecision;
      box-sizing: border-box;
    }

    .isd-wrap { padding: 16px; background: var(--isd-page-bg); }

    .isd-loading { padding: 12px; font-weight: 700; text-align: center; color: var(--isd-ink); font-size: 13px; }

    .isd-top { display: flex; justify-content: center; margin-bottom: 12px; }

    .isd-grid-2 {
      display: grid;
      grid-template-columns: 1fr 1px 1fr;
      gap: 14px;
      align-items: start;
    }
    .isd-grid-2.isd-no-divider { grid-template-columns: 1fr; }
    .isd-grid-2.isd-no-divider .isd-divider { display: none; }

    .isd-divider { width: 1px; background: var(--isd-border); height: 100%; margin: 0 auto; }

    .isd-col { display: grid; gap: 14px; }

    .isd-heading {
      text-align: center;
      font-weight: 800;
      letter-spacing: .08em;
      color: var(--isd-muted);
      margin: 4px 0 -2px;
      font-size: 12px;
      text-transform: uppercase;
    }

    .isd-card {
      background: #ffffff;
      border: 1px solid var(--isd-border);
      border-top: 4px solid #3b82f6;
      padding: 12px;
      border-radius: var(--isd-radius);
      box-shadow: 0 1px 2px rgba(23, 32, 51, 0.06);
    }

    .isd-card.isd-company { border-top-width: 6px; }

    .isd-card, .isd-card * { text-align: center; }

    .isd-card-inner { display: grid; gap: 8px; }

    .isd-sitebar { display: grid; gap: 2px; }

    .isd-eyebrow {
      font-size: 10px;
      font-weight: 800;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--isd-muted);
    }

    .isd-site-name{
      font-weight: 800;
      font-size: 16px;
      color: var(--isd-ink);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .isd-company .isd-site-name { font-size: 19px; }

    .isd-kpi-row {
      display: grid;
      grid-template-columns: repeat(3, minmax(120px, 1fr));
      gap: 8px;
      margin: 0;
    }

    .isd-kpi {
      background: var(--isd-tile-bg);
      border: 1px solid var(--isd-border);
      border-top: 3px solid #3b82f6;
      padding: 7px 6px;
      border-radius: 8px;
      overflow: hidden;
    }

    .isd-kpi--neutral { border-top-color: #3b82f6; }
    .isd-kpi--good { border-top-color: #22c55e; }
    .isd-kpi--bad { border-top-color: #ef4444; }

    .isd-kpi-label {
      font-size: 10px;
      font-weight: 800;
      letter-spacing: .04em;
      text-transform: uppercase;
      color: var(--isd-muted);
      margin-bottom: 4px;
      line-height: 1.15;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .isd-kpi-val {
      font-size: 17px;
      font-weight: 800;
      color: var(--isd-ink);
    }

    .isd-safe-title {
      width: fit-content;
      margin: 2px auto 0;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--isd-muted);
    }

    .isd-safe-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
    }

    .isd-safe-tile {
      background: var(--isd-tile-bg);
      border: 1px solid var(--isd-border);
      border-radius: 8px;
      padding: 6px 4px;
      min-width: 0;
    }

    .isd-safe-h {
      font-size: 10px;
      font-weight: 700;
      color: var(--isd-muted);
      white-space: normal;
      word-break: break-word;
      overflow-wrap: anywhere;
      line-height: 1.15;
      min-height: 26px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .isd-safe-v {
      font-size: 15px;
      font-weight: 800;
      color: var(--isd-ink);
      margin-top: 2px;
    }

    @media (max-width: 1200px) {
      .isd-grid-2 { grid-template-columns: 1fr; }
      .isd-divider { display: none; }
      .isd-kpi-row { grid-template-columns: 1fr; }
      .isd-safe-row { grid-template-columns: 1fr; }
    }
  `;
  wrapper.appendChild(style);
}
