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
