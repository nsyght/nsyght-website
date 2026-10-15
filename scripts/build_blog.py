#!/usr/bin/env python3
"""Rebuild every generated part of the NSYGHT blog from _data/posts.json.

  blog.html                     Start Here row + the 12 newest posts + topic links
  blog-category-<slug>.html     one hub per topic, served at /blog/category/<slug>
  feed.xml                      RSS 2.0 feed of the newest posts, served at /feed.xml
  every published post          "Keep Reading" block with 3 related posts
  sitemap.xml                   topic hub URLs (between the CATEGORY-HUBS markers)

Only the regions between <!-- X:START --> / <!-- X:END --> markers are rewritten,
so post bodies are never touched. Safe to run as often as you like.

Usage: python3 scripts/build_blog.py
"""
import datetime, html, json, os, re, sys
from email.utils import format_datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://nsyght.com'
LATEST_COUNT = 12
FEED_COUNT = 20
CT = ZoneInfo('America/Chicago')
e = html.escape

# Topic hubs, in the order they appear in the category bar.
CATEGORIES = [
    ('Local SEO', 'local-seo',
     'Local SEO Articles',
     'How local service businesses actually win the map pack and organic results: site structure, location pages, links, audits, and the work that compounds.'),
    ('Google Business Profile', 'google-business-profile',
     'Google Business Profile Articles',
     'Categories, reviews, photos, posts, suspensions, and everything else that decides whether your profile gets the call or your competitor does.'),
    ('AI Search', 'ai-search',
     'AI Search Articles',
     'How ChatGPT, Gemini, Perplexity, and Google AI Overviews choose who to cite, and what local businesses can do to be the answer.'),
    ('Google Ads', 'google-ads',
     'Google Ads Articles',
     'Local Services Ads, search campaigns, and how paid spend should work alongside SEO instead of replacing it.'),
    ('Industry Tips', 'industry-tips',
     'Industry SEO Articles',
     'Local search playbooks for specific industries: roofing, dental, law firms, home services, and more.'),
    ('Agency News', 'agency-news',
     'NSYGHT News',
     'What is new at NSYGHT: launches, releases, and the thinking behind them.'),
]
CAT_BY_NAME = {c[0]: c for c in CATEGORIES}

EXTRA_CSS = '''  <style>
    .blog-section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-bottom:1.25rem}
    .blog-section-head .featured-label{margin-bottom:.35rem}
    .blog-section-sub{font-size:.9rem;color:var(--muted);margin:0}
    .start-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:4rem}
    .start-card{background:linear-gradient(145deg,#EEF5FF,#F3EEFF);border:1.5px solid rgba(43,127,204,.2);border-radius:var(--rl);padding:1.5rem;text-decoration:none;display:flex;flex-direction:column;transition:box-shadow .2s,transform .15s}
    .start-card:hover{box-shadow:0 8px 32px rgba(43,127,204,.12);transform:translateY(-2px)}
    .start-step{font-family:var(--font-d);font-size:.72rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--purple);margin-bottom:.6rem}
    .start-title{font-family:var(--font-d);font-size:1rem;font-weight:700;color:var(--text);line-height:1.35;margin-bottom:.6rem}
    .start-meta{margin-top:auto;font-size:.78rem;color:var(--muted)}
    .article-card-img{display:block;width:100%;height:auto;aspect-ratio:16/9;object-fit:cover;border-radius:var(--r);margin-bottom:1.25rem;background:var(--off)}
    .topic-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:4rem}
    .topic-card{background:var(--white);border:1.5px solid var(--border);border-radius:var(--rl);padding:1.5rem;text-decoration:none;transition:border-color .2s,box-shadow .2s}
    .topic-card:hover{border-color:rgba(43,127,204,.3);box-shadow:0 8px 32px rgba(43,127,204,.1)}
    .topic-name{font-family:var(--font-d);font-size:1rem;font-weight:700;color:var(--text);margin-bottom:.35rem}
    .topic-desc{font-size:.85rem;color:var(--mid);line-height:1.6;margin-bottom:.75rem}
    .topic-count{font-size:.78rem;font-weight:600;color:var(--blue)}
    .cat-btn .cat-count{opacity:.6;margin-left:.3rem}
    @media(max-width:1024px){.start-grid{grid-template-columns:1fr 1fr}.topic-grid{grid-template-columns:1fr 1fr}}
    @media(max-width:640px){.start-grid,.topic-grid{grid-template-columns:1fr}}
  </style>'''

