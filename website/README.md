# Website maintenance

The official website is https://tianfuwang.tech/AgenticConsensus/.
This directory is the only maintained website source. The previous copy on
the personal website is retired and is not part of this publishing workflow.

Edit `index.html`, `styles.css` and `script.js` here. English text is readable
without JavaScript; the language switch adds the Chinese version. There are no
external fonts, analytics, application credentials or runtime dependencies.

Preview from the repository root:

```sh
python3 -m http.server 8080 --directory website
```

Visit http://127.0.0.1:8080. Check English and Chinese, keyboard navigation,
desktop and 390px mobile layouts. The example on the page is synthetic and
illustrative; it is not a live application or a measured result.

Pushing changes in `website/` to `main` runs `.github/workflows/website.yml`
and publishes this directory to GitHub Pages. Website publishing does not
deploy the Python application. Keep project links and the canonical URL in
`index.html`, `sitemap.xml` and `llms.txt` consistent if the address changes.
