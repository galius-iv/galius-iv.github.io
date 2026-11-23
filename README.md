# opendeadlock-site

The web page of [OpenDeadlock](https://github.com/galius-iv/opendeadlock): a landing
page, What's new (every change in two or three sentences, with its before/after
screenshots), the changelog in short (each release as its Discord post: one line a
change), the full changelog (`changelog-details.html`, not in the top bar: the short
one's lines link to it), and Games: the public relay's games, live (the page
fetches the relay's `/games`, galius-iv/relay, every 30 s).

    python3 build.py                      # reads ../opendeadlock, writes dist/
    python3 -m http.server -d dist        # look at it

`python3 build.py --publish` builds and then pushes `dist/` to this repository's `gh-pages`
branch, which GitHub Pages serves at https://galius-iv.github.io (after a release, or a
CHANGELOG entry worth showing). `--repo DIR` names another OpenDeadlock checkout; `--version X.Y.Z` the release the
download button names (default: the checkout's last tag). Plain Python 3, nothing to
install.

- `src/index.html`: the landing page's body, a template (`{{VERSION}}`, `{{RELEASE}}`,
  `{{REPO}}`, `{{DISCORD}}`, `{{BUGS}}`, `{{QOL}}`)
- `src/style.css`: the colours, type and panels of the modern UI's design system
  (galius-iv/modern-ui, `ui.css`)
- `build.py`: the pages, from the checkout's `CHANGELOG.md`; the screenshots it shows
  (`docs/readme/`, `docs/changelog/`) and the icon are copied into `dist/img/`; the update
  manifest the game checks once a day, `update/latest.json` and `latest.json.sig`, is the
  release's `update.json` and `update.json.sig` (made by OpenDeadlock's `tools/release.py`,
  GALI-38), fetched with `gh`; without them the ones served now are kept

What's new groups the changes by domain, the `[battle]` after each CHANGELOG.md entry's
kind (`DOMAINS` in build.py; the changelog's header lists them), each under Features, QoL
and Bug fixes. It leaves out the port's own bugs fixed and the changes nobody notices in play
(unreachable code, a hostile network peer ...); the full changelog has every entry.
The short changelog lists each release's entries by title, the port's own fixes only
counted, and cuts a long release at `SHORT_MAX` ("... and N more", as the Discord post).

The page links to [OpenDeadlock's Discord](https://discord.gg/XdEABUBC6Z) (`DISCORD_URL` in build.py): the
landing page's button, the footer and the FAQ.