KEEP_CSS = ('<style>.keep-reading{margin-top:3.5rem;padding-top:2rem;border-top:1px solid var(--border)}'
            '.keep-reading-label{font-size:.68rem;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:var(--blue);margin-bottom:1rem}'
            '.keep-reading-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}'
            '.article-content .keep-reading a.kr-card,.keep-reading a.kr-card{display:flex;flex-direction:column;background:var(--off);border:1px solid var(--border);border-radius:var(--r);padding:1.25rem;text-decoration:none;transition:border-color .2s,box-shadow .2s}'
            '.keep-reading a.kr-card:hover{border-color:rgba(43,127,204,.35);box-shadow:0 6px 24px rgba(43,127,204,.1)}'
            '.kr-cat{font-size:.66rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--blue);margin-bottom:.5rem}'
            '.kr-title{font-family:var(--font-d);font-size:.95rem;font-weight:700;color:var(--text);line-height:1.35;margin-bottom:.5rem}'
            '.kr-meta{margin-top:auto;font-size:.75rem;color:var(--muted)}'
            '.article-content .keep-reading a.kr-more,.keep-reading a.kr-more{display:inline-block;margin-top:1rem;font-size:.85rem;font-weight:600;color:var(--blue);border:0}'
            '@media(max-width:860px){.keep-reading-grid{grid-template-columns:1fr}}</style>')


def read(p):
    with open(os.path.join(ROOT, p), encoding='utf-8') as f:
        return f.read()


def write(p, s):
    path = os.path.join(ROOT, p)
    old = None
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            old = f.read()
    if old != s:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(s)
        print('  wrote', p)


def replace_region(doc, name, body, where):
    start, end = f'<!-- {name}:START -->', f'<!-- {name}:END -->'
    i, j = doc.find(start), doc.find(end)
    if i < 0 or j < 0:
        sys.exit(f'{name} markers missing from {where}')
    return doc[:i + len(start)] + '\n' + body + '\n' + doc[j:]


def cat_slug(name):
    if name in CAT_BY_NAME:
        return CAT_BY_NAME[name][1]
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def human(iso):
    d = datetime.date.fromisoformat(iso)
    return d.strftime('%B ') + str(d.day) + d.strftime(', %Y')


def date_text(p):
    return human(p['date']) if p.get('date') else p.get('date_label', '')


def heal_posts(posts):
    """Add any published blog-*.html page that is missing from posts.json,
    reading its metadata from the page itself (og:title, description,
    articleSection, datePublished, og:image, read time)."""
    known = {p['file'] for p in posts}
    added = []
    for f in sorted(os.listdir(ROOT)):
        if not (f.startswith('blog-') and f.endswith('.html')) or f.startswith('blog-category-') or f in known:
            continue
        s = read(f)
        def grab(pat):
            m = re.search(pat, s)
            return html.unescape(m.group(1)) if m else None
        title = grab(r'<meta property="og:title" content="([^"]+)"')
        cat = grab(r'"articleSection":\s*"([^"]+)"')
        date = grab(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})"')
        if not (title and cat and date):
            print(f'  WARNING: {f} is not in posts.json and is missing metadata; skipped')
            continue
        slug = f[len('blog-'):-len('.html')]
        entry = {'slug': slug, 'url': f'/blog/{slug}', 'file': f,
                 'title': re.sub(r'\s+-\s+NSYGHT$', '', title), 'category': cat,
                 'excerpt': grab(r'<meta name="description" content="([^"]*)"') or '',
                 'read_min': int(grab(r'(\d+) min read') or 0), 'date': date}
        img = grab(r'<meta property="og:image" content="https://nsyght\.com(/[^"]+)"')
        if img:
            entry['image'] = img
        entry['auto'] = True
        posts.append(entry)
        added.append(slug)
    if added:
        write('_data/posts.json', json.dumps(posts, indent=2, ensure_ascii=False) + '\n')
        print('  added to posts.json:', ', '.join(added))
    return posts


def load_posts():
    posts = heal_posts(json.loads(read('_data/posts.json')))
    posts = [p for p in posts if os.path.exists(os.path.join(ROOT, p['file']))]
    # Newest first. Posts without an exact date (the April 2026 launch set) sort
    # after dated ones, keeping their order from posts.json.
    for i, p in enumerate(posts):
        p['_i'] = i
    posts.sort(key=lambda p: (p.get('date') or '0000', -p['_i']), reverse=True)
    return posts


