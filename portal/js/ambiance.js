/** Wide-monitor ambiance: hourly snapshots + mouse parallax. */
(function () {
  const MQ = window.matchMedia("(min-width: 1500px)");
  const MANIFEST_URL = "/api/snapshots/";
  const REFRESH_MS = 10 * 60 * 1000;

  let mouseX = 0;
  let mouseY = 0;
  let targetX = 0;
  let targetY = 0;
  let rafId = 0;
  let looping = false;

  function ensureRails() {
    let left = document.getElementById("ambiance-left");
    let right = document.getElementById("ambiance-right");
    if (!left) {
      left = document.createElement("aside");
      left.id = "ambiance-left";
      left.className = "ambiance-rail ambiance-rail--left";
      left.setAttribute("aria-hidden", "true");
      document.body.appendChild(left);
    }
    if (!right) {
      right = document.createElement("aside");
      right.id = "ambiance-right";
      right.className = "ambiance-rail ambiance-rail--right";
      right.setAttribute("aria-hidden", "true");
      document.body.appendChild(right);
    }
    return { left, right };
  }

  function renderTiles(rail, tiles) {
    rail.innerHTML = tiles
      .map(
        (t, i) => `
      <div class="ambiance-tile" data-depth="${0.55 + (i % 4) * 0.25}" style="--i:${i}">
        <div class="ambiance-tile-inner">
          <img src="${t.url}" alt="" loading="lazy" decoding="async" />
          <span class="ambiance-caption">${t.camera || ""}</span>
        </div>
      </div>`
      )
      .join("");
  }

  async function loadManifest() {
    if (!MQ.matches) {
      document.getElementById("ambiance-left")?.replaceChildren();
      document.getElementById("ambiance-right")?.replaceChildren();
      document.body.classList.remove("has-ambiance");
      return;
    }
    try {
      const res = await fetch(MANIFEST_URL, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const tiles = Array.isArray(data.tiles) ? data.tiles : [];
      if (!tiles.length) return;

      const { left, right } = ensureRails();
      const L = tiles.filter((t) => t.side === "left");
      const R = tiles.filter((t) => t.side === "right");
      const leftTiles = L.length ? L : tiles.slice(0, Math.ceil(tiles.length / 2));
      const rightTiles = R.length ? R : tiles.slice(Math.ceil(tiles.length / 2));

      renderTiles(left, leftTiles);
      renderTiles(right, rightTiles);
      document.body.classList.add("has-ambiance");
      startLoop();
    } catch {
      /* ignore */
    }
  }

  function tick() {
    if (!looping) return;

    if (MQ.matches && document.body.classList.contains("has-ambiance")) {
      mouseX += (targetX - mouseX) * 0.12;
      mouseY += (targetY - mouseY) * 0.12;
      const scrollY = window.scrollY || 0;

      document.querySelectorAll(".ambiance-tile").forEach((tile) => {
        const depth = parseFloat(tile.dataset.depth || "0.7");
        const side = tile.closest(".ambiance-rail--left") ? -1 : 1;
        const mx = mouseX * depth * 42 * side;
        const my = mouseY * depth * 22 + scrollY * depth * 0.05;
        const rot = mouseX * depth * 2.4 * side;
        tile.style.transform = `translate3d(${mx.toFixed(1)}px, ${my.toFixed(1)}px, 0) rotate(${rot.toFixed(2)}deg)`;
      });

      const left = document.getElementById("ambiance-left");
      const right = document.getElementById("ambiance-right");
      if (left) {
        left.style.transform = `translate3d(${(mouseX * -18).toFixed(1)}px, ${(mouseY * -8).toFixed(1)}px, 0)`;
      }
      if (right) {
        right.style.transform = `translate3d(${(mouseX * 18).toFixed(1)}px, ${(mouseY * -10).toFixed(1)}px, 0)`;
      }
    }

    rafId = requestAnimationFrame(tick);
  }

  function startLoop() {
    if (looping) return;
    looping = true;
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(tick);
  }

  function onMouseMove(e) {
    const nx = (e.clientX / Math.max(1, window.innerWidth)) * 2 - 1;
    const ny = (e.clientY / Math.max(1, window.innerHeight)) * 2 - 1;
    targetX = Math.max(-1, Math.min(1, nx));
    targetY = Math.max(-1, Math.min(1, ny));
  }

  function start() {
    loadManifest();
    MQ.addEventListener?.("change", loadManifest);
    window.addEventListener("mousemove", onMouseMove, { passive: true });
    setInterval(loadManifest, REFRESH_MS);
    startLoop();
  }

  window.AmbianceRails = { start, refresh: loadManifest };
})();
