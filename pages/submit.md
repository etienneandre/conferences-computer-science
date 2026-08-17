# Adding a conference

Send what you have.
A link to the call for papers and the deadline is already better than nothing — the rest can be filled in from there, and an incomplete report is far better than none.

## The quickest version for you (and longest to me)

Email the call for papers, or a link to it, to [my email address](https://www.etienne-andre.fr/).
Put the acronym and year in the subject line so it is easy to find later.

But ideally, send (semi-)structured data, see below.

## If you would rather send structured data (preferred)

Every edition here is one small text file. If you send one in this shape it can
be dropped straight in, which saves a round trip. The format is
[TOML](https://toml.io/): everything is optional except the dates, and anything
you leave out simply stays unknown rather than being guessed at.

```toml
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

[proceedings]
publisher = "Springer LNCS"
license = "pay-profit"

[review]
[review.gender.chairs]
men = 3
women = 0

[review.gender.speakers]
men = 2
women = 2

[extra]
journal = "Invited extended versions of selected papers will be recommended to a special issue of Formal Aspects of Computing after the conference proceedings."
award = "Best student paper award"

```

Name the file `<acronym>-<year>.toml`, in lower case: `icfem-2026.toml`.

## The parts worth explaining

**Dates that moved are lists.** The first entry is the date first announced, the
last is the date that actually applied. So `paper = [2026-06-08, 2026-06-22]`
says the deadline was 8 June and was extended to 22 June. If there was no
extension, one date is enough:

```toml
paper = [2026-06-22]
```

And if you know for certain that the deadline held, say so — it is useful, and
it cannot be inferred:

```toml
paper = [2026-06-22]
extensions = false
```

**Leave out what you do not know.** An absent field means "nobody has checked",
which is honest. Writing `false` means "checked, and there is nothing", which is
a stronger claim. Please do not use one for the other.

**Time zones.** Write `tz = "AoE"` if the call says Anywhere on Earth, `"UTC+2"`
or `"CET"` if it names a zone, and leave it out if it says nothing at all.

**Several rounds.** Some conferences take submissions in two waves. Each round
gets its own block:

```toml
[submission]
tz = "AoE"

[[submission.round]]
name = "Round 1"
paper = [2026-04-01]
notification = [2026-05-15]

[[submission.round]]
name = "Round 2"
paper = [2026-07-01]
notification = [2026-08-15]
```

**Proceedings.** For `license`, the useful values are `cc-by`, `cc-by-nd`,
`free` (free to read, authors keep their rights), `free-copy` (free to read,
copyright transferred), `pay`, and `pay-profit`. If you are unsure, name
the publisher and leave the licence out.

## A whole conference, not just one edition

If the conference is not here at all, add a second file describing the series itself, named `conference.toml`:

```toml
acronym = "ICFEM"
name = "International Conference on Formal Engineering Methods"

[core]
id = "1031"

[[core.history]]
from = 2008
rank = "B"

[[core.history]]
from = 2023
rank = "C"

[links]
dblp = "icfem"
```

## Corrections

The same address, and the same principle: a one-line email saying "the ICFEM 2026 deadline moved to 29 June" is perfectly good. No format required.

If something here is wrong about *your* conference — a committee listed incorrectly, a rank out of date, an extension recorded that never happened — please say so directly.
It will be fixed as soon as I can.

…and many thanks for using this Web page 🤓