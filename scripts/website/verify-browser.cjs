// Behavioral acceptance checks for the static project website.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { mkdirSync, writeFileSync } = require("node:fs");
const { resolve } = require("node:path");
const address = process.argv[2] || "http://127.0.0.1:8924";
const session = process.env.AGENT_BROWSER_SESSION || "agenticconsensus-restored-site";
const command = (...args) =>
  execFileSync("agent-browser", ["--session", session, ...args], {
    encoding: "utf8",
    maxBuffer: 8 * 1024 * 1024,
  }).trim();
// Browser input is sent only once entrance motion and smooth scrolling have settled.
const b = (...args) => {
  if (["click", "focus"].includes(args[0])) {
    command(
      "eval",
      `document.querySelector(${JSON.stringify(args[1])}).scrollIntoView({block:"center", behavior:"instant"}); true`,
    );
    command(
      "wait",
      "--fn",
      '[...document.getAnimations()].every(a => a.playState !== "running")',
    );
    command(
      "eval",
      `new Promise(resolve => {
      let previous = scrollY, stable = 0;
      function frame() {
        stable = previous === scrollY ? stable + 1 : 0;
        previous = scrollY;
        if (stable >= 6) resolve(true); else requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    })`,
    );
  }
  return command(...args);
};
const ev = (source) => JSON.parse(b("eval", source));
const checks = [];
const check = (name, fn) => {
  fn();
  checks.push(name);
  console.log("PASS " + name);
};
const out = resolve(process.env.WEBSITE_QA_DIR || "var/website-qa");
const settled = () =>
  b(
    "wait",
    "--fn",
    'document.fonts.status === "loaded" && [...document.getAnimations()].every(a => a.playState !== "running")',
  );
