(function () {
  const SESSION_KEY = "cctv_portal_session";

  /** Persian/Arabic digits → ASCII (common login typo on FA keyboard) */
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

  /** Frigate returns 401 without auth — service is still up */
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

  function renderCard(site, health) {
    const disabled = !site.enabled;
    const href = disabled ? "#" : panelUrl(site);
    const needsLogin = !disabled && !isLoggedIn();

    return `
      <a href="${needsLogin ? "#" : href}" class="card ${site.cssClass}${disabled ? " card--disabled" : ""}"
         ${needsLogin ? `data-login-site="${site.id}"` : ""}
         ${disabled || needsLogin ? "" : ""}
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

  function isLoggedIn() {
    return !!sessionStorage.getItem(SESSION_KEY);
  }

  function showLoginModal() {
    document.getElementById("login-modal")?.classList.add("open");
  }

  function hideLoginModal() {
    document.getElementById("login-modal")?.classList.remove("open");
  }

  // Frigate rejects browser (Origin-bearing) writes without this header
  const CSRF_HEADER = { "X-CSRF-TOKEN": "1" };

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

  function renderAuthHints() {
    if (typeof PORTAL_AUTH === "undefined") return;
    const creds = `مشاهده: <code dir="ltr">${PORTAL_AUTH.viewer.user}</code> / <code dir="ltr">${PORTAL_AUTH.viewer.pass}</code> — مدیریت: <code dir="ltr">${PORTAL_AUTH.admin.user}</code> / <code dir="ltr">${PORTAL_AUTH.admin.pass}</code>`;
    document.querySelectorAll("[data-auth-creds]").forEach((el) => {
      el.innerHTML = creds;
    });
    const quick = document.getElementById("login-quick");
    if (quick) {
      quick.innerHTML = `
        <button type="button" class="btn-quick" data-quick-login="viewer">ورود سریع مشاهده</button>
        <button type="button" class="btn-quick btn-quick--admin" data-quick-login="admin">ورود سریع مدیریت</button>
      `;
    }
  }

  async function loginSite(site, username, password) {
    await clearSiteSession(site);
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
  }

  async function loginAll(username, password) {
    const enabled = SITES.filter((s) => s.enabled);
    const results = [];
    for (const site of enabled) {
      results.push(await loginSite(site, username, password));
    }
    const failed = results.filter((r) => !r.ok);
    if (failed.length > 0) {
      const authFail = failed.every((f) => f.status === 401);
      if (authFail) {
        throw new Error(
          "رمز یا نام کاربری اشتباه است. از دکمه «ورود سریع» استفاده کنید یا Ctrl+Shift+R بزنید."
        );
      }
      throw new Error(`ورود ناموفق: ${failed.map((f) => f.site.title).join("، ")}`);
    }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ user: username, at: Date.now() }));
    return true;
  }

  function setupLogin() {
    const form = document.getElementById("login-form");
    const errEl = document.getElementById("login-error");
    const userBar = document.getElementById("user-bar");
    const logoutBtn = document.getElementById("logout-btn");

    if (isLoggedIn()) {
      const sess = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "{}");
      if (userBar) {
        userBar.hidden = false;
        userBar.querySelector(".user-name").textContent = sess.user || "";
      }
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
        hideLoginModal();
        if (userBar) {
          userBar.hidden = false;
          userBar.querySelector(".user-name").textContent = user;
        }
        await renderAllCards();
      } catch (err) {
        errEl.textContent = err.message || "خطا در ورود";
      } finally {
        btn.disabled = false;
      }
    });

    logoutBtn?.addEventListener("click", async () => {
      for (const site of SITES.filter((s) => s.enabled)) {
        await clearSiteSession(site);
      }
      sessionStorage.removeItem(SESSION_KEY);
      if (userBar) userBar.hidden = true;
      showLoginModal();
      await renderAllCards();
    });

    if (!isLoggedIn()) showLoginModal();

    document.getElementById("show-password")?.addEventListener("change", (e) => {
      const passInput = form?.password;
      if (passInput) passInput.type = e.target.checked ? "text" : "password";
    });

    document.querySelectorAll("[data-quick-login]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!form || typeof PORTAL_AUTH === "undefined") return;
        const role = btn.dataset.quickLogin;
        const account = PORTAL_AUTH[role];
        if (!account) return;
        errEl.textContent = "";
        form.username.value = account.user;
        form.password.value = account.pass;
        const submit = form.querySelector('button[type="submit"]');
        submit.disabled = true;
        try {
          await loginAll(account.user, account.pass);
          hideLoginModal();
          if (userBar) {
            userBar.hidden = false;
            userBar.querySelector(".user-name").textContent = account.user;
          }
          await renderAllCards();
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

  async function renderAllCards() {
    const container = document.getElementById("cards");
    if (!container) return;
    container.innerHTML = SITES.map((s) => renderCard(s, "unknown")).join("");
    if (!isLoggedIn()) bindCardClicks();
    await refreshCards();
  }

  async function refreshCards() {
    const container = document.getElementById("cards");
    if (!container) return;

    await Promise.all(
      SITES.map(async (site) => {
        if (!site.enabled) return;
        const health = await checkHealth(site);
        const stats = isLoggedIn() ? await fetchStats(site) : null;

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
    if (window.LoadMonitor) await window.LoadMonitor.refreshHost();
  }

  async function init() {
    renderAuthHints();
    setupLogin();
    window.LoadMonitor?.start();
    await renderAllCards();
    setInterval(async () => {
      if (isLoggedIn()) await refreshCards();
    }, 30000);
  }

  updateClock();
  setInterval(updateClock, 1000);
  init();
})();
