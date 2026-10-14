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

## Search and AI retrieval

Use this exact project description in the README, visible website text,
structured data and text summary:

> AgenticConsensus is a shared, versioned project state for human–AI coding collaboration.

The English page serves researchers reading the paper and developers reviewing
agent-written changes. Useful query intents include the project name, paper
title, human–AI coding collaboration, versioned project state, evidence across
code revisions, and human authority in agentic code review. The published page
answers these through the research summary, walkthrough, implementation scope
and FAQ; do not create duplicate pages for spelling or query variants.

Keep the self-canonical URL, title, description and social metadata aligned.
The JSON-LD connects the project, arXiv paper, public source code and author
profile. Only describe facts present in the page. The paper's title, author
order, first submission date and DOI come from
[arXiv](https://arxiv.org/abs/2604.17883); keep `CITATION.cff`, citation meta tags
and both BibTeX copies consistent. This overview is not the paper's full text.

The authority for crawler rules is **https://tianfuwang.tech/robots.txt** in
the personal website repository. The `website/robots.txt` file documents this
project's sitemap but cannot override domain-root rules. The root file must
advertise **https://tianfuwang.tech/AgenticConsensus/sitemap.xml** and allow
search crawlers to fetch the page and its resources. Keep search and training
bot policies separate when changing access rules.

The sitemap lists only the canonical page. Update `lastmod` when visible
content changes, rather than on every build. `llms.txt` is a readable resource
map for agents and documentation tools; neither it nor schema guarantees
ranking, AI mentions or citations. Real hyperlinks connect the README,
project website and the author's publication entry in both directions.

After publishing, fetch the domain-root robots file, project sitemap and page,
and repeat the content checks above. Static fetches confirm the delivered HTML
and crawl directives; browser checks cover layout and interactions. Neither
confirms that a search engine has indexed the page.

For measurement, inspect the canonical URL and submit the project sitemap in
Google Search Console and Bing Webmaster Tools using an authorized property.
Track branded and paper-title queries, impressions, clicks and referring
sources. Check AI search results with a fixed panel of project-definition,
paper-discovery and implementation-scope questions, paraphrases and repeated
runs before reporting changes. Search Console or engine-panel access is needed
to establish a baseline; do not infer a visibility score from a single search.

Potential external references include the existing arXiv and alphaXiv entries,
relevant research surveys and editorially maintained developer resource lists.
Only seek inclusion where the work fits and disclose authorship. Any outreach
or third-party edits require their own authorization.
