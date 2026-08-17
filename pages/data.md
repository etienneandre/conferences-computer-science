<!-- pages/data.md — yours to edit. The build renders it and never writes here. -->

# Open data

Everything on this site is available as a file. No key, no rate limit, no
attribution required — though a link back is always welcome, and telling me what
you built is even better.

## The files

- [conferences.json](/data/conferences.json) — one object per edition, with the
  full record
- [conferences.csv](/data/conferences.csv) — the same, flattened, for
  spreadsheets and `pandas`

Both are regenerated whenever the site is rebuilt, which is roughly fortnightly.

## What a row contains

One row per edition. The columns worth explaining:

- `paper_deadline` is the date that actually applied; `paper_deadline_announced`
  is the date first published, and `paper_extended_days` the difference. Keeping
  all three is the point of this dataset — nowhere else records what a deadline
  *was*.
- `timezone` is empty when the organisers did not state one. It is not filled in
  with a guess.
- `submitted` and `accepted` are the overall figures. Where a conference
  publishes only per-track numbers, these are their sum.
- `lat` and `lon` come from a hand-built gazetteer and locate the city, not the
  venue.

An empty field means the information is not recorded, which is not the same as
the information being absent in reality. See [about](/about/#what-is-recorded).

## Calendars

If you want to follow deadlines rather than analyse them, the
[calendar feeds](/ics/) are more convenient.

## Licence

**[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)** — the same
terms as Wikipedia. Use it for anything, including commercially, on two
conditions: say where it came from, and publish anything you build on it under
the same licence.

Attribution: a link to <https://www.conferences-computer.science> and/or [Étienne André](https://www.etienne-andre.fr) is enough.

Calls for papers reproduced under the archive belong to their authors and are kept as they were published; the licence above covers the compilation, not them.
