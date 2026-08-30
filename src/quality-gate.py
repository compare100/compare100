#!/usr/bin/env python3
"""Quality gate for rewritten pages.

Nothing gets committed to the site unless it passes every check below.
These exist because the original content failed all of them: one template,
nouns swapped, no figures, 300 words, stuffed with discourse markers.

Usage:  python quality-gate.py pkg/rewritten/whatever.json
Exit 0 = passed. Exit 1 = rejected, with reasons.
"""
import json, re, sys, os, html
from collections import Counter

MIN_WORDS        = 800     # the old pages averaged 420
MAX_SIBLING_OVERLAP = 0.15 # site-wide duplication was 43%
MIN_FIGURES      = 8       # specific numbers: rates, limits, prices, dates
MIN_SECTIONS     = 3
MIN_CONS         = 3       # a review with no real criticism is advertising

# Phrases that made the old content look machine-written.
BANNED = [
    'furthermore', 'moreover', 'consequently', 'in conclusion', 'ultimately,',
    'it is important to note', 'when it comes to', 'in today', 'look no further',
    'nestled', 'delve', 'tapestry', 'testament to', 'landscape of',
    'is the right choice for your', 'your gateway to', 'revolutionis', 'revolutioniz',
    'trustpilot',
]
# Structural tells: the same heading shape reused across a cluster
BANNED_HEADING_PATTERNS = [
    r'^is .* the right choice',
    r'^why choose ',
    r'^final thoughts',
    r'^conclusion',
]

def text_of(page):
    parts = [page.get('intro', '')]
    parts += [s.get('html', '') for s in page.get('sections', [])]
    parts += [f.get('a', '') for f in page.get('faqs', [])]
    parts.append(page.get('verdict', ''))
    raw = ' '.join(parts)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', raw))).strip()

def shingles(t, n=6):
    w = t.lower().split()
    return set(' '.join(w[i:i + n]) for i in range(len(w) - n + 1))

def check(page, siblings):
    fails = []
    t = text_of(page)
    words = len(t.split())

    if words < MIN_WORDS:
        fails.append(f"only {words} words (minimum {MIN_WORDS})")

    if len(page.get('sections', [])) < MIN_SECTIONS:
        fails.append(f"only {len(page.get('sections', []))} sections (minimum {MIN_SECTIONS})")

    if len(page.get('cons', [])) < MIN_CONS and page.get('verdict', '').strip():
        fails.append(f"only {len(page.get('cons', []))} cons listed (minimum {MIN_CONS}) "
                     "- a review with no real criticism reads as advertising")

    # Specific figures: money, percentages, years, durations, and counts.
    # The count patterns were missing at first, which rejected two pages that were
    # full of hard numbers ("6,000+ dealers", "122,000+ sales", "£1.6bn") simply
    # because none of them happened to be a percentage or a date.
    figs = re.findall(
        r'(£[\d,]+(?:\.\d+)?\s?(?:bn|m|k)?'          # £1,299 / £1.6bn / £750k
        r'|\d+(?:\.\d+)?%'                            # 4.75%
        r'|\b(?:19|20)\d{2}\b'                        # 2026
        r'|\b\d+(?:\.\d+)?\s?(?:days?|months?|years?|hours?|weeks?|miles?)\b'
        r'|\b\d{1,3}(?:,\d{3})+\+?\b'                 # 6,000+ / 122,000
        r'|\b\d+(?:\.\d+)?\s?(?:bn|m|k)\b'            # 2.5m / 1.1bn
        r'|\b\d+\s?(?:in|of)\s?\d+\b)', t)            # 1 in 10
    is_editorial = not page.get('pros') and not page.get('verdict', '').strip()
    if not is_editorial and len(figs) < MIN_FIGURES:
        fails.append(f"only {len(figs)} specific figures (minimum {MIN_FIGURES}) "
                     "- generic prose without numbers is what Google rejected before")

    low = t.lower()
    hits = [b for b in BANNED if b in low]
    if hits:
        fails.append(f"banned phrases present: {', '.join(hits[:6])}")

    for s in page.get('sections', []):
        hd = s.get('heading', '').lower().strip()
        for pat in BANNED_HEADING_PATTERNS:
            if re.search(pat, hd):
                fails.append(f"formulaic heading: '{s.get('heading')}'")

    # duplication against every sibling already on the site
    mine = shingles(t)
    worst, worst_slug = 0.0, ''
    for slug, stext in siblings.items():
        if slug == page['slug']:
            continue
        sh = shingles(stext)
        if not sh or not mine:
            continue
        ov = len(mine & sh) / min(len(mine), len(sh))
        if ov > worst:
            worst, worst_slug = ov, slug
    if worst > MAX_SIBLING_OVERLAP:
        fails.append(f"{worst*100:.0f}% phrase overlap with /{worst_slug}/ "
                     f"(maximum {MAX_SIBLING_OVERLAP*100:.0f}%)")

    # required fields
    for f in ('meta_title', 'meta_description', 'intro', 'verdict'):
        if f == 'verdict' and not page.get('pros'):
            continue                      # editorial pages have no verdict
        if not (page.get(f) or '').strip():
            fails.append(f"missing {f}")
    mt = page.get('meta_title', '')
    if len(mt) > 62:
        fails.append(f"meta_title {len(mt)} chars (max 62)")
    md = page.get('meta_description', '')
    if len(md) > 158:
        fails.append(f"meta_description {len(md)} chars (max 158)")
    # Bing flags a description under about 100 characters as an error and the
    # snippet has room for far more, so a short one is wasted space in the one
    # place a searcher decides whether to click. 120 is the floor.
    if md and len(md) < 120:
        fails.append(f"meta_description {len(md)} chars (min 120)")

    return words, len(figs), round(worst * 100), fails

def load_siblings(exclude_file):
    out = {}
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rewritten')
    for f in os.listdir(d):
        if not f.endswith('.json') or f == os.path.basename(exclude_file):
            continue
        for p in json.load(open(os.path.join(d, f), encoding='utf-8')):
            out[p['slug']] = text_of(p)
    return out

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    path = sys.argv[1]
    pages = json.load(open(path, encoding='utf-8'))
    sib = load_siblings(path)
    for p in pages:                       # pages in the same file check against each other too
        sib.setdefault(p['slug'], text_of(p))

    failed = 0
    print(f"{'page':<44}{'words':>7}{'figs':>6}{'dup%':>6}  result")
    print('-' * 78)
    for p in pages:
        w, f, d, fails = check(p, sib)
        if fails:
            failed += 1
            print(f"{p['slug'][:42]:<44}{w:>7}{f:>6}{d:>5}%  REJECTED")
            for x in fails:
                print(f"{'':<44}      - {x}")
        else:
            print(f"{p['slug'][:42]:<44}{w:>7}{f:>6}{d:>5}%  passed")
    print('-' * 78)
    print(f"{len(pages) - failed} passed, {failed} rejected")
    sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
