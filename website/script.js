(() => {
  "use strict";
  const motionPreference = matchMedia("(prefers-reduced-motion: reduce)");
  const animate = (element, frames, options = {}) => {
    if (!element || motionPreference.matches || !element.animate) return;
    return element.animate(frames, {
      duration: 460,
      easing: "cubic-bezier(.2,.75,.25,1)",
      ...options,
    });
  };
  const enter = (element, delay = 0, distance = 18) =>
    animate(
      element,
      [
        { opacity: 0, transform: `translateY(${distance}px)` },
        { opacity: 1, transform: "translateY(0)" },
      ],
      { delay, fill: "backwards" },
    );
  motionPreference.addEventListener("change", () => {
    if (motionPreference.matches)
      document.getAnimations().forEach((a) => a.cancel());
  });

  // Animate the selection surface itself, so the control visibly follows the choice.
  const moveIndicator = (list, selected) => {
    if (!list || !selected) return;
    list.classList.add("has-indicator");
    list.style.setProperty("--indicator-x", `${selected.offsetLeft}px`);
    list.style.setProperty("--indicator-y", `${selected.offsetTop}px`);
    list.style.setProperty("--indicator-width", `${selected.offsetWidth}px`);
    list.style.setProperty("--indicator-height", `${selected.offsetHeight}px`);
  };

  const menuButton = document.querySelector(".menu-toggle");
  const mobileNav = document.querySelector("#mobile-nav");
  if (menuButton && mobileNav) {
    menuButton.hidden = false;
    let menuMotion;
    const closeMenu = () => {
      menuMotion?.cancel();
      menuButton.setAttribute("aria-expanded", "false");
      const finish = () => { mobileNav.hidden = true; };
      menuMotion = animate(mobileNav, [{ opacity: 1, transform: "translateY(0)" }, { opacity: 0, transform: "translateY(-6px)" }], { duration: 160 });
      if (menuMotion) { menuMotion.onfinish = finish; menuMotion.oncancel = finish; }
      else finish();
    };
    menuButton.addEventListener("click", () => {
      const isOpen = menuButton.getAttribute("aria-expanded") === "true";
      if (isOpen) return closeMenu();
      if (menuMotion) { menuMotion.oncancel = null; menuMotion.cancel(); }
      menuButton.setAttribute("aria-expanded", "true");
      mobileNav.hidden = false;
      menuMotion = enter(mobileNav, 0, -8);
    });
    mobileNav.addEventListener("click", (event) => {
      if (event.target.closest("a")) closeMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !mobileNav.hidden) {
        closeMenu();
        menuButton.focus();
      }
    });
    matchMedia("(min-width: 601px)").addEventListener("change", (event) => {
      if (event.matches) closeMenu();
    });
  }

  // Native links remain available; the no-script stylesheet exposes every panel.
  document.querySelectorAll("[data-tabs]").forEach((group) => {
    const tabs = [...group.querySelectorAll('[role="tab"]')];
    const panels = tabs.map((tab) =>
      document.getElementById(tab.getAttribute("aria-controls")),
    );
    const next = group.querySelector("[data-next-step]");
    const nextLabels = [
      "Next: trace the change",
      "Next: check the evidence",
      "Next: make the decision",
      "Back to the intent",
    ];
    const list = group.querySelector('[role="tablist"]');
    const host = group.querySelector(".demo-content, .showcase-content");
    let heightMotion;
    let selected = -1;
    const positionIndicator = () => {
      if (next) list.setAttribute("aria-orientation", innerWidth <= 600 ? "horizontal" : "vertical");
      moveIndicator(list, tabs[selected]);
    };
    if ("ResizeObserver" in window) new ResizeObserver(positionIndicator).observe(list);
    document.fonts?.ready.then(positionIndicator);
    const select = (index, focus = false) => {
      const changed = selected !== index;
      const wasInitialized = selected !== -1;
      const direction = index > selected ? 1 : -1;
      host.querySelectorAll(".panel-snapshot").forEach((snapshot) => snapshot.remove());
      let snapshot;
      if (changed && wasInitialized && !motionPreference.matches) {
        const outgoing = panels[selected];
        snapshot = outgoing.cloneNode(true);
        snapshot.className = "panel-snapshot";
        snapshot.removeAttribute("id");
        snapshot.removeAttribute("role");
        snapshot.removeAttribute("tabindex");
        snapshot.removeAttribute("aria-labelledby");
        snapshot.setAttribute("aria-hidden", "true");
        snapshot.inert = true;
        snapshot.querySelectorAll("[id]").forEach((el) => el.removeAttribute("id"));
        snapshot.style.padding = getComputedStyle(outgoing).padding;
        const quote = snapshot.querySelector("blockquote");
        if (quote) quote.style.font = getComputedStyle(outgoing.querySelector("blockquote")).font;
        snapshot.style.height = `${outgoing.getBoundingClientRect().height}px`;
      }
      const previousHeight = host.getBoundingClientRect().height;
      heightMotion?.cancel();
      selected = index;
      tabs.forEach((tab, i) => {
        tab.setAttribute("aria-selected", String(i === index));
        tab.tabIndex = i === index ? 0 : -1;
        panels[i].hidden = i !== index;
      });
      group.style.setProperty(
        "--step-progress",
        `${((index + 1) / tabs.length) * 100}%`,
      );
      positionIndicator();
      if (changed && wasInitialized) {
        // A new selection supersedes the previous one, including mid-transition.
        panels.forEach((panel) => panel.getAnimations({ subtree: true }).forEach((a) => a.cancel()));
        const targetHeight = panels[index].getBoundingClientRect().height;
        if (Math.abs(targetHeight - previousHeight) > 1) {
          host.classList.add("is-resizing");
          heightMotion = animate(host, [{ height: `${previousHeight}px` }, { height: `${targetHeight}px` }], { duration: 380 });
          const finish = () => host.classList.remove("is-resizing");
          if (heightMotion) {
            const currentMotion = heightMotion;
            const settle = () => { if (heightMotion === currentMotion) finish(); };
            heightMotion.onfinish = settle; heightMotion.oncancel = settle;
          } else finish();
        }
        if (snapshot) {
          host.append(snapshot);
          const exit = animate(snapshot, [{ opacity: 1, transform: "translateX(0)" }, { opacity: 0, transform: `translateX(${-direction * 8}px)` }], { duration: 180 });
          if (exit) { exit.onfinish = () => snapshot.remove(); exit.oncancel = () => snapshot.remove(); }
          else snapshot.remove();
        }
        [...panels[index].children].forEach((child, i) =>
          animate(child, [{ opacity: 0, transform: `translateX(${direction * 14}px)` }, { opacity: 1, transform: "translateX(0)" }], { duration: 340, delay: 60 + Math.min(i * 35, 105), fill: "backwards" }),
        );
      }
      if (next) {
        next.replaceChildren(document.createTextNode(nextLabels[index] + " "));
        const arrow = document.createElement("span");
        arrow.setAttribute("aria-hidden", "true");
        arrow.textContent = "→";
        next.append(arrow);
      }
      if (focus) tabs[index].focus();
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => select(index));
      tab.addEventListener("keydown", (event) => {
        let target;
        const vertical =
          tab.parentElement.getAttribute("aria-orientation") === "vertical";
        if (event.key === "Home") target = 0;
        else if (event.key === "End") target = tabs.length - 1;
        else if (
          event.key === "ArrowRight" ||
          (vertical && event.key === "ArrowDown")
        )
          target = (index + 1) % tabs.length;
        else if (
          event.key === "ArrowLeft" ||
          (vertical && event.key === "ArrowUp")
        )
          target = (index - 1 + tabs.length) % tabs.length;
        if (target !== undefined) {
          event.preventDefault();
          select(target, true);
        }
      });
    });
    next?.addEventListener("click", () => {
      const index = tabs.findIndex(
        (tab) => tab.getAttribute("aria-selected") === "true",
      );
      const target = (index + 1) % tabs.length;
      select(target);
      // Announce the newly displayed step and keep keyboard focus inside it.
      panels[target].focus({ preventScroll: true });
    });
    select(0);
    if (next) {
      document.querySelectorAll("[data-jump-step]").forEach((link) => {
        link.addEventListener("click", (event) => {
          if (
            event.ctrlKey ||
            event.metaKey ||
            event.shiftKey ||
            event.altKey ||
            event.button !== 0
          )
            return;
          const index = tabs.findIndex(
            (tab) => tab.id === "step-" + link.dataset.jumpStep,
          );
          if (index < 0) return;
          event.preventDefault();
          select(index);
          history.pushState(null, "", "#walkthrough");
          group.scrollIntoView({
            block: "start",
            behavior: motionPreference.matches ? "instant" : "smooth",
          });
          panels[index].focus({ preventScroll: true });
        });
      });
    }
  });

  const toast = document.querySelector("[data-toast]");
  let toastTimer;
  const notify = (message) => {
    if (!toast) return;
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 4500);
  };
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", async () => {
      const source = document.getElementById(button.dataset.copy);
      if (!source) return;
      try {
        if (!navigator.clipboard?.writeText)
          throw new Error("Clipboard is unavailable");
        await navigator.clipboard.writeText(source.textContent.trim());
        notify(
          button.dataset.copy === "bibtex"
            ? "BibTeX copied."
            : "Setup commands copied.",
        );
      } catch {
        const disclosure = source.closest("details");
        if (disclosure) disclosure.open = true;
        const range = document.createRange();
        range.selectNodeContents(source);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        source.scrollIntoView({ block: "center", behavior: "auto" });
        notify(
          "Automatic copy is unavailable. Text selected — press ⌘C or Ctrl+C to copy.",
        );
      }
    });
  });

  // Native image links still work without JavaScript or dialog support.
  const imageDialog = document.querySelector(".image-dialog");
  if (imageDialog?.showModal) {
    const image = imageDialog.querySelector("img");
    const viewport = imageDialog.querySelector(".image-dialog-viewport");
    const zoomButton = imageDialog.querySelector("[data-image-zoom]");
    const closeButton = imageDialog.querySelector("[data-image-close]");
    let dialogMotion;
    const closeImage = () => {
      if (imageDialog.classList.contains("is-closing")) return;
      dialogMotion?.cancel();
      imageDialog.classList.add("is-closing");
      const finish = () => { imageDialog.classList.remove("is-closing"); imageDialog.close(); };
      dialogMotion = animate(imageDialog, [{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: "scale(.98)" }], { duration: 160 });
      if (dialogMotion) { dialogMotion.onfinish = finish; dialogMotion.oncancel = finish; }
      else finish();
    };
    let imageTrigger;
    let previousOverflow;
    const resetZoom = () => {
      imageDialog.classList.remove("is-zoomed");
      zoomButton.setAttribute("aria-pressed", "false");
      zoomButton.textContent = "Actual size";
      viewport.scrollTo(0, 0);
    };
    document.querySelectorAll(".screenshot-link").forEach((link) => {
      link.addEventListener("click", (event) => {
        if (
          event.ctrlKey ||
          event.metaKey ||
          event.shiftKey ||
          event.altKey ||
          event.button !== 0
        )
          return;
        event.preventDefault();
        imageTrigger = link;
        image.src = link.href;
        image.alt = link.querySelector("img").alt;
        imageDialog.querySelector(".image-dialog-caption").textContent =
          image.alt;
        resetZoom();
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        imageDialog.showModal();
        closeButton.focus();
        dialogMotion = animate(imageDialog, [{ opacity: 0, transform: "translateY(14px) scale(.98)" }, { opacity: 1, transform: "translateY(0) scale(1)" }], { duration: 360 });
      });
    });
    imageDialog.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const controls = [zoomButton, closeButton, viewport];
      const index = controls.indexOf(document.activeElement);
      if (event.shiftKey && index <= 0) {
        event.preventDefault();
        viewport.focus();
      } else if (!event.shiftKey && index === controls.length - 1) {
        event.preventDefault();
        zoomButton.focus();
      }
    });
    closeButton.addEventListener("click", closeImage);
    imageDialog.addEventListener("cancel", (event) => { event.preventDefault(); closeImage(); });
    imageDialog.addEventListener("click", (event) => {
      if (event.target !== imageDialog) return;
      const rect = imageDialog.getBoundingClientRect();
      if (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
      )
        closeImage();
    });
    imageDialog.addEventListener("close", () => {
      document.body.style.overflow = previousOverflow;
      imageTrigger?.focus({ preventScroll: true });
    });
    zoomButton.addEventListener("click", () => {
      const zoomed = imageDialog.classList.toggle("is-zoomed");
      zoomButton.setAttribute("aria-pressed", String(zoomed));
      zoomButton.textContent = zoomed ? "Fit to screen" : "Actual size";
      viewport.scrollTo(0, 0);
      image.getAnimations().forEach((a) => a.cancel());
      animate(image, [{ opacity: .6 }, { opacity: 1 }], { duration: 200 });
    });
  }

  // Native disclosures still work without JS; height follows the actual content.
  document.querySelectorAll("details").forEach((details) => {
    const summary = details.querySelector("summary");
    let disclosureMotion;
    let expanded = details.open;
    summary.addEventListener("click", (event) => {
      event.preventDefault();
      const start = details.getBoundingClientRect().height;
      expanded = disclosureMotion?.playState === "running" ? !expanded : !details.open;
      if (disclosureMotion) { disclosureMotion.oncancel = null; disclosureMotion.cancel(); }
      details.open = expanded;
      const end = details.getBoundingClientRect().height;
      details.open = true;
      details.classList.add("is-resizing");
      details.dataset.expanded = String(expanded);
      const finish = () => {
        details.open = expanded;
        details.classList.remove("is-resizing");
        delete details.dataset.expanded;
      };
      disclosureMotion = animate(details, [{ height: `${start}px` }, { height: `${end}px` }], { duration: 300 });
      if (disclosureMotion) { disclosureMotion.onfinish = finish; disclosureMotion.oncancel = finish; }
      else finish();
    });
  });
  const openCitation = () => {
    if (location.hash === "#citation")
      document.querySelector(".citation-source").open = true;
  };
  window.addEventListener("hashchange", openCitation);
  openCitation();

  // A finite, replayable trace: movement explains the review order; it never auto-loops.
  const trace = document.querySelector(".hero-trace");
  const replay = document.querySelector("[data-replay-trace]");
  const nodes = [...document.querySelectorAll(".trace-node")];
  const traceStatus = document.querySelector("[data-trace-status]");
  const traceCount = document.querySelector("[data-trace-count]");
  let traceTimers = [];
  const traceLabels = ["Agree on the scope", "Spot the authority mismatch", "Find the missing evidence", "Keep the decision with a human"];
  const stopTrace = () => {
    traceTimers.forEach(clearTimeout);
    traceTimers = [];
    trace.classList.remove("is-playing");
    nodes.forEach((node) => node.classList.remove("is-tracing"));
    trace.style.setProperty("--trace-progress", "100%");
    traceStatus.textContent = "Intent → change → evidence → decision";
    traceCount.textContent = "04 / 04";
  };
  const playTrace = () => {
    stopTrace();
    if (motionPreference.matches) return;
    trace.classList.add("is-playing");
    const step = (index) => {
      nodes.forEach((node, i) => node.classList.toggle("is-tracing", i === index));
      trace.style.setProperty("--trace-progress", `${(index + 1) * 25}%`);
      traceStatus.textContent = traceLabels[index];
      traceCount.textContent = `0${index + 1} / 04`;
      animate(nodes[index].querySelector(".trace-index"), [{ transform: "scale(.85)" }, { transform: "scale(1.12)", offset: .45 }, { transform: "scale(1)" }], { duration: 500 });
    };
    step(0);
    [1, 2, 3].forEach((index) => traceTimers.push(setTimeout(() => step(index), index * 950)));
    traceTimers.push(setTimeout(stopTrace, 3900));
  };
  if (trace && replay) {
    replay.hidden = false;
    replay.addEventListener("click", playTrace);
    motionPreference.addEventListener("change", stopTrace);
    document.addEventListener("visibilitychange", () => { if (document.hidden) stopTrace(); });
    if ("IntersectionObserver" in window) {
      let introduced = false;
      new IntersectionObserver(([entry]) => {
        if (!entry.isIntersecting) { stopTrace(); return; }
        if (!introduced) { introduced = true; playTrace(); }
      }, { threshold: .35 }).observe(trace);
    }
  }

  // Short, grouped entrances leave large reading surfaces steady and readable.
  document.querySelectorAll(".hero-copy > *").forEach((element, i) => enter(element, i * 65, 12));
  if ("IntersectionObserver" in window) {
    const reveal = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const children = entry.target.matches(".state-model, .resource-list, .hero-authors")
          ? [...entry.target.children] : [entry.target];
        children.forEach((child, i) => enter(child, i * 65, 14));
        reveal.unobserve(entry.target);
      });
    }, { threshold: .15 });
    document.querySelectorAll(".walkthrough-intro > *, .section-heading > *, .credits-heading, .hero-authors, .state-model, .paper-main > h2, .research-note, .start-grid > *, .resource-list, .closing h2").forEach((element) => reveal.observe(element));
  }

  const header = document.querySelector(".site-header");
  const nav = document.querySelector(".top-nav");
  const navLinks = [...nav.querySelectorAll("a")];
  const navSections = navLinks.map((link) => document.querySelector(link.hash));
  let scrollFrame;
  const updateHeader = () => {
    scrollFrame = null;
    header.classList.toggle("is-scrolled", scrollY > 24);
    const distance = document.documentElement.scrollHeight - innerHeight;
    header.style.setProperty("--reading-progress", distance > 0 ? scrollY / distance : 0);
    let active = -1;
    navSections.forEach((section, i) => { if (section.getBoundingClientRect().top <= 220) active = i; });
    navLinks.forEach((link, i) => {
      if (i === active) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
    nav.classList.toggle("has-current", active >= 0);
    if (active >= 0) moveIndicator(nav, navLinks[active]);
  };
  const scheduleHeader = () => { if (!scrollFrame) scrollFrame = requestAnimationFrame(updateHeader); };
  window.addEventListener("scroll", scheduleHeader, { passive: true });
  window.addEventListener("resize", scheduleHeader);
  if ("ResizeObserver" in window) new ResizeObserver(scheduleHeader).observe(document.body);
  document.fonts?.ready.then(scheduleHeader);
  updateHeader();
})();
