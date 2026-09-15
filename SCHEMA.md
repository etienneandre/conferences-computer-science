# SCHEMA.md — Data format for conferences-computer.science

Reference document for the site's data format. Any discrepancy between this file
and the generator's behaviour is a bug — in one or the other.

- **Schema version**: 1.3
- **Format**: [TOML 1.0](https://toml.io/) (read with `tomllib`, standard library since Python 3.11)
- **Encoding**: UTF-8, no BOM, LF line endings
- **Indentation**: 2 spaces inside multi-line tables

---

## 1. Core principles

Five rules govern everything else. When facing a case this document does not
cover, come back to them.

### 1.1 One file per edition

No file describes two editions. Adding an edition means creating a file.

A direct consequence: **no field aggregates several years**. Acceptance rates and
deadline extensions are recorded per edition and recombined by the generator when
rendering a conference page. Nothing is ever copied by hand from one year to the
next.

### 1.2 A missing key is not `false`

| Written | Meaning |
|---|---|
| key absent | **Unknown.** The site displays nothing. |
| `field = false` | **Known to be absent.** The site may state so. |
| `field = true` or a value | Known to be present. |

This distinction is the backbone of the whole schema. Most fields are unknown for
most editions, and that is expected: the site's credibility rests on never
implying knowledge it does not have.

### 1.3 Dates that move are lists

Any deadline that may be pushed back is a **chronological list**, oldest first.
The first element is the originally announced date, the last one is the effective
date.

```toml
paper = [2026-06-08, 2026-06-22]   # extended once, by 14 days
paper = [2026-06-22]               # no known extension
```

The number of extensions is `len(list) - 1`. This applies to every deadline,
including notifications, which are extended more often than one would hope.

### 1.4 A missing file means no edition — conditionally

`conference.toml` may carry `complete_since = YYYY`. For years at or after that
value, a missing edition file means "no edition took place". Before it — and
everywhere when the key is absent — a missing file means "not covered by this
site". Explicit cases use `status` (§ 4.2).

The key is optional precisely because it is an assertion: claiming coverage you
do not have would turn silence into a false statement.

### 1.5 Free text is an acceptable state

`extra.notes` holds anything not yet modelled. A `# TODO: extract` comment marks
what remains to be structured, and `grep -rl "TODO: extract" data/` reports the
backlog at any time. **Data kept as prose is better than data lost, or than a
redesign that never ships.**

---

## 2. Directory layout

```
data/
  enums.toml                  # closed vocabularies with their attributes
  publishers.toml             # publishers, their default licence and notes
  cities.toml                 # place gazetteer
  reserved.toml               # forbidden slugs (URL collisions)
  icfem/
    conference.toml           # series metadata
    2026.toml                 # one edition
    2025.toml
    2012.toml                 # may hold three lines and nothing more
    cfp/
      2026-04-12.txt          # CFP, named after its collection date
      2026-06-02.txt          # version issued after the extension
      2025-05-03.pdf
  qest-formats/
    conference.toml
    ...
```

### 2.1 Slugs

The directory name is the conference **slug** and appears verbatim in the URL
(`/icfem/`).

- allowed characters: `a-z`, `0-9`, `-`
- must not be purely numeric, nor look like a year (`2026`) — otherwise a
  leading digit is fine, since the year is the *second* path segment and
  `30-years-of-uppaal` is unambiguous
- accents are transliterated, `&` becomes `and` (`S&P` → `s-and-p`)
- length 2 to 40
- must not appear in `data/reserved.toml`, which contains at least: `about`,
  `data`, `ics`, `schema`, `changelog`, `search`, `api`, `assets`, `static`,
  `cfp`, `all`, `index`

A slug is **permanent**. A conference that changes its name keeps its slug and
declares the former one in `aliases` (§ 3).

### 2.2 Edition file names

`YYYY.toml`, where `YYYY` is the year the conference **takes place** — not the
year of its submission deadline. This is the year people search for, and the one
that appears in the usual acronym ("ICFEM 2026").

**Reserved, not implemented**: two editions in the same year → `2026a.toml`,
`2026b.toml`. The validator accepts these names and the generator produces the
matching URLs, but no dedicated rendering exists.

---

## 3. `conference.toml` — the series

```toml
# data/icfem/conference.toml
acronym = "ICFEM"
name = "International Conference on Formal Engineering Methods"
complete_since = 2015

# Optional
aliases = ["icfem-old"]
topics = ["formal methods", "verification"]
frequency = "Biennial until 2005, annual since"
homepage = "https://icfem.github.io/"
defunct = 2024                    # or: defunct = "seemingly"

[core]
id = "1031"

[[core.history]]
from = 2020
rank = "B"

[[core.history]]
from = 2023
rank = "C"

[links]
dblp = "icfem"
wikipedia = "International_Conference_on_Formal_Engineering_Methods"
mastodon = "https://fosstodon.org/@icfem"
bluesky = "icfem.bsky.social"
twitter = "icfem"

# Lineage (§ 3.3)
predecessors = ["qest", "formats"]
```

| Key | Type | Required | Notes |
|---|---|---|---|
| `acronym` | string | ✅ | No year. Used for display. |
| `name` | string | ✅ | Generic name, no edition number. |
| `complete_since` | int | | See § 1.4. **Omit when unknown** — an invented value silently turns "not recorded" into "no edition took place". |
| `aliases` | array(string) | | Former slugs. Must satisfy § 2.1 and be globally unique. |
| `topics` | array(string) | | Free vocabulary for now. |
| `frequency` | string | | Free text: real-world frequencies rarely fit an enum. |
| `homepage` | string | | Series portal, distinct from an edition's URL. |
| `defunct` | int or `"seemingly"` | | See § 3.2. |
| `one_off` | bool | | `true` for a single event with no further editions planned (§ 3.2). |
| `core.id` | string | | CORE portal identifier. Stable across rounds. |
| `core.rank` | enum | | Shorthand: current rank, no history known (§ 3.1). |
| `core.history` | array of tables | | See § 3.1. |
| `links.dblp` | string | | DBLP series key, not a URL. |
| `links.wikipedia` | string | | Page title, not a URL. |
| `links.bluesky` | string | | Handle, not a URL. |
| `links.twitter` | string | | Handle, not a URL. Historical; kept for old editions. |
| `links.mastodon` | string | | Full URL (the instance is part of the identity). |
| `predecessors` | array(slug) | | See § 3.3. |

### 3.1 CORE ranks over time

CORE re-ranks conferences every few years, and a single current value erases that
history. Ranks are therefore recorded as a list of **open-ended intervals**: each
entry states the year its rank came into force, and ends implicitly where the
next one begins.

```toml
[[core.history]]
from = 2020
rank = "B"
round = "CORE2020"    # optional: which CORE exercise this comes from

[[core.history]]
from = 2023
rank = "C"
```

Rules:

- entries are sorted by `from`, which must be strictly increasing;
- the rank shown for an edition of year *Y* is the last entry with `from ≤ Y`;
- for a year **before the first entry**, the rank is **unknown** — not `absent`.
  Nothing is displayed (§ 1.2);
- the current rank is the last entry;
- editions never carry a CORE field of their own. The history is authoritative.

For the common case of a single known rank with no history, use the shorthand:

```toml
[core]
rank = "C"
id = "1031"
```

Setting both `core.rank` and `core.history` is a validation error.

> **On data quality.** The migration derives an initial history by collapsing
> consecutive identical per-edition values from the legacy file. Those values
> record the rank known *at data entry time*, not the rank historically in
> force, so derived entries are marked `# TODO: verify` and only the most recent
> one should be trusted without checking.

### 3.2 `defunct`

| Value | Rendering |
|---|---|
| `defunct = 2019` | "Discontinued in 2019" |
| `defunct = "seemingly"` | "Seemingly discontinued" |

This is a property of the **series**, never of an edition. A single cancelled
year uses `status = "cancelled"` on that edition instead (§ 4.2). Defunct series
are sorted into their own group, after past editions.

`one_off = true` marks an event that was never meant to recur — a celebration or
a one-time symposium. It renders as "single event" rather than "discontinued",
which would wrongly suggest a series that failed.

### 3.3 Lineage: mergers, splits, renamings

Three distinct mechanisms, not to be confused:

- **Renaming** (same conference, new name) → `aliases`. One directory only.
- **Merger** (`QEST` + `FORMATS` → `QEST+FORMATS`) → a new slug `qest-formats`
  carrying `predecessors = ["qest", "formats"]`. The original series stay intact
  and each receives `defunct`.
- **Split** → same mechanism, `predecessors` on every resulting series.

The generator derives the reciprocal links, so `qest/` and `formats/` display
"Continues as: QEST+FORMATS" automatically. Never write a `successors` field by
hand.

---

## 4. `YYYY.toml` — one edition

A complete, representative example:

```toml
# data/icfem/2026.toml
edition = 27
title = "27th International Conference on Formal Engineering Methods"
url = "https://icfem2026.github.io/"

[event]
start = 2026-11-17
end = 2026-11-20
city = "Southampton, England"

[submission]
tz = "AoE"
format = "16 pages LNCS + bibliography (regular paper)"
abstract = [2026-06-01, 2026-06-22]
paper = [2026-06-08, 2026-06-22]
notification = [2026-08-08]
camera_ready = [2026-09-14]

[proceedings]
publisher = "Springer LNCS"
# licence omitted: inherited from publishers.toml

[review]
blind = false
rebuttal = false

[stats]
submitted = 50
accepted = 22

[[cfp]]
file = "cfp/2026-04-12.txt"
retrieved = 2026-04-12

[[cfp]]
file = "cfp/2026-06-02.txt"
retrieved = 2026-06-02
note = "after extension"

[extra]
journal = "Invited extended versions of selected papers will be recommended to a special issue of Formal Aspects of Computing."
notes = "Also journal-first presentations. Doctoral symposium."
```

And a minimal, perfectly valid edition — typically an old year for which only the
acceptance rate is known:

```toml
# data/icfem/2012.toml
edition = 14

[stats]
rate = 36.0
```

### 4.1 Top level

| Key | Type | Notes |
|---|---|---|
| `edition` | int | Edition number (27 for the 27th). Drives the "age" styling. |
| `title` | string | Full title **of this edition**, including its ordinal. Falls back to `edition` + `conference.name`. |
| `url` | string | Edition website. May die: see `url_dead`. |
| `url_dead` | bool | `true` → link shown struck through, with an archive.org fallback. |
| `status` | enum | See § 4.2. |

### 4.2 `status`

Absent means a normal edition. Values are defined in `enums.toml`, each carrying
a `listed` attribute that decides whether the edition appears in the front-page
list and in `.ics` feeds:

| Value | Meaning | Listed |
|---|---|---|
| `announced` | Announced, dates not yet published. | yes |
| `cancelled` | Cancelled after announcement. | no |
| `postponed` | Postponed; the actual edition lives elsewhere. | no |
| `joint` | Held jointly with another series; the data lives there (§ 4.2.1). | no |
| `no-edition` | Explicitly: no edition took place that year. | no |

Unlisted editions still appear on the conference page — recording a cancellation
is useful precisely because it is not visible anywhere else.

#### 4.2.1 Joint editions

Two series sometimes run a single joint event for a year or two, then separate
again — FMICS and AVOCS did so in 2016 and 2017. The joint event gets its own
slug and holds all the data; each parent series gets a four-line redirect, so
that its edition numbering stays continuous and its history remains navigable:

```toml
# data/avocs/2016.toml
edition = 16
status = "joint"
joint_with = "fmics-avocs/2016"
```

`joint_with` is a `slug/year` reference. Nothing is duplicated: dates, venue,
proceedings and statistics exist once, in the joint edition. The generator
derives the reciprocal links, so the joint page lists its parent series without
any further declaration.

Do not confuse this with a **merger**, where the parent series end for good
(`predecessors`, § 3.3): after a joint edition, both parents carry on.

### 4.3 `[event]`

| Key | Type | Notes |
|---|---|---|
| `start`, `end` | date | `end` may be omitted for single-day events. |
| `city` | string | **A key in `cities.toml`**, though it looks like free text (§ 7). |
| `venue` | string | Building, campus. Optional. |
| `online` | bool | `true` = fully online (`city` then optional). |
| `hybrid` | bool | |

**Reserved, not implemented**: `colocated_with = ["fmas/2026"]`, using
`slug/year` references made symmetric at build time. Until then, co-location
stays in `extra.notes`.

### 4.4 `[submission]`

| Key | Type | Notes |
|---|---|---|
| `tz` | string | `AoE`, `UTC`, `UTC+2`, `CET`… **Absent means unknown** (§ 4.5). |
| `format` | string | Free text: length, style, paper category. |
| `abstract` | array(date) | Abstract deadline. See § 1.3. |
| `paper` | array(date) | Full paper deadline. **This is the site's sorting date.** |
| `notification` | array(date) | |
| `camera_ready` | array(date) | |
| `registration` | array(date) | Optional, rarely known. |
| `extensions` | bool | `false` = verified, no extension ever happened. `true` = an extension happened but the earlier date is unknown (§ 4.4.1). Omit when nothing is known. |

Lists must be strictly increasing. A date earlier than its predecessor is a data
entry mistake. Real-world exception: a notification date brought *forward* — put
that in `extra.notes`, not in the list.

Deadlines are **inclusive**: a deadline of `2026-06-22` expires at the end of
that day, in the applicable time zone.

#### 4.4.1 Extensions with no known earlier date

Sometimes a deadline is known to have been extended, but the date it moved from
was never recorded. The list then holds a single date — the effective one — and
`extensions = true` states the fact:

```toml
[submission]
paper = [2025-10-18]
extensions = true
```

This completes the three-state pattern of § 1.2 across the whole field: absent
means nothing is known, `false` means no extension ever happened, `true` means
one did and its earlier date is missing. A list of two or more dates is already
self-evident and needs no `extensions` key.

### 4.5 Time zones

A three-step rule:

1. `tz` absent means **unknown**.
2. For every computation (sorting, colour coding, `.ics` timestamps) the
   generator **assumes AoE** (UTC−12, the latest and therefore most conservative
   convention).
3. Display **never mentions the assumed zone**. A time zone is shown only when
   `tz` is explicit.

In short: decide internally, assert nothing publicly. In practice `tz = "AoE"`
will be explicit on a large share of recent editions.

### 4.6 Rounds

Some conferences offer several submission deadlines for the same edition.

```toml
[submission]
tz = "AoE"
format = "12 pages"

[[submission.round]]
name = "Round 1"
paper = [2026-04-01]
notification = [2026-05-15]

[[submission.round]]
name = "Round 2"
paper = [2026-07-01]
notification = [2026-08-15]
```

Rules:

- `tz`, `format` and `extensions` stay at the `[submission]` level and are shared.
- Date keys (`abstract`, `paper`, `notification`, `camera_ready`) live **either**
  at the `[submission]` level **or** inside rounds, never both. Mixing is a
  validation error.
- An edition without `[[submission.round]]` is treated as having a single,
  unnamed implicit round.
- For front-page sorting and colours, the date used is **the next upcoming
  `paper` across all rounds**; if none is upcoming, the most recent past one.

**Reserved, not implemented**: multiple submission categories (regular / tool /
poster / short) will reuse this shape with a `kind` key inside each round. Do not
use it today.

### 4.7 `[proceedings]`

| Key | Type | Notes |
|---|---|---|
| `publisher` | string | A key in `publishers.toml`, or free text if unknown there. |
| `license` | enum | A key in `enums.toml`. **Optional**: inherited from the publisher when omitted. |
| `none` | bool | `true` = no published proceedings. |

**Inheritance.** Most publishers use the same licence everywhere, so
`publishers.toml` carries a `default_license` and edition files stay silent. An
explicit `license` always wins — this is how a Springer volume published open
access is recorded, and the case is common enough that the override must never
be treated as an anomaly.

Writing a `license` identical to the publisher's default is not flagged. Every
migrated edition carries one explicitly, because the legacy publisher/licence
mapping was too irregular to compress safely: Springer LNCS alone appears with
four different licences, and some of those differences are real.

### 4.8 `[review]`

| Key | Type | Notes |
|---|---|---|
| `blind` | enum, string or `false` | Enum key from `enums.toml`, or free text for an unusual model. |
| `rebuttal` | bool or string | `true` when a rebuttal phase exists; a string describes an unusual process. |
| `rebuttal_start`, `rebuttal_end` | date | The rebuttal window, when known. `rebuttal_end` is omitted for a single day. |
| `artifact` | bool or string | |
| `award` | bool or string | |
| `competition` | bool or string | |
| `diversity` | enum | `male-only`, `mixed`, `women-only`. |
| `environment` | bool or string | Environmental or travel policy. |

Every key here accepts a descriptive string wherever a bare `true` would lose
information. Per § 1.2, these keys are simply **absent** for most older editions,
and the corresponding information — where it exists at all — sits in
`extra.notes`. That is expected, not a defect.

### 4.9 `[stats]` — acceptance rates

Simple form:

```toml
[stats]
submitted = 50
accepted = 22
```

Degraded form, when only the percentage is known:

```toml
[stats]
rate = 36.0
```

Per-track form:

```toml
[stats]
# global figures optional: computed as the sum of tracks when omitted

[[stats.track]]
name = "regular"
submitted = 20
accepted = 10

[[stats.track]]
name = "tool"
submitted = 10
accepted = 9
```

Computation rules:

- `rate` is **always derived** from `accepted / submitted` when both are present.
  An explicit `rate` is used only when the counts are missing.
- Tracks without global figures produce a computed global, displayed as
  "overall".
- When both are present and the track sums differ from the global, the validator
  emits a **warning, not an error**: this is a legitimate situation (papers moved
  between tracks, categories not exhaustively listed). A `note` key in `[stats]`
  documents the discrepancy and silences the warning.
- `accepted > submitted` is an error.

### 4.10 `[[cfp]]` — calls for papers

```toml
[[cfp]]
file = "cfp/2026-04-12.txt"
retrieved = 2026-04-12
note = "after extension"     # optional
source = "https://..."       # optional, original URL
```

- `file` is relative to the conference directory and must exist (checked at
  build time).
- Naming: `YYYY-MM-DD.ext`, the date being the day of **collection**, not of
  publication. Accepted extensions: `.txt`, `.pdf`, `.md`, `.html`.
- Several entries mean several versions over time, displayed chronologically.
  The generator renders `/icfem/2026/cfp/` as HTML from the most recent version
  (for indexing) and serves the raw files alongside.

### 4.11 `[extra]` — free text

| Key | Type | Notes |
|---|---|---|
| `journal` | string | Special issue, invited extended versions. |
| `colocated` | string | Co-located events, as prose. Superseded by `event.colocated_with` when that lands (§ 4.3), with nothing lost. |
| `notes` | string | Catch-all. Trusted HTML fragment — see below. |

`notes` and `colocated` are rendered as **HTML**, not Markdown: the legacy page
emitted them raw and they contain links that would otherwise break. This is
first-party content written by the maintainer, so there is no injection concern;
content arriving from the public submission form is escaped instead.

These are the only unstructured fields. Anything added here should be considered
temporary: once a pattern recurs five or six times, it deserves a proper key and
an entry in this document.

### 4.12 `[legacy]` — migration residue

Present only on migrated conferences, in `conference.toml`:

```toml
[legacy]
# TODO: extract — cross-year prose kept once, verbatim.
acceptance = "29% (2009, 36/121), 30% (2011, 31/103), …"
extensions = "1 week (2013), 2 weeks (2014), …"
notes = "…"
```

The pre-2026 data restated a conference's entire history inside every edition.
The most recent copy of each is kept **once** here, so nothing is lost while the
per-edition fields become authoritative. Every key is temporary: extract what is
worth structuring, delete the rest. A conference you have finished reviewing has
no `[legacy]` table at all.

---

## 5. `enums.toml`

The single source of truth for closed vocabularies. Any enum value missing from
this file **fails the build** — this is the safeguard against typos silently
creating phantom categories.

Values carry **attributes**, not just labels, and front-end filters are derived
from those attributes rather than from hard-coded lists of keys. "Show open
access only" means `open_license = true`, so adding a licence never requires
touching filter code.

Licences are described along three independent axes:

| Attribute | Question it answers |
|---|---|
| `free_to_read` | Can a reader obtain the paper without paying? |
| `open_license` | Is it under a proper open licence (Creative Commons)? |
| `authors_keep_rights` | Do the authors retain their copyright? |

"Free but not open" is a real and frequent case — a publisher hosting free PDFs
while holding the copyright — and collapsing it into "open access" would
misrepresent it.

Whether a publisher is for-profit is deliberately **not** a licence attribute: it
is a property of the publisher, and lives in `publishers.toml`.

---

## 6. `publishers.toml`

```toml
["Springer LNCS"]
default_license = "pay-profit"
for_profit = true
url = "https://www.springer.com/gp/computer-science/lncs"

["EPTCS"]
default_license = "cc-by"
for_profit = false

["Elsevier"]
default_license = "pay-profit"
for_profit = true
note = "lobbying against open science"
```

- `default_license` applies to every edition of every conference using this
  publisher, unless overridden (§ 4.7).
- `note` carries commentary about the publisher itself, so it displays wherever
  that publisher appears — including on volumes published under a different
  licence.
- A publisher used in `data/` but absent here produces a **warning**, not an
  error: the name renders as plain text with no licence styling.

---

## 7. `cities.toml`

A shared gazetteer. Editions reference a **text key** identical to what is
already displayed, which makes filling it in gradual and painless.

```toml
["Southampton, England"]
country = "GB"
continent = "EU"
lat = 50.9097
lon = -1.4044
```

- A `city` referenced but missing here produces a **warning**, never an error:
  the edition renders normally, with the text as-is.
- `lat`/`lon` are optional. Without them the entry is still useful (country,
  continent → per-continent `.ics` feeds, coarse geographic filters).
- Fully online events use `event.online = true` and no `city`.
- Filling one or two entries a month is enough to cover the corpus within a year,
  with no dedicated effort. Maps and "conferences near me" then become pure
  presentation, requiring no new data entry.

---

## 8. Validation (`make check`)

The build fails on any **error** and reports **warnings** without blocking.

### Errors

1. Unknown key at any level (this is what catches typos).
2. Missing required field (`acronym`, `name`).
3. Wrong type (date expected, list expected…).
4. Invalid or reserved slug, or a collision with another slug or alias.
5. Enum value missing from `enums.toml`.
6. Date list not strictly increasing.
7. Chronological inconsistency: `abstract ≤ paper ≤ notification ≤ camera_ready ≤
   event.start`, evaluated on effective dates (the last element of each list).
8. `paper` present both at the `[submission]` level and inside rounds.
9. `extensions` set to anything other than `false`.
10. `accepted > submitted`.
11. A referenced CFP file missing from disk.
12. `predecessors` pointing at a non-existent slug.
13. Edition file name not matching `YYYY.toml` or `YYYYx.toml`.
14. Both `core.rank` and `core.history` present.
15. `core.history` entries not strictly increasing by `from`.
16. `joint_with` pointing at a non-existent edition, or at an edition that is
    itself `status = "joint"`.

### Warnings

- `city` missing from `cities.toml`.
- `publisher` missing from `publishers.toml`.
- Track sums differing from global figures (unless `[stats].note` is present).
- A future edition with neither `paper` nor `status`.
- `url` returning HTTP ≥ 400 (only under `make check --network`).
- More than **365 days** between `notification` and `event.start`. Long gaps are
  normal in this field, so this threshold targets one specific mistake: a
  mistyped year.
- Presence of `TODO: extract` or `TODO: verify` (informational count, never
  blocking).

---

## 9. Deliberately out of scope

None of the following may be added without also updating this document, the
validator, and the schema version:

- structured co-location (`event.colocated_with`, § 4.3) — the prose field
  `extra.colocated` holds this meanwhile;
- multiple submission categories (§ 4.6);
- two editions in one year (§ 2.2 — the naming is accepted, the rendering is not);
- programme committees, chairs, invited speakers;
- registration fees;
- persistent identifiers (DOI, per-edition DBLP keys).

---

## Appendix A — Legacy data

The pre-2026 site stored every conference in a single large PHP array, with one
flat entry per edition. That file is archived at `legacy/data.php` and kept
indefinitely as the reference for anything the migration could not interpret. It
is not a live source and must never be edited.

Three shapes from that era have no equivalent here, by design:

- **Numbered pre-extension fields** (`absbefext`, `deadbefext2`, `notifbefext3`,
  and so on) become earlier elements of the corresponding date list (§ 1.3).
- **Cross-year aggregate strings**, which restated a conference's full history of
  acceptance rates and extensions inside every entry, are split across
  per-edition files and recomputed by the generator (§ 1.1).
- **Publisher-specific licences**, where one publisher's name was encoded as a
  licence value, become a publisher entry with a `note` (§ 6). Commentary about
  a publisher now follows the publisher rather than the licence terms.

Everything the migration could not map lands in `extra.notes` with a
`# TODO: extract` marker. The detailed field-by-field mapping lives in
`MIGRATION.md`, alongside the conversion scripts; it is a migration concern, not
part of this schema.

---

## Appendix B — Version history

| Version | Change |
|---|---|
| 1.3 | `extensions` accepts `true` for an extension whose earlier date is unknown (§ 4.4.1). `rebuttal_start` / `rebuttal_end` added (§ 4.8). |
| 1.2 | `complete_since` becomes optional (§ 1.4, § 3). Joint editions get `status = "joint"` and `joint_with` (§ 4.2.1). `one_off` added (§ 3.2). `extra.colocated` added and `notes` declared as trusted HTML (§ 4.11). `[legacy]` documented (§ 4.12). `links.twitter` added. Slug rule relaxed for leading digits, with transliteration and `&` → `and` spelled out (§ 2.1). Redundant-licence warning removed (§ 4.7). |
| 1.1 | CORE ranks become an open-ended interval history (§ 3.1); per-edition CORE field removed. Licences inherited from `publishers.toml` with override (§ 4.7, § 6). `defunct` accepts a year or `"seemingly"` (§ 3.2). `blind` and `rebuttal` accept free text (§ 4.8). `frequency` is free text. CORE `absent` and `unranked` distinguished; invented `national` rank removed. |
| 1.0 | Initial version. |
