// Redirects and 404s.
//
// These 300 rules carry 86,721 impressions of old WordPress URLs into the
// rebuilt site, so they do not get to depend on behaviour that cannot be tested.
//
// Note on wrangler.jsonc: not_found_handling is deliberately NOT set to
// "404-page". The asset router applies that BEFORE handing anything to this
// script, so with it on, every unmatched URL was answered with the 404 page and
// no redirect ever ran — which is also why Cloudflare's own _redirects file
// appeared to do nothing. This script serves the 404 page itself instead.
//
// Assets that exist are served without invoking this script at all, so normal
// page views cost nothing. Only redirects and genuine misses reach here.
import REDIRECTS from "./redirects.js";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // One canonical hostname. Every canonical tag on the site says
    // https://compare100.com, so www serving the same pages would be a second
    // copy of all 407 of them. Send www to the apex and keep the path.
    // Scoped to www. specifically so the workers.dev address still works.
    if (url.hostname.startsWith("www.")) {
      const to = new URL(url.toString());
      to.hostname = url.hostname.slice(4);
      return Response.redirect(to.toString(), 301);
    }

    // Pending rewrites, for the GitHub Action to collect.
    //
    // Claude can write to D1 but cannot push to GitHub — the sandbox proxies git
    // and refuses repositories it has not been given access to. So a scheduled
    // session writes finished pages here, and the Action in this repo picks them
    // up, rebuilds and commits. This endpoint is the handover point.
    //
    // It is public because everything in it is about to be published anyway, and
    // a secret in a public repo's workflow file is not a secret. It is marked
    // noindex and disallowed in robots.txt so it never reaches a search result.
    if (url.pathname === "/_pending.json") {
      const { results } = await env.DB.prepare(
        "SELECT slug, json FROM rewrites WHERE published = 0 ORDER BY written_at"
      ).all();
      return new Response(JSON.stringify(results ?? []), {
        headers: {
          "content-type": "application/json; charset=utf-8",
          "x-robots-tag": "noindex, nofollow",
          "cache-control": "no-store",
        },
      });
    }

    // Match with and without the trailing slash — old inbound links are
    // inconsistent about it, and a 404 is a 404 either way.
    const path = url.pathname;

    // The RSS feed lives at /feed/ because that is the URL WordPress used and the
    // one Pinterest is subscribed to. It is generated as site/feed.xml, because a
    // file with no extension gets no content type from the asset router and a feed
    // reader is entitled to reject text/html. Serve the asset here and type it
    // properly. No asset matches /feed/ itself, so this script always sees it.
    if (path === "/feed" || path === "/feed/") {
      const res = await env.ASSETS.fetch(new URL("/feed.xml", url.origin));
      if (res.ok) {
        return new Response(res.body, {
          status: 200,
          headers: {
            "content-type": "application/rss+xml; charset=utf-8",
            "cache-control": "public, max-age=1800",
          },
        });
      }
    }

    // Permanently removed 27 September 2026 after a trade mark notice from Stobbs
    // acting for Lloyds Bank plc. 410 Gone rather than 404: it tells Google and
    // Bing the page is deliberately gone and will not come back, which drops it
    // from the index faster and stops the crawlers retrying. Not a 301 — the URL
    // must stop resolving, not point somewhere else.
    const GONE = new Set([
      "/lloyds-bank-cash-isa/",
      "/lloyds-bank-club-lloyds-account/",
      "/lloyds-bank-mortgage-deals/",
      "/lloyds-bank-personal-loan/",
      // the WordPress-era dated URLs that used to 301 into them
      "/2025/04/21/lloyds-bank-cash-isa/",
      "/2025/04/21/lloyds-bank-club-lloyds-account/",
      "/2025/04/21/lloyds-bank-mortgage-deals/",
      "/2025/04/21/lloyds-bank-personal-loan/",
    ]);
    const gonePath = path.endsWith("/") ? path : path + "/";
    if (GONE.has(gonePath)) {
      return new Response(
        "<!doctype html><html lang=\"en-GB\"><head><meta charset=\"utf-8\">" +
        "<meta name=\"robots\" content=\"noindex, nofollow\">" +
        "<title>Page removed</title></head><body>" +
        "<h1>Page removed</h1><p>This page has been permanently removed.</p>" +
        "<p><a href=\"/\">Compare100 home</a></p></body></html>",
        {
          status: 410,
          headers: {
            "content-type": "text/html; charset=utf-8",
            "x-robots-tag": "noindex, nofollow",
            "cache-control": "no-store",
          },
        }
      );
    }

    const alt = path.endsWith("/") ? path.slice(0, -1) : path + "/";
    const target = REDIRECTS[path] || REDIRECTS[alt];

    if (target) {
      const to = new URL(target, url.origin);
      to.search = url.search;                  // keep utm_ and other tracking
      return Response.redirect(to.toString(), 301);
    }

    // /category/* runs this script first so a stale hub file can never shadow a
    // redirect. Anything without a rule goes back to the asset server as normal.
    const res = await env.ASSETS.fetch(request);
    if (res.status !== 404) return res;

    const page = await env.ASSETS.fetch(new URL("/404.html", url.origin));
    return new Response(page.body, {
      status: 404,
      headers: { "content-type": "text/html; charset=utf-8" },
    });
  },
};
