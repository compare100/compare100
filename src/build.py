#!/usr/bin/env python3
"""Static site generator for compare100.com — rebuilds from the WordPress WXR export.
Preserves every URL and image path; outputs clean, fast, schema-marked HTML."""
import xml.etree.ElementTree as ET, re, html, os, json, shutil
from collections import defaultdict
from datetime import datetime

# Paths resolve relative to this file, so the repo works anywhere it is cloned.
HERE = os.path.dirname(os.path.abspath(__file__))
WXR  = os.environ.get('C100_WXR', os.path.join(HERE, 'wxr', 'compare100.xml'))
OUT  = os.environ.get('C100_OUT', os.path.join(os.path.dirname(HERE), 'site'))
SITE = 'https://compare100.com'
NS = {'wp': 'http://wordpress.org/export/1.2/',
      'content': 'http://purl.org/rss/1.0/modules/content/',
      'excerpt': 'http://wordpress.org/export/1.2/excerpt/'}

# ---------------------------------------------------------------- parse
root = ET.parse(WXR).getroot(); ch = root.find('channel')

def g(el, path, d=''):
    x = el.find(path, NS)
    return (x.text or d) if x is not None else d

cats, catparent, catname = {}, {}, {}
caticon, catintro, catbrand = {}, {}, {}
for c in ch.findall('wp:category', NS):
    s = g(c, 'wp:category_nicename'); catparent[s] = g(c, 'wp:category_parent')
    # decode once: "Fitness &amp; Wearables" is escaped again downstream otherwise
    catname[s] = html.unescape(g(c, 'wp:cat_name'))
    desc = g(c, 'wp:category_description')
    m = re.search(r'src="([^"]+)"', desc or '')
    if m: caticon[s] = m.group(1).replace('https://compare100.com', '')
    txt = re.sub(r'<[^>]+>', ' ', desc or '')
    txt = re.sub(r'\s+', ' ', html.unescape(txt)).strip()
    if txt: catintro[s] = txt
    for tm in c.findall('wp:termmeta', NS):
        k = tm.find('wp:meta_key', NS); v = tm.find('wp:meta_value', NS)
        if k is not None and k.text == 'brandimage' and v is not None and v.text:
            catbrand[s] = v.text

TOP_EARLY = ['insurance', 'money', 'travel', 'mobile-phones', 'utilities', 'motoring', 'shopping']
atts = {}
for it in ch.findall('item'):
    if g(it, 'wp:post_type') == 'attachment':
        atts[g(it, 'wp:post_id')] = g(it, 'wp:attachment_url')

def relpath(u):
    """Keep image paths identical to the old site so the uploads folder drops straight in.
    Also folds the sister domain compare100.co.uk back onto this site."""
    if not u: return ''
    return re.sub(r'^https?://(?:www\.)?compare100\.(?:com|co\.uk)', '', u)

posts, pages = [], []
for it in ch.findall('item'):
    ty, st = g(it, 'wp:post_type'), g(it, 'wp:status')
    if ty not in ('post', 'page'): continue
    if st != 'publish': continue          # private, draft, pending and blog templates: discarded
    meta = {}
    for pm in it.findall('wp:postmeta', NS):
        meta[g(pm, 'wp:meta_key')] = g(pm, 'wp:meta_value')
    cs = [(e.get('nicename'), e.text) for e in it.findall('category') if e.get('domain') == 'category']
    rec = dict(
        # WordPress stores titles with entities already encoded ("Legal &amp; General").
        # Everything downstream runs esc() on them, so decode once here or the page
        # prints "Legal &amp; General" as literal text.
        title=html.unescape(g(it, 'title')), slug=g(it, 'wp:post_name'), type=ty,
        date=g(it, 'wp:post_date')[:10], modified=g(it, 'wp:post_modified')[:10],
        content=g(it, 'content:encoded'), excerpt=g(it, 'excerpt:encoded'),
        seo_title=meta.get('_yoast_wpseo_title', ''), seo_desc=meta.get('_yoast_wpseo_metadesc', ''),
        focuskw=meta.get('_yoast_wpseo_focuskw', ''),
        logo=relpath(atts.get(meta.get('_thumbnail_id', ''), '')),
        offer_url=meta.get('rehub_offer_product_url', '') or meta.get('learn_more_url', ''),
        btn=meta.get('rehub_offer_btn_text', '') or 'Get Quotes',
        cats=cs, status=st,
    )
    (posts if ty in ('post', 'blog') else pages).append(rec)

# top-level category icons live inside the /compare-uk-*-deals/ pages (first 150x150 image)
DEALS_MAP = {'compare-uk-insurance-deals': 'insurance', 'compare-uk-money-deals': 'money',
             'compare-uk-travel-deals': 'travel', 'compare-uk-mobile-deals': 'mobile-phones',
             'compare-uk-utility-deals': 'utilities', 'compare-uk-motoring-deals': 'motoring',
             'compare-uk-shopping-deals': 'shopping'}
for _p in pages + posts:
    _c = DEALS_MAP.get(_p['slug'])
    if not _c: continue
    _m = re.search(r'(?:src|data-src)="([^"]*wp-content/uploads/[^"]*-150x150\.[a-z]+)"', _p['content'])
    if _m:
        caticon[_c] = relpath(_m.group(1))

# prefer the full-size original over WordPress crop suffixes (sharper on retina)
def _full(u):
    return re.sub(r'-\d+x\d+(\.\w+)$', r'\1', u) if u else u
_att_set = {relpath(u) for u in atts.values()}
for _k, _v in list(caticon.items()):
    _f = _full(_v)
    if _f in _att_set: caticon[_k] = _f

# ---- affiliate link overrides -------------------------------------------
# Paste your network deeplinks into the 'your_affiliate_url' column of
# site/affiliate-links.csv, rerun this build, and every CTA switches over.
AFF = {}
_affcsv = os.path.join(HERE, 'affiliate-links.csv')
if os.path.isfile(_affcsv):
    import csv as _csv
    with open(_affcsv, encoding='utf-8') as _fh:
        for _r in _csv.DictReader(_fh):
            _u = (_r.get('your_affiliate_url') or '').strip()
            if _u: AFF[_r['slug']] = _u
    print(f'affil   {len(AFF)} affiliate overrides loaded from affiliate-links.csv')

for _p in posts:
    if _p['slug'] in AFF:
        _p['offer_url'] = AFF[_p['slug']]

# ---- rewritten content drop-in -----------------------------------------
# Any JSON in pkg/rewritten/*.json replaces the original copy for those slugs.
# Structure per page: slug,title,meta_title,meta_description,intro,sections,
# key_facts,pros,cons,verdict,faqs,checked
REWRITTEN = {}
_rwdir = os.path.join(HERE, 'rewritten')
if os.path.isdir(_rwdir):
    for _f in sorted(os.listdir(_rwdir)):
        if not _f.endswith('.json'): continue
        for _pg in json.load(open(os.path.join(_rwdir, _f), encoding='utf-8')):
            REWRITTEN[_pg['slug']] = _pg
    if REWRITTEN: print(f'rewrite {len(REWRITTEN)} pages have rewritten content')

print(f'parsed  {len(posts)} posts  {len(pages)} pages  {len(atts)} attachments  {len(catparent)} categories')
print(f'icons   {len(caticon)} category icons ({sum(1 for k in TOP_EARLY if k in caticon)}/7 top-level)')

# ---------------------------------------------------------------- clean content
SHORTCODE = re.compile(r'\[/?[a-zA-Z0-9_\- ]+(?:[^\]]*)\]')
LAZY_STUB = re.compile(r'(blank\.gif|noimage_\d+_\d+\.png|data:image/gif;base64)', re.I)

def promote_lazy(h):
    """Rehub/Elementor lazy-load puts blank.gif in src and the real file in data-src.
    Promote the real file BEFORE we strip data-* attributes, then drop any stub left over."""
    def fix(m):
        tag = m.group(0)
        real = None
        for attr in ('data-src', 'data-lazy-src', 'data-original', 'data-lazy'):
            mm = re.search(rf'{attr}="([^"]+)"', tag)
            if mm and not LAZY_STUB.search(mm.group(1)):
                real = mm.group(1); break
        if real:
            tag = re.sub(r'src="[^"]*"', f'src="{real}"', tag, count=1)
            if 'src="' not in tag:
                tag = tag.replace('<img', f'<img src="{real}"', 1)
        srcset = re.search(r'data-srcset="([^"]+)"', tag)
        if srcset:
            tag = re.sub(r'srcset="[^"]*"', '', tag)
            tag = tag.replace('<img', f'<img srcset="{srcset.group(1)}"', 1)
        return tag
    h = re.sub(r'<img\b[^>]*>', fix, h)
    # anything still pointing at a stub has no real image behind it — remove the tag
    h = re.sub(r'<img\b[^>]*>', lambda m: '' if LAZY_STUB.search(m.group(0)) else m.group(0), h)
    return h

TP = re.compile(r'trustpilot', re.I)

