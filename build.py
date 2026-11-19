#!/usr/bin/env python3
"""OpenDeadlock's web page: a landing page, What's new and the full changelog.

    python3 build.py [--repo DIR] [--out DIR] [--version X.Y.Z]

Reads an OpenDeadlock checkout (--repo, default ../opendeadlock: its CHANGELOG.md,
screenshots, icon and tags) and writes DIR (default `dist/`, gitignored) from
`src/index.html` (the landing page, a template), `src/style.css` and CHANGELOG.md:

- index.html     the landing page; the download button names the last tag (`git describe`)
- whatsnew.html  every change a player notices, two or three sentences each, from the
                 entry's "After:" part, with its before/after screenshots
- changelog.html CHANGELOG.md in full, grouped by release (the first tag whose
                 CHANGELOG.md names the entry) rather than by day; What's new tags each
                 change with its release too
- games.html     the public relay's games, live (fetched by the page from RELAY_GAMES)
- downloads.html every platform's zip and the APK of the last release, from this
                 repository's release of it (DL_URL; sizes and date from gh)
- faq.html       the FAQ, from src/faq.html (a template, as the landing page)

with the screenshots it shows (docs/readme/, docs/changelog/) and the icon copied beside
them, so the folder can be served as it is (`python3 -m http.server -d dist`).
Plain Python, nothing to install; the colours and type are the modern UI's
(../modern-ui/ui.css).
"""
import argparse
import functools
import html
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "opendeadlock")  # the checkout; --repo sets it
REPO_URL = "https://github.com/galius-iv/opendeadlock"
# the players' Discord server: finding games, questions, bugs
DISCORD_URL = "https://discord.gg/XdEABUBC6Z"
# The downloads: the release's files again, as a release of this repository, which is
# public (the OpenDeadlock repository is private, so its releases' links work only for its
# members). The page links only here for downloads.
DL_URL = "https://github.com/galius-iv/galius-iv.github.io"
# where the pages are served: link previews and the sitemap need absolute addresses
SITE_URL = "https://galius-iv.github.io/"
# each page's file and the sentence search engines and link previews show for it
PAGES = {
    "home": ("index.html", "Deadlock 2 (1998) rebuilt from its own code: the same game, native "
             "on Windows, macOS, Linux and Android, in HD, with a modern interface, network play "
             "that works and the original's bugs fixed. Bring your own copy from GOG or Steam."),
    "downloads": ("downloads.html", "Download OpenDeadlock for Windows, macOS, Linux or Android. "
                  "You need your own copy of Deadlock 2."),
    "new": ("whatsnew.html", "Every change a player notices in OpenDeadlock against the original "
            "Deadlock 2: bug fixes, new features and quality of life, with screenshots."),
    "log": ("changelog.html", "OpenDeadlock's full changelog, by release: every change against "
            "the original Deadlock 2 and how it was checked."),
    "games": ("games.html", "OpenDeadlock's network games on the public relay, live: games "
              "waiting for players, games under way, and how to join."),
    "faq": ("faq.html", "Questions about OpenDeadlock: what you need, installing, network play, "
            "saves and reporting a bug."),
}
# The public relay (galius-iv/relay): its /games, JSON open to any page (CORS *), counts the
# games and names those their hosts listed (net_public=1); games.html fetches it.
RELAY_GAMES = "https://opendeadlock-relay.fly.dev/games"
# the relay's uptime, watched by UptimeRobot (its page refuses to be framed: a link)
RELAY_STATUS = "https://stats.uptimerobot.com/OMP1tX2SSi"
# UptimeRobot's monitor of the relay (its /healthz every 5 min): the monitor-specific key,
# read-only and for this one monitor, so it may be public. Shields draws the Games badges.
UPTIME_KEY = "m804709281-1c2aa9d9648118257c6ecd63"
UPTIME_BADGE = "https://img.shields.io/uptimerobot/%s/" + UPTIME_KEY + "?style=flat-square&amp;label=%s"

KINDS = [  # (key, label), in the filter's order
    ("feature", "Features"),
    ("qol", "QoL"),
    ("game", "Bug fixes"),
    ("port", "Port fixes"),
]

DOMAINS = [  # (key, label): where in the game a change is, CHANGELOG.md's [domain] after the
    ("battle", "Battle"),     # kind; What's new's sidebar, in this order. The keys are the
    ("armies", "Armies"),     # changelog header's list (its check_docs.py refuses others).
    ("ai", "AI"),
    ("colony", "Colony"),
    ("map", "World map"),
    ("empire", "Empire"),
    ("scenarios", "Scenarios"),
    ("multiplayer", "Multiplayer"),
    ("saves", "Saves"),
    ("interface", "Interface"),
    ("mobile", "Mobile"),
    ("system", "System"),
]

# The settings and platform changes that are features (a new way to play or a new
# platform); the rest of them are quality of life. By title, chosen by hand.
FEATURE = re.compile(r"modern UI|Android|Native Linux|Hotseat: several|\brelay\b|"
                     r"HD terrain|3D world map|zoom|\bfog\b|Realm borders|Health bars|"
                     r"A console|Keys can be remapped|IPv6|another language|Sharp on Retina|"
                     r"Alt\+Enter")


# ---------------------------------------------------------------- markdown

