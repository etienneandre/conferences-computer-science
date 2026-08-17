#!/usr/bin/env python3
"""
check.py — validate the data tree against SCHEMA.md.

Run it before every build and after every hand edit. It is the safety net that
makes editing TOML by hand safe: a typo becomes a build failure instead of a
field that silently disappears from the site.

    ./check.py                  # validate data/
    ./check.py --data data/     # explicit path
    ./check.py --only icfem     # one conference
    ./check.py --strict         # warnings become errors
    ./check.py --network        # also check that edition URLs still resolve
    ./check.py --quiet          # only the summary and the errors

Exit status is 0 when no error was found, 1 otherwise, so it can gate a build:

    make check && make build

Errors are things that would corrupt the site: unknown keys, wrong types,
impossible dates, dangling references. Warnings are things worth knowing that
should not stop a deployment, such as a city not yet in the gazetteer.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

# --------------------------------------------------------------------------
# Schema declaration
#
# Validation is driven by these tables rather than by hand-written checks, so
# that "unknown key" detection is automatic and adding a field to SCHEMA.md
# means adding one line here.
#
# A spec is either a type name, a tuple, or a list of alternatives:
#   "str" "int" "float" "bool" "date"
#   ("enum", <group>)        a key of that group in enums.toml
#   ("list", <spec>)         a TOML array
#   ("table", {...})         a sub-table
#   ("tables", {...})        an array of tables
#   ("literal", value)       exactly this value
#   [spec, spec, ...]        any one of these
# --------------------------------------------------------------------------

CONFERENCE_SPEC: dict = {
    "acronym": "str",
    "name": "str",
    "complete_since": "int",
    "aliases": ("list", "str"),
    "topics": ("list", "str"),
    "frequency": "str",
    "scope": ("enum", "scope"),
    "languages": ("list", "str"),
    "homepage": "str",
    "defunct": ["int", ("literal", "seemingly")],
    "one_off": "bool",
    "predecessors": ("list", "str"),
    "core": ("table", {
        "id": "str",
        # CORE lists some venues as national: "National: China". The rank says
        # `national`, this says which country.
        "national_of": "str",
        "rank": ("enum", "core"),
        "history": ("tables", {
            "from": "int",
            "rank": ("enum", "core"),
            "round": "str",
        }),
    }),
    "links": ("table", {
        "dblp": "str",
        "wikipedia": "str",
        "mastodon": "str",
        "bluesky": "str",
        "twitter": "str",
    }),
    # Transitional: migration residue, tolerated and counted.
    "legacy": ("table", {
        "acceptance": "str",
        "extensions": "str",
        "notes": "str",
    }),
}

CONFERENCE_REQUIRED = ("acronym", "name")

DEADLINE_KEYS = ("abstract", "paper", "notification", "camera_ready", "registration")

# A rebuttal belongs to a submission cycle: with two rounds there are two
# rebuttals, at different dates. Hence here and not in [review].
_ROUND_SPEC = {"name": "str", "rebuttal_start": "date", "rebuttal_end": "date",
               **{k: ("list", "date") for k in DEADLINE_KEYS}}

EDITION_SPEC: dict = {
    "edition": "int",
    "title": "str",
    "url": "str",
    "url_dead": "bool",
    "status": ("enum", "status"),
    "joint_with": "str",
    "event": ("table", {
        "start": "date",
        "end": "date",
        "city": "str",
        "venue": "str",
        "online": "bool",
        "hybrid": "bool",
        "colocated_with": ("list", "str"),
        # Transitional: free-text dates the migration could not parse.
        "dates_text": "str",
    }),
    "submission": ("table", {
        "tz": "str",
        "format": "str",
        "extensions": "bool",
        "rebuttal_start": "date",
        "rebuttal_end": "date",
        "round": ("tables", _ROUND_SPEC),
        **{k: ("list", "date") for k in DEADLINE_KEYS},
    }),
    "proceedings": ("table", {
        "publisher": "str",
        # Post-proceedings: the volume is assembled after the event, so
        # notification and camera-ready legitimately fall after it.
        "post": "bool",
        "license": ("enum", "license"),
        "none": "bool",
        "doi": ["str", ("list", "str")],
    }),
    "review": ("table", {
        "blind": [("enum", "blind"), "str", "bool"],
        "rebuttal": ["bool", "str"],
        "artifact": ["bool", "str"],
        "award": ["bool", "str"],
        "competition": ["bool", "str"],
        "gender_balance": ("enum", "diversity"),
        "gender": ("table", {
            "chairs": ("table", {"women": "int", "men": "int", "other": "int"}),
            "speakers": ("table", {"women": "int", "men": "int", "other": "int"}),
            "committee": ("table", {"women": "int", "men": "int", "other": "int"}),
        }),
        "environment": ["bool", "str"],
    }),
    "stats": ("table", {
        "submitted": "int",
        "accepted": "int",
        "rate": ["float", "int"],
        "note": "str",
        "track": ("tables", {
            "name": "str",
            "submitted": "int",
            "accepted": "int",
            "rate": ["float", "int"],
        }),
    }),
    "cfp": ("tables", {
        "file": "str",
        # Optional: the files collected before 2026 carry no date at all, and
        # inventing one would be worse than leaving it out. Order in the array
        # is what tells the versions apart.
        "retrieved": "date",
        "stage": ("enum", "cfp_stage"),
        "kind": ("enum", "cfp_kind"),
        "note": "str",
        "source": "str",
    }),
    "extra": ("table", {
        "journal": "str",
        "colocated": "str",
        "notes": "str",
    }),
}

# Keys that exist only until the migration residue is cleaned up. They are
# accepted, but counted, so the backlog stays visible without blocking a build.
TRANSITIONAL = {"legacy", "event.dates_text"}

RESERVED_SLUGS = {
    "about", "data", "ics", "schema", "changelog", "search", "api",
    "assets", "static", "cfp", "all", "index", "404", "robots", "sitemap",
}

RE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$")
RE_EDITION_FILE = re.compile(r"^((?:19|20)\d{2})([a-z])?\.toml$")
RE_YEARLIKE = re.compile(r"^(?:19|20)\d{2}$")
RE_REF = re.compile(r"^([a-z0-9-]+)/((?:19|20)\d{2}[a-z]?)$")

CHRONOLOGY = ("abstract", "paper", "notification", "camera_ready")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

class Report:
    def __init__(self, quiet: bool = False) -> None:
        self.errors: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []
        self.counters: Counter[str] = Counter()
        self.quiet = quiet

    def error(self, where: str, message: str) -> None:
        self.errors.append((where, message))

    def warn(self, where: str, message: str) -> None:
        self.warnings.append((where, message))

    def count(self, key: str, n: int = 1) -> None:
        self.counters[key] += n


# --------------------------------------------------------------------------
# Type checking
# --------------------------------------------------------------------------

def type_name(value) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, date):
        return "date"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "table"
    return type(value).__name__


def describe(spec) -> str:
    if isinstance(spec, list):
        return " or ".join(describe(s) for s in spec)
    if isinstance(spec, tuple):
        kind = spec[0]
        if kind == "enum":
            return f"one of the {spec[1]} values in enums.toml"
        if kind == "list":
            return f"a list of {describe(spec[1])}"
        if kind == "literal":
            return f'"{spec[1]}"'
        if kind in ("table", "tables"):
            return "a table"
    return {"str": "a string", "int": "an integer", "float": "a number",
            "bool": "true or false", "date": "a date"}.get(spec, str(spec))


class Validator:
    def __init__(self, enums: dict, report: Report) -> None:
        self.enums = enums
        self.report = report

    def enum_keys(self, group: str) -> set[str]:
        table = self.enums.get(group, {})
        keys = set(table)
        # A value may be spelled either as the table key (A-star) or as its
        # `key` field (A*); both are accepted, since enums.toml carries both.
        keys |= {v["key"] for v in table.values()
                 if isinstance(v, dict) and isinstance(v.get("key"), str)}
        return keys

    def matches(self, value, spec) -> bool:
        if isinstance(spec, list):
            return any(self.matches(value, s) for s in spec)
        if isinstance(spec, tuple):
            kind = spec[0]
            if kind == "literal":
                return value == spec[1]
            if kind == "enum":
                return isinstance(value, str) and value in self.enum_keys(spec[1])
            if kind == "list":
                return isinstance(value, list) and all(
                    self.matches(v, spec[1]) for v in value)
            if kind == "table":
                return isinstance(value, dict)
            if kind == "tables":
                return isinstance(value, list) and all(
                    isinstance(v, dict) for v in value)
            return False
        if spec == "float":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if spec == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        if spec == "date":
            return isinstance(value, date)
        return type_name(value) == spec

    def walk(self, data: dict, spec: dict, where: str, path: str = "") -> None:
        """Check every key against the spec, reporting unknown keys and bad types."""
        for key, value in data.items():
            full = f"{path}.{key}" if path else key

            if key not in spec:
                near = self.suggest(key, spec)
                hint = f" — did you mean `{near}`?" if near else ""
                self.report.error(where, f"unknown key `{full}`{hint}")
                continue

            if full in TRANSITIONAL or path in TRANSITIONAL:
                self.report.count(f"transitional:{full}")

            keyspec = spec[key]

            if not self.matches(value, keyspec):
                self.report.error(
                    where,
                    f"`{full}` should be {describe(keyspec)}, "
                    f"got {type_name(value)} ({value!r:.40})")
                continue

            if isinstance(keyspec, tuple):
                if keyspec[0] == "table":
                    self.walk(value, keyspec[1], where, full)
                elif keyspec[0] == "tables":
                    for i, item in enumerate(value):
                        self.walk(item, keyspec[1], where, f"{full}[{i}]")

    @staticmethod
    def suggest(key: str, spec: dict) -> str | None:
        """Cheap nearest-neighbour, to turn a typo report into a fix."""
        best, best_score = None, 0.0
        for candidate in spec:
            common = len(set(key) & set(candidate))
            score = common / max(len(set(key) | set(candidate)), 1)
            if key.startswith(candidate[:3]) or candidate.startswith(key[:3]):
                score += 0.3
            if score > best_score:
                best, best_score = candidate, score
        return best if best_score > 0.55 else None


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_toml(path: Path, report: Report) -> dict | None:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        report.error(str(path), f"not valid TOML — {exc}")
    except OSError as exc:
        report.error(str(path), f"cannot read — {exc}")
    return None


def load_side_file(data_dir: Path, name: str, report: Report) -> dict:
    path = data_dir / name
    if not path.exists():
        report.warn(name, "file missing — related checks are skipped")
        return {}
    return load_toml(path, report) or {}


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_slug(slug: str, where: str, report: Report) -> None:
    if not RE_SLUG.match(slug):
        report.error(where, f"invalid slug `{slug}`: use a-z, 0-9 and hyphens, "
                            f"2 to 40 characters, no leading or trailing hyphen")
    elif RE_YEARLIKE.match(slug) or slug.isdigit():
        report.error(where, f"slug `{slug}` is purely numeric or looks like a year")
    elif slug in RESERVED_SLUGS:
        report.error(where, f"slug `{slug}` is reserved for a site URL")


def check_date_list(values: list, key: str, where: str, report: Report) -> None:
    for a, b in zip(values, values[1:]):
        if b <= a:
            report.error(where, f"`{key}` is not strictly increasing: "
                                f"{a} is followed by {b}")


def effective(container: dict, key: str) -> date | None:
    """The date that actually applied: the last of the list."""
    values = container.get(key)
    return values[-1] if isinstance(values, list) and values else None


def deadline_groups(edition: dict) -> list[tuple[str, dict]]:
    """Every container that may hold deadline keys, labelled for messages.

    The submission table is always included, even when rounds exist: having
    both is an error, but the lists must still be checked rather than silently
    skipped while that error is being reported.
    """
    submission = edition.get("submission")
    if not isinstance(submission, dict):
        return []
    groups: list[tuple[str, dict]] = [("", submission)]
    rounds = submission.get("round")
    if isinstance(rounds, list):
        for i, group in enumerate(rounds):
            if isinstance(group, dict):
                groups.append((str(group.get("name") or f"round {i + 1}"), group))
    return groups


def check_chronology(edition: dict, where: str, report: Report) -> None:
    start = edition.get("event", {}).get("start")
    # With post-proceedings, deadlines after the event are the normal case and
    # not a mistake. The check is not dropped, only widened: a deadline more
    # than a year after the event is still almost certainly a mistyped year.
    post = bool(edition.get("proceedings", {}).get("post"))

    for label, group in deadline_groups(edition):
        prefix = f"{label}: " if label else ""

        seen: list[tuple[str, date]] = []
        for key in CHRONOLOGY:
            value = effective(group, key)
            if value is not None:
                seen.append((key, value))

        for (ka, va), (kb, vb) in zip(seen, seen[1:]):
            if vb < va:
                report.error(where, f"{prefix}`{kb}` ({vb}) is before `{ka}` ({va})")

        if seen and isinstance(start, date):
            last_key, last_date = seen[-1]
            if last_date > start:
                if not post:
                    report.error(where, f"{prefix}`{last_key}` ({last_date}) is after "
                                        f"the event starts ({start}) — if the "
                                        f"proceedings are published afterwards, "
                                        f"set `proceedings.post = true`")
                elif last_date - start > timedelta(days=365):
                    report.warn(where, f"{prefix}`{last_key}` ({last_date}) is more "
                                       f"than a year after the event ({start}), "
                                       f"which is a lot even for post-proceedings")

        notification = effective(group, "notification")
        if isinstance(start, date) and isinstance(notification, date):
            if start - notification > timedelta(days=365):
                report.warn(where, f"{prefix}more than a year between notification "
                                   f"({notification}) and the event ({start}) — "
                                   f"check for a mistyped year")


def check_rounds(edition: dict, where: str, report: Report) -> None:
    submission = edition.get("submission")
    if not isinstance(submission, dict):
        return
    rounds = submission.get("round")
    if not isinstance(rounds, list) or not rounds:
        return
    clash = [k for k in DEADLINE_KEYS if k in submission]
    if clash:
        report.error(where, "deadline keys must be either at the `[submission]` "
                            "level or inside rounds, not both: "
                            + ", ".join(f"`{k}`" for k in clash))


def check_stats(edition: dict, where: str, report: Report) -> None:
    stats = edition.get("stats")
    if not isinstance(stats, dict):
        return

    def pair(container: dict, label: str) -> tuple[int | None, int | None]:
        acc, sub = container.get("accepted"), container.get("submitted")
        if isinstance(acc, int) and isinstance(sub, int):
            if acc > sub:
                report.error(where, f"{label}accepted ({acc}) exceeds "
                                    f"submitted ({sub})")
            if sub == 0:
                report.error(where, f"{label}submitted is zero")
        return acc, sub

    total_acc, total_sub = pair(stats, "")

    tracks = stats.get("track")
    if isinstance(tracks, list) and tracks:
        sum_acc = sum_sub = 0
        complete = True
        for i, track in enumerate(tracks):
            label = f"track `{track.get('name', i)}`: "
            acc, sub = pair(track, label)
            if acc is None or sub is None:
                complete = False
            else:
                sum_acc += acc
                sum_sub += sub

        if complete and total_acc is not None and total_sub is not None:
            if (sum_acc, sum_sub) != (total_acc, total_sub) and "note" not in stats:
                report.warn(where,
                            f"tracks sum to {sum_acc}/{sum_sub} but the global "
                            f"figures are {total_acc}/{total_sub} — legitimate if "
                            f"papers moved between tracks; add `note` to silence this")

    rate = stats.get("rate")
    if isinstance(rate, (int, float)) and not isinstance(rate, bool):
        if not 0 <= rate <= 100:
            report.error(where, f"rate ({rate}) is not a percentage")
        if total_acc is not None and total_sub:
            computed = 100 * total_acc / total_sub
            if abs(computed - rate) > 1.0:
                report.warn(where, f"rate ({rate}%) disagrees with the counts "
                                   f"({computed:.1f}%) — the counts win")


def gender_totals(gender: dict, *groups: str) -> tuple[int, int, int]:
    women = men = other = 0
    for name in groups:
        counts = gender.get(name) or {}
        women += counts.get("women") or 0
        men += counts.get("men") or 0
        other += counts.get("other") or 0
    return women, men, other


def check_rebuttal(edition: dict, where: str, report: Report) -> None:
    for label, group in deadline_groups(edition):
        prefix = f"{label}: " if label else ""
        start, end = group.get("rebuttal_start"), group.get("rebuttal_end")
        if isinstance(start, date) and isinstance(end, date) and end < start:
            report.error(where, f"{prefix}rebuttal_end ({end}) is before "
                                f"rebuttal_start ({start})")
        if end is not None and start is None:
            report.error(where, f"{prefix}`rebuttal_end` without `rebuttal_start`")
        notification = effective(group, "notification")
        if isinstance(start, date) and isinstance(notification, date) and start > notification:
            report.warn(where, f"{prefix}rebuttal starts ({start}) after "
                               f"notification ({notification})")


def check_review(edition: dict, where: str, report: Report) -> None:
    review = edition.get("review")
    if not isinstance(review, dict):
        return

    gender = review.get("gender")
    if isinstance(gender, dict):
        women, men, other = gender_totals(gender, "chairs", "speakers")
        declared = review.get("gender_balance")
        if women + men + other:
            derived = ("male-only" if women == 0 and other == 0 else
                       "women-only" if men == 0 and other == 0 else "mixed")
            if declared and declared != derived:
                report.warn(where,
                            f"`gender_balance` says {declared!r} but the counts give "
                            f"{derived!r} ({women} women, {men} men"
                            + (f", {other} other" if other else "") + "); "
                            f"the counts win — remove the redundant key")
        elif "chairs" in gender or "speakers" in gender:
            report.warn(where, "`review.gender` has chairs or speakers but every "
                               "count is zero or missing")


RGI_SUBDIVISIONS = {"GB-ENG", "GB-SCT", "GB-WLS"}
RE_DOI = re.compile(r"^10\.\d{4,9}/\S+$")


def check_doi(edition: dict, where: str, report: Report) -> None:
    value = edition.get("proceedings", {}).get("doi")
    items = [value] if isinstance(value, str) else (value or [])
    for doi in items:
        if not isinstance(doi, str):
            continue
        clean = doi.strip()
        if clean.startswith(("http://", "https://", "doi:")):
            report.error(where, f"`doi` must be the bare identifier, not a URL: {doi!r}")
        elif not RE_DOI.match(clean):
            report.warn(where, f"{doi!r} does not look like a DOI (expected 10.xxxx/...)")


def check_event(edition: dict, where: str, report: Report,
                cities: dict, seen_cities: Counter) -> None:
    event = edition.get("event")
    if not isinstance(event, dict):
        return

    start, end = event.get("start"), event.get("end")
    if isinstance(start, date) and isinstance(end, date) and end < start:
        report.error(where, f"event ends ({end}) before it starts ({start})")
    if end is not None and start is None:
        report.error(where, "`event.end` without `event.start`")

    city = event.get("city")
    if isinstance(city, str):
        seen_cities[city] += 1
        if cities and city not in cities:
            report.warn(where, f"city {city!r} is not in cities.toml")
    elif not event.get("online") and start is not None:
        report.warn(where, "no city and not marked online")


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

class Checker:
    def __init__(self, data_dir: Path, report: Report, network: bool = False) -> None:
        self.dir = data_dir
        self.report = report
        self.network = network
        self.enums = load_side_file(data_dir, "enums.toml", report)
        self.cities = load_side_file(data_dir, "cities.toml", report)
        self.publishers = load_side_file(data_dir, "publishers.toml", report)
        self.validator = Validator(self.enums, report)

        self.slugs: dict[str, dict] = {}
        self.editions: dict[str, dict[str, dict]] = defaultdict(dict)
        self.aliases: dict[str, str] = {}
        self.seen_cities: Counter[str] = Counter()
        self.seen_publishers: Counter[str] = Counter()
        self.n_conf = self.n_ed = 0

    # -- pass 1: read and validate each file in isolation -----------------

    def read(self, only: str | None) -> None:
        for directory in sorted(p for p in self.dir.iterdir() if p.is_dir()):
            slug = directory.name
            if only and slug != only:
                continue

            conf_path = directory / "conference.toml"
            if not conf_path.exists():
                self.report.error(f"{slug}/", "no conference.toml")
                continue

            check_slug(slug, f"{slug}/", self.report)
            conf = load_toml(conf_path, self.report)
            if conf is None:
                continue

            where = f"{slug}/conference.toml"
            self.validator.walk(conf, CONFERENCE_SPEC, where)
            for key in CONFERENCE_REQUIRED:
                if key not in conf:
                    self.report.error(where, f"missing required key `{key}`")
            self.check_core(conf, where)

            for alias in conf.get("aliases", []) or []:
                if isinstance(alias, str):
                    check_slug(alias, f"{where} (alias)", self.report)
                    if alias in self.aliases:
                        self.report.error(where, f"alias `{alias}` already claimed "
                                                 f"by `{self.aliases[alias]}`")
                    self.aliases[alias] = slug

            self.slugs[slug] = conf
            self.n_conf += 1
            self.read_editions(directory, slug)

    def check_core(self, conf: dict, where: str) -> None:
        core = conf.get("core")
        if not isinstance(core, dict):
            return
        history = core.get("history")
        if "rank" in core and isinstance(history, list) and history:
            self.report.error(where, "`core.rank` and `core.history` are mutually "
                                     "exclusive: rank is the shorthand for a single "
                                     "known value")
        if isinstance(history, list):
            years = [h.get("from") for h in history if isinstance(h.get("from"), int)]
            for a, b in zip(years, years[1:]):
                if b <= a:
                    self.report.error(where, f"`core.history` must increase by "
                                             f"`from`: {a} is followed by {b}")
            for entry in history:
                if "from" not in entry or "rank" not in entry:
                    self.report.error(where, "each `core.history` entry needs both "
                                             "`from` and `rank`")

    def read_editions(self, directory: Path, slug: str) -> None:
        for path in sorted(directory.glob("*.toml")):
            if path.name == "conference.toml":
                continue

            match = RE_EDITION_FILE.match(path.name)
            if not match:
                self.report.error(f"{slug}/{path.name}",
                                  "edition files must be named YYYY.toml "
                                  "(or YYYYa.toml for a second edition in a year)")
                continue

            where = f"{slug}/{path.name}"
            edition = load_toml(path, self.report)
            if edition is None:
                continue

            self.validator.walk(edition, EDITION_SPEC, where)
            self.editions[slug][match.group(1) + (match.group(2) or "")] = edition
            self.n_ed += 1

            year = int(match.group(1))
            self.check_edition(edition, where, slug, year, directory)

    def check_edition(self, edition: dict, where: str, slug: str,
                      year: int, directory: Path) -> None:
        for label, group in deadline_groups(edition):
            prefix = f"{label}: " if label else ""
            for key in DEADLINE_KEYS:
                values = group.get(key)
                if isinstance(values, list):
                    check_date_list(values, prefix + key, where, self.report)

        check_rounds(edition, where, self.report)
        check_chronology(edition, where, self.report)
        check_stats(edition, where, self.report)
        check_review(edition, where, self.report)
        check_doi(edition, where, self.report)
        check_rebuttal(edition, where, self.report)
        check_event(edition, where, self.report, self.cities, self.seen_cities)

        publisher = edition.get("proceedings", {}).get("publisher")
        if isinstance(publisher, str):
            self.seen_publishers[publisher] += 1
            if self.publishers and publisher not in self.publishers:
                if not self.publisher_alias(publisher):
                    self.report.warn(where, f"publisher {publisher!r} is not in "
                                            f"publishers.toml")

        for i, cfp in enumerate(edition.get("cfp", []) or []):
            name = cfp.get("file")
            if isinstance(name, str) and not (directory / name).exists():
                self.report.error(where, f"cfp[{i}] refers to `{name}`, "
                                         f"which does not exist")

        # A future edition with nothing to show is usually an oversight.
        if year >= date.today().year and "status" not in edition:
            has_deadline = any(effective(g, "paper")
                               for _, g in deadline_groups(edition))
            if not has_deadline:
                self.report.warn(where, "future edition with no paper deadline "
                                        "and no `status`")

    def publisher_alias(self, name: str) -> bool:
        for entry in self.publishers.values():
            if isinstance(entry, dict) and name in (entry.get("aliases") or []):
                return True
        return False

    # -- pass 2: cross-file references ------------------------------------

    def check_references(self) -> None:
        for slug, conf in self.slugs.items():
            where = f"{slug}/conference.toml"

            for other in conf.get("predecessors", []) or []:
                if isinstance(other, str) and other not in self.slugs:
                    self.report.error(where, f"`predecessors` names `{other}`, "
                                             f"which has no directory")
                elif other == slug:
                    self.report.error(where, "`predecessors` names the conference itself")

            if slug in self.aliases:
                self.report.error(where, f"slug `{slug}` is also an alias of "
                                         f"`{self.aliases[slug]}`")

            complete = conf.get("complete_since")
            if isinstance(complete, int) and not 1960 <= complete <= date.today().year + 1:
                self.report.error(where, f"`complete_since` ({complete}) is implausible")

        for slug, editions in self.editions.items():
            for key, edition in editions.items():
                where = f"{slug}/{key}.toml"

                for other in edition.get("event", {}).get("colocated_with", []) or []:
                    match = RE_REF.match(other) if isinstance(other, str) else None
                    if not match:
                        self.report.error(where, f"`colocated_with` entries must look "
                                                 f"like `slug/year`, got {other!r}")
                    elif self.editions.get(match.group(1), {}).get(match.group(2)) is None:
                        self.report.error(where, f"`colocated_with` names `{other}`, "
                                                 f"which does not exist")
                    elif other == f"{slug}/{key}":
                        self.report.error(where, "`colocated_with` names this edition")

                ref = edition.get("joint_with")
                if not isinstance(ref, str):
                    if edition.get("status") == "joint":
                        self.report.error(where, "`status = \"joint\"` requires "
                                                 "`joint_with`")
                    continue

                match = RE_REF.match(ref)
                if not match:
                    self.report.error(where, f"`joint_with` must look like "
                                             f"`slug/year`, got {ref!r}")
                    continue

                target_slug, target_year = match.groups()
                target = self.editions.get(target_slug, {}).get(target_year)
                if target is None:
                    self.report.error(where, f"`joint_with` points at `{ref}`, "
                                             f"which does not exist")
                elif target.get("status") == "joint":
                    self.report.error(where, f"`joint_with` points at `{ref}`, "
                                             f"which is itself a redirect")
                elif edition.get("status") != "joint":
                    self.report.warn(where, "`joint_with` without "
                                            "`status = \"joint\"`")

    # -- pass 3: whole-corpus counters ------------------------------------

    def count_markers(self, only: str | None) -> None:
        for path in sorted(self.dir.rglob("*.toml")):
            if only and path.parent.name != only:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for marker in ("TODO: verify", "TODO: extract"):
                if marker in text:
                    self.report.count(f"marker:{marker}")

    def check_urls(self) -> None:
        import urllib.error
        import urllib.request

        seen: dict[str, int] = {}
        for slug, editions in self.editions.items():
            for key, edition in editions.items():
                url = edition.get("url")
                if not isinstance(url, str) or edition.get("url_dead"):
                    continue
                where = f"{slug}/{key}.toml"
                if url in seen:
                    status = seen[url]
                else:
                    request = urllib.request.Request(
                        url, method="HEAD",
                        headers={"User-Agent": "conferences-computer.science link check"})
                    try:
                        with urllib.request.urlopen(request, timeout=10) as response:
                            status = response.status
                    except urllib.error.HTTPError as exc:
                        status = exc.code
                    except Exception:
                        status = 0
                    seen[url] = status
                if status == 0:
                    self.report.warn(where, f"{url} could not be reached")
                elif status >= 400:
                    self.report.warn(where, f"{url} returns HTTP {status} — "
                                            f"consider `url_dead = true`")


# --------------------------------------------------------------------------

def render(report: Report, checker: Checker, strict: bool) -> None:
    out = sys.stdout

    def section(title: str, items: list[tuple[str, str]]) -> None:
        print(f"\n{title} ({len(items)})", file=out)
        print("-" * 62, file=out)
        by_file: dict[str, list[str]] = defaultdict(list)
        for where, message in items:
            by_file[where].append(message)
        for where in sorted(by_file):
            print(f"  {where}", file=out)
            for message in by_file[where]:
                print(f"      {message}", file=out)

    if report.errors:
        section("ERRORS", report.errors)
    if report.warnings and not report.quiet:
        section("WARNINGS", report.warnings)

    print(f"\n{'=' * 62}", file=out)
    print(f"  {checker.n_conf} conferences, {checker.n_ed} editions", file=out)

    markers = {k[7:]: v for k, v in report.counters.items() if k.startswith("marker:")}
    if markers:
        detail = ", ".join(f"{v} files with {k!r}" for k, v in sorted(markers.items()))
        print(f"  cleanup backlog: {detail}", file=out)

    transitional = {k[13:]: v for k, v in report.counters.items()
                    if k.startswith("transitional:")}
    if transitional:
        detail = ", ".join(f"{k} ×{v}" for k, v in sorted(transitional.items()))
        print(f"  transitional fields still in use: {detail}", file=out)

    missing_cities = sum(1 for c in checker.seen_cities
                         if checker.cities and c not in checker.cities)
    if missing_cities:
        print(f"  {missing_cities}/{len(checker.seen_cities)} distinct cities "
              f"not yet in cities.toml", file=out)

    verdict = "FAILED" if report.errors or (strict and report.warnings) else "OK"
    print(f"  {len(report.errors)} errors, {len(report.warnings)} warnings  →  "
          f"{verdict}", file=out)
    print("=" * 62, file=out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--only", metavar="SLUG")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as errors")
    parser.add_argument("--network", action="store_true",
                        help="also check that edition URLs resolve (slow)")
    parser.add_argument("--quiet", action="store_true",
                        help="hide warnings")
    args = parser.parse_args()

    if not args.data.is_dir():
        print(f"error: {args.data} is not a directory", file=sys.stderr)
        return 2

    report = Report(quiet=args.quiet)
    checker = Checker(args.data, report, network=args.network)
    checker.read(args.only)
    checker.check_references()
    checker.count_markers(args.only)
    if args.network:
        checker.check_urls()

    render(report, checker, args.strict)
    return 1 if report.errors or (args.strict and report.warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