def strip_trustpilot(h):
    """The site owner does not want Trustpilot referenced anywhere. Remove it
    surgically: whole list items / table rows that mention it, individual
    sentences inside paragraphs, and any link to trustpilot.com."""
    if not h or not TP.search(h): return h
    # whole <li> or <tr> blocks that mention it
    for tag in ('li', 'tr'):
        h = re.sub(rf'<{tag}\b[^>]*>(?:(?!</{tag}>).)*?trustpilot(?:(?!</{tag}>).)*?</{tag}>',
                   '', h, flags=re.S | re.I)
    # unwrap or drop links to trustpilot
    h = re.sub(r'<a\b[^>]*trustpilot[^>]*>(.*?)</a>', r'\1', h, flags=re.S | re.I)
    # sentence-level removal inside text blocks
    def clean_block(m):
        inner = m.group(2)
        if not TP.search(inner): return m.group(0)
        parts = re.split(r'(?<=[.!?])\s+', inner)
        kept = [p for p in parts if not TP.search(p)]
        out = ' '.join(kept).strip()
        return '' if not out else f'{m.group(1)}{out}{m.group(3)}'
    h = re.sub(r'(<p\b[^>]*>)(.*?)(</p>)', clean_block, h, flags=re.S | re.I)
    h = re.sub(r'(<h[1-6]\b[^>]*>)(.*?)(</h[1-6]>)', clean_block, h, flags=re.S | re.I)
    # any stray leftover text node
    h = re.sub(r'[^<>.!?]*trustpilot[^<>.!?]*[.!?]?', '', h, flags=re.I)
    h = re.sub(r'<(p|li|td)\b[^>]*>\s*</\1>', '', h, flags=re.I)
    h = re.sub(r'\s{2,}', ' ', h)
    return h

DEMO_HOSTS = re.compile(r'(reviewit\.wpsoul\.net|wpsoul\.com|demo\.|placeholder)', re.I)
# Affiliate networks serve their banner creative from their own servers on purpose:
# that is how impressions are tracked. These must stay external.
AFFILIATE_CREATIVE = re.compile(
    r'(awin1\.com|zenaps\.com|tradetracker\.net|prf\.hn|pjtra\.com|lduhtrp\.net|'
    r'anrdoezrs\.net|dpbolvw\.net|jdoqocy\.com|tkqlhce\.com|kqzyfj\.com|ftjcfx\.com|'
    r'omgt\d?\.com|affiliatefuture\.com|webgains\.com|ikhnaie\.link|shareasale\.com|'
    r'impact-ad|sjv\.io|pxf\.io)', re.I)

def strip_demo_and_size(h):
    """Rehub demo images point at the theme author's server. Remove them.
    Inline SVG icons have no size limit and blow up to container width. Cap them."""
    def keep(m):
        tag = m.group(0)
        if DEMO_HOSTS.search(tag): return ''            # theme-demo junk
        src = re.search(r'src="(https?://[^"]+)"', tag)
        if src and 'compare100.com' not in src.group(1):
            if AFFILIATE_CREATIVE.search(src.group(1)):
                return tag                              # affiliate banner: must stay external
            return ''                                   # any other third-party image: drop
        return tag
    h = re.sub(r'<img\b[^>]*>', keep, h)
    def svg(m):
        tag = m.group(0)
        if 'width=' not in tag:
            tag = tag.replace('<svg', '<svg width="48" height="48"', 1)
        return tag.replace('<svg', '<svg class="cicon-svg"', 1)
    h = re.sub(r'<svg\b[^>]*>', svg, h)
    return h

def absolutise(h):
    """Every asset must be root-relative so it is served by the NEW host, never the old VPS."""
    h = re.sub(r'(src|srcset|href)="https?://(?:www\.)?compare100\.(?:com|co\.uk)', r'\1="', h)
    return h

def normalise_headings(h):
    """Rebuild the imported body's heading outline so it starts at h2 and never
    skips a level.

    Elementor picked heading tags for their size, not their meaning, so pages open
    with an <h3> under the page <h1>, or jump h2 -> h4. A skipped level tells a
    crawler and a screen reader that a section is missing. Two passes:

    1. A heading longer than 90 characters is a paragraph somebody made bold.
       Demote it, or it both breaks the outline and dilutes what the page is about.
    2. Re-level whatever is left. A stack of the original depths maps them onto a
       contiguous h2, h3, h4... outline, so relative nesting is preserved even
       though the absolute numbers change.
    """
    def unhead(m):
        text = html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
        if len(text) > 90:
            return f'<p><strong>{m.group(2).strip()}</strong></p>'
        return m.group(0)
    h = re.sub(r'<h([2-6])[^>]*>(.*?)</h\1>', unhead, h, flags=re.S)

    stack = []
    def relevel(m):
        lvl, inner = int(m.group(1)), m.group(2)
        while stack and stack[-1] >= lvl:
            stack.pop()
        stack.append(lvl)
        return f'<h{min(6, len(stack) + 1)}>{inner}</h{min(6, len(stack) + 1)}>'
    return re.sub(r'<h([2-6])[^>]*>(.*?)</h\1>', relevel, h, flags=re.S)

def clean(h):
    if not h: return ''
    h = re.sub(r'<!--.*?-->', '', h, flags=re.S)          # WP block + Elementor comments
    h = SHORTCODE.sub('', h)
    h = re.sub(r'<(script|style|iframe|noscript)\b.*?</\1>', '', h, flags=re.S | re.I)
    h = promote_lazy(h)                                    # BEFORE data-* is stripped
    h = strip_demo_and_size(h)                             # kill theme-demo images, cap SVGs
    h = strip_trustpilot(h)                                # owner: never mention Trustpilot
    h = absolutise(h)
    h = re.sub(r'\son\w+="[^"]*"', '', h)                  # inline handlers
    h = re.sub(r'\s(class|id|style|data-[\w-]+)="[^"]*"', '', h)   # theme cruft
    h = re.sub(r'<img\b(?![^>]*\bloading=)', '<img loading="lazy" ', h)  # native lazy, no JS
    # An affiliate creative with no alt is an unlabelled advert to a screen reader
    # and an unlabelled image to Google. Mark it as advertising rather than guess.
    h = re.sub(r'<img\b(?![^>]*\balt=)', '<img alt="Advertisement" ', h)
    # The imported body sometimes carries its own <h1>, which collides with the
    # page heading. Two h1s on a page tells a crawler neither is the subject.
    h = re.sub(r'<(/?)h1\b', r'<\1h2', h)
    h = normalise_headings(h)
    h = re.sub(r'<p>\s*</p>', '', h)
    h = re.sub(r'\n{3,}', '\n\n', h)
    return h.strip()

def paragraphs(h):
    """Return list of block-level HTML chunks, converting bare text to <p>."""
    h = clean(h)
    if not h: return []
    if '<p' not in h and '<h' not in h and '<ul' not in h:
        return [f'<p>{p.strip()}</p>' for p in h.split('\n\n') if p.strip()]
    return [h]

def words(h):
    return len(re.sub(r'<[^>]+>', ' ', clean(h)).split())

# ---------------------------------------------------------------- link rewriting
# LINKFIX: content still links to old category slugs. Send internal links straight
# to the final destination rather than bouncing through a 301.
LINKMAP = {}
_rd = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pkg', '_redirects')
if os.path.isfile(_rd):
    for _l in open(_rd, encoding='utf-8'):
        _p = _l.split()
        if len(_p) >= 2: LINKMAP[_p[0].rstrip('/') + '/'] = _p[1]

def fix_links(h, self_slug=''):
    def sub(m):
        url = m.group(1)
        if 'compare100.com' in url or 'compare100.co.uk' in url or url.startswith('/'):
            r = (relpath(url) or '/').replace('&amp;authuser=1', '').replace('&authuser=1', '')
            key = r.split('#')[0].split('?')[0]
            if not key.endswith('/'): key += '/'
            if key in LINKMAP: r = LINKMAP[key]
            return f'href="{r}"'
        return f'href="{url}" rel="sponsored nofollow noopener" target="_blank"'
    return re.sub(r'href="([^"]+)"', sub, h)

# ---------------------------------------------------------------- taxonomy
# The seven /compare-uk-*-deals/ pages are no longer rendered from their old
# WordPress content — the generated section hub is written to those addresses
# instead, so the URL keeps its 16 months of search history and gains a page
# that actually lists every child category. Rendering both would race, and
# whichever ran last would win.
SECTION_PAGES = set(DEALS_MAP)

DROP_PAGES = {'shop', 'my-account', 'cart', 'checkout', 'wishlist', 'comparison'}
TOP = ['insurance', 'money', 'travel', 'mobile-phones', 'utilities', 'motoring', 'shopping']
# The seven section hubs live at their original WordPress addresses. Google has
# 16 months of history on these; the /category/{x}/ equivalents had none, and are
# now 301s onto these. Changing this map without adding the matching redirects
# would strand every section page.
SECTION_URL = {
    'insurance':     '/compare-uk-insurance-deals/',
    'money':         '/compare-uk-money-deals/',
    'travel':        '/compare-uk-travel-deals/',
    'mobile-phones': '/compare-uk-mobile-deals/',
    'utilities':     '/compare-uk-utility-deals/',
    'motoring':      '/compare-uk-motoring-deals/',
    'shopping':      '/compare-uk-shopping-deals/',
}
def section_url(s):
    return SECTION_URL.get(s, f'/category/{s}/')

