#!/usr/bin/env python3
"""Publish the next queued blog posts.

Run daily by .github/workflows/release-posts.yml. For each post it:
  1. moves _queue/blog-<slug>.html to the site root and stamps today's date
  2. adds the /blog/<slug> redirect to netlify.toml
  3. adds the URL to sitemap.xml
  4. adds the post to _data/posts.json
  5. rebuilds the blog (scripts/build_blog.py): /blog index, topic hubs,
     Keep Reading links on every post, and /feed.xml

Usage: python3 scripts/release_posts.py [--force] [--count N] [--dry-run]
  --force    release even if a release already ran today
  --count N  release exactly N posts instead of following the rules in queue.json
"""
import argparse, datetime, json, os, re, sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, '_queue', 'queue.json')
REDIRECT_MARK = '# ── AUTO-PUBLISHED POSTS ──'
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

    netlify, sitemap = read('netlify.toml'), read('sitemap.xml')
    data = json.loads(read('_data/posts.json'))
    for mark, doc, text in ((REDIRECT_MARK, 'netlify.toml', netlify), (SITEMAP_MARK, 'sitemap.xml', sitemap)):
        if mark not in text:
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
        if not any(d['slug'] == slug for d in data):
            entry = {'slug': slug, 'url': f'/blog/{slug}', 'file': f'blog-{slug}.html', 'title': p['title'],
                     'category': p['category'], 'excerpt': p['excerpt'], 'read_min': p['read_min'], 'date': iso}
            m = re.search(r'<meta property="og:image" content="https://nsyght\.com(/[^"]+)"', page)
            if m:
                entry['image'] = m.group(1)
            entry['auto'] = True
            data.append(entry)
        print('  published /blog/' + slug)

    write('netlify.toml', netlify)
    write('sitemap.xml', sitemap)
    write('_data/posts.json', json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    q['posts'] = rest
    q['last_release_date'] = iso
    q.setdefault('published', []).extend({'slug': p['slug'], 'date': iso} for p in batch)
    write('_queue/queue.json', json.dumps(q, indent=2, ensure_ascii=False) + '\n')
    print(f'{len(rest)} posts left in the queue')

    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
    import fix_footer, build_blog
    fix_footer.main([os.path.join(ROOT, f'blog-{p["slug"]}.html') for p in batch])
    build_blog.main()


if __name__ == '__main__':
    main()