def card(p):
    img = ''
    if p.get('image'):
        img = f'\n      <img class="article-card-img" src="{e(p["image"])}" alt="" width="1200" height="675" loading="lazy" decoding="async"/>'
    badge = f'\n      <div class="article-card-badge">{e(p["badge"])}</div>' if p.get('badge') else ''
    return f'''    <a href="{e(p['url'])}" class="article-card">{img}{badge}
      <div class="article-card-category">{e(p['category'])}</div>
      <div class="article-card-title">{e(p['title'])}</div>
      <p class="article-card-excerpt">{e(p['excerpt'])}</p>
      <div class="article-card-meta"><span>By Don Phelps</span><span>{e(date_text(p))}</span><span>{p['read_min']} min read</span></div>
      <span class="article-card-cta">Read the article &rarr;</span>
    </a>'''


def cat_bar(cats, active=None):
    out = ['  <div class="cat-bar">',
           f'    <a href="/blog" class="cat-btn{" active" if active is None else ""}">All</a>']
    for name, slug, _, _ in CATEGORIES:
        if name in cats:
            cls = ' active' if active == name else ''
            out.append(f'    <a href="/blog/category/{slug}" class="cat-btn{cls}">{e(name)}<span class="cat-count">{len(cats[name])}</span></a>')
    out.append('  </div>')
    return '\n'.join(out)


def topic_grid(cats, skip=None):
    out = ['  <div class="topic-grid">']
    for name, slug, _, desc in CATEGORIES:
        if name in cats and name != skip:
            n = len(cats[name])
            out.append(f'''    <a href="/blog/category/{slug}" class="topic-card">
      <div class="topic-name">{e(name)}</div>
      <p class="topic-desc">{e(desc)}</p>
      <span class="topic-count">{n} article{"s" if n != 1 else ""} &rarr;</span>
    </a>''')
    out.append('  </div>')
    return '\n'.join(out)


def meta_block(title, desc, url, ld):
    return f'''  <title>{e(title)}</title>
  <meta name="description" content="{e(desc)}"/>
  <link rel="canonical" href="{url}"/>
  <link rel="alternate" type="application/rss+xml" title="NSYGHT Local SEO Resources" href="{SITE}/feed.xml"/>
  <meta property="og:title" content="{e(title)}"/>
  <meta property="og:description" content="{e(desc)}"/>
  <meta property="og:type" content="website"/>
  <meta property="og:url" content="{url}"/>
''' + '\n'.join(f'  <script type="application/ld+json">\n{json.dumps(x, indent=2, ensure_ascii=False)}\n  </script>' for x in ld) + '\n' + EXTRA_CSS


def hero_block(crumbs, badge, h1, h1_span, intro):
    c = []
    for label, href in crumbs:
        if href:
            c.append(f'      <a href="{href}" style="color:rgba(255,255,255,.55);text-decoration:none">{e(label)}</a>')
            c.append('      <span style="color:rgba(255,255,255,.35)">&rsaquo;</span>')
        else:
            c.append(f'      <span>{e(label)}</span>')
    c = '\n'.join(c)
    return f'''<section class="blog-hero">
  <div class="blog-hero-inner">
    <nav class="breadcrumb" aria-label="Breadcrumb" style="display:flex;align-items:center;gap:.5rem;font-size:.78rem;color:rgba(255,255,255,.55);margin-bottom:1.5rem">
{c}
    </nav>
    <div class="page-badge" style="margin-bottom:1.25rem">{e(badge)}</div>
    <h1>{e(h1)}<br/><span>{e(h1_span)}</span></h1>
    <p>{e(intro)}</p>
  </div>
</section>'''


def item_list(posts):
    return {'@type': 'ItemList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'url': SITE + p['url'], 'name': p['title']}
        for i, p in enumerate(posts)]}


PUBLISHER = {'@type': 'Organization', 'name': 'NSYGHT', 'url': SITE}
AUTHOR = {'@type': 'Person', 'name': 'Don Phelps', 'url': SITE + '/about'}