NAVNAME = {'insurance': 'Insurance', 'money': 'Money', 'travel': 'Travel',
           'mobile-phones': 'Mobiles', 'utilities': 'Utilities',
           'motoring': 'Motoring', 'shopping': 'Shopping'}
children = defaultdict(list)
for s, p in catparent.items():
    if p in TOP: children[p].append(s)
for k in children: children[k].sort(key=lambda s: catname.get(s, s))

def cat_icon(slug, size=54):
    u = caticon.get(slug, '')
    if not u: return ''
    return (f'<img class="cicon" src="{u}" alt="" width="{size}" height="{size}" '
            f'loading="lazy" decoding="async">')

def cat_url(slug):
    p = catparent.get(slug, '')
    return f'/category/{p}/{slug}/' if p else f'/category/{slug}/'

bycat = defaultdict(list)
for p in posts:
    if p.get('status') != 'publish': continue   # private/draft never appear in listings
    for slug, name in p['cats']:
        bycat[slug].append(p)
for k in bycat:
    bycat[k].sort(key=lambda x: x['title'])

def primary_cat(p):
    for slug, name in p['cats']:
        if catparent.get(slug) in TOP: return slug
    return p['cats'][0][0] if p['cats'] else ''

# ---------------------------------------------------------------- templates
CSS = """*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#16202c;--mut:#5b6875;--line:#e4e8ed;--brand:#1d4ed8;--bg:#f6f8fa}
body{font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:#fff}
a{color:var(--brand)}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
header.top{background:#fff;border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;justify-content:space-between;padding:16px 20px}
.logo{display:inline-block;line-height:0}
.logo img{width:225px;height:41px;object-fit:contain;display:block}
nav.main{background:#1f2733}
nav.main ul{display:flex;flex-wrap:wrap;list-style:none;max-width:1120px;margin:0 auto;padding:0 12px}
nav.main a{display:block;padding:13px 16px;color:#e8edf3;text-decoration:none;font-size:14.5px;font-weight:600}
nav.main a:hover{background:#2c3644}
.crumb{font-size:13px;color:var(--mut);padding:16px 0}
.crumb a{color:var(--mut)}
.layout{display:grid;grid-template-columns:1fr 300px;gap:34px;padding:8px 0 48px}
@media(max-width:900px){.layout{grid-template-columns:1fr}}
h1{font-size:31px;line-height:1.25;margin:6px 0 14px;letter-spacing:-.4px}
h2{font-size:22px;margin:30px 0 12px}
h3{font-size:18px;margin:22px 0 10px}
article p{margin:0 0 15px}
article ul,article ol{margin:0 0 16px 22px}
article li{margin:6px 0}
.meta{font-size:13px;color:var(--mut);border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:22px}
.offer{border:1px solid var(--line);border-radius:10px;padding:20px;text-align:center;background:#fff;box-shadow:0 1px 3px rgba(20,30,45,.06)}
.offer img{width:180px;height:180px;object-fit:contain;margin:0 auto 14px;display:block;background:#fff}
.btn{display:inline-block;background:var(--brand);color:#fff;text-decoration:none;font-weight:700;padding:12px 24px;border-radius:7px;font-size:15px}
.btn:hover{background:#1739a8}
.card{display:flex;gap:20px;align-items:center;border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:14px;background:#fff}
.card .thumb{flex:0 0 132px;text-align:center}
.card .thumb img{width:120px;height:120px;object-fit:contain;background:#fff;display:block;margin:0 auto}
.card h3{margin:0 0 6px;font-size:17px}
.card h3 a{text-decoration:none}
.card p{font-size:14.5px;color:var(--mut);margin:0}
.card .go{flex:0 0 auto}
@media(max-width:640px){.card{flex-direction:column;text-align:center}}
aside h4{font-size:15px;margin:0 0 10px;text-transform:uppercase;letter-spacing:.4px;color:var(--mut)}
aside ul{list-style:none;border:1px solid var(--line);border-radius:10px;overflow:hidden}
aside li a{display:block;padding:11px 15px;border-bottom:1px solid var(--line);text-decoration:none;font-size:14.5px;color:var(--ink)}
aside li:last-child a{border-bottom:0}
aside li a:hover{background:var(--bg)}
.related{border-top:1px solid var(--line);margin-top:36px;padding-top:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:16px}
.grid a{display:block;border:1px solid var(--line);border-radius:9px;padding:14px;text-decoration:none;color:var(--ink);font-size:14px;font-weight:600}
.grid a:hover{border-color:var(--brand)}
.grid img{width:100%;height:88px;object-fit:contain;background:#fff;margin-bottom:9px;display:block}
.disc{background:#fff8e6;border:1px solid #f2dfae;border-radius:8px;padding:12px 15px;font-size:13.5px;color:#6a5628;margin:0 0 22px}
footer{background:#1f2733;color:#b9c3ce;margin-top:40px;padding:34px 0;font-size:14px}
footer a{color:#dde4ec;text-decoration:none;margin-right:18px}
.facts{width:100%;border-collapse:collapse;margin:6px 0 24px;font-size:15px}
.facts th,.facts td{border:1px solid var(--line);padding:10px 13px;text-align:left;vertical-align:top}
.facts th{background:var(--bg);width:38%;font-weight:600}
.pc{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:8px 0 26px}
@media(max-width:640px){.pc{grid-template-columns:1fr}}
.pc>div{border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.pc h3{margin:0 0 10px;font-size:16px}
.pc ul{margin:0 0 0 18px}
.pc li{margin:7px 0;font-size:14.7px}
.pros{background:#f2fbf5;border-color:#cfe9d8!important}
.cons{background:#fdf5f5;border-color:#f0d8d8!important}
.verdict{border-left:4px solid var(--brand);background:var(--bg);padding:16px 20px;border-radius:0 8px 8px 0;margin:8px 0 26px}
.verdict h3{margin:0 0 8px;font-size:17px}
.faq{border-top:1px solid var(--line);margin-top:30px;padding-top:20px}
.faq details{border:1px solid var(--line);border-radius:8px;padding:13px 16px;margin-bottom:10px}
.faq summary{font-weight:650;cursor:pointer;font-size:15.5px}
.faq p{margin:10px 0 0;font-size:15px}
.checked{font-size:13px;color:var(--mut);margin-top:26px;padding-top:14px;border-top:1px solid var(--line)}
.cmp{width:100%;border-collapse:collapse;margin:8px 0 26px;font-size:15px}
.cmp th{background:var(--bg);border:1px solid var(--line);padding:9px 12px;text-align:left;font-size:13px;text-transform:uppercase;letter-spacing:.4px;color:var(--mut)}
.cmp td{border:1px solid var(--line);padding:12px;vertical-align:middle}
.cmp td.tl{width:88px;text-align:center}
.cmp td.tl img{width:72px;height:72px;object-fit:contain;background:#fff}
.cmp td.tc{width:150px;text-align:center}
.cmp a{text-decoration:none}
.tsub{font-size:13.5px;color:var(--mut);margin-top:4px;line-height:1.45}
.tfact{font-size:13px;margin-top:5px;color:#1f2937}
.tfact span{display:inline-block;background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:1px 6px;margin-right:6px;font-size:11.5px;text-transform:uppercase;letter-spacing:.3px;color:var(--mut)}
.tmore{display:inline-block;margin-top:7px;font-size:13px;font-weight:600;color:var(--brand)}
.tbtn{display:inline-block;background:var(--brand);color:#fff;font-weight:700;padding:9px 16px;border-radius:6px;font-size:14px;white-space:nowrap}
.tbtn:hover{background:#1739a8}
@media(max-width:640px){.cmp td.tl{width:60px}.cmp td.tl img{width:52px;height:52px}.cmp td.tc{width:110px}.tbtn{padding:8px 11px;font-size:13px}}
article img{max-width:100%;height:auto}
article img:not([width]){max-width:200px}
article svg,.cicon-svg{max-width:56px!important;max-height:56px!important;width:auto;height:auto;display:inline-block;vertical-align:middle}
article form{display:flex;gap:8px;max-width:480px;margin:0 0 26px}
article input[type=text],article input[type=search]{flex:1;padding:12px 15px;border:1px solid var(--line);border-radius:8px;font-size:15.5px;font-family:inherit;min-width:0}
article input[type=submit],article button[type=submit]{background:var(--brand);color:#fff;border:0;padding:12px 22px;border-radius:8px;font-weight:700;font-size:15px;cursor:pointer;white-space:nowrap}
article input[type=hidden]{display:none}
article table{max-width:100%;overflow-x:auto;display:block}
article iframe,article video{max-width:100%}
@media(max-width:640px){
  h1{font-size:25px}
  h2{font-size:20px}
  .wrap{padding:0 14px}
  article form{flex-direction:column}
  article input[type=submit]{width:100%}
  nav.main a{padding:11px 12px;font-size:14px}
  .cmp thead{display:none}
  .cmp,.cmp tbody,.cmp tr,.cmp td{display:block;width:100%}
  .cmp tr{border:1px solid var(--line);border-radius:10px;margin-bottom:12px;padding:12px}
  .cmp td{border:0;padding:6px 0;text-align:left}
  .cmp td.tl,.cmp td.tc{text-align:center}
  .cmp td.tl img{margin:0 auto}
}
/* ---- homepage ---- */
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.lede{font-size:17px;line-height:1.62;color:#374151;max-width:70ch}
.searchbox{position:relative;margin:22px 0 30px;max-width:620px}
.searchbox input{width:100%;box-sizing:border-box;font-size:16px;padding:14px 16px;
  border:2px solid var(--line);border-radius:10px;background:#fff;font-family:inherit}
.searchbox input:focus{outline:0;border-color:var(--brand);box-shadow:0 0 0 4px rgba(28,58,190,.10)}
.qres{position:absolute;z-index:30;left:0;right:0;top:calc(100% + 6px);background:#fff;
  border:1px solid var(--line);border-radius:10px;box-shadow:0 12px 28px rgba(16,24,40,.14);overflow:hidden}
.qres a{display:flex;justify-content:space-between;gap:12px;align-items:baseline;
  padding:11px 14px;text-decoration:none;border-bottom:1px solid var(--line)}
.qres a:last-child{border-bottom:0}
.qres a:hover{background:var(--bg)}
.qres a strong{font-weight:600;font-size:15px}
.qres a span{font-size:12.5px;color:var(--mut);white-space:nowrap}
.qnone{margin:0;padding:13px 14px;font-size:14px;color:var(--mut)}
.hcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:12px;margin:10px 0 30px}
.hcard{display:flex;flex-direction:column;align-items:center;text-align:center;gap:7px;
  padding:18px 12px;border:1px solid var(--line);border-radius:12px;background:#fff;text-decoration:none}
.hcard:hover{border-color:var(--brand);box-shadow:0 6px 18px rgba(16,24,40,.08)}
.hcard img,.hcard svg{width:54px!important;height:54px!important;object-fit:contain}
.hcard strong{font-size:15.5px;color:var(--ink)}
.hcard span{font-size:12.5px;color:var(--mut)}
.fgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:12px 0 30px}
.fcard{display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px;padding:14px 10px;
  border:1px solid var(--line);border-radius:12px;background:#fff;text-decoration:none}
.fcard:hover{border-color:var(--brand)}
.fcard img{width:88px;height:88px;object-fit:contain;background:#fff}
.fcard strong{font-size:14px;line-height:1.35;color:var(--ink)}
.fcard span{font-size:12px;color:var(--mut)}
ul.howto{list-style:none;padding:0;margin:10px 0 28px;display:grid;gap:10px}
ul.howto li{border:1px solid var(--line);border-left:4px solid var(--brand);border-radius:8px;
  padding:13px 16px;font-size:15px;line-height:1.6;background:#fff}
@media(max-width:640px){.hcards{grid-template-columns:repeat(2,1fr)}.fgrid{grid-template-columns:repeat(2,1fr)}}
.smlist{list-style:none;padding:0;margin:6px 0 18px;display:grid;
  grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:2px 16px}
.smlist li{font-size:14.5px;padding:3px 0}
.legal{margin-top:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,.14);
  font-size:12.5px;line-height:1.6;opacity:.72;max-width:none}
.legal p{margin:0 0 8px}
.legal a{display:inline;padding:0;text-decoration:underline}
.cta{display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap;
  background:var(--bg);border:1px solid var(--line);border-left:5px solid var(--brand);
  border-radius:10px;padding:16px 18px;margin:22px 0}
.cta strong{display:block;font-size:16.5px;margin-bottom:3px}
.cta span{font-size:13px;color:var(--mut);line-height:1.5}
.cta .btn{white-space:nowrap;flex-shrink:0}
@media(max-width:640px){.cta{flex-direction:column;align-items:stretch;text-align:center}
  .cta .btn{width:100%;box-sizing:border-box}}
.hub-intro{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin-bottom:22px;font-size:15.5px;border-left:5px solid var(--accent,var(--brand))}
.hubhead{display:flex;align-items:center;gap:14px;margin:6px 0 12px}
.hubhead h1{margin:0}
.cicon{object-fit:contain;flex:0 0 auto;display:inline-block;vertical-align:middle}
.cathead{display:flex;align-items:center;gap:11px}
.cathead a{text-decoration:none}
.grid a .cicon{display:block;margin:0 auto 8px}
a.sidecat{display:flex!important;align-items:center;gap:9px}
a.sidecat .cicon{width:22px;height:22px}
"""

