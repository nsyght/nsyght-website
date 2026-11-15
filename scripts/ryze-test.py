#!/usr/bin/env python3
"""Exercise publishing against an isolated temporary copy, never the live site."""
import hashlib, json, os, pathlib, shutil, subprocess, tempfile
root = pathlib.Path(__file__).resolve().parents[1]
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
with tempfile.TemporaryDirectory(prefix='ryze-check-') as tmp:
    site = pathlib.Path(tmp) / 'site'
    shutil.copytree(root, site, ignore=shutil.ignore_patterns('.git', '__pycache__'))
    data = site / 'blog/data'
    data.mkdir(parents=True, exist_ok=True)
    article = dict(slug='ryze-integration-check', title='Publishing integration check', body_markdown='## Check\n\nVerified.', body_html='<h2 id="check">Check</h2><p>Verified.</p>', blocks=[], meta_title='Integration check | NSYGHT', meta_description='Integration check.', excerpt='Integration check.', primary_keyword=None, image=None, published_at='2026-11-15T00:00:00.000Z', updated_at='2026-11-15T00:00:00.000Z', status='published')
    (data / 'integration-check.json').write_text(json.dumps(article))
    draft = dict(article, slug='ryze-draft-check', status='drafted')
    (data / 'draft-check.json').write_text(json.dumps(draft))
    def run():
        subprocess.run(['node', 'scripts/ryze-convert.mjs'], cwd=site, env=env, check=True)
    run()
    page = (site / 'blog/ryze-integration-check/index.html').read_text()
    assert article['body_html'] in page and '[object Object]' not in page
    assert '<h1>Publishing integration check</h1>' in page
    schemas = [json.loads(s) for s in __import__('re').findall(r'<script type="application/ld\+json">(.*?)</script>', page, __import__('re').S)]
    breadcrumbs = [s for s in schemas if s.get('@type') == 'BreadcrumbList']
    assert len(breadcrumbs) == 1
    assert breadcrumbs[0]['itemListElement'] == [
        {'@type':'ListItem','position':1,'name':'Home','item':'https://nsyght.com/'},
        {'@type':'ListItem','position':2,'name':'Resources','item':'https://nsyght.com/blog'},
        {'@type':'ListItem','position':3,'name':article['title'],'item':'https://nsyght.com/blog/'+article['slug']}
    ]
    assert '<span aria-current="page">Publishing integration check</span>' in page
    article_schemas = [s for s in schemas if s.get('@type') == 'Article']
    assert len(article_schemas) == 1 and article_schemas[0]['author']['name'] == 'Don Phelps'
    assert not (site / 'blog/ryze-draft-check/index.html').exists()
    posts = json.loads((site / '_data/posts.json').read_text())
    entry = next(p for p in posts if p['slug'] == article['slug'])
    assert entry['file'] == 'blog/ryze-integration-check/index.html'
    assert article['title'] in (site / 'blog.html').read_text()
    assert article['slug'] in (site / 'sitemap.xml').read_text()
    assert article['slug'] in (site / 'feed.xml').read_text()
    def snapshot():
        return {str(p.relative_to(site)): hashlib.sha256(p.read_bytes()).hexdigest() for p in site.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
    before = snapshot()
    run()
    assert before == snapshot(), 'Second run must not change files'
    original = (site / 'blog-local-seo-2026.html').read_bytes()
    collision = dict(article, slug='local-seo-2026')
    (data / 'collision-check.json').write_text(json.dumps(collision))
    result = subprocess.run(['node', 'scripts/ryze-convert.mjs'], cwd=site, env=env, capture_output=True)
    assert result.returncode != 0, 'Existing articles must be protected'
    assert (site / 'blog-local-seo-2026.html').read_bytes() == original
print('PASS: article, index, feed, sitemap, draft exclusion, repeatability, collision protection')
