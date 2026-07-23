/** Admin-only panel: login audit + camera health (SQLite via portal API).
 *  Camera sections are tabbed (broken / event history) with IP+name search. */
(function () {
  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function isAdmin() {
    try {
      const raw = localStorage.getItem("cctv_portal_session");
      if (!raw) return false;
      const sess = JSON.parse(raw);
      // PORTAL_AUTH is a top-level const in auth-config.js — a global binding,
      // NOT a window property — so read it by name (as app.js does), not off window.
      const adminUser =
        (typeof PORTAL_AUTH !== "undefined" && PORTAL_AUTH?.admin?.user) || "admin";
      if (!(sess?.at && Date.now() - sess.at <= 30 * 24 * 60 * 60 * 1000)) return false;
      return sess?.user === adminUser;
    } catch {
      return false;
    }
  }

  function fmtTs(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("fa-IR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return iso;
    }
  }

  function eventLabel(ev) {
    const map = {
      login: "ورود",
      logout: "خروج",
      login_failed: "ورود ناموفق",
      broken: "خراب/قطع",
      recovered: "بازگشت",
      offline: "آفلاین",
      seen: "ثبت اولیه",
    };
    return map[ev] || esc(ev);
  }

  /** Camera IP from the generated map (config-derived). "" if unknown. */
  function camIp(site, camera) {
    try {
      return (
        (typeof CAMERA_IP !== "undefined" &&
          CAMERA_IP[site] &&
          CAMERA_IP[site][camera]) ||
        ""
      );
    } catch {
      return "";
    }
  }

  async function fetchJson(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error("fetch failed");
    return res.json();
  }

  // ---- Camera tab + search state -------------------------------------------
  let _broken = [];
  let _camEvents = [];
  let _activeTab = "broken";
  let _search = "";
  let _bound = false;

  function rowMatches(row) {
    if (!_search) return true;
    const ip = camIp(row.site, row.camera);
    const hay = [
      row.camera,
      row.site,
      ip,
      row.detail,
      row.last_detail,
      eventLabel(row.event || row.status),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return hay.includes(_search);
  }

  function renderAuthTable(events) {
    if (!events?.length) {
      return '<p class="admin-empty">هنوز لاگ ورودی ثبت نشده است.</p>';
    }
    const rows = events
      .map(
        (e) => `
      <tr class="${e.success ? "" : "row-fail"}">
        <td>${fmtTs(e.ts)}</td>
        <td>${eventLabel(e.event)}</td>
        <td dir="ltr">${e.username ? esc(e.username) : "—"}</td>
        <td dir="ltr">${e.ip ? esc(e.ip) : "—"}</td>
        <td>${e.success ? "موفق" : "ناموفق"}</td>
      </tr>`
      )
      .join("");
    return `
      <div class="admin-table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>زمان</th>
              <th>رویداد</th>
              <th>کاربر</th>
              <th>IP</th>
              <th>وضعیت</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function renderBrokenTable(cameras) {
    const list = (cameras || []).filter(rowMatches);
    if (!list.length) {
      return _search
        ? '<p class="admin-empty">موردی با این جستجو پیدا نشد.</p>'
        : '<p class="admin-empty">دوربین خراب فعالی در پایگاه ثبت نیست.</p>';
    }
    const rows = list
      .map(
        (c) => `
      <tr>
        <td dir="ltr">${esc(c.camera)}</td>
        <td dir="ltr">${camIp(c.site, c.camera) ? esc(camIp(c.site, c.camera)) : "—"}</td>
        <td>${c.site ? esc(c.site) : "—"}</td>
        <td>${c.status === "offline" ? "آفلاین" : "خراب/قطع"}</td>
        <td>${fmtTs(c.last_change)}</td>
        <td>${c.last_detail ? esc(c.last_detail) : "—"}</td>
      </tr>`
      )
      .join("");
    return `
      <div class="admin-table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>دوربین</th>
              <th>IP</th>
              <th>بخش</th>
              <th>وضعیت</th>
              <th>آخرین تغییر</th>
              <th>توضیح</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function renderCamEvents(events) {
    const list = (events || []).filter(rowMatches);
    if (!list.length) {
      return _search
        ? '<p class="admin-empty">موردی با این جستجو پیدا نشد.</p>'
        : '<p class="admin-empty">رویداد دوربینی ثبت نشده است.</p>';
    }
    const rows = list
      .map(
        (e) => `
      <tr>
        <td>${fmtTs(e.ts)}</td>
        <td>${eventLabel(e.event)}</td>
        <td dir="ltr">${esc(e.camera)}</td>
        <td dir="ltr">${camIp(e.site, e.camera) ? esc(camIp(e.site, e.camera)) : "—"}</td>
        <td>${e.site ? esc(e.site) : "—"}</td>
        <td>${e.detail ? esc(e.detail) : "—"}</td>
      </tr>`
      )
      .join("");
    return `
      <div class="admin-table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>زمان</th>
              <th>رویداد</th>
              <th>دوربین</th>
              <th>IP</th>
              <th>بخش</th>
              <th>توضیح</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function renderCameraSection() {
    const brokenEl = document.getElementById("admin-broken");
    const camEvEl = document.getElementById("admin-cam-events");
    if (brokenEl) {
      brokenEl.innerHTML = renderBrokenTable(_broken);
      brokenEl.hidden = _activeTab !== "broken";
    }
    if (camEvEl) {
      camEvEl.innerHTML = renderCamEvents(_camEvents);
      camEvEl.hidden = _activeTab !== "events";
    }
    document.querySelectorAll("[data-cam-tab]").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.camTab === _activeTab);
    });
  }

  function bindCameraControls() {
    if (_bound) return;
    _bound = true;
    document.querySelectorAll("[data-cam-tab]").forEach((b) => {
      b.addEventListener("click", () => {
        _activeTab = b.dataset.camTab;
        renderCameraSection();
      });
    });
    const search = document.getElementById("admin-cam-search");
    if (search) {
      search.addEventListener("input", () => {
        _search = search.value.trim().toLowerCase();
        renderCameraSection();
      });
    }
  }

  async function refreshAdminPanel() {
    const panel = document.getElementById("admin-panel");
    if (!panel) return;

    if (!isAdmin()) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;

    const authEl = document.getElementById("admin-auth-log");
    const brokenEl = document.getElementById("admin-broken");
    const camEvEl = document.getElementById("admin-cam-events");
    if (authEl) authEl.innerHTML = '<p class="admin-empty">در حال بارگذاری…</p>';
    if (brokenEl && _activeTab === "broken")
      brokenEl.innerHTML = '<p class="admin-empty">در حال بارگذاری…</p>';
    if (camEvEl && _activeTab === "events")
      camEvEl.innerHTML = '<p class="admin-empty">در حال بارگذاری…</p>';

    try {
      const [audit, broken, camEvents] = await Promise.all([
        fetchJson("/api/audit/?limit=100"),
        fetchJson("/api/cameras/broken/"),
        fetchJson("/api/cameras/events/?limit=100"),
      ]);
      if (authEl) authEl.innerHTML = renderAuthTable(audit.events || []);
      _broken = broken.cameras || [];
      _camEvents = camEvents.events || [];
      bindCameraControls();
      renderCameraSection();
    } catch {
      if (authEl) authEl.innerHTML = '<p class="admin-empty">خطا در خواندن لاگ‌ها</p>';
    }
  }

  function hideAdminPanel() {
    const panel = document.getElementById("admin-panel");
    if (panel) panel.hidden = true;
  }

  window.AdminPanel = { refresh: refreshAdminPanel, hide: hideAdminPanel, isAdmin };
})();