def nav_html():
    li = ''.join(f'<li><a href="{section_url(s)}">{NAVNAME[s]}</a></li>' for s in TOP)
    return f'<nav class="main"><ul><li><a href="/">Home</a></li>{li}</ul></nav>'

def sidebar(active=''):
    out = ['<aside><h4>Browse categories</h4><ul>']
    for s in TOP:
        out.append(f'<li><a class="sidecat" href="{section_url(s)}">{cat_icon(s, 24)}<strong>{NAVNAME[s]}</strong></a></li>')
        for k in children[s]:
            if s == active or k == active:
                out.append(f'<li><a class="sidecat" href="{cat_url(k)}">{cat_icon(k, 26)}{catname[k]}</a></li>')
    out.append('</ul></aside>')
    return ''.join(out)

def esc(s): return html.escape(s or '', quote=True)

def fit_title(t, limit=60):
    """Google truncates around 60 characters. A title that gets cut mid-word
    loses the brand and reads as broken in the result. Trim at a separator or a
    word boundary instead, keeping the front of the title where the keywords are."""
    t = (t or '').strip()
    # Measure what the searcher sees: "&amp;" is five characters of source but
    # one character in a result snippet. Counting raw length trims good titles.
    if len(html.unescape(t)) <= limit:
        return t
    for sep in (' | ', ' \u2014 ', ' \u2013 ', ' - ', ': '):
        if sep in t:
            head = t.rsplit(sep, 1)[0].strip()
            if len(html.unescape(head)) <= limit:
                return head
    cut = t[:limit]
    return (cut.rsplit(' ', 1)[0] if ' ' in cut else cut).rstrip(' ,;:|-\u2013\u2014')

ICONS = '/wp-content/uploads/icons'
THEME = '#0183ff'          # sampled from the site's own favicon
OG_DEFAULT = ICONS + '/og-default.jpg'

def shell(title, desc, canonical, body, schema=None, extra_head='',
          robots='index,follow,max-image-preview:large', share=None, og_type='website'):
    title = fit_title(title)
    # A page with its own logo shares better than a generic card, but the platforms
    # crop to 1.91:1 and a 120px logo looks like a smudge. Only use a page image
    # where we know it is a real asset; otherwise fall back to the branded card.
    og_image, og_w, og_h = (share, 1200, 630) if share else (OG_DEFAULT, 1200, 630)
    s = f'<script type="application/ld+json">{json.dumps(schema)}</script>' if schema else ''
    return f"""<!doctype html><html lang="en-GB"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}{canonical}">
<link rel="icon" href="/wp-content/uploads/2025/08/Favicon-1.webp">
<link rel="apple-touch-icon" sizes="180x180" href="{ICONS}/icon-180.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="{THEME}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{SITE}{canonical}"><meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="Compare100"><meta property="og:locale" content="en_GB">
<meta property="og:image" content="{SITE}{og_image}">
<meta property="og:image:width" content="{og_w}"><meta property="og:image:height" content="{og_h}">
<meta property="og:image:alt" content="{esc(title)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{SITE}{og_image}">
<meta name="robots" content="{robots}">
<style>{CSS}</style>{extra_head}{s}</head><body>
<header class="top"><div class="wrap"><a class="logo" href="/"><img src="/wp-content/uploads/2025/08/Logo-450x82-1.webp" alt="Compare100.com" width="225" height="41"></a></div></header>
{nav_html()}
<div class="wrap">{body}</div>
<footer><div class="wrap">
<a href="/about-us/">About</a><a href="/contact-us/">Contact</a>
<a href="/sitemap/">Site map</a>
<a href="/privacy-policy-2/">Privacy</a><a href="/terms-and-conditions/">Terms</a>
<div class="legal">
<p><strong>Compare100.com is not a financial adviser and is not authorised or regulated by the Financial Conduct Authority.</strong> Everything on this site is general information, not personal advice. We do not know your circumstances and cannot tell you which product to buy. For regulated advice speak to an FCA-authorised adviser; for free impartial guidance, <a href="https://www.moneyhelper.org.uk/" rel="nofollow noopener" target="_blank">MoneyHelper</a> is government-backed.</p>
<p>We are paid commission by providers when a reader takes out a product through our links. It costs you nothing extra and it does not affect the order providers are listed in. We do not cover the whole of the market. Rates, cover levels and terms change without notice &mdash; each page shows the date its figures were last checked, and you should confirm them with the provider before applying.</p>
<p>Site run by Andrew King. &copy; {datetime.now().year} Compare100.com</p>
</div>
</div></footer></body></html>"""

