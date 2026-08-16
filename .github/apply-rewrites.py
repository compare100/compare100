#!/usr/bin/env python3
"""Collect finished rewrites from the live site, rebuild, and commit anything that changed.

Runs on a schedule whether or not there is new content, because site/ is committed
output and Cloudflare serves it as-is. A change to build.py alone would otherwise sit
in the repo doing nothing until the next page happened to be published - which is
exactly what happened with the schema fix on 2026-08-16.

Claude can write to Cloudflare D1 but cannot push to GitHub, so a scheduled
Claude session writes each finished, quality-gated page into D1 and this script
— running inside GitHub Actions, which *can* push — collects them.

Deliberately stdlib only. build.py has no dependencies either, so the whole
publish step needs nothing installed.

Exit 0 and change nothing when there is nothing pending. That is the normal case.
"""
import json, os, subprocess, sys, urllib.request

PENDING = "https://compare100.com/_pending.json"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTBOX = os.path.join(HERE, "src", "rewritten", "auto.json")


def fetch():
    req = urllib.request.Request(PENDING, headers={"User-Agent": "compare100-publisher"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def rebuild():
    """Regenerate site/ from build.py. The caller commits whatever changed."""
    r = subprocess.run([sys.executable, os.path.join(HERE, "src", "build.py")],
                       capture_output=True, text=True)
    print(r.stdout or "", r.stderr or "")
    if r.returncode != 0:
        print("BUILD FAILED")
        return 1
    return 0


def main():
    try:
        rows = fetch()
    except Exception as e:                      # site down, DNS, anything
        print(f"could not reach {PENDING}: {e}")
        return 0                                # never fail the run over this

    if not rows:
        print("nothing pending - rebuilding anyway in case the templates changed")
        return rebuild()

    existing = []
    if os.path.isfile(OUTBOX):
        existing = json.load(open(OUTBOX, encoding="utf-8"))
    by_slug = {p["slug"]: p for p in existing}

    added = []
    for row in rows:
        try:
            page = json.loads(row["json"])
        except Exception as e:
            print(f"skipping {row.get('slug')}: unreadable JSON ({e})")
            continue
        if not page.get("slug"):
            print("skipping a row with no slug")
            continue
        by_slug[page["slug"]] = page          # a later rewrite supersedes an earlier one
        added.append(page["slug"])

    if not added:
        print("nothing usable in the pending set")
        return 0

    # Remember exactly how the outbox looked, so a rejected page can be undone
    # precisely. Relying on `git checkout` here was wrong: the very first run
    # creates this file, git has never seen it, the checkout fails silently and
    # the rejected page stays on disk waiting to be committed.
    had_file = os.path.isfile(OUTBOX)
    before = open(OUTBOX, encoding="utf-8").read() if had_file else None

    def undo():
        if had_file:
            with open(OUTBOX, "w", encoding="utf-8") as fh:
                fh.write(before)
        elif os.path.isfile(OUTBOX):
            os.remove(OUTBOX)

    merged = sorted(by_slug.values(), key=lambda p: p["slug"])
    os.makedirs(os.path.dirname(OUTBOX), exist_ok=True)
    with open(OUTBOX, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=1, ensure_ascii=False)

    # The gate runs again here. It already ran before the page reached D1, but a
    # page is also checked against every sibling, and siblings change. Better to
    # fail the publish than to ship a page that has become a duplicate.
    gate = subprocess.run(
        [sys.executable, os.path.join(HERE, "src", "quality-gate.py"), OUTBOX],
        capture_output=True, text=True)
    print(gate.stdout or "", gate.stderr or "")
    if gate.returncode != 0:
        print("QUALITY GATE FAILED - nothing published")
        undo()
        return 1

    if rebuild() != 0:
        print("BUILD FAILED - nothing published")
        undo()
        rebuild()                       # leave site/ consistent with the repo
        return 1

    print("PUBLISHED: " + ", ".join(sorted(added)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
