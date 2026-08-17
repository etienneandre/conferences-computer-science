# conferences-computer.science

Submission deadlines for conferences in theoretical computer science, sorted by
what closes next. Live at
[conferences-computer.science](https://www.conferences-computer.science).

Plain text files in, static HTML out. No database, no framework, no build
server: one Python script reads a tree of TOML files and writes the site.

---

## Who does what

The important thing to know about this repository is which parts are yours,
which are the machine's, and which must never be edited by hand.

| Path | Who writes it | Notes |
|---|---|---|
| `data/` | **You** | The corpus. One directory per conference, one file per edition. |
| `pages/` | **You** | Prose: the About and Submit pages, the footer, the disclaimer. Never touched by the build. |
| `site.toml` | **You** | Configuration, and the two lines that flip the site live. |
| `.env` | **You** | Host credentials. Never committed. |
| `templates/`, `assets/`, `*.py` | Generated, then edited by hand | The machinery. Regenerate or patch, but read the comments first. |
| `public/` | **The build** | Deleted and rewritten at will. Nothing here is a source. |
| `legacy/data.php` | Nobody, ever | The old site's 35,000-line data file, kept as the reference for anything the migration could not interpret. |

If you are about to edit something in `public/`, stop: the change will be gone
at the next build. The source is in `data/` or `pages/`.

---

## Getting started

```sh
pip install jinja2                 # the only dependency
./assets/fonts/get-fonts.sh        # once: fetches the six self-hosted faces
make preview                       # validate, build, serve on :8000
```

Then open <http://localhost:8000/>.

`make preview` runs PHP's built-in server through `dev-server.php`, which
reproduces the parts of Apache that matter locally: directory URLs, the trailing
slash redirect, the deny rules on `cache/` and `_data/`. A plain static server
will not do — the front page is PHP.

---

## Everyday work

```sh
make check          # validate data/ against SCHEMA.md
make               # check, then build into public/
make preview        # build and serve
make one SLUG=icfem # build a single conference, to iterate quickly
make stats          # what is left to tidy up
make deploy-dry     # show what would be uploaded, change nothing
make deploy         # upload
make help           # every target
```

`make check` runs before every build, so a typo in a TOML file stops the build
instead of quietly dropping a field from the site. That is the whole point of
it: hand-edited data needs a net.

### Adding an edition

Copy last year's file, change the dates:

```sh
cp data/icfem/2026.toml data/icfem/2027.toml
$EDITOR data/icfem/2027.toml
make check
```

The format is documented in [`SCHEMA.md`](SCHEMA.md), which is the reference for
everything in `data/`. Two rules carry most of the weight:

- **A missing key means "nobody has checked".** `false` means "checked, and
  there is nothing". They are different claims and the site keeps them apart.
- **Dates that moved are lists**: `paper = [2026-06-08, 2026-06-22]` says the
  deadline was announced for 8 June and extended to 22 June. That history is the
  most useful thing here and exists nowhere else.

### Adding calls for papers

```sh
make cfps FROM=~/cfps         # dry run, writes build/cfp-report.md
make cfps-write FROM=~/cfps   # copy the files and edit the TOML
```

Files are matched by name (`ICFEM-2026-extended.txt`), copied into
`data/<slug>/cfp/`, and recorded in the edition file. Nothing is renamed. Safe
to re-run: entries already present are left alone.

---

## Deploying

Copy `.env.example` to `.env` and fill it in, then:

```sh
make remote-test    # connect, list, exit — do this first
make deploy-dry     # exactly what would be transferred
make deploy
```

Two things to know:

**There is no `--delete`.** The old site can sit alongside the new one for as
long as you want. Add the flag only once the changeover is done.

**The build is idempotent.** A file whose content has not changed is not
rewritten, so its modification time survives and `mirror` skips it. A deploy
transfers what changed, usually a handful of pages out of fifteen hundred.

### Going live

```sh
make golive         # prints the two lines to change; changes nothing
```

In `site.toml`: set `front_page = "index"` and `draft = false`, then deploy.
`draft` controls a `noindex` on every page, which is what keeps search engines
away from a site that is still being assembled.

---

## How the front page works

Every other page is static HTML. The front page cannot be: it is ordered by what
closes next, so it changes daily.

The build pre-renders each row with four markers standing in for the parts that
depend on today's date — the urgency colour, the gauge length, the countdown,
and whether it has passed. `future.php` sorts, substitutes four strings, and
concatenates. It never reads TOML and does not know what a licence is, so it
cannot drift out of step with the generator.

The result is cached under a key containing both the date and a fingerprint of
the build, so it regenerates on the first visit of each UTC day, and a deploy
takes effect at once instead of waiting for midnight. **There is no cron job.**

If anything at all fails, the request falls through to
`<front_page>.fallback.html`, a static snapshot written at build time. The worst
case is an ordering a few days stale, never a blank page — and the page says so,
because the ordering date is stamped in the HTML and the JavaScript warns when it
stops moving.

To exercise all this on the live server without waiting for midnight, use the
`debug_token` from `site.toml`:

```
https://…/future.php?refresh=<token>
```

It bypasses the cache and appends a diagnostic comment to the HTML.

---

## Repository layout

```
data/            the corpus: TOML, one file per edition, plus cfp/ archives
pages/           your prose, rendered into the site chrome
templates/       Jinja2
assets/          CSS, JavaScript, self-hosted fonts
legacy/          the old data.php, archived and read-only

build.py         the generator
check.py         the validator — run before every build
calendars.py     iCalendar feeds
import_cfps.py   files a folder of collected calls into data/
dev-server.php   local preview router, never deployed

SCHEMA.md        the data format. The reference for everything in data/
MIGRATION.md     how the old site was converted. Historical
```

---

## Design notes

A few decisions that are easy to undo by accident:

**Colour never carries meaning alone.** Every deadline urgency step is paired
with words, so the list works in black and white and for a colour-blind reader.

**Flags are derived from ISO codes, never stored.** `cities.toml` holds
`country = "GB"`; the emoji is computed. Only England, Scotland and Wales have
subdivision flags that fonts actually draw — anything else falls back to the
national flag.

**Nothing is loaded from a third party** except the venue map, which fetches
OpenStreetMap tiles only after the reader asks. Fonts are self-hosted precisely
so that reading a page tells nobody else anything.

**The site never asserts what it does not know.** Where a conference states no
time zone, sorting assumes Anywhere on Earth — the latest reading, so nothing
shows as closed when it might be open — but the page does not claim that is what
the organisers meant.

---

## Licence

The compiled data is under **CC BY-SA 4.0** — credit the source, and keep
derivatives under the same terms. Share-alike rather than non-commercial: a site
that copies this has to leave its own version equally open, which protects the
work better than a clause that would also block a university spin-off.

The code is under **MIT**: nobody is served by making the generator harder to
reuse than the data.

Calls for papers under `data/*/cfp/` belong to their authors and are kept as
published.
