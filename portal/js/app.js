(function () {
  const SESSION_KEY = "cctv_portal_session";
  const SESSION_DAYS = 30;
  const SESSION_MS = SESSION_DAYS * 24 * 60 * 60 * 1000;
  const CSRF_HEADER = { "X-CSRF-TOKEN": "1" };

  /** Persian/Arabic digits → ASCII */
  function normalizeLogin(value) {
    if (!value) return "";
    let s = value.trim().normalize("NFKC");
    const persian = "۰۱۲۳۴۵۶۷۸۹";
    const arabic = "٠١٢٣٤٥٦٧٨٩";
    for (let i = 0; i < 10; i++) {
      s = s.replaceAll(persian[i], String(i));
      s = s.replaceAll(arabic[i], String(i));
    }
    return s;
  }

  function panelUrl(site) {
    if (window.PORTAL_CONFIG?.useSubdomains && window.PORTAL_CONFIG?.domain) {
      const d = window.PORTAL_CONFIG.domain;
      return `https://${site.slug}.${d}/`;
    }
    return `/${site.slug}/`;
  }

  function updateClock() {
    const el = document.getElementById("clock");
    if (!el) return;
    el.textContent = new Date().toLocaleString("fa-IR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function getSession() {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      if (!raw) return null;
      const sess = JSON.parse(raw);
      if (!sess?.at || Date.now() - sess.at > SESSION_MS) {
        localStorage.removeItem(SESSION_KEY);
        return null;
      }
      return sess;
    } catch {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
  }

  function isLoggedIn() {
    return !!getSession();
  }

  function saveSession(user) {
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ user, at: Date.now() })
    );
  }

  function clearSession() {
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
  }

  async function logAuthEvent(event, username, success = true, detail = null) {
    try {
      await fetch("/api/audit/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ event, username, success, detail }),
      });
    } catch {
      /* ignore audit failures */
    }
  }

  function updateIntro() {
    /* intro section removed */
  }

  async function checkHealth(site) {
    try {
      const res = await fetch(site.healthPath, { method: "GET", cache: "no-store" });
      return res.status > 0 && res.status < 500 ? "online" : "offline";
    } catch {
      return "offline";
    }
  }

  async function fetchStats(site, retried = false) {
    try {
      const res = await fetch(`${site.apiPath}stats`, {
        cache: "no-store",
        credentials: "include",
      });
      // Frigate cookie expired mid-session — silently re-login once and retry
      if (res.status === 401 && !retried && isLoggedIn()) {
        const state = await ensureSiteAuth(site);
        if (state === true) return fetchStats(site, true);
        return null;
      }
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  function statusLabel(state) {
    if (state === "online") return "آنلاین";
    if (state === "offline") return "آفلاین";
    return "در حال بررسی…";
  }

  function buildStatsHtml(site, stats) {
    const count = stats?.cameras
      ? Object.keys(stats.cameras).length
      : site.cameraCount;
    const active = stats?.cameras
      ? Object.values(stats.cameras).filter((c) => c.camera_fps > 0).length
      : null;

    return `
      <div class="stat">
        <span class="stat-value">${count}</span>
        <span class="stat-label">دوربین</span>
      </div>
      <div class="stat">
        <span class="stat-value">${active !== null ? active : "—"}</span>
        <span class="stat-label">فعال</span>
      </div>
    `;
  }

  function renderCameraSummary(liveBroken = 0) {
    const inv = typeof CAMERA_INVENTORY !== "undefined" ? CAMERA_INVENTORY : null;
    const totalEl = document.getElementById("summary-total");
    const inactiveEl = document.getElementById("summary-inactive");
    const brokenEl = document.getElementById("summary-broken");
    if (!inv || !totalEl) return;

    totalEl.textContent = String(inv.total);
    inactiveEl.textContent = String(inv.inactive);
    brokenEl.textContent = String(Math.max(inv.broken, liveBroken));
  }

  function renderCard(site, health) {
    const disabled = !site.enabled;
    const href = disabled ? "#" : panelUrl(site);
    const needsLogin = !disabled && !isLoggedIn();

    return `
      <a href="${needsLogin ? "#" : href}" class="card ${site.cssClass}${disabled ? " card--disabled" : ""}"
         ${needsLogin ? `data-login-site="${site.id}"` : `data-panel-site="${site.id}"`}
         aria-label="ورود به ${site.title}">
        <div class="card-top">
          <div class="card-icon" aria-hidden="true">${site.icon}</div>
          <div class="status status--${health}" data-site="${site.id}">
            <span class="status-dot"></span>
            <span>${disabled ? "غیرفعال" : statusLabel(health)}</span>
          </div>
        </div>
        <h2 class="card-title">${site.title}</h2>
        <div class="card-en">${site.titleEn}</div>
        <p class="card-desc">${site.description}</p>
        <div class="card-stats" data-stats="${site.id}">
          ${buildStatsHtml(site, null)}
        </div>
        <div class="card-load" data-frigate-load="${site.id}" aria-live="polite"></div>
        <div class="card-action">
          ${disabled ? '<span class="badge-soon">به‌زودی</span>' : "<span>ورود به پنل</span>"}
          ${
            disabled
              ? ""
              : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 5l-7 7 7 7"/>
          </svg>`
          }
        </div>
      </a>
    `;
  }

  function showLoginModal() {
    document.getElementById("login-modal")?.classList.add("open");
  }

  function hideLoginModal() {
    document.getElementById("login-modal")?.classList.remove("open");
  }

  async function clearSiteSession(site) {
    try {
      await fetch(`${site.apiPath}logout`, {
        method: "POST",
        headers: { ...CSRF_HEADER },
        credentials: "include",
        cache: "no-store",
      });
    } catch {
      /* ignore */
    }
  }

  function renderQuickLogin() {
    const quick = document.getElementById("login-quick");
    if (!quick || typeof PORTAL_AUTH === "undefined") return;
    quick.innerHTML = `
      <button type="button" class="btn-quick" data-quick-login="viewer">ورود ویور</button>
      <button type="button" class="btn-quick btn-quick--admin" data-quick-login="admin">ورود ادمین</button>
    `;
  }

  async function loginSite(site, username, password) {
    try {
      const res = await fetch(`${site.apiPath}login`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...CSRF_HEADER },
        credentials: "include",
        cache: "no-store",
        body: JSON.stringify({ user: username, password }),
      });
      if (!res.ok) {
        let msg = "";
        try {
          const data = await res.json();
          msg = data.message || "";
        } catch {
          /* ignore */
        }
        return { site, ok: false, status: res.status, msg };
      }
      return { site, ok: true, status: res.status, msg: "" };
    } catch {
      // Network error (site down / restarting) — not a credential problem
      return { site, ok: false, status: 0, msg: "network" };
    }
  }

  /** Login to every enabled site. Succeeds if at least one site accepts —
   *  one offline Frigate must not lock the user out of the others. */
  async function loginAll(username, password) {
    const enabled = SITES.filter((s) => s.enabled);
    const results = [];
    for (const site of enabled) {
      results.push(await loginSite(site, username, password));
    }
    const failed = results.filter((r) => !r.ok);
    if (failed.length === results.length) {
      const authFail = failed.every((f) => f.status === 401);
      await logAuthEvent(
        "login_failed",
        username,
        false,
        authFail ? "bad credentials" : failed.map((f) => f.site.id).join(",")
      );
      if (authFail) {
        throw new Error("نام کاربری یا رمز عبور اشتباه است.");
      }
      throw new Error(`ورود ناموفق: ${failed.map((f) => f.site.title).join("، ")}`);
    }
    saveSession(username);
    await logAuthEvent(
      "login",
      username,
      true,
      failed.length ? `degraded: ${failed.map((f) => f.site.id).join(",")}` : null
    );
    return true;
  }

  /** Check the Frigate cookie is really valid on this device (browsers may
   *  drop cookies while the portal session in localStorage survives). */
  async function verifySiteAuth(site) {
    try {
      const res = await fetch(`${site.apiPath}profile`, {
        credentials: "include",
        cache: "no-store",
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  /** Make sure ONE site's Frigate cookie is valid; silently re-login if not.
   *  Returns true (cookie ok), false (site unreachable / unknown account —
   *  keep portal session, Frigate will ask itself if really needed),
   *  or "unauthorized" (stored credentials rejected — real re-login needed). */
  async function ensureSiteAuth(site) {
    if (await verifySiteAuth(site)) return true;

    const sess = getSession();
    if (!sess) return "unauthorized";
    const account =
      typeof PORTAL_AUTH !== "undefined"
        ? Object.values(PORTAL_AUTH).find((a) => a.user === sess.user)
        : null;
    if (!account) return false;

    const res = await loginSite(site, account.user, account.pass);
    if (res.status === 401) return "unauthorized";
    return res.ok;
  }

  /** Resolve with `fallback` if `promise` takes longer than `ms` —
   *  a slow Frigate must never block opening its panel. */
  function withTimeout(promise, ms, fallback) {
    return Promise.race([
      promise,
      new Promise((resolve) => setTimeout(() => resolve(fallback), ms)),
    ]);
  }

  function forceRelogin() {
    clearSession();
    const userBar = document.getElementById("user-bar");
    if (userBar) userBar.hidden = true;
    updateIntro();
    if (window.AdminPanel) window.AdminPanel.hide();
    showLoginModal();
  }

  /** Background refresh of all sites' cookies. Logs the user out ONLY when
   *  the stored credentials are explicitly rejected (401) — never because a
   *  Frigate instance is offline or the network hiccuped. */
  async function refreshAllSiteAuth() {
    if (!isLoggedIn()) return false;
    const enabled = SITES.filter((s) => s.enabled);
    const states = await Promise.all(enabled.map((s) => ensureSiteAuth(s)));
    if (states.some((s) => s === "unauthorized")) {
      forceRelogin();
      await renderAllCards();
      return false;
    }
    return true;
  }

  async function afterLogin(user) {
    hideLoginModal();
    const userBar = document.getElementById("user-bar");
    if (userBar) {
      userBar.hidden = false;
      userBar.querySelector(".user-name").textContent = user;
    }
    updateIntro();
    await renderAllCards();
    if (window.AdminPanel) await window.AdminPanel.refresh();
  }

  function updateMascot() {
    const mascot = document.getElementById("cctv-mascot");
    const form = document.getElementById("login-form");
    const show = document.getElementById("show-password");
    if (!mascot || !form) return;
    const passFocused = document.activeElement === form.password;
    mascot.classList.toggle("cctv-mascot--shy", passFocused && !show?.checked);
    mascot.classList.toggle("cctv-mascot--peek", !!show?.checked);
  }

  function setupLogin() {
    const form = document.getElementById("login-form");
    const errEl = document.getElementById("login-error");
    const userBar = document.getElementById("user-bar");
    const logoutBtn = document.getElementById("logout-btn");

    const sess = getSession();
    if (sess && userBar) {
      userBar.hidden = false;
      userBar.querySelector(".user-name").textContent = sess.user || "";
    }

    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      errEl.textContent = "";
      const user = normalizeLogin(form.username.value);
      const pass = normalizeLogin(form.password.value);
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        await loginAll(user, pass);
        await afterLogin(user);
      } catch (err) {
        errEl.textContent = err.message || "خطا در ورود";
      } finally {
        btn.disabled = false;
      }
    });

    logoutBtn?.addEventListener("click", async () => {
      const sess = getSession();
      const user = sess?.user || "";
      for (const site of SITES.filter((s) => s.enabled)) {
        await clearSiteSession(site);
      }
      await logAuthEvent("logout", user, true);
      clearSession();
      if (userBar) userBar.hidden = true;
      updateIntro();
      if (window.AdminPanel) window.AdminPanel.hide();
      showLoginModal();
      await renderAllCards();
    });

    if (!isLoggedIn()) showLoginModal();

    document.getElementById("show-password")?.addEventListener("change", (e) => {
      const passInput = form?.password;
      if (passInput) passInput.type = e.target.checked ? "text" : "password";
      updateMascot();
    });

    const passInput = form?.password;
    const userInput = form?.username;
    passInput?.addEventListener("focus", updateMascot);
    passInput?.addEventListener("blur", updateMascot);
    userInput?.addEventListener("focus", updateMascot);
    updateMascot();

    document.querySelectorAll("[data-quick-login]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!form || typeof PORTAL_AUTH === "undefined") return;
        const account = PORTAL_AUTH[btn.dataset.quickLogin];
        if (!account) return;
        errEl.textContent = "";
        form.username.value = account.user;
        form.password.value = account.pass;
        const submit = form.querySelector('button[type="submit"]');
        submit.disabled = true;
        try {
          await loginAll(account.user, account.pass);
          await afterLogin(account.user);
        } catch (err) {
          errEl.textContent = err.message || "خطا در ورود";
        } finally {
          submit.disabled = false;
        }
      });
    });
  }

  function bindCardClicks() {
    document.querySelectorAll("[data-login-site]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        showLoginModal();
      });
    });
  }

  /** Before opening Frigate UI, refresh THAT site's cookie if needed.
   *  Best-effort: navigation always proceeds unless credentials are
   *  explicitly rejected — never blocked by another (offline) site. */
  function bindPanelGuards() {
    document.querySelectorAll("a.card[href]:not([href='#'])").forEach((el) => {
      el.addEventListener("click", async (e) => {
        if (!isLoggedIn()) return;
        const href = el.getAttribute("href");
        if (!href || href === "#") return;
        const site = SITES.find((s) => s.id === el.dataset.panelSite);
        e.preventDefault();
        el.classList.add("card--busy");
        try {
          const state = site
            ? await withTimeout(ensureSiteAuth(site), 4000, true)
            : true;
          if (state === "unauthorized") {
            // A newly-created temporary Frigate may not have portal users synced
            // yet. Never trap the user on the portal: open Frigate's native
            // login page. Permanent sites still force a unified portal re-login.
            if (site?.temporary) {
              window.location.href = href;
              return;
            }
            forceRelogin();
            await renderAllCards();
            return;
          }
          window.location.href = href;
        } finally {
          el.classList.remove("card--busy");
        }
      });
    });
  }

  async function renderAllCards() {
    const container = document.getElementById("cards");
    if (!container) return;
    updateIntro();
    container.innerHTML = SITES.map((s) => renderCard(s, "unknown")).join("");
    if (!isLoggedIn()) bindCardClicks();
    else bindPanelGuards();
    await refreshCards();
  }

  async function reportCameraStatuses(reports) {
    if (!reports.length) return;
    try {
      await fetch("/api/cameras/report/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ cameras: reports }),
      });
    } catch {
      /* ignore */
    }
  }

  async function refreshCards() {
    const container = document.getElementById("cards");
    if (!container) return;

    let liveBroken = 0;
    const cameraReports = [];

    await Promise.all(
      SITES.map(async (site) => {
        if (!site.enabled) return;
        const health = await checkHealth(site);
        const stats = isLoggedIn() ? await fetchStats(site) : null;

        if (stats?.cameras) {
          for (const [name, cam] of Object.entries(stats.cameras)) {
            const ok = cam && cam.camera_fps > 0;
            if (!ok) liveBroken += 1;
            cameraReports.push({
              camera: name,
              site: site.id,
              status: ok ? "ok" : "broken",
              detail: ok ? null : `fps=${cam?.camera_fps ?? 0}`,
            });
          }
        }

        const statusEl = container.querySelector(`[data-site="${site.id}"]`);
        if (statusEl) {
          statusEl.className = `status status--${health}`;
          statusEl.querySelector("span:last-child").textContent = statusLabel(health);
        }

        const statsEl = container.querySelector(`[data-stats="${site.id}"]`);
        if (statsEl) statsEl.innerHTML = buildStatsHtml(site, stats);
        if (stats && window.LoadMonitor) {
          window.LoadMonitor.renderFrigateLoad(site.id, stats);
        }
      })
    );

    if (isLoggedIn() && cameraReports.length) {
      await reportCameraStatuses(cameraReports);
    }

    renderCameraSummary(liveBroken);
    if (window.LoadMonitor) await window.LoadMonitor.refreshHost();
    if (window.AdminPanel) await window.AdminPanel.refresh();
  }

  async function init() {
    renderQuickLogin();
    updateIntro();
    renderCameraSummary(0);
    setupLogin();
    document.getElementById("admin-refresh-btn")?.addEventListener("click", () => {
      window.AdminPanel?.refresh();
    });
    window.LoadMonitor?.start();

    if (isLoggedIn()) {
      // Non-blocking: refresh cookies in background; only a real 401
      // (changed password) forces the login modal.
      refreshAllSiteAuth();
    } else {
      showLoginModal();
    }

    await renderAllCards();
    setInterval(async () => {
      if (isLoggedIn()) await refreshCards();
    }, 30000);
  }

  updateClock();
  setInterval(updateClock, 1000);
  init();
})();