DISCLOSURE = '<p class="disc"><strong>Affiliate disclosure:</strong> we may earn a commission if you take out a product through links on this page. It costs you nothing extra and does not influence how providers are listed.</p>'

def crumbs(items):
    parts = ['<div class="crumb">']
    parts.append(' &rsaquo; '.join(
        (f'<a href="{u}">{esc(n)}</a>' if u else esc(n)) for n, u in items))
    parts.append('</div>')
    return ''.join(parts)

def crumb_schema(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n,
                                 **({"item": SITE + u} if u else {})}
                                for i, (n, u) in enumerate(items)]}


def render_rewritten(p, pc, parent, cr, sibs, cta=None):
    """Render a page that has rewritten structured content."""
    IS_EDITORIAL = not p.get('pros') and not p.get('cons') and not p.get('verdict', '').strip()
    facts = ''.join(f'<tr><th>{esc(html.unescape(f["label"]))}</th><td>{f["value"]}</td></tr>'
                    for f in p.get('key_facts', []))
    facts = f'<table class="facts"><tbody>{facts}</tbody></table>' if facts else ''
    secs = ''.join(f'<h2>{esc(s["heading"])}</h2>{s["html"]}' for s in p.get('sections', []))
    pros = ''.join(f'<li>{esc(x)}</li>' for x in p.get('pros', []))
    cons = ''.join(f'<li>{esc(x)}</li>' for x in p.get('cons', []))
    pc_html = (f'<div class="pc"><div class="pros"><h3>Where it wins</h3><ul>{pros}</ul></div>'
               f'<div class="cons"><h3>Where it falls short</h3><ul>{cons}</ul></div></div>'
               ) if (pros or cons) else ''
    verdict = (f'<div class="verdict"><h3>Our verdict</h3><p>{p["verdict"]}</p></div>'
               if p.get('verdict', '').strip() else '')
    faqs = p.get('faqs', [])
    faq_html = ''
    if faqs:
        items = ''.join(f'<details><summary>{esc(f["q"])}</summary><p>{f["a"]}</p></details>'
                        for f in faqs)
        faq_html = f'<div class="faq"><h2>Common questions</h2>{items}</div>'
    checked = p.get('checked', datetime.now().strftime('%d %B %Y'))

    # The only call to action used to live in the sidebar, which on a phone sits
    # BELOW the whole article — a reader had to scroll past 10,000 characters to
    # reach it. Put one under the intro, where someone who is already convinced
    # can act, and one after the verdict for someone who read to the end.
    def cta_block(label):
        if not (cta and cta[0]):
            return ''
        url, btn, name = cta
        return (f'<div class="cta"><div><strong>{esc(label)}</strong>'
                f'<span>Opens {esc(name)} in a new tab. We may earn a commission '
                f'&mdash; it costs you nothing extra.</span></div>'
                f'<a class="btn" href="{url}" rel="sponsored nofollow noopener" '
                f'target="_blank">{esc(btn)}</a></div>')

    if IS_EDITORIAL:
        body = (f'<h1>{esc(p["title"])}</h1>'
                f'<div class="meta">Last updated {checked}</div>'
                + p.get('intro','') + facts + secs + faq_html)
    else:
        body = (f'<h1>{esc(p["title"])}</h1>'
                f'<div class="meta">Rates and terms checked {checked} &middot; '
                f'{catname.get(pc,"")} &middot; Compare100 editorial team</div>'
                + DISCLOSURE + p.get('intro','')
                # FAQs sit BEFORE the verdict so the page closes on the verdict and
                # its button. Questions are supporting detail; the verdict is the
                # closing argument, and it should be the last thing read.
                + cta_block('Check what you would pay') + facts + secs + pc_html
                + faq_html + verdict + cta_block('Ready to compare?')
                + f'<p class="checked">Figures were taken from each provider\'s own published '
                  f'terms on {checked}. Variable rates can change at any time &mdash; confirm the '
                  f'current rate with the provider before applying.</p>')
    return body, faqs

# DEADLINK: after everything is written, resolve or unwrap links that go nowhere.
def resolve_dead_links():
    import difflib
    real = set()
    for r, _d, fs in os.walk(OUT):
        if 'index.html' in fs:
            real.add(('/' + os.path.relpath(r, OUT).replace('\\', '/') + '/').replace('//', '/'))
    real.add('/')
    slugmap = {u.strip('/').split('/')[-1]: u for u in real if u.strip('/')}
    fixed = unwrapped = 0
    for r, _d, fs in os.walk(OUT):
        if 'index.html' not in fs: continue
        p = os.path.join(r, 'index.html')
        h = open(p, encoding='utf-8').read()
        orig = h
        def sub(m):
            nonlocal fixed, unwrapped
            href, inner = m.group(1), m.group(2)
            base = href.split('#')[0].split('?')[0].replace('&amp;', '&').split('&')[0]
            if not base.startswith('/') or base.startswith('/wp-content'): return m.group(0)
            key = base if base.endswith('/') else base + '/'
            if key in real: return m.group(0)
            tail = key.strip('/').split('/')[-1]
            if tail in slugmap:
                fixed += 1
                return f'<a href="{slugmap[tail]}">{inner}</a>'
            near = difflib.get_close_matches(tail, slugmap.keys(), n=1, cutoff=0.86)
            if near:
                fixed += 1
                return f'<a href="{slugmap[near[0]]}">{inner}</a>'
            unwrapped += 1
            return inner                      # dead: keep the words, drop the link
        h = re.sub(r'<a href="([^"]+)"[^>]*>(.*?)</a>', sub, h, flags=re.S)
        if h != orig: open(p, 'w', encoding='utf-8').write(h)
    print(f'links   {fixed} repointed, {unwrapped} dead links unwrapped')

# ---------------------------------------------------------------- write
# Some of the WordPress copy is double-encoded at source ("S&amp;amp;P" in the export,
# which renders on screen as "S&amp;P"). Collapse one layer on the way out so readers
# see "S&P" and an em dash instead of the entity spelt out.
DOUBLE_ENC = re.compile(r'&amp;(amp|lt|gt|quot|apos|nbsp|mdash|ndash|hellip|pound|euro|'
                        r'rsquo|lsquo|rdquo|ldquo|middot|times|deg|#\d{2,5});')

def write(path, content):
    content = DOUBLE_ENC.sub(r'&\1;', content)
    if path == '/':
        full = os.path.join(OUT, 'index.html')
    elif path.endswith('.html'):          # a real filename, e.g. /404.html
        full = os.path.join(OUT, path.strip('/'))
    else:                                 # a pretty URL, e.g. /admiral-car-insurance-review/
        full = os.path.join(OUT, path.strip('/'), 'index.html')
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, 'w', encoding='utf-8').write(content)
    return len(content)

# Clear the generated pages but KEEP wp-content — that is where the 415 images live,
# they are committed to the repo once and never regenerated. Wiping OUT wholesale
# would delete every image on the site on the next rebuild.
KEEP = {'wp-content'}
if os.path.isdir(OUT):
    for _e in os.listdir(OUT):
        if _e in KEEP: continue
        _p = os.path.join(OUT, _e)
        shutil.rmtree(_p) if os.path.isdir(_p) else os.remove(_p)
os.makedirs(OUT, exist_ok=True)
urls, sizes = [], []

# ---- posts
for p in posts:
    pc = primary_cat(p)
    parent = catparent.get(pc, '')
    cr = [('Home', '/')]
    if parent in TOP: cr.append((NAVNAME[parent], section_url(parent)))
    if pc: cr.append((catname.get(pc, pc), cat_url(pc)))
    cr.append((p['title'], ''))

    body_html = fix_links(''.join(paragraphs(p['content'])))
    offer = ''
    if p['offer_url'] or p['logo']:
        img = f'<img src="{p["logo"]}" alt="{esc(p["title"])} logo" width="180" height="180" loading="lazy" decoding="async">' if p['logo'] else ''
        btn = f'<a class="btn" href="{p["offer_url"]}" rel="sponsored nofollow noopener" target="_blank">{esc(p["btn"])}</a>' if p['offer_url'] else ''
        offer = f'<div class="offer">{img}{btn}</div>'

    sibs = [x for x in bycat.get(pc, []) if x['slug'] != p['slug']][:8]
    rel = ''
    if sibs:
        cards = ''.join(
            f'<a href="/{s["slug"]}/">' +
            (f'<img src="{s["logo"]}" alt="{esc(s["title"])} logo" width="180" height="88" loading="lazy" decoding="async">' if s['logo'] else '') +
            f'{esc(s["title"])}</a>' for s in sibs)
        rel = f'<div class="related"><h2>Compare other {catname.get(pc,"providers")} providers</h2><div class="grid">{cards}</div></div>'

    schema = {"@context": "https://schema.org", "@graph": [
        crumb_schema(cr),
        {"@type": "Review", "name": p['title'],
         "itemReviewed": {"@type": "Product", "name": p['title'],
                          "category": catname.get(pc, ''),
                          **({"image": SITE + p['logo']} if p['logo'] else {})},
         "author": {"@type": "Organization", "name": "Compare100"},
         "publisher": {"@type": "Organization", "name": "Compare100",
                       "url": SITE},
         "datePublished": p['date'], "dateModified": p['modified'],
         "url": f"{SITE}/{p['slug']}/"}]}

    rw = REWRITTEN.get(p['slug'])
    extra_faqs = []
    if rw:
        art, extra_faqs = render_rewritten(rw, pc, parent, cr, sibs,
                                           cta=(p['offer_url'], p['btn'], p['title']))
        p['seo_title'] = rw.get('meta_title') or p['seo_title']
        p['seo_desc']  = rw.get('meta_description') or p['seo_desc']
    else:
        art = (f'<h1>{esc(p["title"])}</h1>'
               f'<div class="meta">Last updated {p["modified"]} &middot; '
               f'{catname.get(pc,"")} &middot; Compare100 editorial team</div>'
               + DISCLOSURE + body_html)
    if extra_faqs:
        schema["@graph"].append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"],
             "acceptedAnswer": {"@type": "Answer",
                                "text": re.sub(r'<[^>]+>', '', f["a"])}} for f in extra_faqs]})
    main = (crumbs(cr) + '<div class="layout"><main><article>'
            + art + '</article>' + rel + '</main>'
            + f'<aside>{offer}{sidebar(pc)[7:]}' + '</div>')
    _pub = p.get('status', 'publish') == 'publish'
    n = write(f'/{p["slug"]}/', shell(p['seo_title'] or f'{p["title"]} | Compare100',
                                      p['seo_desc'] or f'Compare {p["title"]} with Compare100.',
                                      f'/{p["slug"]}/', main, schema,
                                      robots='index,follow,max-image-preview:large' if _pub else 'noindex,nofollow'))
    if _pub: urls.append((f'/{p["slug"]}/', p['modified']))
    sizes.append(n)

