"""Check the public contract: links, assets, metadata, and statement consistency."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
import json

ROOT = Path(__file__).resolve().parents[2] / "website"
class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.refs = []
        self.metas = []
        self.json_blocks = []
        self.in_json = False
        self.h1_count = 0
    def handle_starttag(self, tag, items):
        a = dict(items)
        if a.get('id'):
            assert a['id'] not in self.ids, f"Duplicate ID: {a['id']}"
            self.ids.add(a['id'])
        if tag == 'meta': self.metas.append(a)
        if tag == 'h1': self.h1_count += 1
        for field in ('href', 'src'):
            if a.get(field): self.refs.append(a[field])
        for field in ('aria-controls', 'aria-labelledby'):
            self.refs.extend('#' + value for value in a.get(field, '').split())
        self.in_json = tag == 'script' and a.get('type') == 'application/ld+json'
    def handle_endtag(self, tag):
        if tag == 'script': self.in_json = False
    def handle_data(self, data):
        if self.in_json: self.json_blocks.append(json.loads(data))

source = (ROOT / 'index.html').read_text()
page = Page(); page.feed(source)
assert page.h1_count == 1
for value in page.refs:
    url = urlsplit(value)
    if url.scheme or url.netloc: continue
    if url.path:
        assert (ROOT / unquote(url.path)).is_file(), f'Missing local resource: {value}'
    elif url.fragment:
        assert url.fragment in page.ids, f'Missing anchor: {value}'
assert len(page.json_blocks) == 1
entities = page.json_blocks[0]['@graph']
article = next(x for x in entities if x['@type'] == 'ScholarlyArticle')
meta = {x.get('name', x.get('property')): x.get('content') for x in page.metas}
assert article['headline'] == meta['citation_title']
assert len(article['author']) == 8
assert sum(x.get('name') == 'citation_author' for x in page.metas) == 8
assert 'citation_conference_title' not in meta
assert meta['citation_arxiv_id'] == '2604.17883'
assert meta['citation_pdf_url'] == 'https://arxiv.org/pdf/2604.17883'
assert 'https://www.alphaxiv.org/abs/2604.17883' in source
for name in ('index.html', 'llms.txt'):
    text = (ROOT / name).read_text()
    for obsolete in ('KDD 2026', '10 participants', '10<span>participants', 'Position: Scaling'):
        assert obsolete not in text, f'Outdated public claim in {name}: {obsolete}'
    assert '2604.17883' in text
    assert 'coming soon' in text or 'preparing an update' in text
assert 'agentic-consensus-paper"' not in source, 'Do not offer the private manuscript source as a public CTA'
assert (ROOT / 'assets/agentic-consensus-paper.pdf').read_bytes().startswith(b'%PDF-')
manifest = json.loads((ROOT / 'site.webmanifest').read_text())
for icon in manifest['icons']:
    assert (ROOT / icon['src']).is_file()
for name in ('DM-Sans-OFL.txt','Instrument-Serif-OFL.txt'):
    assert 'SIL OPEN FONT LICENSE' in (ROOT / 'assets/fonts' / name).read_text()
print(f'PASS: {len(page.refs)} resource/anchor references; one H1; paper metadata; author count; current claims; PDF; font licenses.')
