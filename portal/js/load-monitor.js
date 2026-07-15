/** Server + per-Frigate load monitoring for portal dashboard. */
(function () {
  const HOST_METRICS_PATH = "/api/host-metrics/";
  const POLL_MS = 30000;

  function num(v) {
    const n = typeof v === "number" ? v : parseFloat(v);
    return Number.isFinite(n) ? n : 0;
  }

  function parseFrigateCpu(stats) {
    if (!stats?.cpu_usages || typeof stats.cpu_usages !== "object") return null;
    let total = 0;
    let seen = false;
    for (const [key, val] of Object.entries(stats.cpu_usages)) {
      if (!/^\d+$/.test(key)) continue;
      if (!val || typeof val !== "object") continue;
      total += num(val.cpu);
      seen = true;
    }
    if (!seen) return null;
    return Math.round(total * 10) / 10;
  }

  function parseFrigateMemPct(stats) {
    if (!stats?.cpu_usages || typeof stats.cpu_usages !== "object") return null;
    let total = 0;
    let seen = false;
    for (const [key, val] of Object.entries(stats.cpu_usages)) {
      if (!/^\d+$/.test(key)) continue;
      if (!val || typeof val !== "object") continue;
      total += num(val.mem);
      seen = true;
    }
    if (!seen) return null;
    return Math.round(total * 10) / 10;
  }

  async function fetchHostMetrics() {
    try {
      const res = await fetch(HOST_METRICS_PATH, { cache: "no-store" });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  const SEV_ORDER = { ok: 0, warn: 1, danger: 2 };

  /** CPU severity from load/cores ratio.
   *  ratio < warnRatio → ok · warnRatio..dangerRatio → warn · ≥ dangerRatio → danger */
  function cpuSeverity(host) {
    const cores = num(host.cpu_cores) || 1;
    const ratio = num(host.load_average["1m"]) / cores;
    const warnRatio = host.load_limit ? host.load_limit / cores : 0.5;
    const dangerRatio = 1.0;
    if (ratio >= dangerRatio) return "danger";
    if (ratio >= warnRatio) return "warn";
    return "ok";
  }

  /** RAM severity: < limit → ok · limit..2×limit → warn · ≥ 2×limit → danger */
  function ramSeverity(host) {
    const used = num(host.memory.used_percent);
    const limit = num(host.memory_limit_percent) || 30;
    const dangerLimit = limit * 2;
    if (used >= dangerLimit) return "danger";
    if (used >= limit) return "warn";
    return "ok";
  }

  function worst(a, b) {
    return SEV_ORDER[a] >= SEV_ORDER[b] ? a : b;
  }

  function applyMetricSeverity(el, sev) {
    if (!el) return;
    el.classList.remove("is-ok", "is-warn", "is-danger");
    el.classList.add(`is-${sev}`);
  }

  function renderHostPanel(host) {
    const el = document.getElementById("status-overview");
    const loadVal = document.getElementById("host-load-value");
    const loadHint = document.getElementById("host-load-hint");
    const loadMetric = loadVal ? loadVal.closest(".status-metric") : null;
    const ramVal = document.getElementById("host-ram-value");
    const ramHint = document.getElementById("host-ram-hint");
    const ramMetric = ramVal ? ramVal.closest(".status-metric") : null;
    const msg = document.getElementById("status-overview-msg");
    if (!el) return;

    if (!host) {
      el.className = "status-overview status-overview--unknown";
      if (loadVal) loadVal.textContent = "—";
      if (ramVal) ramVal.textContent = "—";
      applyMetricSeverity(loadMetric, "ok");
      applyMetricSeverity(ramMetric, "ok");
      if (msg) msg.innerHTML = "";
      return;
    }

    const cpuSev = cpuSeverity(host);
    const ramSev = ramSeverity(host);
    const overall = worst(cpuSev, ramSev);
    el.className = `status-overview status-overview--${overall}`;

    applyMetricSeverity(loadMetric, cpuSev);
    applyMetricSeverity(ramMetric, ramSev);

    if (loadVal) {
      loadVal.textContent = host.load_average["1m"].toFixed(1);
    }
    if (loadHint) {
      loadHint.textContent = `حد ${host.load_limit} · ${host.cpu_cores} هسته`;
    }
    if (ramVal) {
      ramVal.textContent = `${Math.round(host.memory.used_percent)}%`;
    }
    if (ramHint) {
      ramHint.textContent = `حد ${host.memory_limit_percent}%`;
    }

    if (!msg) return;
    const alerts = [];
    if (cpuSev === "danger") {
      alerts.push({
        sev: "danger",
        text: `فشار بحرانی CPU: load ${host.load_average["1m"].toFixed(2)} برابر یا بیشتر از ${host.cpu_cores} هسته — سیستم پایدار نیست`,
      });
    } else if (cpuSev === "warn") {
      alerts.push({
        sev: "warn",
        text: `CPU رو به فشار: load ${host.load_average["1m"].toFixed(2)} از حد ${host.load_limit} گذشت — مراقب باشید`,
      });
    }
    if (ramSev === "danger") {
      alerts.push({
        sev: "danger",
        text: `RAM بحرانی: ${host.memory.used_percent}% مصرف — افزودن دوربین ممنوع`,
      });
    } else if (ramSev === "warn") {
      alerts.push({
        sev: "warn",
        text: `RAM: ${host.memory.used_percent}% مصرف (حد ${host.memory_limit_percent}%) — افزودن دوربین توصیه نمی‌شود`,
      });
    }
    msg.innerHTML =
      alerts.length > 0
        ? alerts
            .map((a) => `<p class="status-alert status-alert--${a.sev}">${a.text}</p>`)
            .join("")
        : `<p class="status-ok-msg">وضعیت سرور در محدوده امن است</p>`;
  }

  function renderFrigateLoad(siteId, stats) {
    const el = document.querySelector(`[data-frigate-load="${siteId}"]`);
    if (!el) return;

    const cpu = parseFrigateCpu(stats);
    const mem = parseFrigateMemPct(stats);
    if (cpu === null && mem === null) {
      el.textContent = "";
      return;
    }
    const parts = [];
    if (cpu !== null) parts.push(`CPU: ${cpu}%`);
    if (mem !== null) parts.push(`RAM: ${mem}%`);
    el.textContent = parts.join(" · ");
  }

  async function refreshHost() {
    const host = await fetchHostMetrics();
    renderHostPanel(host);
    return host;
  }

  let timer = null;

  function start() {
    refreshHost();
    if (timer) clearInterval(timer);
    timer = setInterval(refreshHost, POLL_MS);
  }

  window.LoadMonitor = {
    refreshHost,
    start,
    renderFrigateLoad,
    parseFrigateCpu,
    parseFrigateMemPct,
  };
})();