# ---- child category hubs
for parent in TOP:
    for c in children[parent]:
        lst = bycat.get(c, [])
        cr = [('Home', '/'), (NAVNAME[parent], section_url(parent)), (catname[c], '')]
        items = {"@context": "https://schema.org", "@type": "ItemList",
                 "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": x['title'],
                                      "url": f"{SITE}/{x['slug']}/"} for i, x in enumerate(lst)]}
        intro = catintro.get(c) or (f'Compare {len(lst)} {catname[c].lower()} providers side by side. '
                                    'We list cover, features and current offers so you can see the differences at a glance.')
        # ONE listing per hub. This used to render the table AND a card list of the
        # same providers underneath it — the same logos, links and buttons twice on
        # the page. Duplicate content, and on a 5-provider category it was obvious.
        # The table is the denser format and reflows to cards on mobile, so the card
        # block went and its longer description moved into the row.
        trows = ''
        for x in lst:
            rw = REWRITTEN.get(x['slug'])
            fact = ''
            src = clean(x['content'])
            if rw and rw.get('key_facts'):
                kf = rw['key_facts'][0]
                fact = f'<div class="tfact"><span>{esc(html.unescape(kf["label"]))}</span> {kf["value"]}</div>'
                src = rw.get('verdict') or rw.get('intro') or src
            elif rw and (rw.get('verdict') or rw.get('intro')):
                src = rw.get('verdict') or rw.get('intro')
            # unescape first: the source already contains &mdash; etc, and esc() below
            # would otherwise print the entity as literal text in the row
            sn = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', src))).strip()
            desc = esc(sn[:185].rsplit(' ', 1)[0]) + '&hellip;' if len(sn) > 185 else esc(sn)
            go = (f'<a class="tbtn" href="{x["offer_url"]}" rel="sponsored nofollow noopener" '
                  f'target="_blank">{esc(x["btn"])}</a>') if x['offer_url'] else ''
            logo = (f'<img src="{x["logo"]}" alt="{esc(x["title"])} logo" width="72" height="72" loading="lazy">'
                    if x['logo'] else '')
            trows += (f'<tr><td class="tl">{logo}</td>'
                      f'<td><a href="/{x["slug"]}/"><strong>{esc(x["title"])}</strong></a>'
                      f'{fact}<div class="tsub">{desc}</div>'
                      f'<a class="tmore" href="/{x["slug"]}/">Read our {esc(x["title"])} review</a></td>'
                      f'<td class="tc">{go}</td></tr>')
        table = (f'<h2>All {len(lst)} {esc(catname[c].lower())} providers compared</h2>'
                 f'<table class="cmp"><thead><tr><th></th><th>Provider</th><th></th></tr></thead>'
                 f'<tbody>{trows}</tbody></table>') if trows else ''
        # sibling categories — keeps link equity inside the section
        sibs_cat = [k for k in children[parent] if k != c and bycat.get(k)]
        sib_links = ''
        if sibs_cat:
            sib_links = ('<div class="related"><h2>Other ' + esc(NAVNAME[parent]) + ' categories</h2><div class="grid">'
                         + ''.join(f'<a href="{cat_url(k)}">{cat_icon(k, 34)}{esc(catname[k])}</a>'
                                   for k in sibs_cat) + '</div></div>')
        body = (crumbs(cr) + f'<div class="layout cat-{c}"><main>'
                f'<div class="hubhead">{cat_icon(c, 64)}<h1>Compare {esc(catname[c])}</h1></div>'
                f'<div class="hub-intro">{esc(intro)}</div>'
                + DISCLOSURE + table
                + sib_links + '</main>' + sidebar(c) + '</div>')
        n = write(cat_url(c), shell(f'Compare {catname[c]} — {len(lst)} UK Providers | Compare100',
                                    f'Compare {len(lst)} UK {catname[c].lower()} providers side by side. Features, cover and current deals.',
                                    cat_url(c), body, items))
        urls.append((cat_url(c), datetime.now().strftime('%Y-%m-%d'))); sizes.append(n)

# ---- top-level category hubs
for parent in TOP:
    cr = [('Home', '/'), (NAVNAME[parent], '')]
    blocks = ''
    for c in children[parent]:
        lst = bycat.get(c, [])
        if not lst: continue
        chips = ''.join(f'<a href="/{x["slug"]}/">' +
                        (f'<img src="{x["logo"]}" alt="{esc(x["title"])} logo" width="180" height="88" loading="lazy" decoding="async">' if x['logo'] else '') +
                        f'{esc(x["title"])}</a>' for x in lst[:8])
        blocks += (f'<h2 class="cathead">{cat_icon(c, 34)}<a href="{cat_url(c)}">{esc(catname[c])}</a> '
                   f'<span style="font-size:14px;font-weight:400;color:#5b6875">({len(lst)} providers)</span></h2>'
                   f'<div class="grid">{chips}</div>')
    body = (crumbs(cr) + f'<div class="layout cat-{parent}"><main>'
            f'<div class="hubhead">{cat_icon(parent, 64)}<h1>Compare UK {NAVNAME[parent]} Deals</h1></div>'
            f'<div class="hub-intro">Browse every {NAVNAME[parent].lower()} category on Compare100 and compare UK providers side by side.</div>'
            + blocks + '</main>' + sidebar(parent) + '</div>')
    _su = section_url(parent)
    n = write(_su, shell(f'Compare UK {NAVNAME[parent]} Deals | Compare100',
                         f'Compare UK {NAVNAME[parent].lower()} providers and deals side by side at Compare100.',
                         _su, body, crumb_schema(cr)))
    urls.append((_su, datetime.now().strftime('%Y-%m-%d'))); sizes.append(n)

# ---- static pages
REWRITTEN_PAGES = True
for p in pages:
    if p['slug'] in ('home', ''): continue  # rendered as the homepage itself
    if p['slug'] in DROP_PAGES: continue    # theme leftovers with no content
    if p['slug'] in SECTION_PAGES: continue # rendered as the section hub, further up
    cr = [('Home', '/'), (p['title'], '')]
    rwp = REWRITTEN.get(p['slug'])
    if rwp:
        art, pfaqs = render_rewritten(rwp, '', '', cr, [])
        p['seo_title'] = rwp.get('meta_title') or p['seo_title']
        p['seo_desc']  = rwp.get('meta_description') or p['seo_desc']
    else:
        art = f'<h1>{esc(p["title"])}</h1>' + fix_links(''.join(paragraphs(p['content'])))
        pfaqs = []
    _sch = crumb_schema(cr)
    if pfaqs:
        _sch = {"@context": "https://schema.org", "@graph": [_sch, {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"],
             "acceptedAnswer": {"@type": "Answer", "text": re.sub(r'<[^>]+>', '', f["a"])}} for f in pfaqs]}]}
    body = (crumbs(cr) + '<div class="layout"><main><article>' + art +
            '</article></main>' + sidebar() + '</div>')
    _pub = p.get('status', 'publish') == 'publish'
    n = write(f'/{p["slug"]}/', shell(p['seo_title'] or f'{p["title"]} | Compare100',
                                      p['seo_desc'] or p['title'], f'/{p["slug"]}/', body,
                                      _sch,
                                      robots='index,follow,max-image-preview:large' if _pub else 'noindex,nofollow'))
    if _pub: urls.append((f'/{p["slug"]}/', p['modified']))
    sizes.append(n)