def inline(text):
    """CHANGELOG.md's inline markdown: code, bold, italics, links."""
    codes = []

    def keep(m):
        codes.append("<code>%s</code>" % html.escape(m.group(1)))
        return "\0%d\0" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", keep, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)

    def link(m):
        label, url = m.group(1), m.group(2)
        if not re.match(r"[a-z]+:", url) and not url.startswith("#"):
            url = "%s/blob/main/%s" % (REPO_URL, url)
        return '<a href="%s">%s</a>' % (html.escape(url), label)

    text = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    return re.sub(r"\0(\d+)\0", lambda m: codes[int(m.group(1))], text)


IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


def figure(alt, src):
    src = img_path(src)
    return ('<figure><a href="%s"><img src="%s" alt="%s" loading="lazy"></a>'
            '<figcaption>%s</figcaption></figure>'
            % (src, src, html.escape(alt), inline(alt)))


def img_path(src):
    return "img/" + os.path.basename(src)


def png_size(src):
    """A PNG's width and height, from its header; None if it is not found."""
    for p in (src, os.path.join("docs", "changelog", os.path.basename(src))):
        path = os.path.join(ROOT, p)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                head = f.read(24)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    return None


def before_after(pics):
    """The entry's before/after pair for the slider, [(caption, src)] -> (before, after) or
    None: a `X-before.png` with `X-after.png`, or else with the first other `X-*.png` (the
    zoomed views: `colonyzoom-in`); both of one size, or the slider would not line up."""
    for b in [p for p in pics if os.path.basename(p[1]).endswith("-before.png")]:
        prefix = os.path.basename(b[1])[:-len("before.png")]
        others = [p for p in pics if p is not b and os.path.basename(p[1]).startswith(prefix)]
        others.sort(key=lambda p: not os.path.basename(p[1]).endswith("-after.png"))
        for a in others:
            size = png_size(b[1])
            if size and size == png_size(a[1]):
                return b, a
    return None


def compare(pair, small=False):
    """A before/after slider (compare.js): the after picture, the before over it clipped
    at the handle; a range input across it moves the handle, by mouse, touch or keys."""
    (bcap, bsrc), (acap, asrc) = pair
    w, h = png_size(bsrc)

    def label(cap, default):
        return html.escape(cap if 0 < len(cap) <= 40 else default)

    return ('<div class="compare%s" style="aspect-ratio:%d/%d">'
            '<img src="%s" alt="%s" loading="lazy">'
            '<div class="cmp-before"><img src="%s" alt="%s" loading="lazy"></div>'
            '<i class="cmp-handle"></i>'
            '<span class="cmp-label l">%s</span><span class="cmp-label r">%s</span>'
            '<input type="range" min="0" max="100" value="50" aria-label="Before and after">'
            '</div>' % (" small" if small else "", w, h, img_path(asrc), html.escape(acap),
                        img_path(bsrc), html.escape(bcap),
                        label(bcap, "Before"), label(acap, "After")))


def blocks(lines):
    """Split lines into blocks: ('p', text) ('ul', [items]) ('table', rows) ('img', [(alt, src)])."""
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            out.append(("table", rows))
            continue
        if re.match(r"[-*] ", line):
            items = []
            while i < len(lines) and lines[i].strip():
                if re.match(r"[-*] ", lines[i]):
                    items.append(lines[i][2:].strip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append(("ul", items))
            continue
        para = []
        while (i < len(lines) and lines[i].strip() and not lines[i].startswith("|")
               and not (para and re.match(r"[-*] ", lines[i]))):
            para.append(lines[i].strip())
            i += 1
        text = " ".join(para)
        imgs = IMAGE.findall(text)
        if imgs and not IMAGE.sub("", text).strip():
            out.append(("img", imgs))
        else:
            out.append(("p", text))
    return out


def render(blks, pair=None):
    """Blocks to HTML; a before/after `pair` becomes a slider where its pictures were."""
    parts = []
    skip = {pair[0][1], pair[1][1]} if pair else set()
    placed = [False]

    def shots(figs):
        figs = [(a, s) for a, s in figs
                if s not in skip and os.path.basename(s) not in HIDDEN_PICTURES]
        out = ""
        if skip and not placed[0]:
            out += compare(pair)
            placed[0] = True
        if figs:
            out += '<div class="shots">%s</div>' % "".join(figure(a, s) for a, s in figs)
        return out

    for kind, val in blks:
        if kind == "p":
            parts.append("<p>%s</p>" % inline(val))
        elif kind == "ul":
            parts.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline(x) for x in val))
        elif kind == "img":
            parts.append(shots(val))
        elif kind == "table":
            if any(IMAGE.search(c) for r in val for c in r):
                # a table of screenshots: its first row captions the pictures below
                caps, pics = val[0], [IMAGE.search(c) for r in val[1:] for c in r]
                parts.append(shots([(caps[k] if k < len(caps) else m.group(1), m.group(2))
                                    for k, m in enumerate(p for p in pics if p)]))
            else:
                head, *body = val
                parts.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
                    "".join("<th>%s</th>" % inline(c) for c in head),
                    "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r)
                            for r in body)))
    return "\n".join(parts)


# ---------------------------------------------------------------- the changelog