def build_index(shell, posts, cats):
    start = sorted((p for p in posts if p.get('start_here')), key=lambda p: p['start_here'])
    latest = posts[:LATEST_COUNT]
    steps = []
    for n, p in enumerate(start, 1):
        steps.append(f'''    <a href="{e(p['url'])}" class="start-card">
      <div class="start-step">Step {n}</div>
      <div class="start-title">{e(p['title'])}</div>
      <div class="start-meta">{e(p['category'])} &middot; {p['read_min']} min read</div>
    </a>''')
    body = '\n'.join([
        cat_bar(cats),
        '',
        '  <div class="blog-section-head"><div><div class="featured-label">Start Here</div>'
        '<p class="blog-section-sub">New to local SEO or AI search? Read these four first. Everything else builds on them.</p></div></div>',
        '  <div class="start-grid">', *steps, '  </div>',
        '',
        f'  <div class="blog-section-head"><div><div class="featured-label">Latest Articles</div>'
        f'<p class="blog-section-sub">The {len(latest)} newest posts. Older articles live in the topic hubs below.</p></div></div>',
        '  <div class="featured-grid">', *[card(p) for p in latest], '  </div>',
        '',
        '  <div class="blog-section-head"><div><div class="featured-label">Browse by Topic</div>'
        f'<p class="blog-section-sub">All {len(posts)} articles, organized by what you are trying to fix.</p></div></div>',
        topic_grid(cats),
    ])
    title = 'Local SEO Resources, Insights & Podcast - NSYGHT'
    desc = ('Local SEO articles, guides, and the Local SEO Unlocked podcast from Don Phelps. '
            'Practical search strategy for local service businesses. No fluff, no generic advice.')
    ld = [
        {'@context': 'https://schema.org', '@type': 'Blog', 'name': 'NSYGHT Local SEO Resources',
         'description': 'Local SEO articles, guides, and insights from Don Phelps covering search engine optimization, Google Business Profile management, AI search visibility, and digital marketing strategy for local service businesses.',
         'url': SITE + '/blog', 'publisher': PUBLISHER, 'author': AUTHOR,
         'blogPost': [{'@type': 'BlogPosting', 'headline': p['title'], 'url': SITE + p['url'],
                       **({'datePublished': p['date']} if p.get('date') else {})} for p in latest]},
        {'@context': 'https://schema.org', '@type': 'PodcastSeries', 'name': 'Local SEO Unlocked',
         'description': 'A podcast by Don Phelps covering local SEO strategy, AI search visibility, Google Business Profile management, and digital marketing for local service businesses.',
         'url': 'https://localseounlocked.buzzsprout.com/', 'author': {'@type': 'Person', 'name': 'Don Phelps'},
         'sameAs': ['https://localseounlocked.buzzsprout.com/',
                    'https://podcasts.apple.com/us/podcast/local-seo-unlocked/id1892876171']},
        {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE},
            {'@type': 'ListItem', 'position': 2, 'name': 'Resources', 'item': SITE + '/blog'}]},
    ]
    doc = replace_region(shell, 'META', meta_block(title, desc, SITE + '/blog', ld), 'blog.html')
    doc = replace_region(doc, 'HERO', hero_block(
        [('Home', '/'), ('Resources', None)], 'From Don Phelps',
        'Local SEO Insights.', 'No Fluff. No Generic Advice.',
        'Articles, guides, and the Local SEO Unlocked podcast, all focused on helping local service businesses '
        'get found by the customers searching for them right now.'), 'blog.html')
    doc = replace_region(doc, 'INDEX', body, 'blog.html')
    return doc


def build_hub(shell, name, posts, cats):
    _, slug, heading, desc = CAT_BY_NAME.get(name, (name, cat_slug(name), name + ' Articles', ''))
    url = f'{SITE}/blog/category/{slug}'
    body = '\n'.join([
        cat_bar(cats, active=name),
        '',
        f'  <div class="blog-section-head"><div><div class="featured-label">{e(name)}</div>'
        f'<p class="blog-section-sub">{len(posts)} article{"s" if len(posts) != 1 else ""}, newest first.</p></div></div>',
        '  <div class="featured-grid">', *[card(p) for p in posts], '  </div>',
        '',
        '  <div class="blog-section-head"><div><div class="featured-label">Other Topics</div></div></div>',
        topic_grid(cats, skip=name),
    ])
    title = f'{heading} - NSYGHT'
    ld = [
        {'@context': 'https://schema.org', '@type': 'CollectionPage', 'name': heading, 'description': desc,
         'url': url, 'isPartOf': {'@type': 'Blog', 'name': 'NSYGHT Local SEO Resources', 'url': SITE + '/blog'},
         'publisher': PUBLISHER, 'mainEntity': item_list(posts)},
        {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE},
            {'@type': 'ListItem', 'position': 2, 'name': 'Resources', 'item': SITE + '/blog'},
            {'@type': 'ListItem', 'position': 3, 'name': name, 'item': url}]},
    ]
    doc = replace_region(shell, 'META', meta_block(title, desc, url, ld), 'blog.html')
    doc = replace_region(doc, 'HERO', hero_block(
        [('Home', '/'), ('Resources', '/blog'), (name, None)], 'Topic Hub', heading + '.',
        'From Don Phelps.', desc), 'blog.html')
    doc = replace_region(doc, 'PODCAST', '', 'blog.html')
    doc = replace_region(doc, 'INDEX', body, 'blog.html')
    return doc


