#!/usr/bin/env python3
"""Pull new BabyLoveGrowth articles into the blog queue.

Run by .github/workflows/release-posts.yml before the daily release, and on demand.
For each BabyLoveGrowth article that is not already on the site or in the queue it:
1. builds a full NSYGHT post page from a published post used as the template
   (same header, footer, sidebar and schema as every other post)
2. cleans the article: no em dashes, ids on every H2, NSYGHT links made relative,
   outside links open in a new tab
3. adds internal links to the matching NSYGHT service or industry page when the
   topic overlaps one (rules in _queue/blg_rules.json)
4. holds off-topic articles instead of queueing them (also in blg_rules.json)
5. saves the cover image to /images/blog and appends the post to _queue/queue.json

The release script then publishes from the queue as usual.

Needs the BLG_API_KEY environment variable (a GitHub Actions secret).
Usage: python3 scripts/pull_blg.py [--dry-run]
"""
import argparse, datetime, html, json, os, re, sys, time, unicodedata, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = 'https://api.babylovegrowth.ai/api/integrations/v1/articles'
SITE = 'https://nsyght.com'
WPM = 220


def read(p):
    with open(os.path.join(ROOT, p), encoding='utf-8') as f:
        return f.read()


def write(p, s):
    full = os.path.join(ROOT, p)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(s)


