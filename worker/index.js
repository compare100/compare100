// Redirects, done in code.
//
// The _redirects file is left in place (Cloudflare may honour it), but this
// Worker is what actually guarantees them. These 293 rules carry 86,721
// impressions of old WordPress URLs into the rebuilt site, so they are not
// something to leave depending on behaviour that could not be verified.
//
// Assets are served BEFORE this script runs (run_worker_first defaults to
// false), so a request for a real page never reaches here and never costs a
// Worker invocation. Only misses land in this file.
import REDIRECTS from "./redirects.json";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Match with and without the trailing slash — old inbound links are
    // inconsistent about it and a 404 is a 404 either way.
    const path = url.pathname;
    const alt = path.endsWith("/") ? path.slice(0, -1) : path + "/";
    const target = REDIRECTS[path] || REDIRECTS[alt];

    if (target) {
      const to = new URL(target, url.origin);
      to.search = url.search;                 // keep utm_ and other tracking
      return Response.redirect(to.toString(), 301);
    }

    // No rule: hand back to the asset server, which serves 404.html.
    return env.ASSETS.fetch(request);
  },
};
