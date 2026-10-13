# Website maintenance

The official website is https://tianfuwang.tech/AgenticConsensus/.
This directory is the only maintained website source. It preserves the original
project website's layout, typography, walkthrough, motion and workspace captures,
migrated from `GeminiLight/agentic-consensus-site` at commit
`be10d658e9347b050179367156ac3c3c18276838` on 2026-10-14.

Edit `index.html`, `styles.css` and `script.js` here. The original English page
remains readable without JavaScript. Fonts, images and the public preprint PDF
are bundled in `assets/`; retain the font license notices. There are no application
credentials, analytics or external runtime dependencies in the site source.

Preview from the repository root:

```sh
python3 -m http.server 8080 --directory website
```

Visit http://127.0.0.1:8080. The walkthrough is synthetic and illustrative;
it is not a live application or a measured result. Paper links refer to the
existing arXiv preprint and clearly distinguish the forthcoming update.

Run the original site's verification tools from the repository root:

```sh
python3 scripts/website/verify-content.py
(cd website && SITE_URL=https://tianfuwang.tech/AgenticConsensus/ OLD_SITE_URL=https://tianfuwang.tech/agentic-consensus/ python3 ../scripts/website/verify-site-seo.py)
node --check website/script.js
# With a local preview and agent-browser available:
node scripts/website/verify-browser.cjs http://127.0.0.1:8080
```

The browser checks cover desktop and mobile layouts, the walkthrough and
workspace tabs, keyboard navigation, image viewer, copy controls, reduced motion,
accessibility and page errors. Reports are saved to ignored `var/website-qa/`.

Pushing changes in `website/` to `main` runs `.github/workflows/website.yml`
and publishes this directory to GitHub Pages. Website publishing does not
deploy the Python application. Keep project links and the canonical URL in
`index.html`, `sitemap.xml` and `llms.txt` consistent if the address changes.

The previous `/agentic-consensus/` and `/agentic-consensus-site/` deployments are
retired to redirects to this canonical website, preserving query strings and
section anchors. Do not publish a second full website at either old address.
