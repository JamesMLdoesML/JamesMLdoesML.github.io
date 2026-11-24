#!/usr/bin/env python3
"""Synchronize series labels, generate the sitemap and RSS feed, and stage public files."""
import argparse
from datetime import datetime, timezone
from email.utils import format_datetime
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://jamesmldoesml.github.io"
FEED_PATH = "blogs/rss.xml"
ATOM_NS = "http://www.w3.org/2005/Atom"


class ArticleMetadata(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.metadata = {}
        self.canonical = None
        self.feed(source.split("</head>", 1)[0])

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and "content" in attrs:
            self.metadata[attrs.get("property") or attrs.get("name")] = attrs["content"]
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")


def pages():
    return sorted([*ROOT.glob("*.html"), *ROOT.glob("blogs/*.html"),
                   *ROOT.glob("blogs/*/index.html")])


def synchronize(check=False):
    catalog = json.loads((ROOT / "data/series.json").read_text())
    # Derive secondary labels so a title is edited only once in the catalog.
    for key, values in catalog.items():
        title = values["title"]
        catalog[key] = {
            "page_title": f"{title} · James Ming Liang Ang",
            "description": f"{title}. A series by James Ming Liang Ang.",
            "taster_label": f"{title} · Taster Series",
            "citation_label": f"{title}: Taster Series",
            **values,
        }
    stale = []
    for path in pages():
        source = path.read_text()

        def replace(match):
            tag, attrs, body, close = match.groups()
            key = re.search(r'data-series="([^"]+)"', attrs)[1]
            field = re.search(r'data-field="([^"]+)"', attrs)[1]
            value = catalog[key]["title" if field == "aria_label" else field]
            if field in ("description", "aria_label"):
                attribute = "content" if field == "description" else "aria-label"
                attrs = re.sub(rf'{attribute}="[^"]*"',
                               lambda _: f'{attribute}="{html.escape(value, quote=True)}"', attrs)
                return f"<{tag}{attrs}>" + (body or "") + (close or "")
            return f"<{tag}{attrs}>{html.escape(value)}{close}"

        # Bound elements contain plain text, except article containers whose label
        # is an attribute. Match those opening tags separately to avoid nesting.
        opening = re.compile(r'<(meta|article)(\b[^>]*data-series="[^"]+"[^>]*data-field="[^"]+"[^>]*)>()()', re.S)
        updated = opening.sub(replace, source)
        text = re.compile(r'<(title|h1|a|p|span)(\b[^>]*data-series="[^"]+"[^>]*data-field="[^"]+"[^>]*)>([^<]*)(</\1>)', re.S)
        updated = text.sub(replace, updated)
        if updated != source:
            stale.append(str(path.relative_to(ROOT)))
            if not check:
                path.write_text(updated)
    if check and stale:
        raise SystemExit("Run python3 scripts/build.py to synchronize: " + ", ".join(stale))


def sitemap():
    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    tree = ET.Element(ns + "urlset")
    for path in pages():
        if 'http-equiv="refresh"' in path.read_text():
            continue
        relative = path.relative_to(ROOT).as_posix()
        route = "/" + relative
        if route.endswith("index.html"):
            route = route[:-10]
        ET.SubElement(ET.SubElement(tree, ns + "url"), ns + "loc").text = ORIGIN + route
    ET.indent(tree)
    (ROOT / "sitemap.xml").write_bytes(ET.tostring(tree, encoding="utf-8", xml_declaration=True))


def rss(check=False):
    ET.register_namespace("atom", ATOM_NS)
    tree = ET.Element("rss", version="2.0")
    channel = ET.SubElement(tree, "channel")
    ET.SubElement(channel, "title").text = "Blog · James Ming Liang Ang"
    ET.SubElement(channel, "link").text = f"{ORIGIN}/blogs/"
    ET.SubElement(channel, "description").text = "Primers and essays by James Ming Liang Ang."
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, f"{{{ATOM_NS}}}link", href=f"{ORIGIN}/{FEED_PATH}",
                  rel="self", type="application/rss+xml")

    entries = []
    for path in sorted(ROOT.glob("blogs/*/index.html")):
        article = ArticleMetadata(path.read_text(encoding="utf-8"))
        published = article.metadata.get("article:published_time")
        if published is None:
            continue
        title = article.metadata.get("og:title")
        description = article.metadata.get("description")
        if not (article.canonical and title and description):
            raise SystemExit(f"{path.relative_to(ROOT)}: RSS requires a canonical URL, og:title and description")
        try:
            date = datetime.fromisoformat(published)
        except ValueError:
            raise SystemExit(f"{path.relative_to(ROOT)}: invalid article:published_time {published!r}") from None
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        entries.append((date, article.canonical, title, description))

    for date, url, title, description in sorted(entries, reverse=True):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url
        ET.SubElement(item, "description").text = description
        ET.SubElement(item, "pubDate").text = format_datetime(date.astimezone(timezone.utc), usegmt=True)

    ET.indent(tree)
    contents = ET.tostring(tree, encoding="utf-8", xml_declaration=True) + b"\n"
    target = ROOT / FEED_PATH
    if check:
        if not target.is_file() or target.read_bytes() != contents:
            raise SystemExit(f"Run python3 scripts/build.py to regenerate {FEED_PATH}")
    else:
        target.write_bytes(contents)


def stage():
    destination = ROOT / "dist"
    # Stage into a new folder first; replace only the generated deployment copy.
    staging = ROOT / "tmp/site-build"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for path in [*pages(), ROOT / "sitemap.xml", ROOT / FEED_PATH, ROOT / ".nojekyll"]:
        target = staging / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    shutil.copytree(ROOT / "assets", staging / "assets")
    # Downloads are explicitly public, tracked resources. Never copy ignored
    # tutorial files, project notes, Python sources, or rendering caches.
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--", "blogs"], cwd=ROOT).decode().split("\0")
    public_extensions = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".mp4", ".webp", ".pdf", ".ipynb", ".zip", ".npz", ".json"}
    for name in tracked:
        if not name:
            continue
        path = ROOT / name
        if path.is_file() and path.suffix.lower() in public_extensions:
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    subprocess.run([sys.executable, str(ROOT / "scripts/check_links.py"), str(staging)], check=True)
    if destination.exists():
        shutil.rmtree(destination)
    staging.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check catalog and RSS freshness without writing files")
    args = parser.parse_args()
    synchronize(args.check)
    rss(args.check)
    if not args.check:
        sitemap()
        stage()
        print("Built dist/; series labels, sitemap and RSS feed synchronized.")