def parse_changelog():
    """[(date, [entry])], each entry a dict: title, kind, key, domains, slug, lines."""
    text = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    intro, *days = re.split(r"^## ", text, flags=re.M)
    out, slugs = [], set()
    for day in days:
        head, _, rest = day.partition("\n")
        chunks = re.split(r"^### ", rest, flags=re.M)
        lead, entries = chunks[0], []
        for chunk in chunks[1:]:
            title, _, body = chunk.partition("\n")
            kind = ""
            if " -- " in title:
                title, kind = title.rsplit(" -- ", 1)
            domains = []
            m = re.search(r"\s*\[([a-z, ]+)\]\s*$", kind)
            if m:
                kind, domains = kind[:m.start()], [d.strip() for d in m.group(1).split(",")]
            if not domains:  # an older checkout: What's new would be one ungrouped list
                sys.exit("build.py: CHANGELOG.md's %r has no [domain] after its kind; is %s "
                         "up to date (git pull)?" % (title, ROOT))
            unknown = set(domains) - set(dict(DOMAINS))
            if unknown:
                sys.exit("build.py: CHANGELOG.md's %r names domains it does not know: %s"
                         % (title, ", ".join(sorted(unknown))))
            slug = base = re.sub(r"[^a-z0-9]+", "-", re.sub(r"`", "", title.lower())).strip("-")[:60]
            n = 2
            while slug in slugs:
                slug, n = "%s-%d" % (base, n), n + 1
            slugs.add(slug)
            key = kind_key(kind)
            if key in ("setting", "platform"):
                key = "feature" if FEATURE.search(title) else "qol"
            entries.append({"title": title.strip(), "kind": kind.strip(),
                            "key": key, "domains": domains, "slug": slug,
                            "lines": body.rstrip().split("\n")})
        out.append((head.strip(), lead.strip(), entries))
    return intro, out


def by_version(days):
    """The changelog's days regrouped by release: [(version, lead, [entry])], newest first.
    An entry belongs to the first tag whose CHANGELOG.md names it (by title); one no tag
    names yet is "Unreleased". Each entry gets its "version"."""
    try:
        tags = subprocess.check_output(["git", "tag", "--list", "v*", "--sort=v:refname"],
                                       cwd=ROOT, text=True).split()
    except (subprocess.CalledProcessError, OSError):
        tags = []
    first = {}
    for tag in tags:
        text = subprocess.check_output(["git", "show", tag + ":CHANGELOG.md"], cwd=ROOT, text=True)
        for title in re.findall(r"^### (.*)$", text, flags=re.M):
            first.setdefault(title.rsplit(" -- ", 1)[0].strip(), tag)
    groups = {}
    for _, lead, entries in days:
        for e in entries:
            e["version"] = first.get(e["title"], "Unreleased")
            groups.setdefault(e["version"], ([], []))[1].append(e)
        if lead:  # only "Before this log": the start, before the first release
            groups.setdefault(tags[0] if tags else "Unreleased", ([], []))[0].append(lead)
    order = ["Unreleased"] + tags[::-1]
    return [(v, "\n\n".join(groups[v][0]), groups[v][1]) for v in order if v in groups]


def kind_key(kind):
    first = kind.split(",")[0].split("(")[0].strip().lower()
    if first.startswith("port") or first == "documentation":
        return "port"
    if first.startswith("game"):
        return "game"
    if first.startswith("setting"):
        return "setting"
    return "platform"


def noticeable(entry):
    """False for the changes What's new leaves out: the port's own bugs fixed, and those
    nobody sees in play (unreachable code, a hostile peer ...)."""
    if entry["key"] == "port":
        return False
    note = entry["kind"].lower()
    return not re.search(r"\bno (visible |audible )?effect|unreachable|none in play|bad peer|"
                         r"no visible|no audible|normal play unchanged|documentation", note)


SENTENCE = re.compile(r"(?<=[.!?])[\")]?\s+(?=[A-Z\"(`])")


def summary(entry):
    """Two or three sentences: what the player gets, from the entry's "After:" part."""
    prose = []
    for kind, val in blocks(entry["lines"]):
        if kind != "p":
            continue
        if re.match(r"(Checked|How|Not yet|Played|Reproduced)\b", val):
            break
        prose.append(val)
    text = " ".join(prose)
    text = re.sub(r"^((#\d+|`[0-9a-f]{7,12}`)(, (#\d+|`[0-9a-f]{7,12}`))*)[^.]*?\.\s+", "", text)
    text = re.sub(r"^#\d+, (`\w+`)? ?\([^)]*\)\.\s+", "", text)
    m = re.search(r"\bAfter(, ([^:]+))?:\s*", text)
    if m:
        rest = text[m.end():]
        text = (m.group(2)[0].upper() + m.group(2)[1:] + ": " + rest) if m.group(2) else rest
    text = re.split(r"\s+Checked( by)?[: ]", text)[0]
    sentences = [s.strip() for s in SENTENCE.split(text) if s.strip()]
    keep, size = [], 0
    for s in sentences:
        if keep and (len(keep) == 3 or size + len(s) > 300):
            break
        keep.append(s)
        size += len(s)
    text = " ".join(keep)
    if text:
        text = text[0].upper() + text[1:]
    return text


