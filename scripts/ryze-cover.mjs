// Remove only body images whose URL matches the separately rendered cover.
// Keep unrelated illustrations, scripts, image metadata and source articles intact.
export function withoutRepeatedCover(html, coverUrls) {
  const normalize = value => {
    try { return new URL(value.replace(/&amp;/g, '&'), 'https://nsyght.com').href; }
    catch { return null; }
  };
  const covers = new Set(coverUrls.filter(Boolean).map(normalize).filter(Boolean));
  if (!covers.size) return html;
  return html.replace(/<!--[\s\S]*?-->|<script\b[^>]*>[\s\S]*?<\/script\s*>|<img\b[^>]*>/gi, tag => {
    if (!/^<img\b/i.test(tag)) return tag;
    const src = tag.match(/\ssrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i);
    return src && covers.has(normalize(src[1] ?? src[2] ?? src[3])) ? '' : tag;
  });
}