mkdirSync(out, { recursive: true });
try {
  b("open", address);
  b("wait", "--fn", 'document.fonts.status === "loaded"');
  check(
    "No horizontal overflow at 320, 375, 390, 768, 1024, and 1440px",
    () => {
      for (const width of [320, 375, 390, 768, 1024, 1440]) {
        b("set", "viewport", String(width), "1000");
        assert.equal(
          ev("document.documentElement.scrollWidth > innerWidth"),
          false,
          `${width}px`,
        );
      }
    },
  );
  check(
    "Walkthrough tabs expose the intended content and only one panel",
    () => {
      for (const step of ["intent", "change", "evidence", "decision"]) {
        b("click", "#step-" + step);
        assert.equal(
          ev(`document.querySelector('#panel-${step}').hidden`),
          false,
        );
        assert.equal(
          ev(
            '[...document.querySelectorAll(".demo-panel")].filter(x=>!x.hidden).length',
          ),
          1,
        );
        assert.equal(
          ev(
            `document.querySelector('#step-${step}').getAttribute('aria-selected')`,
          ),
          "true",
        );
      }
      assert.match(
        ev('document.querySelector("#panel-decision").textContent'),
        /Not ready to approve/,
      );
      b("click", "[data-next-step]");
      assert.equal(ev("document.activeElement.id"), "panel-intent");
      assert.equal(ev('document.querySelector("#panel-intent").hidden'), false);
    },
  );
  check("Tab arrow keys, Home and End move focus and selection", () => {
    b("focus", "#step-intent");
    b("press", "ArrowDown");
    assert.equal(ev("document.activeElement.id"), "step-change");
    b("press", "End");
    assert.equal(ev("document.activeElement.id"), "step-decision");
    b("press", "Home");
    assert.equal(ev("document.activeElement.id"), "step-intent");
  });
  check("All real workspace views and full-size image links work", () => {
    for (const [tab, panel] of [
      ["commitments", "commitments"],
      ["map", "map"],
      ["decision", "decision"],
    ]) {
      b("click", "#view-" + tab);
      b(
        "wait",
        "--fn",
        `[...document.querySelectorAll('#screen-${panel} img')].every(i=>i.complete && i.naturalWidth>0)`,
      );
      assert.equal(
        ev(`document.querySelector('#screen-${panel}').hidden`),
        false,
      );
      assert.equal(
        ev(
          '[...document.querySelectorAll(".screen-panel")].filter(x=>!x.hidden).length',
        ),
        1,
      );
      assert.ok(
        ev(`document.querySelector('#screen-${panel} a').href`).includes(
          "/assets/",
        ),
      );
    }
    b("focus", "#view-decision");
    b("press", "Home");
    b("press", "ArrowRight");
    assert.equal(ev("document.activeElement.id"), "view-map");
  });
  check(
    "Hero trace links select the matching step, update progress, and focus the panel",
    () => {
      for (const [index, step] of [
        "intent",
        "change",
        "evidence",
        "decision",
      ].entries()) {
        b("open", address);
        settled();
        b("click", `[data-jump-step="${step}"]`);
        assert.equal(
          ev(
            `document.querySelector('#step-${step}').getAttribute('aria-selected')`,
          ),
          "true",
        );
        assert.equal(ev("document.activeElement.id"), `panel-${step}`);
        assert.equal(
          ev(
            'document.querySelector(".review-demo").style.getPropertyValue("--step-progress")',
          ),
          `${(index + 1) * 25}%`,
        );
      }
    },
  );
  check(
    "Image viewer fits, zooms, traps focus, and restores focus and scrolling on dismissal",
    () => {
      for (const width of [1440, 390]) {
        b("set", "viewport", String(width), "1000");
        b("open", address);
        b("click", "#view-map");
        b("click", "#screen-map .screenshot-link");
        assert.equal(ev('document.querySelector(".image-dialog").open'), true);
        assert.equal(
          ev('document.activeElement.hasAttribute("data-image-close")'),
          true,
        );
        assert.equal(ev("document.body.style.overflow"), "hidden");
        assert.equal(
          ev(
            'document.querySelector(".image-dialog").getBoundingClientRect().width <= innerWidth',
          ),
          true,
        );
        b("click", "[data-image-zoom]");
        assert.equal(
          ev(
            'document.querySelector("[data-image-zoom]").getAttribute("aria-pressed")',
          ),
          "true",
        );
        assert.equal(
          ev(
            'document.querySelector(".image-dialog-viewport").scrollWidth > document.querySelector(".image-dialog-viewport").clientWidth',
          ),
          true,
        );
        b("focus", ".image-dialog-viewport");
        b("press", "Tab");
        assert.equal(
          ev('document.activeElement.hasAttribute("data-image-zoom")'),
          true,
        );
        b("click", "[data-image-zoom]");
        assert.equal(
          ev(
            'document.querySelector("[data-image-zoom]").getAttribute("aria-pressed")',
          ),
          "false",
        );
        b("press", "Escape");
        b("wait", "--fn", '!document.querySelector(".image-dialog").open');
        assert.equal(ev('document.querySelector(".image-dialog").open'), false);
        assert.equal(ev("document.body.style.overflow"), "");
        assert.equal(
          ev('document.activeElement.closest(".screen-panel").id'),
          "screen-map",
        );
      }
    },
  );
  check(
    "Mobile navigation opens, dismisses with Escape, and follows anchors",
    () => {
      b("set", "viewport", "390", "844");
      b("scroll", "top");
      b("click", ".menu-toggle");
      assert.equal(ev('document.querySelector("#mobile-nav").hidden'), false);
      b("press", "Escape");
      b("wait", "--fn", 'document.querySelector("#mobile-nav").hidden');
      assert.equal(ev('document.querySelector("#mobile-nav").hidden'), true);
      assert.equal(ev("document.activeElement.className"), "menu-toggle");
      b("click", ".menu-toggle");
      b("click", '#mobile-nav a[href="#research"]');
      b("wait", "--fn", 'document.querySelector("#mobile-nav").hidden');
      assert.equal(ev('document.querySelector("#mobile-nav").hidden'), true);
      assert.equal(ev("location.hash"), "#research");
    },
  );
  check(
    "Copy success reports the exact citation; failure selects text honestly",
    () => {
      ev(
        'Object.defineProperty(navigator.clipboard,"writeText",{value:async text => { document.body.dataset.copied = text; },configurable:true}); true',
      );
      b("click", '[data-copy="bibtex"]');
      assert.equal(
        ev("document.body.dataset.copied"),
        ev('document.querySelector("#bibtex").textContent.trim()'),
      );
      assert.equal(
        ev('document.querySelector("[data-toast]").textContent'),
        "BibTeX copied.",
      );
      ev(
        'Object.defineProperty(navigator.clipboard,"writeText",{value:async () => { throw new Error("denied"); },configurable:true}); true',
      );
      b("click", '[data-copy="quickstart"]');
      assert.match(
        ev('document.querySelector("[data-toast]").textContent'),
        /Automatic copy is unavailable/,
      );
      assert.equal(
        ev("window.getSelection().toString()"),
        ev('document.querySelector("#quickstart").textContent'),
      );
      b("click", '[data-copy="bibtex"]');
      assert.equal(ev('document.querySelector(".citation-source").open'), true);
      assert.equal(
        ev("window.getSelection().toString()"),
        ev('document.querySelector("#bibtex").textContent'),
      );
      b("reload");
    },
  );
  check("All demo panels remain within the page at 320px", () => {
    b("set", "viewport", "320", "844");
    for (const step of ["intent", "change", "evidence", "decision"]) {
      b("click", "#step-" + step);
      assert.equal(
        ev("document.documentElement.scrollWidth > innerWidth"),
        false,
        step,
      );
    }
  });
  b("reload");
  b("wait", "--fn", 'document.fonts.status === "loaded"');
  for (const [label, width, height] of [
    ["desktop", 1440, 1000],
    ["tablet", 768, 1024],
    ["mobile", 390, 844],
  ]) {
    b("set", "viewport", String(width), String(height));
    b("open", address);
    b("wait", "--fn", 'document.fonts.status === "loaded"');
    settled();
    b("screenshot", resolve(out, label + ".png"));
    if (label === "desktop")
      b("screenshot", "--full", resolve(out, "desktop-full.png"));
  }
  check("Citation deep link opens the reusable citation", () => {
    b("open", address + "/#citation");
    assert.equal(ev('document.querySelector(".citation-source").open'), true);
  });
  check(
    "Tab transitions run and reduced-motion preference immediately cancels them",
    () => {
      b("open", address);
      const transition = ev(`(() => {
      document.querySelector('#step-evidence').click();
      return document.querySelector('#panel-evidence').getAnimations({subtree:true}).length;
    })()`);
      assert.ok(transition > 0);
      b("set", "media", "light", "reduced-motion");
      b(
        "wait",
        "--fn",
        'matchMedia("(prefers-reduced-motion: reduce)").matches && document.getAnimations().filter(a=>a.playState==="running").length === 0',
      );
      assert.equal(
        ev(
          'document.getAnimations().filter(a=>a.playState==="running").length',
        ),
        0,
      );
      assert.equal(
        ev("getComputedStyle(document.documentElement).scrollBehavior"),
        "auto",
      );
      b("click", "#step-decision");
      assert.equal(
        ev(
          'document.getAnimations().filter(a=>a.playState==="running").length',
        ),
        0,
      );
      assert.equal(
        ev(
          'getComputedStyle(document.querySelector("#panel-decision")).opacity',
        ),
        "1",
      );
    },
  );
  check("Rapid changes settle to the final tab with a correctly sized selection marker", () => {
    b("set", "media", "light");
    for (const width of [390, 1440]) {
      b("set", "viewport", String(width), "1000");
      ev(`(() => { for (const name of ['change','decision','intent','evidence']) document.querySelector('#step-' + name).click(); return true; })()`);
      settled();
      assert.equal(ev('document.querySelector("#step-evidence").getAttribute("aria-selected")'), "true");
      assert.equal(ev('document.querySelectorAll(".demo-panel:not([hidden])").length'), 1);
      assert.equal(ev('document.querySelector(".demo-tabs").getAttribute("aria-orientation")'), width < 601 ? "horizontal" : "vertical");
      assert.ok(ev(`(() => { const list = document.querySelector('.demo-tabs'), tab = document.querySelector('#step-evidence'); return Math.abs(parseFloat(list.style.getPropertyValue('--indicator-width')) - tab.offsetWidth) < 1; })()`));
      assert.equal(ev('document.querySelector(".demo-content").style.height'), "");
    }
    b("click", "#view-decision");
    settled();
    assert.ok(ev(`(() => { const host = document.querySelector('.showcase-content'); return Math.abs(host.getBoundingClientRect().height - host.querySelector(':scope > .screen-panel:not([hidden])').getBoundingClientRect().height) < 2; })()`));
  });
  check("Disclosures animate both ways, recover from rapid toggles, and retain native final state", () => {
    b("click", ".faq-list details:first-child summary");
    settled();
    assert.equal(ev('document.querySelector(".faq-list details").open'), true);
    b("click", ".faq-list details:first-child summary");
    b("wait", "--fn", '!document.querySelector(".faq-list details").open');
    ev(`(() => { const summary = document.querySelector('.faq-list summary'); summary.click(); summary.click(); summary.click(); return true; })()`);
    settled();
    assert.equal(ev('document.querySelector(".faq-list details").open'), true);
    assert.equal(ev('document.querySelector(".faq-list details").classList.contains("is-resizing")'), false);
  });
  check("The review trace plays once, can replay, stops off screen, and respects reduced motion", () => {
    b("open", address);
    b("wait", "--fn", 'document.querySelector(".hero-trace").classList.contains("is-playing")');
    b("wait", "--fn", 'document.querySelector("[data-trace-count]").textContent === "02 / 04"');
    b("wait", "--fn", '!document.querySelector(".hero-trace").classList.contains("is-playing")');
    b("click", "[data-replay-trace]");
    assert.equal(ev('document.querySelector(".hero-trace").classList.contains("is-playing")'), true);
    ev('document.querySelector("#research").scrollIntoView({behavior:"instant"}); true');
    b("wait", "--fn", '!document.querySelector(".hero-trace").classList.contains("is-playing")');
    b("set", "media", "light", "reduced-motion");
    b("open", address);
    assert.equal(ev('document.querySelector(".hero-trace").classList.contains("is-playing")'), false);
    assert.equal(ev('getComputedStyle(document.querySelector("[data-replay-trace]")).display'), "none");
  });
  check(
    "WCAG A/AA automated scans pass for all steps and the image viewer",
    () => {
      b("set", "viewport", "1440", "1000");
      for (const step of ["intent", "change", "evidence", "decision"]) {
        b("click", "#step-" + step);
        const audit = JSON.parse(
          b("a11y", "--tags", "wcag2a,wcag2aa", "--json"),
        );
        assert.equal(
          audit.data.counts.violations,
          0,
          JSON.stringify(audit.data.violations),
        );
        writeFileSync(
          resolve(out, `a11y-${step}.json`),
          JSON.stringify(audit, null, 2) + "\n",
        );
      }
      b("set", "viewport", "390", "844");
      b("click", "#view-map");
      b("click", "#screen-map .screenshot-link");
      const audit = JSON.parse(b("a11y", "--tags", "wcag2a,wcag2aa", "--json"));
      assert.equal(
        audit.data.counts.violations,
        0,
        JSON.stringify(audit.data.violations),
      );
      writeFileSync(
        resolve(out, "a11y-dialog.json"),
        JSON.stringify(audit, null, 2) + "\n",
      );
      b("press", "Escape");
    },
  );
  const errors = JSON.parse(b("errors", "--json"));
  assert.deepEqual(errors.data.errors, [], "No uncaught browser errors");
  writeFileSync(
    resolve(out, "browser-errors.json"),
    JSON.stringify(errors, null, 2) + "\n",
  );
  writeFileSync(
    resolve(out, "browser-checks.json"),
    JSON.stringify({ address, checks }, null, 2) + "\n",
  );
  console.log(
    `Passed ${checks.length} behavior groups. Captured desktop, tablet, mobile, and full page.`,
  );
} finally {
  b("close");
}
