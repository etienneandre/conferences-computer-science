# Adding a conference

Send what you have.
A link to the call for papers and the deadline is already better than nothing — the rest can be filled in from there, and an incomplete report is far better than none.

## The quickest version for you (and longest to me)

Email the call for papers, or a link to it, to [my email address](https://www.etienne-andre.fr/en/contact.html).
Put the acronym and year in the subject line so it is easy to find later.

But ideally, send (semi-)structured data, see below.

## If you would rather send structured data (preferred)

Please, refer to the instructions below, and either [send me an email](https://www.etienne-andre.fr/en/contact.html) or [make a pull request](https://github.com/etienneandre/conferences-computer-science#important-about-this-git-repository) (preferred, but require a github account).

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

And if you know it *was* extended but not from when — which happens often, as
the original date vanishes from the call the moment it is updated — say that
instead, naming the deadline that moved:

```toml
abstract = [2022-02-28]
paper = [2022-03-07]
extensions = ["abstract"]
```

That records an extension on the abstract deadline whose earlier date is lost,
and claims nothing at all about the paper deadline.

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

**Proceedings.** For `license`, the values are:

- `cc-by`, `cc-by-sa`, `cc-by-nd`, `cc-by-nc-nd` — an open licence, authors keep their rights
- `free` — free to read, authors keep their rights
- `free-copy` — free to read, copyright transferred
- `acm` — ACM Digital Library
- `pay` — paywalled
- `pay-profit` — paywalled, for-profit publisher
- `pay-profit-embargo` — paywalled and for-profit, open after an embargo

If you are unsure, name the publisher and leave the licence out: most
publishers have a usual one, and a guess here is worse than a blank.

**Special issues.** `[extra] journal` is for what the call *promises*:

```toml
[extra]
journal = "Selected papers will be invited to a special issue of Formal Aspects of Computing."
```

Once an issue has actually come out, it gets recorded properly, which is far
more useful — it is almost impossible to find again otherwise. An edition can
have several, in different journals and different years, so each one is its own
block:

```toml
[[special_issue]]
journal = "Science of Computer Programming"
volume = "204"
issue = "S1"
year = 2021
papers = 6
doi = "10.1016/j.scico.2021.102600"
```

Everything except `journal` is optional, but a `doi` or a `url` is what makes
it findable. `volume` and `issue` are quoted, because journals number them
`3-4` and `S1` as often as `4`. And if the promised issue never appeared, that
is worth knowing too:

```toml
special_issue = false
```

**Acceptance rate.** By default, the syntax is easy:

```toml
[stats]
submitted = 47
accepted = 20
```


**Acceptance rate per track/category.** When the conference gives detailed figures by track (Track A, Track B) or category (regular papers, short papers…), the syntax is

```toml
[stats]
[[stats.track]]
name = "Track A"
submitted = 523
accepted = 155

[[stats.track]]
name = "Track B"
submitted = 105
accepted = 35
```


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
