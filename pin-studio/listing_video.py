"""Listing videos for Etsy and Payhip, from the website's own data.

    python pin-studio/listing_video.py --site ../obenpaper-site --product in-mind
    python pin-studio/listing_video.py --site ../obenpaper-site --product in-mind \\
        --format landscape --pages 1,4,5,7 --out in-mind-landscape.mp4
    python pin-studio/listing_video.py --site ../obenpaper-site --product well-read --edition print
    python pin-studio/listing_video.py --site ../obenpaper-site --all --out-dir listing-videos/

The same flip-through as a video pin, square (1080×1080, default) or
landscape (1920×1080). Everything is read from an obenpaper-site checkout —
the preview pages, the product's name, sub line and collection
(lib/products.json), its colours (app/globals.css) and the page it should
lead with (lib/previews.json → lead_page) — so nothing is typed by hand.

The footer carries the "obenpaper" wordmark only: Etsy does not allow
pointing buyers to another shop, so the URL is left off. Pass --footer
obenpaper.com for a video that will only be used off Etsy.

Renders go wherever --out / --out-dir says; they are deliverables to upload,
not part of this repo (listing-videos/ is git-ignored).
"""

import argparse
import json
import os
import re
import sys

STUDIO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, STUDIO)

from video_spec import MAX_PAGES, build_spec, render  # noqa: E402


def site_data(site):
    def read(*parts):
        with open(os.path.join(site, *parts), encoding="utf-8") as fh:
            return fh.read()

    previews = json.loads(read("lib", "previews.json"))
    products = json.loads(read("lib", "products.json"))
    tokens = {m[0].lower(): m[1] for m in re.findall(r"--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", read("app", "globals.css"))}
    by_store = {}
    for c in products["collections"]:
        for p in c["products"]:
            by_store[p["slug"]] = {**p, "collection": c["name"]}
    return previews, by_store, tokens


def choose_pages(count, lead, wanted=4):
    """Page 1, the lead page, and pages spread evenly between — in page order."""
    picks = {1}
    if lead:
        picks.add(lead)
    step = count / wanted
    i = 0
    while len(picks) < min(wanted, count) and i < wanted * 3:
        picks.add(min(count, 1 + round(i * step)))
        i += 1
    return sorted(picks)[:MAX_PAGES]


def spec_for(site, slug, fmt, pages_arg, footer, edition=None):
    previews, by_store, tokens = site_data(site)
    entry = previews["products"].get(slug)
    if not entry:
        raise SystemExit(f"'{slug}' has no previews on the site (see lib/previews.json)")
    product = by_store.get(entry["store_slug"])
    if not product:
        raise SystemExit(f"'{slug}' → {entry['store_slug']} is not in lib/products.json")
    edition = edition or ("tablet" if "tablet" in entry["editions"] else "print")
    if edition not in entry["editions"]:
        raise SystemExit(f"'{slug}' has no {edition} edition")
    images = entry["editions"][edition]["images"]
    pages = [int(p) for p in pages_arg.split(",")] if pages_arg else choose_pages(len(images), entry.get("lead_page"))
    folder = (os.path.join(site, "public", "previews", previews["_flat_dir"]) if entry.get("layout") == "flat"
              else os.path.join(site, "public", "previews", slug, edition))
    paths = [os.path.join(folder, images[p - 1]) for p in pages]
    accent = {
        "main": tokens[product["accent"]],
        "dark": tokens.get(f"{product['accent']}-dark", tokens["ink"]),
        "bg": tokens.get(f"{product['accent']}-bg", tokens["cream"]),
    }
    return build_spec(fmt, accent, product["collection"], product["name"], product.get("sub", ""),
                      paths, footer, edition=edition)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", required=True, help="path to an obenpaper-site checkout")
    ap.add_argument("--product", help="readable preview slug, e.g. in-mind")
    ap.add_argument("--all", action="store_true", help="every product with previews")
    ap.add_argument("--format", default="square", choices=["square", "landscape", "pin"])
    ap.add_argument("--edition", choices=["tablet", "print"], help="default: tablet when there is one")
    ap.add_argument("--pages", help="comma-separated page numbers, e.g. 1,4,5,7 (default: chosen)")
    ap.add_argument("--footer", default="", help="right-hand footer text (default none — Etsy)")
    ap.add_argument("--out", help="output .mp4 for one product")
    ap.add_argument("--out-dir", default="listing-videos", help="folder for --all, or when --out is not given")
    args = ap.parse_args()

    if not args.product and not args.all:
        ap.error("give --product <slug> or --all")
    previews, _, _ = site_data(args.site)
    slugs = sorted(previews["products"]) if args.all else [args.product]
    failed = 0
    for slug in slugs:
        out = args.out if (args.out and not args.all) else os.path.join(args.out_dir, f"{slug}-{args.format}.mp4")
        try:
            render(spec_for(args.site, slug, args.format, None if args.all else args.pages, args.footer, args.edition), out)
            print(f"rendered {out}")
        except (ValueError, RuntimeError, FileNotFoundError) as exc:
            print(f"FAILED {slug}: {exc}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
