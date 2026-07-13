/** Server + per-Frigate load monitoring for portal dashboard. */
(function () {
  const HOST_METRICS_PATH = "/api/host-metrics/";
  const POLL_MS = 30000;

  function num(v) {
    const n = typeof v === "number" ? v : parseFloat(v);
    return Number.isFinite(n) ? n : 0;
  }

  /** Sum CPU% of Frigate container processes (PIDs). Values from API are strings. */
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

  /** Sum process memory % (of host), as reported by Frigate. */
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

  function statusClass(host) {
    if (!host) return "system-status--unknown";
    if (!host.stable) return "system-status--danger";
    if (host.cpu_pressure || host.memory_pressure) return "system-status--warn";
    return "system-status--ok";
  }

  function renderHostPanel(host) {
    const el = document.getElementById("system-status");
    if (!el) return;

    if (!host) {
      el.hidden = true;
      return;
    }

    el.hidden = false;
    el.className = `system-status ${statusClass(host)}`;

    const alerts = [];
    if (host.cpu_pressure) {
      alerts.push(
        `فشار CPU: load میانگین ${host.load_average["1m"].toFixed(2)} از حد ${host.load_limit} (${host.cpu_cores} هسته) — سیستم ممکن است پایدار نماند`
      );
    }
    if (host.memory_pressure) {
      alerts.push(
        `RAM: ${host.memory.used_percent}% مصرف (حد مجاز ${host.memory_limit_percent}%) — افزودن دوربین توصیه نمی‌شود`
      );
    }

    const alertHtml =
      alerts.length > 0
        ? `<div class="system-alerts">${alerts.map((a) => `<p class="system-alert">${a}</p>`).join("")}</div>`
        : `<p class="system-ok-msg">وضعیت سرور در محدوده امن است</p>`;

    el.innerHTML = `
      <h2 class="system-status-title">وضعیت سرور اصلی</h2>
      <div class="system-status-grid">
        <div class="system-metric">
          <span class="system-metric-label">Load (1m)</span>
          <span class="system-metric-value">${host.load_average["1m"].toFixed(2)} / ${host.load_limit}</span>
          <span class="system-metric-hint">${host.cpu_cores} هسته — حد ۵۰٪</span>
        </div>
        <div class="system-metric">
          <span class="system-metric-label">RAM</span>
          <span class="system-metric-value">${host.memory.used_percent}%</span>
          <span class="system-metric-hint">حد مجاز ${host.memory_limit_percent}%</span>
        </div>
      </div>
      ${alertHtml}
    `;
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
    // CPU% can exceed 100 on multi-core (same as docker stats)
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
