/** Server + per-Frigate load monitoring for portal dashboard. */
(function () {
  const HOST_METRICS_PATH = "/api/host-metrics/";
  const POLL_MS = 30000;

  function parseFrigateCpu(stats) {
    if (!stats?.cpu_usages || typeof stats.cpu_usages !== "object") return null;
    let total = 0;
    for (const [key, val] of Object.entries(stats.cpu_usages)) {
      if (!/^\d+$/.test(key)) continue;
      if (val && typeof val === "object" && typeof val.cpu === "number") {
        total += val.cpu;
      } else if (typeof val === "number") {
        total += val;
      }
    }
    return Math.round(total * 10) / 10;
  }

  function parseFrigateMemMb(stats) {
    if (stats?.service?.mem_usage_mb) return Math.round(stats.service.mem_usage_mb);
    if (stats?.mem_usages && typeof stats.mem_usages === "object") {
      let total = 0;
      for (const [key, val] of Object.entries(stats.mem_usages)) {
        if (!/^\d+$/.test(key)) continue;
        if (val && typeof val === "object" && typeof val.mem === "number") {
          total += val.mem;
        }
      }
      if (total > 0) return Math.round(total);
    }
    return null;
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
        `RAM: ${host.memory.used_percent}% مصرف (حد مجاز ${host.memory_limit_percent}%) — افزودن Frigate/دوربین توصیه نمی‌شود`
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
    const mem = parseFrigateMemMb(stats);
    if (cpu === null && mem === null) {
      el.textContent = "";
      return;
    }
    const parts = [];
    if (cpu !== null) parts.push(`CPU فرایند: ${cpu}%`);
    if (mem !== null) parts.push(`RAM: ${mem} MB`);
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
    parseFrigateMemMb,
  };
})();
