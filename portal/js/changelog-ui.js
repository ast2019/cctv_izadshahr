/** Render version badge + auto-expiring changelog (hidden after 2 days). */
(function () {
  const MS_PER_DAY = 86400000;
  const VISIBLE_DAYS = 2;

  function daysSince(dateStr) {
    const entry = new Date(dateStr + "T12:00:00");
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const entryDay = new Date(entry.getFullYear(), entry.getMonth(), entry.getDate());
    return Math.floor((today - entryDay) / MS_PER_DAY);
  }

  function formatDateFa(dateStr) {
    return new Date(dateStr + "T12:00:00").toLocaleDateString("fa-IR", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  function visibleEntries() {
    return CHANGELOG.map((entry) => ({
      ...entry,
      ageDays: daysSince(entry.date),
    })).filter((e) => e.ageDays < VISIBLE_DAYS);
  }

  function renderVersion() {
    const el = document.getElementById("portal-version");
    if (el && typeof PORTAL_VERSION !== "undefined") {
      el.textContent = `v${PORTAL_VERSION}`;
    }
  }

  function renderChangelog() {
    const container = document.getElementById("changelog");
    if (!container) return;

    const entries = visibleEntries();
    if (entries.length === 0) {
      container.hidden = true;
      return;
    }

    container.hidden = false;
    container.innerHTML = entries
      .map((entry) => {
        const opacityClass = entry.ageDays === 0 ? "" : " changelog-entry--fade";
        return `
        <article class="changelog-entry${opacityClass}" data-age="${entry.ageDays}">
          <header class="changelog-entry-header">
            <span class="changelog-version">v${entry.version}</span>
            <time datetime="${entry.date}">${formatDateFa(entry.date)}</time>
          </header>
          <ul>
            ${entry.items.map((item) => `<li>${item}</li>`).join("")}
          </ul>
        </article>
      `;
      })
      .join("");
  }

  function init() {
    renderVersion();
    renderChangelog();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