# ---- homepage
tiles = ''
for s in TOP:
    sub = ''.join(f'<a href="{cat_url(c)}">{cat_icon(c, 40)}{esc(catname[c])} '
                  f'<span style="color:#5b6875;font-weight:400">({len(bycat.get(c,[]))})</span></a>'
                  for c in children[s] if bycat.get(c))
    tiles += (f'<h2 class="cathead">{cat_icon(s, 38)}<a href="{section_url(s)}">{NAVNAME[s]}</a></h2>'
              f'<div class="grid">{sub}</div>')
# The old WordPress homepage was dumped straight in here, which shipped three faults:
# a search form posting to the WordPress site that will not exist after the VPS goes,
# a "top categories" strip missing Utilities, and the same seven categories listed
# again lower down under "3 Easy Steps". Rebuilt from the site's own data instead.
_provider_total = sum(len(v) for v in bycat.values())
_cat_count = sum(1 for c in catparent if bycat.get(c))

hero_cards = ''.join(
    f'<a class="hcard" href="{section_url(s)}">{cat_icon(s, 54)}'
    f'<strong>{NAVNAME[s]}</strong>'
    f'<span>{sum(len(bycat.get(c, [])) for c in children[s])} providers &middot; '
    f'{sum(1 for c in children[s] if bycat.get(c))} categories</span></a>' for s in TOP)

# Featured strip: researched pages, insurance first — those are the ones that pay,
# so they get the homepage link equity rather than the savings pages that do not.
_FEAT_ORDER = {'insurance': 0, 'motoring': 1, 'travel': 2, 'utilities': 3,
               'mobile-phones': 4, 'shopping': 5, 'money': 6}
_feat = sorted((x for x in posts if x['slug'] in REWRITTEN and x['logo']),
               key=lambda x: (_FEAT_ORDER.get(catparent.get(primary_cat(x), ''), 9),
                              x['title']))[:8]
featured = ''
if _feat:
    featured = ('<h2>Recently researched</h2>'
                '<p class="lede">These reviews were checked against the provider&rsquo;s own published '
                'terms, with the date of that check shown on each page.</p><div class="fgrid">'
                + ''.join(f'<a class="fcard" href="/{x["slug"]}/">'
                          f'<img src="{x["logo"]}" alt="{esc(x["title"])} logo" width="110" height="110" loading="lazy">'
                          f'<strong>{esc(x["title"])}</strong>'
                          f'<span>Checked {esc(REWRITTEN[x["slug"]].get("checked", ""))}</span></a>'
                          for x in _feat) + '</div>')

_homehtml = (
    '<h1>Compare UK deals side by side</h1>'
    f'<p class="lede">Compare100 compares <strong>{_provider_total} UK providers</strong> across '
    f'<strong>{_cat_count} categories</strong> &mdash; insurance, savings and current accounts, travel, '
    'mobiles, energy, motoring and shopping. Independent, run by one person, and comparing '
    'providers since 2011.</p>'
    '<div class="searchbox"><label for="q" class="vh">Search Compare100</label>'
    '<input id="q" type="search" placeholder="Search a provider or product &mdash; try &ldquo;car insurance&rdquo;" '
    'autocomplete="off" spellcheck="false">'
    '<div id="qr" class="qres" hidden></div></div>'
    '<h2>Browse by section</h2>'
    f'<div class="hcards">{hero_cards}</div>'
    + featured +
    '<h2>How this site works, and how it is paid for</h2>'
    '<ul class="howto">'
    '<li><strong>We are paid by commission, not by you.</strong> If you take out a product through a '
    'link here, the provider may pay us. The price you pay is the same as going direct.</li>'
    '<li><strong>Commission does not decide the running order.</strong> Providers are not able to buy '
    'position, and pages that criticise a provider carry the same links as any other.</li>'
    '<li><strong>Figures come from the provider&rsquo;s own terms.</strong> Not from other comparison '
    'sites, which are frequently out of date. Each page shows when its figures were last checked.</li>'
    '<li><strong>We are not a broker or an adviser.</strong> We do not generate quotes and we do not '
    'give regulated financial advice. <a href="/about-us/">More about who runs this site</a>.</li>'
    '</ul>'
    '<h2>Before you renew anything</h2>'
    '<ul class="howto">'
    '<li><strong>Loyalty is penalised.</strong> Set a reminder 3&ndash;4 weeks before an insurance or '
    'energy renewal and compare then &mdash; that window is when the market is open to you.</li>'
    '<li><strong>The headline price is not the price.</strong> Check the excess on insurance, exit fees '
    'on savings and finance, and the contract length on mobiles and broadband.</li>'
    '<li><strong>Check what a bundle actually saves.</strong> Combining buildings and contents, or '
    'broadband and TV, sometimes discounts and sometimes just simplifies the bill.</li>'
    '</ul>')

home = ('<div class="layout"><main><article>' + _homehtml + '</article>'
        + DISCLOSURE + '<h2>Every category on Compare100</h2>' + tiles + '</main>' + sidebar() + '</div>')

# search index for the box above — built from the pages that actually exist
_index = [{'u': f'/{x["slug"]}/', 't': x['title'],
           'c': catname.get(primary_cat(x), '')} for x in posts]
_index += [{'u': cat_url(c), 't': f'Compare {catname[c]}', 'c': 'Category'}
           for c in catparent if bycat.get(c)]
open(os.path.join(OUT, 'search-index.json'), 'w', encoding='utf-8').write(
    json.dumps(_index, ensure_ascii=False, separators=(',', ':')))

SEARCH_JS = """<script>
(function(){var i=document.getElementById('q'),r=document.getElementById('qr'),d=null,t;
if(!i)return;
function load(){if(d)return Promise.resolve(d);
 return fetch('/search-index.json').then(function(x){return x.json()}).then(function(j){d=j;return j})}
function go(){var q=i.value.trim().toLowerCase();
 if(q.length<2){r.hidden=true;r.innerHTML='';return}
 load().then(function(j){var w=q.split(/\\s+/),out=[];
  for(var k=0;k<j.length&&out.length<40;k++){var s=(j[k].t+' '+j[k].c).toLowerCase(),ok=true;
   for(var m=0;m<w.length;m++){if(s.indexOf(w[m])<0){ok=false;break}}
   if(ok)out.push(j[k])}
  function rank(x){var p=x.t.toLowerCase().indexOf(q);return (p<0?50:p)-(x.c==='Category'?6:0)}
  out.sort(function(a,b){return rank(a)-rank(b)});
  r.innerHTML=out.length?out.slice(0,8).map(function(x){
    return '<a href="'+x.u+'"><strong>'+x.t+'</strong><span>'+x.c+'</span></a>'}).join('')
   :'<p class="qnone">Nothing matches &ldquo;'+i.value.replace(/[<>&]/g,'')+'&rdquo;. Try a provider name, or browse the sections below.</p>';
  r.hidden=false})}
i.addEventListener('input',function(){clearTimeout(t);t=setTimeout(go,120)});
document.addEventListener('click',function(e){if(!r.contains(e.target)&&e.target!==i)r.hidden=true});
})();
</script>"""
n = write('/', shell('Compare100.com | Compare UK Insurance, Money, Travel and Utility Deals',
                     'Compare UK providers side by side across insurance, money, travel, mobiles, utilities, motoring and shopping.',
                     '/', home + SEARCH_JS,
                     {"@context": "https://schema.org", "@type": "WebSite", "name": "Compare100",
                      "url": SITE}))
urls.append(('/', datetime.now().strftime('%Y-%m-%d'))); sizes.append(n)

# ---- 404
# Cloudflare serves this for anything that does not match a file. Without it the
# visitor gets a bare platform error page with no way back into the site.
_404 = ('<div class="layout"><main><article>'
        '<h1>That page has moved or no longer exists</h1>'
        '<p class="lede">This site was rebuilt in 2026 and a few addresses changed. '
        'Most old links redirect automatically &mdash; if you got here, this one did not.</p>'
        '<div class="searchbox"><label for="q" class="vh">Search Compare100</label>'
        '<input id="q" type="search" placeholder="Search for a provider or product" '
        'autocomplete="off" spellcheck="false">'
        '<div id="qr" class="qres" hidden></div></div>'
        '<h2>Or pick a section</h2>'
        f'<div class="hcards">{hero_cards}</div>'
        '</article></main>' + sidebar() + '</div>')
write('/404.html', shell('Page not found | Compare100',
                         'That page has moved or no longer exists. Search or browse the sections.',
                         '/404.html', _404 + SEARCH_JS, robots='noindex,follow'))

# ---- HTML sitemap
# 321 of 323 pages have no inbound link from anywhere on the web. A human-readable
# directory gives a crawler a second route into every page, and a reader a way to
# see the whole site at once.
_html_sm = ['<div class="layout"><main><article>',
            '<h1>Every page on Compare100</h1>',
            f'<p class="lede">All {len(urls)} pages, grouped by section. '
            'Everything we compare is here.</p>']