def short(entry, limit=150):
    """One short sentence for What's new: the summary's first, its asides in brackets
    dropped, cut at a clause (or a word) when it is still long."""
    text = summary(entry)
    text = re.sub(r"\s*\([^()]*\)", "", text)
    text = (SENTENCE.split(text) or [""])[0].strip()
    if len(text) > limit:
        cut = max(text.rfind(c, 0, limit) for c in ("; ", ": ", ", ", " -- "))
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        text = text[:cut].rstrip(" ,;:-")
    text = text.rstrip(".")
    return text + "." if text else ""


def plain_title(entry):
    """The title without its setting's name in brackets: for the sidebar."""
    return re.sub(r"\s*\(`[^`]*`[^)]*\)", "", entry["title"]).strip()


# Screenshots the site does not show: frames caught halfway through an animation, which
# read as noise out of the game (zoomswitch's way in and out).
HIDDEN_PICTURES = {"zoomswitch-in.png", "zoomswitch-out.png"}


def images(entry):
    """The entry's screenshots: [(caption, src)], less HIDDEN_PICTURES."""
    return [p for p in _images(entry) if os.path.basename(p[1]) not in HIDDEN_PICTURES]


def _images(entry):
    out = []
    for kind, val in blocks(entry["lines"]):
        if kind == "img":
            out += val
        elif kind == "table":
            caps = val[0]
            pics = [IMAGE.search(c) for r in val[1:] for c in r]
            pics = [p for p in pics if p]
            if pics:
                out += [(caps[k] if k < len(caps) else p.group(1), p.group(2))
                        for k, p in enumerate(pics)]
        elif kind == "p":
            out += IMAGE.findall(val)
    return out


# ---------------------------------------------------------------- pages

def page(title, active, body, version, extra_head=""):
    nav = "".join('<a href="%s"%s>%s</a>' % (href, ' class="on"' if key == active else "", label)
                  for key, href, label in [("downloads", "downloads.html", "Downloads"),
                                           ("new", "whatsnew.html", "What's new"),
                                           ("log", "changelog.html", "Changelog"),
                                           ("games", "games.html", "Games"),
                                           ("faq", "faq.html", "FAQ")])
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
<link rel="canonical" href="%(url)s">
<meta property="og:type" content="website">
<meta property="og:site_name" content="OpenDeadlock">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(url)s">
<meta property="og:image" content="%(site)simg/og.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="OpenDeadlock: Deadlock 2's world map in the modern interface">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#07090d">
<link rel="icon" href="img/opendeadlock.png">
<link rel="apple-touch-icon" href="img/opendeadlock.png">
<link rel="stylesheet" href="style.css">%(extra)s
</head><body>
<header class="top"><div class="wrap">
  <a class="brand" href="index.html"><img src="img/opendeadlock.png" alt="">OpenDeadlock</a>
  <button class="menu" aria-label="Menu" aria-expanded="false" aria-controls="nav"><i></i><i></i><i></i></button>
  <nav id="nav">%(nav)s<a class="ext" href="%(discord)s">Discord<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3H3v10h10v-3M9 2h5v5M14 2 7 9" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></a><a class="ext" href="%(repo)s">GitHub<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3H3v10h10v-3M9 2h5v5M14 2 7 9" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></a></nav>
