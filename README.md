# compare100.com

Static site. 413 pages, no database, no build step on deploy.

- `site/` — the website Netlify serves. Generated, but committed.
- `src/build.py` — regenerates `site/` from the WordPress export. Source of truth.
- `src/quality-gate.py` — content gate. Nothing ships without passing it.
- `src/rewritten/*.json` — rewritten page content, keyed by slug.

## Rebuild

```
python3 src/build.py
```

Preserves `site/wp-content/` (the images) and regenerates everything else.

## Rules enforced at build time

No absolute compare100.com asset URLs, no third-party images, no lazy-load
stubs, no compare100.co.uk references, no redirects to the homepage,
no Trustpilot.
