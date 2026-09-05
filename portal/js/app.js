(function () {
  const SESSION_KEY = "cctv_portal_session";
  /** Username from the HttpOnly portal_session cookie — the only login token. */
  let portalUser = null;

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

  function isLoggedIn() {
    return !!portalUser;
  }

  function saveSession(user) {
    portalUser = user || null;
    window.__PORTAL_USER = portalUser;
    if (!user) {
      localStorage.removeItem(SESSION_KEY);
      return;
    }
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ user, at: Date.now() })
    );
  }

  function clearSession() {
    saveSession(null);
  }

  function safeNextPath() {
    const next = new URLSearchParams(location.search).get("next");
    if (!next || !next.startsWith("/") || next.startsWith("//")) return null;
    if (next.includes("://") || next.includes("\\")) return null;
    if (next.startsWith("/api") || next.startsWith("/internal")) return null;
    return next;
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

  async function fetchStats(site) {
    try {
      const res = await fetch(`${site.apiPath}stats`, {
        cache: "no-store",
        credentials: "include",
      });
      if (res.status === 401) {
        forceRelogin();
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

  async function verifyPortalSession() {
    try {
      const res = await fetch("/api/session/", {
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) return null;
      const data = await res.json();
      return data?.username || null;
    } catch {
      return null;
    }
  }

  async function portalLogin(username, password) {
    const res = await fetch("/api/portal-login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      cache: "no-store",
      body: JSON.stringify({ username, password }),
    });
    if (res.status === 401) {
      // Frigate rejected the password. If some instances never answered, the
      // account may live on one of those — say so instead of blaming the user.
      const info = await res.json().catch(() => ({}));
      if (info.unreachable > 0) {
        throw new Error(
          `رمز از نظر سرورهای پاسخ‌داده‌شده اشتباه است، ولی ${info.unreachable} سرور پاسخ نداد. اگر رمز درست است، کمی بعد دوباره تلاش کنید.`
        );
      }
      throw new Error("نام کاربری یا رمز عبور اشتباه است.");
    }
    if (res.status === 503) {
      throw new Error("سرویس ورود در دسترس نیست — بعداً تلاش کنید.");
    }
    if (!res.ok) {
      throw new Error("ورود ناموفق.");
    }
    const data = await res.json().catch(() => ({}));
    saveSession(data.username || username);
    return data.username || username;
  }

  async function portalLogout() {
    try {
      await fetch("/api/portal-logout/", {
        method: "POST",
        credentials: "include",
        cache: "no-store",
      });
    } catch {
      /* ignore */
    }
  }

  function forceRelogin() {
    clearSession();
    const userBar = document.getElementById("user-bar");
    if (userBar) userBar.hidden = true;
    updateIntro();
    if (window.AdminPanel) window.AdminPanel.hide();
    showLoginModal();
  }

  async function afterLogin(user) {
    hideLoginModal();
    const userBar = document.getElementById("user-bar");
    if (userBar) {
      userBar.hidden = false;
      userBar.querySelector(".user-name").textContent = user;
    }
    updateIntro();
    const next = safeNextPath();
    if (next) {
      window.location.assign(next);
      return;
    }
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

    if (portalUser && userBar) {
      userBar.hidden = false;
      userBar.querySelector(".user-name").textContent = portalUser;
    }

    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      errEl.textContent = "";
      const user = normalizeLogin(form.username.value);
      const pass = normalizeLogin(form.password.value);
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        const loggedInAs = await portalLogin(user, pass);
        await afterLogin(loggedInAs);
      } catch (err) {
        errEl.textContent = err.message || "خطا در ورود";
      } finally {
        btn.disabled = false;
      }
    });

    logoutBtn?.addEventListener("click", async () => {
      await portalLogout();
      clearSession();
      if (userBar) userBar.hidden = true;
      updateIntro();
      if (window.AdminPanel) window.AdminPanel.hide();
      showLoginModal();
      await renderAllCards();
    });

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

  }

  function bindCardClicks() {
    document.querySelectorAll("[data-login-site]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        showLoginModal();
      });
    });
  }

  /** Confirm the portal cookie is still valid, then open the Frigate UI. */
  function bindPanelGuards() {
    document.querySelectorAll("a.card[href]:not([href='#'])").forEach((el) => {
      el.addEventListener("click", async (e) => {
        if (!isLoggedIn()) return;
        const href = el.getAttribute("href");
        if (!href || href === "#") return;
        e.preventDefault();
        el.classList.add("card--busy");
        try {
          const user = await verifyPortalSession();
          if (!user) {
            forceRelogin();
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
    updateIntro();
    renderCameraSummary(0);
    const cookieUser = await verifyPortalSession();
    if (cookieUser) saveSession(cookieUser);
    else clearSession();
    setupLogin();
    document.getElementById("admin-refresh-btn")?.addEventListener("click", () => {
      window.AdminPanel?.refresh();
    });
    window.LoadMonitor?.start();

    if (!cookieUser) showLoginModal();

    await renderAllCards();
    setInterval(async () => {
      if (isLoggedIn()) await refreshCards();
    }, 30000);
  }

  updateClock();
  setInterval(updateClock, 1000);
  init();
})();
