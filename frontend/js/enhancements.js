/**
 * BiliSum v2.0 - Frontend Enhancements Runtime
 * Interactive whale, parallax clouds, modal animations, page transitions
 * Depends on enhancements.css being loaded after style.css
 */
(function () {
  "use strict";

  // =============================================================
  // UTILITY: DOM ready
  // =============================================================
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  // =============================================================
  // UTILITY: Set UI state (loading/empty/error/ready)
  // =============================================================
  window.setUIState = function (containerId, state) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.setAttribute("data-ui-state", state);
  };

  // =============================================================
  // UTILITY: Render error state into a container
  // =============================================================
  window.renderErrorState = function (containerId, opts) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const msg = opts.message || "未知错误";
    const retryFn = opts.onRetry || null;
    const icon = opts.icon || "&#9888;"; // warning
    const title = opts.title || "出错了";

    el.innerHTML =
      `<div class="error-state">
        <div class="error-state-icon">${icon}</div>
        <div class="error-state-title">${title}</div>
        <div class="error-state-message">${escapeHtml(msg)}</div>
        <div class="error-state-actions">
          ${retryFn ? '<button class="btn btn-outline btn-sm" id="errorRetryBtn">&#x21bb; 重试</button>' : ""}
        </div>
      </div>`;
    if (retryFn) {
      const btn = el.querySelector('#errorRetryBtn');
      if (btn) btn.addEventListener('click', retryFn);
    }
  };

  // =============================================================
  // UTILITY: Render empty state into a container
  // =============================================================
  window.renderEmptyState = function (containerId, opts) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const title = opts.title || "暂无内容";
    const text = opts.text || "";
    const icon = opts.icon || "&#128464;"; // default
    const actionHTML = opts.actionHTML || "";

    el.innerHTML =
      `<div class="empty-state">
        <div class="empty-state-icon">${icon}</div>
        <div class="empty-state-title">${title}</div>
        ${text ? '<div class="empty-state-text">' + escapeHtml(text) + "</div>" : ""}
        ${actionHTML ? '<div class="empty-state-action">' + actionHTML + "</div>" : ""}
      </div>`;
  };

  // =============================================================
  // UTILITY: Button loading state
  // =============================================================
  window.setBtnLoading = function (btn, isLoading) {
    if (typeof btn === "string") btn = document.getElementById(btn);
    if (!btn) return;
    if (isLoading) {
      btn.classList.add("btn-loading");
      btn.disabled = true;
    } else {
      btn.classList.remove("btn-loading");
      btn.disabled = false;
    }
  };

  // =============================================================
  // MODULE 1: Interactive Whale
  // Replaces body::after static SVG with interactive DOM SVG
  // States: idle (breathing) -> hover (curious) -> click (leap)
  // =============================================================

  const whaleSVG = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 250">
      <defs>
        <linearGradient id="bodyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:#e8f4fd"/>
          <stop offset="40%" style="stop-color:#d0e8f8"/>
          <stop offset="100%" style="stop-color:#b0d4ec"/>
        </linearGradient>
        <radialGradient id="bellyGrad" cx="50%" cy="50%">
          <stop offset="0%" style="stop-color:#f4f8fc"/>
          <stop offset="100%" style="stop-color:#e0eef6"/>
        </radialGradient>
      </defs>
      <!-- Body -->
      <path d="M35 125 Q15 70 65 80 Q110 45 180 68 Q255 50 310 80 Q365 55 370 115 Q372 145 355 155 Q340 165 310 150 Q255 175 180 155 Q110 168 65 150 Q20 160 35 125Z" fill="url(#bodyGrad)"/>
      <!-- Belly -->
      <ellipse cx="190" cy="140" rx="120" ry="28" fill="url(#bellyGrad)" opacity="0.85"/>
      <!-- Pectoral fin -->
      <path d="M155 140 Q165 180 140 190 Q125 175 140 145Z" fill="#c4def2"/>
      <!-- Tail fluke -->
      <path d="M355 125 Q390 85 400 70 Q385 120 395 155 Q375 140 360 130Z" fill="#b0d4ec"/>
      <path d="M355 130 Q380 125 390 135 Q375 130 360 132Z" fill="#98c4de"/>
      <!-- Dorsal fin -->
      <path d="M195 72 Q210 35 225 68Z" fill="#c4def2"/>
      <!-- Eye with highlights -->
      <ellipse cx="350" cy="105" rx="11" ry="14" fill="#3a5a7c"/>
      <ellipse class="whale-eye-highlight" cx="353" cy="101" rx="4.5" ry="5.5" fill="white"/>
      <circle cx="356" cy="98" r="2" fill="white"/>
      <circle cx="349" cy="108" r="1.2" fill="white"/>
      <path d="M340 100 Q350 93 360 98" stroke="#3a5a7c" stroke-width="2.5" fill="none" stroke-linecap="round"/>
      <!-- Blush -->
      <ellipse class="whale-blush" cx="335" cy="122" rx="14" ry="8" fill="#fce4ec" opacity="0.6"/>
      <!-- Smile -->
      <path d="M330 112 Q340 120 320 126" stroke="#3a5a7c" stroke-width="2.2" fill="none" stroke-linecap="round" opacity="0.7"/>
      <!-- Water spout group -->
      <g class="whale-spout-group">
        <path d="M108 78 Q105 38 100 18" stroke="#dcecf8" stroke-width="3.5" fill="none" stroke-linecap="round" opacity="0.9"/>
        <path d="M115 74 Q120 30 118 12" stroke="#dcecf8" stroke-width="3" fill="none" stroke-linecap="round" opacity="0.8"/>
        <path d="M102 76 Q92 42 88 22" stroke="#dcecf8" stroke-width="2.5" fill="none" stroke-linecap="round" opacity="0.7"/>
        <circle cx="100" cy="16" r="4" fill="#e0eef8" opacity="0.85"/>
        <circle cx="118" cy="10" r="3.2" fill="#e0eef8" opacity="0.75"/>
        <circle cx="88" cy="20" r="2.8" fill="#e0eef8" opacity="0.65"/>
        <circle cx="108" cy="6" r="2.5" fill="#e8f2fa" opacity="0.55"/>
        <circle cx="95" cy="8" r="1.8" fill="#eef6fc" opacity="0.4"/>
        <circle cx="120" cy="3" r="1.5" fill="#eef6fc" opacity="0.35"/>
      </g>
      <!-- Sparkle stars -->
      <g opacity="0.85">
        <path d="M260 65 L262 58 L264 65 L271 67 L264 69 L262 76 L260 69 L253 67Z" fill="#fff1c1"/>
        <path d="M375 85 L376 80 L377 85 L382 86 L377 87 L376 92 L375 87 L370 86Z" fill="#fff1c1"/>
        <path d="M210 48 L212 42 L214 48 L220 50 L214 52 L212 58 L210 52 L204 50Z" fill="#fffdf0"/>
        <path d="M310 55 L312 49 L314 55 L320 57 L314 59 L312 65 L310 59 L304 57Z" fill="#fffdf0"/>
        <path d="M170 58 L171 54 L172 58 L176 59 L172 60 L171 64 L170 60 L166 59Z" fill="#fff1c1"/>
        <path d="M390 100 L391 97 L392 100 L395 101 L392 102 L391 105 L390 102 L387 101Z" fill="#fffdf0"/>
        <circle cx="285" cy="52" r="1.8" fill="#fff1c1"/>
        <circle cx="240" cy="72" r="1.5" fill="#fffdf0"/>
        <circle cx="320" cy="45" r="1.3" fill="#fff1c1"/>
        <circle cx="195" cy="80" r="1.1" fill="#fffdf0"/>
        <circle cx="360" cy="60" r="1.6" fill="#fff1c1"/>
      </g>
      <!-- Tiny companion bird -->
      <g opacity="0.65">
        <path d="M245 35 Q250 32 255 35" stroke="#7eb8da" stroke-width="1.5" fill="none" stroke-linecap="round"/>
        <path d="M245 35 L242 38 L244 37 L243 40 L246 38 L248 39 L246 36Z" fill="#a0d0ef"/>
      </g>
    </svg>`;

  function initWhale() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    // Create whale stage
    const stage = document.createElement("div");
    stage.className = "whale-stage";
    stage.id = "interactiveWhale";
    stage.setAttribute("aria-hidden", "true");
    document.body.appendChild(stage);

    // Create whale actor
    const actor = document.createElement("div");
    actor.className = "whale-actor";
    actor.innerHTML = whaleSVG;
    actor.setAttribute("role", "img");
    actor.setAttribute("aria-label", "一只在天空中游动的鲸鱼");
    actor.title = "点击让鲸鱼跳跃！";
    stage.appendChild(actor);

    // Exhale animation cycle
    const spout = actor.querySelector(".whale-spout-group");
    let exhaleTimer;

    function startExhaleCycle() {
      if (actor.classList.contains("leaping")) return;
      spout.classList.add("exhaling");
      exhaleTimer = setTimeout(() => {
        spout.classList.remove("exhaling");
        exhaleTimer = setTimeout(startExhaleCycle, 2000);
      }, 2400);
    }

    function stopExhaleCycle() {
      spout.classList.remove("exhaling");
      clearTimeout(exhaleTimer);
    }

    // Hover: whale tracks mouse position within viewport, tilts toward cursor
    let hoverRAF = null;

    actor.addEventListener("mouseenter", () => {
      actor.classList.add("hovering");
      startExhaleCycle();

      document.addEventListener("mousemove", onWhaleHover, { passive: true });
    });

    actor.addEventListener("mouseleave", () => {
      actor.classList.remove("hovering");
      stopExhaleCycle();
      document.removeEventListener("mousemove", onWhaleHover);
      if (hoverRAF) cancelAnimationFrame(hoverRAF);
      // Reset position
      actor.style.transform = "";
    });

    function onWhaleHover(e) {
      if (hoverRAF) cancelAnimationFrame(hoverRAF);
      hoverRAF = requestAnimationFrame(() => {
        const rect = actor.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dx = (e.clientX - cx) / window.innerWidth;
        const dy = (e.clientY - cy) / window.innerHeight;
        const tiltX = dy * 8; // pitch
        const tiltY = dx * 6; // yaw
        const moveX = dx * 20;
        const moveY = dy * 15;
        actor.style.transform = `translate(${moveX}px, ${moveY}px) rotateX(${-tiltX}deg) rotateY(${tiltY}deg)`;
      });
    }

    // Click: leap animation
    actor.addEventListener("click", (e) => {
      if (actor.classList.contains("leaping")) return;
      e.stopPropagation();
      stopExhaleCycle();
      actor.classList.add("leaping");
      actor.classList.remove("hovering");
      document.removeEventListener("mousemove", onWhaleHover);
      actor.style.transform = "";

      // Spawn splash particles
      spawnSplash(actor);

      // Return to idle after leap
      setTimeout(() => {
        actor.classList.remove("leaping");
        actor.classList.add("returned");
        setTimeout(() => {
          actor.classList.remove("returned");
        }, 100);
      }, 1200);
    });

    // Start first exhale
    startExhaleCycle();
  }

  function spawnSplash(actor) {
    const rect = actor.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height * 0.7;

    const container = document.createElement("div");
    container.className = "whale-splash";
    container.style.left = cx + "px";
    container.style.top = cy + "px";
    document.body.appendChild(container);

    const count = 12;
    for (let i = 0; i < count; i++) {
      const droplet = document.createElement("div");
      droplet.className = "droplet";
      const angle = (Math.PI * 2 * i) / count + Math.random() * 0.5;
      const distance = 25 + Math.random() * 45;
      droplet.style.setProperty("--sx", Math.cos(angle) * distance + "px");
      droplet.style.setProperty(
        "--sy",
        Math.sin(angle) * distance - 20 - Math.random() * 30 + "px"
      );
      droplet.style.animationDelay = Math.random() * 0.15 + "s";
      droplet.style.width = 4 + Math.random() * 8 + "px";
      droplet.style.height = droplet.style.width;
      container.appendChild(droplet);
    }

    setTimeout(() => {
      container.remove();
    }, 1000);
  }

  // =============================================================
  // MODULE 2: Parallax Cloud Layers
  // Replaces body::before radial-gradient clouds
  // =============================================================

  function initClouds() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const layers = [
      { cls: "cloud-layer--far", blobs: generateBlobs(6, 8, 14) },
      { cls: "cloud-layer--mid", blobs: generateBlobs(5, 5, 10) },
      { cls: "cloud-layer--near", blobs: generateBlobs(4, 3, 7) },
    ];

    layers.forEach((layer) => {
      const el = document.createElement("div");
      el.className = "cloud-layer " + layer.cls;
      el.setAttribute("aria-hidden", "true");
      layer.blobs.forEach((b) => {
        const blob = document.createElement("div");
        blob.className = "cloud-blob cloud-blob--" + b.size;
        blob.style.top = b.top + "%";
        blob.style.left = b.left + "%";
        blob.style.animationDelay = b.delay + "s";
        blob.style.animationDuration = b.duration + "s";
        el.appendChild(blob);
      });
      document.body.insertBefore(el, document.body.firstChild);
    });

    // Create .cloud-container wrapper for scroll parallax (v7.1)
    const container = document.createElement("div");
    container.className = "cloud-container";
    document.querySelectorAll(".cloud-layer").forEach(layer => {
      container.appendChild(layer);
    });
    document.body.insertBefore(container, document.body.firstChild);

    // Mouse-driven parallax on near + mid layers
    let parallaxRAF;
    document.addEventListener(
      "mousemove",
      (e) => {
        if (parallaxRAF) cancelAnimationFrame(parallaxRAF);
        parallaxRAF = requestAnimationFrame(() => {
          const xPct = e.clientX / window.innerWidth;
          const yPct = e.clientY / window.innerHeight;
          const nearLayer = document.querySelector(".cloud-layer--near");
          const midLayer = document.querySelector(".cloud-layer--mid");
          if (nearLayer) {
            nearLayer.classList.add("parallax-active");
            nearLayer.style.transform = `translate(${(xPct - 0.5) * -12}px, ${(yPct - 0.5) * -8}px)`;
          }
          if (midLayer) {
            midLayer.classList.add("parallax-active");
            midLayer.style.transform = `translate(${(xPct - 0.5) * -6}px, ${(yPct - 0.5) * -4}px)`;
          }
        });
      },
      { passive: true }
    );

    // Parallax: react to scroll on content areas
    const scrollAreas = document.querySelectorAll(
      ".content-area, .summary-main, .browse-grid-panel, .kb-chat, .fav-right"
    );
    scrollAreas.forEach((area) => {
      area.addEventListener(
        "scroll",
        () => {
          const farLayer = document.querySelector(".cloud-layer--far");
          if (farLayer) {
            farLayer.style.transform = `translateY(${area.scrollTop * 0.02}px)`;
          }
        },
        { passive: true }
      );
    });
  }

  function generateBlobs(count, minTop, maxTop) {
    const sizes = ["lg", "md", "md", "sm", "sm", "xs", "xs"];
    const blobs = [];
    for (let i = 0; i < count; i++) {
      blobs.push({
        size: sizes[Math.floor(Math.random() * sizes.length)],
        top: minTop + Math.random() * (maxTop - minTop),
        left: Math.random() * 110 - 10, // -10% to 110%
        delay: Math.random() * 30,
        duration: 40 + Math.random() * 60,
      });
    }
    return blobs;
  }

  // =============================================================
  // MODULE 3: Modal Open/Close Animations
  // Replaces display:none/flex toggle with animated visibility
  // =============================================================

  function initModals() {
    // Patch openSettings to use animation
    const origOpenSettings = window.openSettings;
    window.openSettings = function () {
      origOpenSettings();
      const modal = document.getElementById("settingsModal");
      if (modal) animateModalOpen(modal);
    };

    // Patch closeSettings to use animation
    const origCloseSettings = window.closeSettings;
    window.closeSettings = function () {
      const modal = document.getElementById("settingsModal");
      if (modal && modal.classList.contains("open")) {
        animateModalClose(modal, () => {
          origCloseSettings();
        });
      } else {
        origCloseSettings();
      }
    };

    // Patch openLogin
    const origOpenLogin = window.openLogin;
    window.openLogin = function () {
      origOpenLogin();
      const modal = document.getElementById("loginModal");
      if (modal) animateModalOpen(modal);
    };

    // Patch closeLogin
    const origCloseLogin = window.closeLogin;
    window.closeLogin = function () {
      const modal = document.getElementById("loginModal");
      if (modal && modal.classList.contains("open")) {
        animateModalClose(modal, () => {
          origCloseLogin();
        });
      } else {
        origCloseLogin();
      }
    };

    // Intercept all modal-backdrop click-to-close
    document.querySelectorAll(".modal-backdrop").forEach((bd) => {
      bd.addEventListener("click", function (e) {
        if (e.target === this && this.classList.contains("open")) {
          const modal = this;
          animateModalClose(modal, () => {
            modal.style.display = "none";
            modal.classList.remove("open", "closing");
          });
        }
      });
    });

    // Also handle .btn-icon close buttons
    document.addEventListener("click", (e) => {
      const closeBtn = e.target.closest(".btn-icon");
      if (!closeBtn) return;
      const modal = closeBtn.closest(".modal-backdrop");
      if (!modal || !modal.classList.contains("open")) return;
      // Let the original handler fire, but animate
      const origHandler = closeBtn.onclick;
      if (origHandler) {
        e.preventDefault();
        e.stopPropagation();
        animateModalClose(modal, () => {
          closeBtn.onclick = null;
          closeBtn.click();
          setTimeout(() => {
            closeBtn.onclick = origHandler;
          }, 50);
        });
      }
    });
  }

  function animateModalOpen(modal) {
    modal.style.display = "flex";
    // Force reflow
    modal.offsetHeight;
    modal.classList.add("open");
    modal.classList.remove("closing");
  }

  function animateModalClose(modal, callback) {
    modal.classList.remove("open");
    modal.classList.add("closing");
    setTimeout(() => {
      modal.classList.remove("closing");
      if (callback) callback();
    }, 250);
  }

  // =============================================================
  // MODULE 4: View Transition API Navigation
  // Intercepts hard location.href to use view-transition
  // =============================================================

  function initPageTransitions() {
    // Only enable if View Transition API is supported
    if (!document.startViewTransition) return;

    // Intercept all internal navigation
    document.addEventListener("click", (e) => {
      const link = e.target.closest("a");
      if (!link) return;

      const href = link.getAttribute("href");
      if (!href || href.startsWith("http") || href.startsWith("#") || href.startsWith("javascript:"))
        return;

      // Only intercept internal page links
      if (
        href === "/browse" ||
        href === "/summary" ||
        href === "/kb" ||
        href === "/favorites" ||
        href === "/tools"
      ) {
        e.preventDefault();
        document.startViewTransition(() => {
          window.location.href = href;
        });
      }
    });

    // Also intercept onclick="location.href=..." patterns
    const origAssign = window.location.assign.bind(window.location);
    // We can't easily intercept location.href, but the <a> tag and onclick handlers will be caught
  }

  // =============================================================
  // MODULE 5: Surface existing skeleton functions on API calls
  // =============================================================

  function enhanceSkeletonUsage() {
    // Patch showLoading/hideLoading to use skeleton where possible
    const origShowLoading = window.showLoading;
    window.showLoading = function (msg) {
      // If overlay exists, use it; otherwise fall through
      const overlay = document.getElementById("loadingOverlay");
      if (overlay) {
        origShowLoading(msg);
      }
    };

    // Provide a unified skeleton -> content pattern
    window.loadWithSkeleton = async function (containerId, skeletonType, fetchFn) {
      showSkeleton(containerId, skeletonType);
      try {
        const result = await fetchFn();
        hideSkeleton(containerId);
        return result;
      } catch (e) {
        hideSkeleton(containerId);
        throw e;
      }
    };
  }

  // =============================================================
  // MODULE 6: Error boundary & global enhancement
  // =============================================================

  function initErrorBoundary() {
    // Wrap the existing window.onerror with full parameter passthrough
    // common.js already handles toast, so we preserve that and add logging
    const origOnerror = window.onerror;
    window.onerror = function (msg, url, line, col, error) {
      // Log structured error for diagnostics (no duplicate toast)
      try {
        console.error(
          "[BiliSum v2.0] uncaught error:",
          { msg, url, line, col, stack: error && error.stack ? error.stack : undefined }
        );
        // Show error-state inline in content-area only if possible
        const contentArea = document.querySelector(".content-area");
        if (contentArea && typeof window.renderErrorState === "function") {
          window.renderErrorState("content-area", {
            message: msg,
            title: "JS Error",
            icon: "&#x26A0;",
            onRetry: function () { location.reload(); }
          });
        }
      } catch (e) {}
      // Forward all params to original handler (common.js: showToast + return false)
      if (origOnerror) return origOnerror.call(this, msg, url, line, col, error);
      return false;
    };
  }

  // =============================================================
  // MODULE 7: Smooth scroll-to for result cards & anchor links
  // =============================================================

  function initSmoothScroll() {
    // Already set in CSS: html { scroll-behavior: smooth; }
    // Enhance anchors within content-area
    document.addEventListener("click", (e) => {
      const target = e.target.closest('[href^="#"]');
      if (!target) return;
      const id = target.getAttribute("href").slice(1);
      const el = document.getElementById(id);
      if (el) {
        e.preventDefault();
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  // =============================================================
  // INIT: Bootstrap all modules
  // =============================================================

  ready(function () {
    initWhale();
    initClouds();
    initModals();
    initPageTransitions();
    enhanceSkeletonUsage();
    initErrorBoundary();
    initSmoothScroll();
    initWhaleInteractionV7();
    initCloudParallaxV7();

    // Set up ResizeObserver for desktop-first responsive adaptation
    if (window.ResizeObserver) {
      const ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const width = entry.contentRect.width;
          const html = document.documentElement;
          if (width >= 1440) html.dataset.breakpoint = "xl";
          else if (width >= 1024) html.dataset.breakpoint = "lg";
          else if (width >= 768) html.dataset.breakpoint = "md";
          else if (width >= 601) html.dataset.breakpoint = "sm";
          else html.dataset.breakpoint = "xs";
        }
      });
      ro.observe(document.documentElement);
    }

    console.log(
      "%c BiliSum v2.0 %c frontend-design enhancements loaded ",
      "background: linear-gradient(135deg, #7eb8da, #5b9ed4); color: #fff; padding: 4px 8px; border-radius: 4px; font-weight: 600;",
      "color: #7eb8da;"
    );
    console.log(
      "%c Interactive whale %c | Parallax clouds %c | Modal animations %c | View Transitions %c | Unified states",
      "color: #fb7299;",
      "color: #7eb8da;",
      "color: #5b9ed4;",
      "color: #b0d4ec;",
      "color: #999;"
    );
  });
})();

// ====== Whale Interaction v4 (v7.1) ======
  function initWhaleInteractionV7() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const whale = document.getElementById('interactiveWhale');
    if (!whale) return;

    // 5-axis animation state machine: idle -> breathe -> curious -> leap -> spout
    let state = 'idle';
    let hoverTimer = null;

    whale.addEventListener('mouseenter', () => {
        state = 'curious';
        whale.style.transform = 'scale(1.05)';
        whale.style.transition = 'transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)';
        clearTimeout(hoverTimer);
    });

    whale.addEventListener('mouseleave', () => {
        state = 'idle';
        whale.style.transform = 'scale(1)';
        hoverTimer = setTimeout(() => {
            state = 'breathe';
        }, 2000);
    });

    whale.addEventListener('click', () => {
        if (state === 'leap') return;
        state = 'leap';
        whale.style.transform = 'scale(1.15) translateY(-10px)';
        whale.style.transition = 'transform 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
        setTimeout(() => {
            whale.style.transform = 'scale(1) translateY(0)';
            state = 'idle';
        }, 600);

        // Trigger scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

// ====== Parallax Cloud System v2 (v7.1) ======
  function initCloudParallaxV7() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const cloudContainer = document.querySelector('.cloud-container');
    if (!cloudContainer) return;

    // 3-layer parallax: clouds drift at different speeds
    const layers = cloudContainer.querySelectorAll('.cloud-layer');
    const speeds = [0.2, 0.5, 0.8]; // slow to fast

    let scrollY = 0;
    window.addEventListener('scroll', () => {
        scrollY = window.scrollY;
        layers.forEach((layer, i) => {
            if (layer && speeds[i]) {
                // Append to existing transform to avoid clobbering the main module's mouse/scroll parallax
                const currentTransform = layer.style.transform || '';
                layer.style.transform = currentTransform + ' translateX(' + (scrollY * speeds[i] * 0.1) + 'px)';
            }
        });
    }, { passive: true });
  }