def api_get(url, key, tries=5):
    for i in range(tries):
        req = urllib.request.Request(url, headers={'X-API-Key': key, 'Content-Type': 'application/json',
                                                   'User-Agent': 'nsyght-blog-sync/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as err:
            if err.code == 401:
                sys.exit('BabyLoveGrowth said 401: check the BLG_API_KEY secret.')
            if err.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 ** (i + 1))
                continue
            raise
        except urllib.error.URLError:
            if i < tries - 1:
                time.sleep(2 ** (i + 1))
                continue
            raise


def list_articles(key):
    out, offset = [], 0
    while True:
        page = api_get(f'{API}?limit=50&offset={offset}', key)
        items = page if isinstance(page, list) else (page.get('data') or page.get('articles') or [])
        out.extend(items)
        if len(items) < 50:
            return out
        offset += 50
        time.sleep(0.5)


def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return re.sub(r'-{2,}', '-', s)


def words(s):
    return set(w for w in re.findall(r'[a-z0-9]+', s.lower()) if len(w) > 2 and w not in
               {'the', 'and', 'for', 'how', 'what', 'your', 'with', 'that', 'from', 'guide', '2026', 'you'})


def similar(a, b):
    wa, wb = words(a), words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.6


def no_dashes(s):
    """House style: no em dashes. Keep number ranges readable."""
    s = re.sub(r'(\d)\s*[—–]\s*(\d)', r'\1 to \2', s)
    s = re.sub(r'\s*—\s*', ', ', s)
    s = re.sub(r'\s+–\s+', ', ', s)
    s = s.replace('&mdash;', ', ')
    return re.sub(r',\s*,', ',', s)


def text_of(h):
    return html.unescape(re.sub(r'<[^>]+>', '', h)).strip()


def pick_category(a, rules):
    hay = ' '.join([a.get('title', ''), a.get('seedKeyword', '')] + list(a.get('keywords') or [])).lower()
    for cat, terms in rules['categories']:
        if any(t in hay for t in terms):
            return cat
    return rules['default_category']


def matching_links(a, rules):
    hay = ' '.join([a.get('title', ''), a.get('seedKeyword', '')]).lower()
    hits = [r for r in rules['internal_links'] if any(t in hay for t in r['match'])]
    return hits[:2]


def held_reason(a, rules):
    hay = ' '.join([a.get('title', ''), a.get('seedKeyword', '')]).lower()
    for h in rules['hold']:
        if any(t in hay for t in h['match']):
            return h['reason']
    return None


def clean_body(body, links):
    body = re.sub(r'<(script|style)\b.*?</\1>', '', body, flags=re.S | re.I)
    body = re.sub(r'<h1\b[^>]*>.*?</h1>', '', body, flags=re.S | re.I)
    body = no_dashes(body)
    # NSYGHT links relative, outside links in a new tab
    body = re.sub(r'href="https?://(?:www\.)?nsyght\.com(/[^"]*)?"', lambda m: f'href="{m.group(1) or "/"}"', body)

    def ext(m):
        tag = m.group(0)
        if 'href="http' in tag and 'target=' not in tag:
            tag = tag[:-1] + ' target="_blank" rel="noopener">'
        return tag
    body = re.sub(r'<a\b[^>]*>', ext, body)
    # ids on H2s, for the table of contents
    used = set()

    def h2(m):
        attrs, inner = m.group(1), m.group(2)
        idm = re.search(r'\bid="([^"]+)"', attrs)
        hid = idm.group(1) if idm else slugify(text_of(inner))[:80] or 'section'
        base, n = hid, 2
        while hid in used:
            hid, n = f'{base}-{n}', n + 1
        used.add(hid)
        return f'<h2 id="{hid}">{inner}</h2>'
    body = re.sub(r'<h2\b([^>]*)>(.*?)</h2>', h2, body, flags=re.S | re.I)
    # internal links: first plain mention in a paragraph, plus a short callout after the opening paragraph
    for r in links:
        for phrase in r['phrases']:
            pat = re.compile(r'(<p\b[^>]*>(?:(?!</p>).)*?)(?<![\w-])(' + re.escape(phrase) + r')(?![\w-])', re.I | re.S)

            def link_first(m):
                before = m.group(1)
                if before.count('<a ') > before.count('</a>'):
                    return m.group(0)
                return f'{before}<a href="{r["url"]}">{m.group(2)}</a>'
            new = pat.sub(link_first, body, count=1)
            if new != body:
                body = new
                break
    if links:
        lines = ''.join(f'<p>{r["callout"]}</p>' for r in links)
        callout = f'<div class="callout green"><div class="callout-label">Want this done for you?</div>{lines}</div>'
        end = body.find('</p>')
        body = body[:end + 4] + '\n' + callout + body[end + 4:] if end >= 0 else callout + body
    return body.strip()


def faq_block(faq):
    items = (faq or {}).get('mainEntity') or []
    if not items:
        return ''
    rows = []
    for q in items:
        name = no_dashes(html.escape(text_of(q.get('name', ''))))
        ans = no_dashes(html.escape(text_of((q.get('acceptedAnswer') or {}).get('text', ''))))
        if name and ans:
            rows.append(f'      <div class="faq-open-item">\n        <div class="faq-open-q">{name}</div>\n'
                        f'        <p class="faq-open-a">{ans}</p>\n      </div>')
    if not rows:
        return ''
    return '<h2 id="faq">Frequently Asked Questions</h2>\n    <div class="faq-open">\n' + '\n'.join(rows) + '\n    </div>'


def save_cover(url, slug, dry):
    if not url:
        return None
    ext = os.path.splitext(url.split('?')[0])[1].lower()
    if ext not in ('.webp', '.jpg', '.jpeg', '.png', '.gif', '.avif'):
        ext = '.jpg'
    rel = f'images/blog/{slug}-cover{ext}'
    if dry:
        return '/' + rel
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'nsyght-blog-sync/1.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        full = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as f:
            f.write(data)
        return '/' + rel
    except Exception as err:
        print(f'   cover image not saved ({err}); using the original URL')
        return url


def build_page(tpl, a, slug, category, cover, links, rules):
    title = no_dashes(text_of(a['title']))
    desc = no_dashes(text_of(a.get('meta_description') or a.get('excerpt') or ''))[:300]
    url = f'{SITE}/blog/{slug}'
    img_abs = cover if cover.startswith('http') else SITE + cover
    body = clean_body(a.get('content_html') or '', links)
    if not re.search(r'<h2[^>]*>[^<]*(FAQ|Frequently)', body, re.I):
        body += '\n' + faq_block(a.get('faqJsonLd'))
    n_words = len(text_of(body).split())
    read_min = max(3, round(n_words / WPM))
    alt = html.escape(f'{title} cover image')
    cover_fig = f'<figure class="post-cover"><img src="{html.escape(cover)}" alt="{alt}" width="1080" height="720" fetchpriority="high"/></figure>'
    E = html.escape
    s = tpl
    s = re.sub(r'<title>.*?</title>', f'<title>{E(title)} - NSYGHT</title>', s, count=1, flags=re.S)
    for pat, val in ((r'<meta name="description" content="[^"]*"', f'<meta name="description" content="{E(desc)}"'),
                     (r'<link rel="canonical" href="[^"]*"', f'<link rel="canonical" href="{url}"'),
                     (r'<meta property="og:title" content="[^"]*"', f'<meta property="og:title" content="{E(title)} - NSYGHT"'),
                     (r'<meta property="og:description" content="[^"]*"', f'<meta property="og:description" content="{E(desc)}"'),
                     (r'<meta property="og:url" content="[^"]*"', f'<meta property="og:url" content="{url}"'),
                     (r'<meta property="og:image" content="[^"]*"', f'<meta property="og:image" content="{E(img_abs)}"'),
                     (r'<meta property="article:published_time" content="[^"]*"', '<meta property="article:published_time" content="%%DATE_ISO%%"')):
        s = re.sub(pat, lambda m: val, s, count=1)

    article_ld = {
        '@context': 'https://schema.org', '@type': 'Article', 'headline': title, 'description': desc,
        'datePublished': '%%DATE_ISO%%', 'dateModified': '%%DATE_ISO%%',
        'author': {'@type': 'Person', 'name': 'Don Phelps', 'url': f'{SITE}/about',
                   'sameAs': ['https://www.linkedin.com/in/donphelpsseo/']},
        'publisher': {'@type': 'Organization', 'name': 'NSYGHT', 'url': SITE,
                      'logo': {'@type': 'ImageObject', 'url': f'{SITE}/logo.png'}},
        'mainEntityOfPage': {'@type': 'WebPage', '@id': url}, 'url': url, 'image': img_abs,
        'articleSection': category,
    }
    crumbs = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE},
        {'@type': 'ListItem', 'position': 2, 'name': 'Resources', 'item': f'{SITE}/blog'},
        {'@type': 'ListItem', 'position': 3, 'name': title, 'item': url}]}
    faq = a.get('faqJsonLd') if (a.get('faqJsonLd') or {}).get('mainEntity') else None
    if faq:
        faq = json.loads(no_dashes(json.dumps(faq, ensure_ascii=False)))

    def ld(obj):
        return '<script type="application/ld+json">\n' + json.dumps(obj, indent=2, ensure_ascii=False) + '\n</script>'

    def swap_ld(doc, typ, obj):
        pat = re.compile(r'<script type="application/ld\+json">\s*\{\s*"@context": "https://schema.org",\s*"@type": "' + typ + r'".*?</script>', re.S)
        if obj is None:
            return pat.sub('', doc, count=1)
        return pat.sub(lambda m: ld(obj), doc, count=1)
    s = swap_ld(s, 'Article', article_ld)
    s = swap_ld(s, 'FAQPage', faq)
    s = swap_ld(s, 'BreadcrumbList', crumbs)

    # hero
    s = re.sub(r'(<nav class="breadcrumb".*?<span style="color:rgba\(255,255,255,\.35\)">&rsaquo;</span>\s*<a href="/blog".*?</a>\s*<span style="color:rgba\(255,255,255,\.35\)">&rsaquo;</span>\s*<span>)[^<]*(</span>)',
               lambda m: m.group(1) + E(category) + m.group(2), s, count=1, flags=re.S)
    s = re.sub(r'<div class="post-category">[^<]*</div>', f'<div class="post-category">{E(category)}</div>', s, count=1)
    s = re.sub(r'<h1>.*?</h1>', f'<h1>{E(title)}</h1>', s, count=1, flags=re.S)
    s = re.sub(r'<div class="post-meta-info">.*?</div>',
               f'<div class="post-meta-info">\n        <span><time datetime="%%DATE_ISO%%">%%DATE_HUMAN%%</time></span>\n        <span>{read_min} min read</span>\n      </div>',
               s, count=1, flags=re.S)
    # article body, up to the Keep Reading block (rebuilt by build_blog.py)
    start = s.index('<article class="article-content">') + len('<article class="article-content">')
    kr = s.index('<!-- KEEP-READING:START -->')
    s = s[:start] + '\n    ' + cover_fig + '\n\n' + body + '\n  ' + s[kr:]
    s = re.sub(r'<!-- KEEP-READING:START -->.*?<!-- KEEP-READING:END -->',
               '<!-- KEEP-READING:START -->\n<!-- KEEP-READING:END -->', s, count=1, flags=re.S)
    # sidebar: table of contents and related pages
    toc = ''.join(f'\n        <li><a href="#{hid}">{E(text_of(t))}</a></li>'
                  for hid, t in re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body, re.S))
    s = re.sub(r'(<ul class="toc-list">).*?(\n\s*</ul>)', lambda m: m.group(1) + toc + m.group(2), s, count=1, flags=re.S)
    rel = [(r['url'], r['label']) for r in links] + [tuple(x) for x in rules['related_defaults'].get(category, rules['related_defaults']['_'])]
    seen, items = set(), []
    for u, label in rel:
        if u not in seen and len(items) < 4:
            seen.add(u)
            items.append(f'\n        <li><a href="{u}">&rarr; {E(label)}</a></li>')
    s = re.sub(r'(<ul class="sidebar-related-links">).*?(\n\s*</ul>)', lambda m: m.group(1) + ''.join(items) + m.group(2), s, count=1, flags=re.S)
    excerpt = desc if len(desc) <= 200 else desc[:197].rsplit(' ', 1)[0] + '...'
    return s, title, excerpt, read_min


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    key = os.environ.get('BLG_API_KEY', '').strip()
    rules = json.loads(read('_queue/blg_rules.json'))
    if not key:
        print('BLG_API_KEY is not set. Skipping the BabyLoveGrowth pull.')
        return
    if not rules.get('enabled') and not a.dry_run:
        print('BabyLoveGrowth pull is turned off in _queue/blg_rules.json ("enabled": false). Skipping.')
        return

    q = json.loads(read('_queue/queue.json'))
    posts = json.loads(read('_data/posts.json'))
    log_path = '_queue/blg_imported.json'
    log = json.loads(read(log_path)) if os.path.exists(os.path.join(ROOT, log_path)) else {'imported': {}, 'skipped': {}}
    known_slugs = {p['slug'] for p in posts} | {p['slug'] for p in q['posts']} | {p['slug'] for p in q.get('held', [])}
    known_titles = [p['title'] for p in posts] + [p.get('title', '') for p in q['posts']]
    tpl = read(rules['template'])
    cutoff = rules.get('only_created_after', '')

    arts = list_articles(key)
    print(f'BabyLoveGrowth returned {len(arts)} articles')
    new = 0
    for s in sorted(arts, key=lambda x: x.get('created_at') or ''):
        aid = str(s.get('id'))
        if aid in log['imported'] or aid in log['skipped']:
            continue
        title = text_of(s.get('title') or '')
        kw = (s.get('seedKeyword') or '').strip()
        slug = slugify(kw) if kw else slugify(s.get('slug') or title)
        if (s.get('languageCode') or 'en')[:2] != 'en':
            log['skipped'][aid] = 'not English'
            continue
        if cutoff and (s.get('created_at') or '') <= cutoff:
            log['skipped'][aid] = f'created before {cutoff}'
            continue
        if slug in known_slugs or any(similar(title, t) for t in known_titles) or \
                any(slugify(kw) == p['slug'] or similar(kw, p['title']) for p in posts if kw):
            print(f' already on the site: {title}')
            log['skipped'][aid] = 'already on the site'
            continue
        if s.get('published_url') and 'nsyght.com' not in s['published_url']:
            log['skipped'][aid] = 'published elsewhere'
            continue
        base, n = slug, 2
        while slug in known_slugs:
            slug, n = f'{base}-{n}', n + 1
        reason = held_reason(s, rules)
        if a.dry_run:
            print(f' would {"HOLD" if reason else "queue"}: /blog/{slug}  ({title}){"  reason: " + reason if reason else ""}')
            continue
        full = api_get(f'{API}/{aid}', key)
        full = full.get('data', full) if isinstance(full, dict) else full
        if not (full.get('content_html') or '').strip():
            print(f' no content yet, will retry later: {title}')
            continue
        category = pick_category(full, rules)
        links = matching_links(full, rules)
        cover = save_cover(full.get('hero_image_url'), slug, False) or rules['fallback_image']
        page, ptitle, excerpt, read_min = build_page(tpl, full, slug, category, cover, links, rules)
        f = f'_queue/blog-{slug}.html'
        write(f, page)
        entry = {'slug': slug, 'file': f, 'title': ptitle, 'category': category, 'excerpt': excerpt,
                 'read_min': read_min, 'source': 'babylovegrowth', 'blg_id': aid}
        if reason:
            entry['reason'] = reason
            q.setdefault('held', []).append(entry)
            print(f' held /blog/{slug}: {reason}')
        else:
            q['posts'].append(entry)
            print(f' queued /blog/{slug} ({category}{", links to " + ", ".join(r["url"] for r in links) if links else ""})')
        log['imported'][aid] = {'slug': slug, 'date': datetime.date.today().isoformat(), 'held': bool(reason)}
        known_slugs.add(slug)
        known_titles.append(ptitle)
        new += 1
        time.sleep(0.5)

    if a.dry_run:
        return
    write('_queue/queue.json', json.dumps(q, indent=2, ensure_ascii=False) + '\n')
    write(log_path, json.dumps(log, indent=2, ensure_ascii=False) + '\n')
    print(f'{new} new articles added. {len(q["posts"])} posts now in the queue.')


if __name__ == '__main__':
    main()
