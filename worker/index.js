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
