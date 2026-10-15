#!/usr/bin/env python3
"""Normalize the shared site footer on every page. Safe to run repeatedly.

  * Services links point at the /services/... routes that exist in netlify.toml
  * Industries column includes Real Estate Investors
  * Footer tagline has no em dash
  * Dead Cloudflare email-decode script (and /cdn-cgi/ email links) removed

Usage: python3 scripts/fix_footer.py [files...]   (default: every *.html in the
site root and _queue/)
"""
import glob, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LINKS = {
    '<a href="/seo">SEO</a>': '<a href="/services/seo">SEO</a>',
    '<a href="/web-design">Website Design</a>': '<a href="/services/web-design">Website Design</a>',
    '<a href="/google-ads">Google Ads</a>': '<a href="/services/google-ads">Google Ads</a>',
    '<a href="/facebook-ads">Facebook Ads</a>': '<a href="/services/facebook-ads">Facebook Ads</a>',
    '<a href="/social-media">Social Media</a>': '<a href="/services/social-media">Social Media</a>',
}
HOME = '<li><a href="/industries/home-services">Home Services</a></li>'
REI = '<li><a href="/industries/real-estate-investors">Real Estate Investors</a></li>'
TAG_OLD = 'Based in Austin, TX — serving businesses nationwide.'
TAG_NEW = 'Based in Austin, TX, serving businesses nationwide.'
CF_SCRIPT = re.compile(r'<script data-cfasync="false" src="/cdn-cgi/scripts/[^"]*/email-decode\.min\.js"></script>')
CF_LINK = re.compile(r'<a href="/cdn-cgi/l/email-protection#[0-9a-f]+"><span class="__cf_email__" data-cfemail="[0-9a-f]+">\[email&#160;protected\]</span></a>')
EMAIL_JS = ("<a href=\"/contact\" id=\"email-link\">Email us</a>"
            "<script>(function(){var e='inf'+'o@'+'nsyght'+'.com',a=document.getElementById('email-link');"
            "a.href='mai'+'lto:'+e;a.textContent=e;})();</script>")


def fix(s):
    m = re.search(r'<footer>.*?</footer>', s, re.S)
    if m:
        ft = m.group(0)
        for a, b in LINKS.items():
            ft = ft.replace(a, b)
        if REI not in ft and HOME in ft:
            ft = ft.replace(HOME, HOME + REI, 1)
        ft = ft.replace(TAG_OLD, TAG_NEW)
        s = s[:m.start()] + ft + s[m.end():]
    s = CF_SCRIPT.sub('', s)
    s = CF_LINK.sub(EMAIL_JS, s)
    return s


def main(files):
    files = files or sorted(glob.glob(os.path.join(ROOT, '*.html')) + glob.glob(os.path.join(ROOT, '_queue', '*.html')))
    for f in files:
        with open(f, encoding='utf-8') as fh:
            s = fh.read()
        t = fix(s)
        if t != s:
            with open(f, 'w', encoding='utf-8') as fh:
                fh.write(t)
            print('fixed', os.path.relpath(f, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