def related(p, posts):
    others = [q for q in posts if q['slug'] != p['slug']]
    picks = [q for q in others if q['category'] == p['category']]
    picks += sorted((q for q in others if q.get('start_here') and q not in picks), key=lambda q: q['start_here'])
    picks += [q for q in others if q not in picks]
    return picks[:3]


def keep_reading(p, posts, cats):
    cards = ''.join(
        f'<a href="{e(q["url"])}" class="kr-card"><span class="kr-cat">{e(q["category"])}</span>'
        f'<span class="kr-title">{e(q["title"])}</span><span class="kr-meta">{q["read_min"]} min read</span></a>'
        for q in related(p, posts))
    more = ''
    if len(cats.get(p['category'], [])) > 1:
        more = f'<a href="/blog/category/{cat_slug(p["category"])}" class="kr-more">More {e(p["category"])} articles &rarr;</a>'
    else:
        more = '<a href="/blog" class="kr-more">All articles &rarr;</a>'
    return (f'<aside class="keep-reading" aria-label="Keep reading">{KEEP_CSS}'
            f'<div class="keep-reading-label">Keep Reading</div><div class="keep-reading-grid">{cards}</div>{more}</aside>')


def inject_keep_reading(p, posts, cats):
    doc = read(p['file'])
    block = '<!-- KEEP-READING:START -->\n' + keep_reading(p, posts, cats) + '\n<!-- KEEP-READING:END -->'
    if '<!-- KEEP-READING:START -->' in doc:
        doc = re.sub(r'<!-- KEEP-READING:START -->.*?<!-- KEEP-READING:END -->', lambda m: block, doc, flags=re.S)
    else:
        anchor = '</article>' if '</article>' in doc else '</main>'
        i = doc.rfind(anchor)
        if i < 0:
            print(f'  WARNING: no </article> or </main> in {p["file"]}, skipped Keep Reading')
            return
        doc = doc[:i] + block + '\n  ' + doc[i:]
    write(p['file'], doc)


def build_feed(posts):
    items = []
    dated = [p for p in posts if p.get('date')]
    for p in posts[:FEED_COUNT]:
        pub = ''
        if p.get('date'):
            d = datetime.datetime.combine(datetime.date.fromisoformat(p['date']), datetime.time(8, 0), CT)
            pub = f'\n      <pubDate>{format_datetime(d)}</pubDate>'
        link = SITE + p['url']
        items.append(f'''    <item>
      <title>{e(p['title'])}</title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>{pub}
      <dc:creator>Don Phelps</dc:creator>
      <category>{e(p['category'])}</category>
      <description>{e(p['excerpt'])}</description>
    </item>''')
    last = ''
    if dated:
        d = datetime.datetime.combine(datetime.date.fromisoformat(max(p['date'] for p in dated)), datetime.time(8, 0), CT)
        last = f'\n    <lastBuildDate>{format_datetime(d)}</lastBuildDate>'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>NSYGHT Local SEO Resources</title>
    <link>{SITE}/blog</link>
    <atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>Local SEO, Google Business Profile, and AI search articles from Don Phelps at NSYGHT.</description>
    <language>en-us</language>{last}
{chr(10).join(items)}
  </channel>
</rss>
'''


def update_sitemap(cats):
    sm = read('sitemap.xml')
    lines = '\n'.join(f'  <url><loc>{SITE}/blog/category/{slug}</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>'
                      for name, slug, _, _ in CATEGORIES if name in cats)
    write('sitemap.xml', replace_region(sm, 'CATEGORY-HUBS', lines, 'sitemap.xml'))


def main():
    posts = load_posts()
    cats = {}
    for p in posts:
        cats.setdefault(p['category'], []).append(p)
    for name in cats:
        if name not in CAT_BY_NAME:
            print(f'  WARNING: category {name!r} has no hub description in build_blog.py; using defaults')
            CATEGORIES.append((name, cat_slug(name), name + ' Articles',
                               f'Articles from Don Phelps about {name.lower()}.'))
            CAT_BY_NAME[name] = CATEGORIES[-1]

    shell = read('blog.html')
    write('blog.html', build_index(shell, posts, cats))
    for name, ps in cats.items():
        write(f'blog-category-{cat_slug(name)}.html', build_hub(shell, name, ps, cats))
    for p in posts:
        inject_keep_reading(p, posts, cats)
    write('feed.xml', build_feed(posts))
    update_sitemap(cats)
    print(f'Built blog: {len(posts)} posts, {len(cats)} topic hubs')


if __name__ == '__main__':
    main()