for _s in TOP:
    _html_sm.append(f'<h2 class="cathead">{cat_icon(_s, 34)}'
                    f'<a href="{section_url(_s)}">{esc(NAVNAME[_s])}</a></h2>')
    for _c in children[_s]:
        _lst = bycat.get(_c, [])
        if not _lst: continue
        _html_sm.append(f'<h3><a href="{cat_url(_c)}">{esc(catname[_c])}</a></h3><ul class="smlist">')
        for _x in sorted(_lst, key=lambda z: z['title']):
            _html_sm.append(f'<li><a href="/{_x["slug"]}/">{esc(_x["title"])}</a></li>')
        _html_sm.append('</ul>')
_other = [p for p in pages if p['slug'] not in DROP_PAGES and p['slug'] not in SECTION_PAGES
          and p['slug'] not in ('home', '')]
if _other:
    _html_sm.append('<h2>Information</h2><ul class="smlist">')
    for _p in sorted(_other, key=lambda z: z['title']):
        _html_sm.append(f'<li><a href="/{_p["slug"]}/">{esc(_p["title"])}</a></li>')
    _html_sm.append('</ul>')
_html_sm.append('</article></main>' + sidebar() + '</div>')
n = write('/sitemap/', shell('Site Map | Every Page on Compare100',
                             f'A directory of all {len(urls)} pages on Compare100, grouped by section.',
                             '/sitemap/', ''.join(_html_sm),
                             crumb_schema([('Home', '/'), ('Site map', '')])))
urls.append(('/sitemap/', datetime.now().strftime('%Y-%m-%d'))); sizes.append(n)

# ---- sitemap + robots
sm = ['<?xml version="1.0" encoding="UTF-8"?>',
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
for u, m in urls:
    sm.append(f'<url><loc>{SITE}{u}</loc><lastmod>{m}</lastmod></url>')
sm.append('</urlset>')
open(os.path.join(OUT, 'sitemap.xml'), 'w').write('\n'.join(sm))
# robots.txt — AI crawlers are deliberately ALLOWED. Bing already sends this site
# 42x the traffic Google does, and Bing feeds ChatGPT; being the source a chatbot
# cites is free referral traffic an affiliate site cannot otherwise buy. The only
# things blocked are the WordPress leftovers that should never have been crawlable.
open(os.path.join(OUT, 'robots.txt'), 'w').write(f"""User-agent: *
Allow: /
Disallow: /wp-admin/
Disallow: /wp-login.php
Disallow: /?s=
Disallow: /search/
Disallow: /_pending.json

# Answer engines and AI assistants — explicitly welcome.
User-agent: GPTBot
Allow: /
User-agent: OAI-SearchBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: Claude-Web
Allow: /
User-agent: Google-Extended
Allow: /
User-agent: Applebot-Extended
Allow: /
User-agent: CCBot
Allow: /

Sitemap: {SITE}/sitemap.xml
""")

# ---- web app manifest (stops the icon 404s and makes the site installable)
json.dump({
    "name": "Compare100.com",
    "short_name": "Compare100",
    "description": "Compare UK insurance, money, travel, mobile, utility, "
                   "motoring and shopping providers side by side.",
    "start_url": "/",
    "display": "browser",
    "background_color": "#ffffff",
    "theme_color": THEME,
    "icons": [
        {"src": f"{ICONS}/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": f"{ICONS}/icon-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "any maskable"},
    ],
}, open(os.path.join(OUT, 'site.webmanifest'), 'w', encoding='utf-8'), indent=2)

# ---- llms.txt
# An emerging convention, not a ranking factor, and no engine has confirmed using
# it. It costs a few lines and gives an answer engine a clean map instead of
# making it infer one from 407 pages of HTML.
_ll = ['# Compare100.com', '',
       '> An independent UK comparison site run by one person, Andrew King, '
       'covering insurance, money, travel, mobiles, utilities, motoring and shopping. '
       'Not authorised or regulated by the FCA; publishes information, not advice. '
       'Paid by affiliate commission, which does not affect the order providers are listed in.',
       '', '## Sections', '']
for _s in TOP:
    _n = sum(len(bycat.get(_c, [])) for _c in children[_s])
    _ll.append(f'- [{NAVNAME[_s]}]({SITE}{section_url(_s)}): {_n} providers across '
               f'{sum(1 for _c in children[_s] if bycat.get(_c))} categories')
_ll += ['', '## Categories', '']
for _s in TOP:
    for _c in children[_s]:
        if bycat.get(_c):
            _ll.append(f'- [{catname[_c]}]({SITE}{cat_url(_c)}): '
                       f'{len(bycat[_c])} providers compared')
_ll += ['', '## Notes for answer engines', '',
        '- Every page shows the date its figures were last verified against the '
        "provider's own published terms.",
        '- Reviews state real drawbacks, not only benefits.',
        '- Figures come from provider documentation, not from other comparison sites.',
        f'- Full page list: {SITE}/sitemap/', '']
open(os.path.join(OUT, 'llms.txt'), 'w', encoding='utf-8').write('\n'.join(_ll))

_lf = list(_ll[:4]) + ['', '## Every page', '']
for _s in TOP:
    _lf.append(f'### {NAVNAME[_s]}')
    for _c in children[_s]:
        if not bycat.get(_c): continue
        _lf.append(f'\n#### {catname[_c]}\n')
        for _x in sorted(bycat[_c], key=lambda z: z['title']):
            _d = (REWRITTEN.get(_x['slug'], {}).get('meta_description')
                  or _x.get('seo_desc') or '')
            _lf.append(f'- [{_x["title"]}]({SITE}/{_x["slug"]}/)'
                       + (f': {re.sub(chr(60) + "[^>]+>", "", _d)[:150]}' if _d else ''))
    _lf.append('')
open(os.path.join(OUT, 'llms-full.txt'), 'w', encoding='utf-8').write('\n'.join(_lf))
print(f'seo     robots.txt, site.webmanifest, llms.txt, llms-full.txt written')

# Hand-maintained files that are NOT generated: the 293 redirects rescuing old URLs,
# and the cache headers. They live in src/static/ so a rebuild cannot lose them.
_static = os.path.join(HERE, 'static')
if os.path.isdir(_static):
    for _f in os.listdir(_static):
        shutil.copy2(os.path.join(_static, _f), os.path.join(OUT, _f))
    print(f'static  {len(os.listdir(_static))} files copied (_redirects, _headers)')

# Compile the redirect list into the Worker's lookup table. Cloudflare's own
# _redirects handling did not fire on the deployed site, so the Worker is what
# actually performs these 301s — but _redirects stays the single source of
# truth, and this keeps the two from drifting apart.
_rfile = os.path.join(_static, '_redirects')
if os.path.isfile(_rfile):
    _map = {}
    for _l in open(_rfile, encoding='utf-8'):
        _s = _l.strip()
        if not _s or _s.startswith('#'):
            continue
        _p = _s.split()
        if len(_p) >= 2:
            _map[_p[0]] = _p[1]
    _wdir = os.path.join(os.path.dirname(HERE), 'worker')
    if os.path.isdir(_wdir):
        # Emitted as a JS module, not JSON. Importing .json needs an import
        # attribute in some runtimes and not others; a plain module has no such
        # ambiguity and cannot fail at deploy time over it.
        with open(os.path.join(_wdir, 'redirects.js'), 'w', encoding='utf-8') as _fh:
            _fh.write('// Generated by src/build.py from src/static/_redirects.\n'
                      '// Do not edit by hand - edit _redirects and rebuild.\n'
                      'export default ' + json.dumps(_map, indent=0, sort_keys=True) + ';\n')
        # A redirect pointing at a page that does not exist sends the visitor
        # from one 404 to another. Catch it here rather than in Search Console.
        _pages = {'/'}
        for _d, _, _fs in os.walk(OUT):
            if 'index.html' in _fs:
                _u = '/' + os.path.relpath(_d, OUT).replace(os.sep, '/').strip('.').lstrip('/')
                _pages.add(_u if _u.endswith('/') else _u + '/')
        _dead = [f'{k} -> {v}' for k, v in _map.items() if v not in _pages]
        if _dead:
            print(f'ERROR   {len(_dead)} redirects point at pages that do not exist:')
            for _x in _dead[:10]:
                print('        ' + _x)
            raise SystemExit(1)
        print(f'worker  {len(_map)} redirects compiled, all destinations verified')

# The image manifest has to match what the pages actually reference, every build.
_need = set()
for _dir, _, _fs in os.walk(OUT):
    for _f in _fs:
        if not _f.endswith('.html'): continue
        for _u in re.findall(r'(?:src|href)="(/wp-content/uploads/[^"]+)"',
                             open(os.path.join(_dir, _f), encoding='utf-8').read()):
            _need.add(_u.split('?')[0])
open(os.path.join(OUT, 'images-needed.txt'), 'w', encoding='utf-8').write(
    '\n'.join(sorted(_need)) + '\n')
print(f'images  {len(_need)} referenced by the built pages')

resolve_dead_links()
print(f'\nbuilt   {len(urls)} pages')
print(f'sizes   avg {sum(sizes)/len(sizes)/1024:.1f} KB   max {max(sizes)/1024:.1f} KB   (old site: 157 KB median)')
print(f'output  {OUT}')