</div></header>
<script>
// the phone's menu: the button opens the top bar's links below it; a link, Esc or a click
// outside closes them
(() => {
  const top = document.querySelector('.top'), btn = top.querySelector('.menu');
  const set = (open) => { top.classList.toggle('open', open); btn.setAttribute('aria-expanded', open); };
  btn.addEventListener('click', () => set(!top.classList.contains('open')));
  top.querySelectorAll('nav a').forEach((a) => a.addEventListener('click', () => set(false)));
  document.addEventListener('click', (e) => { if (!top.contains(e.target)) set(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') set(false); });
})();
</script>
%(body)s
<footer><div class="wrap">
  <p><strong>Unofficial.</strong> Not affiliated with or endorsed by the rights holder of
  Deadlock 2. No game data is included: you need your own copy of Deadlock 2 (<a
  href="https://www.gog.com/game/deadlock_2_shrine_wars">GOG</a> or <a
  href="https://store.steampowered.com/app/328450">Steam</a>).</p>
  <p class="dim">OpenDeadlock v%(version)s &middot; <a href="%(discord)s">Discord</a> &middot; <a href="%(repo)s">%(repo_short)s</a></p>
</div></footer>
<script src="lightbox.js"></script>
<script src="compare.js"></script>
</body></html>
""" % {"title": html.escape(title), "desc": html.escape(PAGES[active][1]),
       "url": SITE_URL + ("" if active == "home" else PAGES[active][0]), "site": SITE_URL,
       "nav": nav, "body": body, "version": version, "repo": REPO_URL, "discord": DISCORD_URL,
       "repo_short": REPO_URL.split("//")[1], "extra": extra_head}


def entry_title(entry):
    return inline(entry["title"])


def domain_chips(entry):
    return "".join('<span class="chip d-%s">%s</span>' % (d, dict(DOMAINS)[d])
                   for d in entry["domains"])


def whatsnew(days, version, used):
    """Every change a player notices, one short sentence each, under Features, QoL and Bug
    fixes, newest first in each; the sidebar shows one domain's (Battle, Colony ...) or all.
    The port's own bugs fixed are only in the changelog (noticeable)."""
    items = [(e["version"], e) for _, _, entries in days for e in entries if noticeable(e)]
    counts = {}
    for _, e in items:
        for d in e["domains"]:
            counts[d] = counts.get(d, 0) + 1
    side = ['<a class="filt k-all on" href="#all" data-k="all">All<span>%d</span></a>' % len(items)]
    side += ['<a class="filt" href="#%s" data-k="%s">%s<span>%d</span></a>'
             % (k, k, label, counts[k]) for k, label in DOMAINS if counts.get(k)]
    cards = {}
    for ver, e in items:
        pics = images(e)
        pair = before_after(pics)
        used.update(src for _, src in pics)
        pics = pics[:2]
        shots = ""
        if pair:
            shots = compare(pair, small=True)
        elif pics:
            shots = '<div class="thumbs">%s</div>' % "".join(
                '<a href="%s"><img src="%s" alt="%s" loading="lazy"></a>'
                % (img_path(src), img_path(src), html.escape(alt)) for alt, src in pics)
        cards.setdefault(e["key"], []).append(
            '<article class="item" id="%s" data-d="%s"><div class="item-text"><h3>%s</h3>'
            '<p>%s <a class="more" href="changelog.html#%s">More</a></p>'
            '<span class="meta">%s<span class="date">%s</span></span></div>%s</article>'
            % (e["slug"], " ".join(e["domains"]), inline(plain_title(e)), inline(short(e)),
               e["slug"], domain_chips(e), html.escape(ver), shots))
    groups = ['<section class="group k-%s"><h2>%s</h2>%s</section>'
              % (k, label, "\n".join(cards[k])) for k, label in KINDS if cards.get(k)]
    body = """<main class="wrap doc with-toc">
<aside class="toc side">%s</aside>
<div>
<h1>What's new</h1>
<p class="lead">What plays differently from the original Deadlock 2, by where in the game,
newest first. The <a href="changelog.html">full changelog</a> has the details, and the
port's own bugs fixed.</p>
<div class="items">%s</div>
</div>
</main>
<script>
// the sidebar's filters: All, or one domain alone, each under Features, QoL and Bug fixes
// (a kind with none of the domain's hidden); the address keeps it (#battle), and an
// address naming a change (#its-slug) shows all
const filts = document.querySelectorAll('.filt'), items = document.querySelectorAll('.item');
function show(k) {
  if (![...filts].some(f => f.dataset.k === k)) k = 'all';
  filts.forEach(f => f.classList.toggle('on', f.dataset.k === k));
  items.forEach(i => i.hidden = k !== 'all' && !i.dataset.d.split(' ').includes(k));
  document.querySelectorAll('.group').forEach(g => g.hidden = !g.querySelector('.item:not([hidden])'));
}
filts.forEach(f => f.addEventListener('click', e => {
  e.preventDefault();
  history.replaceState(null, '', f.dataset.k === 'all' ? location.pathname : '#' + f.dataset.k);
  show(f.dataset.k);
  window.scrollTo(0, 0);
}));
show(location.hash.slice(1));
</script>""" % ("".join(side), "\n".join(groups))
    return page("What's new - OpenDeadlock", "new", body, version)


def changelog(intro, days, version, used):
    toc, parts = [], []
    for ver, lead, entries in days:
        anchor = re.sub(r"[^a-z0-9]+", "-", ver.lower()).strip("-")
        toc.append('<a href="#%s">%s</a>' % (anchor, html.escape(ver)))
        sec = ['<h2 id="%s">%s</h2>' % (anchor, html.escape(ver))]
        for e in entries:
            used.update(src for _, src in images(e))
            chip = '<span class="chip k-%s">%s</span>' % (e["key"], html.escape(e["kind"] or "change"))
            sec.append('<article id="%s" class="entry"><div class="card-head">%s%s'
                       '<h3><a href="#%s">%s</a></h3></div>%s</article>'
                       % (e["slug"], chip, domain_chips(e), e["slug"], entry_title(e),
                          render(blocks(e["lines"]), before_after(images(e)))))
        if lead:  # what the first steps changed, before the log began: the oldest, so last
            sec.append('<article id="before" class="entry"><div class="card-head">'
                       '<h3><a href="#before">Before this log</a></h3></div>%s</article>'
                       % render(blocks(lead.split("\n"))))
        parts.append("<section>%s</section>" % "\n".join(sec))
    intro_body = re.sub(r"^# .*\n", "", intro).strip()
    body = """<main class="wrap doc with-toc">
<aside class="toc"><div class="section-title">Versions</div>%s</aside>
<div>
<h1>Changelog</h1>
<div class="intro">%s</div>
%s
</div>
</main>""" % ("".join(toc), render(blocks(intro_body.split("\n"))), "\n".join(parts))
    return page("Changelog - OpenDeadlock", "log", body, version)


# The release's zips: (platform, its zip's tail, what it runs on). From the release notes
# release.py writes (OpenDeadlock's tools/release.py).
PLATFORMS = [
    ("Windows", "windows-x64", "64-bit Windows"),
    ("Windows", "windows-x86", "32-bit build: 32-bit or 64-bit Windows"),
    ("macOS", "macos-arm64", "macOS 26 or later, Apple silicon. Not notarized: once, in its folder, "
                             "<code>xattr -dr com.apple.quarantine .</code>"),
    ("Linux", "linux-x86_64", "x86_64, glibc 2.28 or later (2018 on); SDL3 is in the zip. No folder "
                              "dialog: its files in the Deadlock 2 folder, GOG's installer in its folder, or "
                              "<code>gamedir=</code> in <code>opendeadlock.ini</code>"),
    ("Linux", "linux-arm64", "arm64, glibc 2.28 or later; SDL3 is in the zip. No folder "
                             "dialog: its files in the Deadlock 2 folder, GOG's installer in its folder, or "
                             "<code>gamedir=</code> in <code>opendeadlock.ini</code>"),
]


@functools.lru_cache(None)
def release_info(version):
    """The release's date and its files' sizes, from GitHub (gh: the downloads' release,
    DL_URL's); ({}, None) when gh cannot say, and the page goes without them."""
    try:
        out = subprocess.check_output(
            ["gh", "release", "view", "v" + version, "-R", DL_URL.split("github.com/")[1],
             "--json", "publishedAt,assets"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
        data = json.loads(out)
        return {a["name"]: a["size"] for a in data["assets"]}, data["publishedAt"][:10]
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError):
        return {}, None


def downloads(version):
    """Every platform's zip of the last release, with what it needs, and the checksums."""
    sizes, date = release_info(version)
    base = "%s/releases/download/v%s/" % (DL_URL, version)
    rows = []
    for name, tail, needs in PLATFORMS:
        zip_name = "opendeadlock-%s-%s.zip" % (version, tail)
        size = sizes.get(zip_name)
        rows.append(
            '<div class="dl-row"><div class="dl-what"><h3>%s <span>%s</span></h3><p>%s</p></div>'
            '<a class="btn primary" href="%s%s">Download%s</a></div>'
            % (name, tail.split("-", 1)[1], needs, base, zip_name,
               " <small>%.1f MB</small>" % (size / 1e6) if size else ""))
    apk = "opendeadlock-%s-android.apk" % version
    size = sizes.get(apk)
    rows.append('<div class="dl-row"><div class="dl-what"><h3>Android <span>tablets</span></h3>'
                '<p>Android 7 or later, tablets in landscape (arm64, x86_64). Tried on the '
                'emulator so far. Install the APK, start it once, then copy the Deadlock 2 '
                'folder\'s files into <code>Android/data/org.opendeadlock/files</code>.</p></div>'
                '<a class="btn primary" href="%s%s">Download%s</a></div>'
                % (base, apk, " <small>%.1f MB</small>" % (size / 1e6) if size else ""))
    sums = ('<a href="%sSHA256SUMS">SHA256SUMS</a>' % base) if (not sizes or "SHA256SUMS" in sizes) else ""
    body = """<main class="wrap doc downloads">
<h1>Downloads</h1>
<p class="lead">OpenDeadlock v%(v)s%(date)s. Unpack the zip anywhere and start
<code>opendeadlock</code>; the first start asks for your Deadlock 2 folder or GOG's installer.</p>
<div class="dl-list">%(rows)s</div>
<p class="dim small">%(sums)s%(sep)s<a href="%(rel)s">Release notes</a> &middot;
<a href="%(dl)s/releases">All releases</a> &middot; <a href="whatsnew.html">What's new</a> &middot;
<a href="faq.html">FAQ</a></p>
<p class="note">You need your own copy of Deadlock 2, installed from the CD, Steam or GOG, or GOG's
installer: no game data is in the download. Network games need the same version on every
machine.</p>
</main>""" % {"v": version, "date": ", released %s" % date if date else "", "rows": "".join(rows),
              "sums": sums, "sep": " &middot; " if sums else "",
              "rel": "%s/releases/tag/v%s" % (DL_URL, version), "dl": DL_URL}
    return page("Downloads - OpenDeadlock", "downloads", body, version)


def games(version):
    """The public games, live from the relay: the page fetches them every 30 s. A
    player's text (a game's name) goes in as text, never as HTML."""
    body = """<main class="wrap doc">
<h1>Games</h1>
<p class="lead">Network games on the public relay right now. Hosts who list their game
(<em>List my games publicly</em>, or <code>net_public=1</code>) show here with its code;
the others are only counted.</p>
<div class="stats" id="now">
  <div class="stat"><b data-k="playing">&ndash;</b><span>games under way</span></div>
  <div class="stat"><b data-k="lobbies">&ndash;</b><span>waiting for players</span></div>
  <div class="stat"><b data-k="players">&ndash;</b><span>players online</span></div>
</div>
<a class="uptime" href="%(uptime)s" target="_blank" rel="noopener" title="Relay status (UptimeRobot)">
<img src="%(up)s" alt="Relay status" height="20">
<img src="%(d7)s" alt="Relay uptime, 7 days" height="20">
<img src="%(d30)s" alt="Relay uptime, 30 days" height="20"></a>
<div class="section-title">Waiting for players</div>
<ul class="games" id="lobbies"><li class="empty">Loading&hellip;</li></ul>
<p class="dim join">Join with the game's code: F2 on the Join a Game screen, or
<code>--join CODE</code> on the command line. All players need the same version.
Looking for players? Ask on <a href="%(discord)s">Discord</a>.</p>
<div class="section-title">Under way</div>
<ul class="games" id="playing"><li class="empty">Loading&hellip;</li></ul>
<div class="section-title">Played</div>
<div class="stats small" id="played">
  <div class="stat"><b data-k="today">&ndash;</b><span>today</span></div>
  <div class="stat"><b data-k="last7Days">&ndash;</b><span>last 7 days</span></div>
  <div class="stat"><b data-k="total">&ndash;</b><span>in all</span></div>
  <div class="stat"><b data-k="longestMinutes">&ndash;</b><span>longest, minutes</span></div>
</div>
<p class="dim status" id="status"></p>
<p class="dim">Is the relay up? Its uptime and any outages:
<a href="%(uptime)s" target="_blank" rel="noopener">relay status</a> (UptimeRobot).</p>
</main>
<script>
const URL_GAMES = %(url)s;
const el = (tag, cls, text) => { const e = document.createElement(tag);
  if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
function fill(box, obj) {
  box.querySelectorAll('b[data-k]').forEach(b => b.textContent = obj[b.dataset.k] ?? 0);
}
function list(ul, items, row, empty) {
  ul.replaceChildren(...(items.length ? items.map(row) : [el('li', 'empty', empty)]));
}
// the host's release (its git describe: v0.1.0); a game older than that field gives its
// build's date only
function release(l) { return l.release || 'v' + l.version; }
function game(name, meta) {
  const li = el('li'); li.append(el('span', 'name', name || 'A game'), meta); return li;
}
async function load() {
  const status = document.getElementById('status');
  try {
    const r = await fetch(URL_GAMES, { cache: 'no-store' });
    if (!r.ok) throw new Error(r.status);
    const g = await r.json();
    fill(document.getElementById('now'), g.now);
    fill(document.getElementById('played'), g.played);
    list(document.getElementById('lobbies'), g.lobbies, l => {
      const meta = el('span', 'meta');
      meta.append(el('span', '', l.players + '/' + l.max + ' players \u00b7 ' + release(l) + ' \u00b7 '));
      const code = el('button', 'code', l.code);
      code.title = 'Copy the code';
      code.onclick = () => navigator.clipboard?.writeText(l.code).then(() => {
        code.classList.add('copied'); setTimeout(() => code.classList.remove('copied'), 1200); });
      meta.append(code);
      return game(l.name, meta);
    }, 'No listed game is waiting for players.');
    list(document.getElementById('playing'), g.playing,
      p => game(p.name, el('span', 'meta', p.players + ' players \u00b7 ' + (p.release ? p.release + ' \u00b7 ' : '') + p.minutes + ' min')),
      'No listed game is under way.');
    status.textContent = 'Updated ' + new Date().toLocaleTimeString() + ' \u00b7 every 30 s';
  } catch (e) {
    status.textContent = 'The relay could not be reached; trying again in 30 s.';
  }
}
load();
setInterval(() => { if (!document.hidden) load(); }, 30000);
</script>""" % {"url": json.dumps(RELAY_GAMES), "uptime": RELAY_STATUS,
              "up": UPTIME_BADGE % ("status", "relay"),
              "discord": DISCORD_URL,
              "d7": UPTIME_BADGE % ("ratio/7", "uptime%207%20days"),
              "d30": UPTIME_BADGE % ("ratio/30", "uptime%2030%20days")}
    return page("Games - OpenDeadlock", "games", body, version)


def last_tag():
    try:
        tag = subprocess.check_output(["git", "describe", "--tags", "--abbrev=0"], cwd=ROOT,
                                      text=True, stderr=subprocess.DEVNULL).strip()
        return tag.lstrip("v")
    except (subprocess.CalledProcessError, OSError):
        return None


def main():
    global ROOT
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=ROOT, help="the OpenDeadlock checkout (default ../opendeadlock)")
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    ap.add_argument("--version", help="the release the download button names (default: the last tag)")
    ap.add_argument("--publish", action="store_true",
                    help="then push the built pages to this repository's gh-pages branch (GitHub Pages)")
    args = ap.parse_args()
    ROOT = os.path.abspath(args.repo)
    if not os.path.isfile(os.path.join(ROOT, "CHANGELOG.md")):
        sys.exit("build.py: no CHANGELOG.md in %s; give --repo" % ROOT)
    version = args.version or last_tag()
    if not version:
        sys.exit("build.py: no tag to name the release; give --version")

    intro, days = parse_changelog()
    days = by_version(days)
    entries = [e for _, _, es in days for e in es]
    counts = {k: sum(1 for e in entries if e["key"] == k) for k, _ in KINDS}

    shutil.rmtree(os.path.join(args.out, "img"), ignore_errors=True)  # only the pictures shown
    os.makedirs(os.path.join(args.out, "img"), exist_ok=True)
    used = set()
    pages = {"whatsnew.html": whatsnew(days, version, used),
             "changelog.html": changelog(intro, days, version, used),
             "games.html": games(version),
             "downloads.html": downloads(version)}

    fields = {"VERSION": version, "REPO": REPO_URL, "DISCORD": DISCORD_URL,
              "RELEASE": "%s/releases/tag/v%s" % (DL_URL, version),
              "DOWNLOAD": "%s/releases/download/v%s/opendeadlock-%s" % (DL_URL, version, version),
              "SIZES": html.escape(json.dumps(release_info(version)[0])),
              "BUGS": str(counts["game"]),
              "QOL": str(counts["feature"] + counts["qol"])}
    for name, key, title in [("index.html", "home", "OpenDeadlock - Deadlock 2, rebuilt for today"),
                             ("faq.html", "faq", "FAQ - OpenDeadlock")]:
        text = open(os.path.join(HERE, "src", name), encoding="utf-8").read()
        for k, v in fields.items():
            text = text.replace("{{%s}}" % k, v)
        pages[name] = page(title, key, re.search(r"<body>(.*)</body>", text, re.S).group(1).strip(),
                           version)
        used.update(re.findall(r'src="img/([^"]+)"', text))

    for name, text in pages.items():
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            f.write(text)
    for name in ("style.css", "lightbox.js", "compare.js"):
        shutil.copy(os.path.join(HERE, "src", name), args.out)
    shutil.copy(os.path.join(ROOT, "assets", "icon", "out", "opendeadlock.png"),
                os.path.join(args.out, "img"))
    missing = []
    for src in sorted(used):
        found = [p for p in (src, os.path.join("docs", "changelog", os.path.basename(src)),
                             os.path.join("docs", "readme", os.path.basename(src)))
                 if os.path.isfile(os.path.join(ROOT, p))]
        if found:
            shutil.copy(os.path.join(ROOT, found[0]), os.path.join(args.out, "img"))
        elif os.path.basename(src) != "opendeadlock.png":
            missing.append(src)
    for src in missing:
        print("build.py: missing picture %s" % src, file=sys.stderr)
    og_image(os.path.join(args.out, "img"))
    with open(os.path.join(args.out, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n'
                % "".join("  <url><loc>%s%s</loc></url>\n"
                          % (SITE_URL, "" if k == "home" else name) for k, (name, _) in PAGES.items()))
    with open(os.path.join(args.out, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n" % SITE_URL)
    shown = sum(1 for e in entries if noticeable(e))
    print("build.py: %s (v%s): %d changes, %d in What's new, %d pictures"
          % (args.out, version, len(entries), shown, len(used)))
    if missing:
        return 1
    if args.publish:
        publish(args.out, version)
    return 0


def og_image(img):
    """img/og.jpg, the picture link previews show (1200x630): the modern UI's world map,
    darkened at the bottom under the name and the line. Needs Pillow; without it there
    is none, and link previews go without a picture."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("build.py: no Pillow (pip install pillow): no og.jpg for link previews", file=sys.stderr)
        return
    shot = Image.open(os.path.join(img, "modern-worldmap.png")).convert("RGB")
    w, h = shot.size
    ch = round(w * 630 / 1200)
    top = (h - ch) // 2
    pic = shot.crop((0, top, w, top + ch)).resize((1200, 630), Image.LANCZOS)
    shade = Image.new("L", (1, 630))
    for y in range(630):
        shade.putpixel((0, y), max(0, min(235, int((y - 280) * 1.1))))
    pic.paste(Image.new("RGB", (1200, 630), (6, 10, 16)), (0, 0), shade.resize((1200, 630)))
    draw = ImageDraw.Draw(pic)

    def font(size, face):  # face: the index in Avenir Next.ttc, 0 Bold, 5 Medium
        for path, index in (("/System/Library/Fonts/Avenir Next.ttc", face),
                            ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0)):
            try:
                return ImageFont.truetype(path, size, index=index)
            except OSError:
                continue
        return ImageFont.load_default()
    icon = Image.open(os.path.join(img, "opendeadlock.png")).convert("RGBA").resize((96, 96))
    pic.paste(icon, (56, 450), icon)
    draw.text((172, 452), "OpenDeadlock", font=font(64, 0), fill=(255, 255, 255))
    draw.text((174, 530), "Deadlock 2, rebuilt for today's machines", font=font(32, 5),
              fill=(70, 224, 255))
    pic.save(os.path.join(img, "og.jpg"), quality=85, optimize=True, progressive=True)


def publish(out, version):
    """The built folder as the gh-pages branch of this repository's origin, which GitHub
    Pages serves: one commit, replacing the last (the history of the pages is not kept;
    the sources' is, on main)."""
    url = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=HERE, text=True).strip()
    rev = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, text=True).strip()
    open(os.path.join(out, ".nojekyll"), "w").close()  # served as they are, no Jekyll
    git = lambda *a: subprocess.check_call(["git", *a], cwd=out)
    shutil.rmtree(os.path.join(out, ".git"), ignore_errors=True)
    git("init", "-q", "-b", "gh-pages")
    git("add", "-A")
    git("-c", "user.name=build.py", "-c", "user.email=build.py@localhost",
        "commit", "-q", "-m", "The pages, built from %s for v%s" % (rev, version))
    git("push", "-q", "--force", url, "gh-pages")
    shutil.rmtree(os.path.join(out, ".git"))
    print("build.py: published to %s (gh-pages)" % url)


if __name__ == "__main__":
    sys.exit(main())
