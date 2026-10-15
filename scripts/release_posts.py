#!/usr/bin/env python3
"""Publish the next queued blog posts.

Run daily by .github/workflows/release-posts.yml. For each post it:
  1. moves _queue/blog-<slug>.html to the site root and stamps today's date
  2. adds the /blog/<slug> redirect to netlify.toml
  3. adds the URL to sitemap.xml
  4. adds a card to the top of the article list in blog.html

Usage: python3 scripts/release_posts.py [--force] [--count N] [--dry-run]
  --force    release even if a release already ran today
  --count N  release exactly N posts instead of following the rules in queue.json
"""
import argparse, datetime, html, json, os, sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, '_queue', 'queue.json')
REDIRECT_MARK = '# ── AUTO-PUBLISHED POSTS ──'
CARD_MARK = '<!-- AUTO-POSTS:START -->'
SITEMAP_MARK = '<!-- AUTO-POSTS -->'


def read(p):
    with open(os.path.join(ROOT, p), encoding='utf-8') as f:
        return f.read()


def write(p, s):
    with open(os.path.join(ROOT, p), 'w', encoding='utf-8') as f:
        f.write(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--count', type=int)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    q = json.loads(read('_queue/queue.json'))
    today = datetime.datetime.now(ZoneInfo('America/Chicago')).date()
    iso = today.isoformat()
    human = today.strftime('%B ') + str(today.day) + today.strftime(', %Y')

    if q.get('last_release_date') == iso and not a.force:
        print(f'Already released posts on {iso}. Use --force to release more.')
        return
    posts = q['posts']
    if not posts:
        print('Queue is empty. Nothing to publish.')
        return
    r = q['rules']
    n = a.count if a.count is not None else (
        r['backlog_per_day'] if len(posts) > r['switch_to_steady_when_queue_at_or_below'] else r['steady_per_day'])
    batch, rest = posts[:n], posts[n:]
    print(f'{len(posts)} queued, releasing {len(batch)} on {iso}')
    if a.dry_run:
        for p in batch:
            print('  would publish /blog/' + p['slug'])
        return

    netlify, sitemap, blog = read('netlify.toml'), read('sitemap.xml'), read('blog.html')
    for mark, doc in ((REDIRECT_MARK, 'netlify.toml'), (SITEMAP_MARK, 'sitemap.xml'), (CARD_MARK, 'blog.html')):
        if mark not in {'netlify.toml': netlify, 'sitemap.xml': sitemap, 'blog.html': blog}[doc]:
            sys.exit(f'Marker {mark!r} missing from {doc}')

    for p in batch:
        slug = p['slug']
        page = read(p['file']).replace('%%DATE_ISO%%', iso).replace('%%DATE_HUMAN%%', human)
        write(f'blog-{slug}.html', page)
        os.remove(os.path.join(ROOT, p['file']))

        if f'from = "/blog/{slug}"' not in netlify:
            netlify = netlify.replace(REDIRECT_MARK, REDIRECT_MARK + f'\n[[redirects]]\n  from = "/blog/{slug}"\n  to = "/blog-{slug}.html"\n  status = 200\n', 1)
        loc = f'https://nsyght.com/blog/{slug}'
        if loc not in sitemap:
            sitemap = sitemap.replace(SITEMAP_MARK, SITEMAP_MARK + f'\n  <url><loc>{loc}</loc><lastmod>{iso}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>', 1)
        e = html.escape
        card = f'''
    <a href="/blog/{slug}" class="article-card">
      <div class="article-card-category">{e(p['category'])}</div>
      <div class="article-card-title">{e(p['title'])}</div>
      <p class="article-card-excerpt">{e(p['excerpt'])}</p>
      <div class="article-card-meta"><span>By Don Phelps</span><span>{human}</span><span>{p['read_min']} min read</span></div>
      <span class="article-card-cta">Read the article &rarr;</span>
    </a>
'''
        if f'href="/blog/{slug}"' not in blog:
            blog = blog.replace(CARD_MARK, CARD_MARK + card, 1)
        print('  published /blog/' + slug)

    write('netlify.toml', netlify)
    write('sitemap.xml', sitemap)
    write('blog.html', blog)
    q['posts'] = rest
    q['last_release_date'] = iso
    q.setdefault('published', []).extend({'slug': p['slug'], 'date': iso} for p in batch)
    write('_queue/queue.json', json.dumps(q, indent=2, ensure_ascii=False) + '\n')
    print(f'{len(rest)} posts left in the queue')


if __name__ == '__main__':
    main()
