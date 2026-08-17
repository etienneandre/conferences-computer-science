#!/usr/bin/env python3
"""
build.py — turn the TOML data tree into the static site.

    ./build.py                    # build everything into public/
    ./build.py --only icfem       # one conference, for a quick look
    ./build.py --serve            # build, then serve public/ on :8000
    ./build.py --clean            # remove public/ first

Run `check.py` before this: the generator assumes the data is valid and will
happily render nonsense that the validator would have caught.

The model is built in three passes, because pages need facts that live in other
files: an edition's CORE rank comes from the series, its previous edition comes
from a sibling file, and a joint edition points at another conference entirely.
Passes are:

    1. read      every TOML file into plain dicts
    2. resolve   cross-references, derived values, ordering
    3. render    one page per edition, one per conference
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import calendars

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    from markupsafe import Markup
except ImportError:
    sys.exit("error: Jinja2 is required — pip install jinja2")

HERE = Path(__file__).resolve().parent

# Anywhere on Earth: the last place on the planet where a given date is still
# running. A deadline of the 22nd expires at 12:00 UTC on the 23rd.
AOE = timezone(timedelta(hours=-12))

DEADLINE_KEYS = ("abstract", "paper", "notification", "camera_ready", "registration")

DEADLINE_LABELS = {
    "abstract": "Abstract registration",
    "paper": "Full paper",
    "notification": "Notification",
    "camera_ready": "Camera ready",
    "registration": "Registration",
}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# The first CORE round. Before it there were no ranks to know, so saying
# "unknown before <year>" would invent an absence.
CORE_FIRST_ROUND = 2008


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def load_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


# The only subdivision flags Unicode recommends for general interchange, and so
# the only ones fonts actually draw. A tag sequence for Québec or Catalonia is
# well-formed and renders as nothing at all, which is worse than the national
# flag it would replace.
RGI_SUBDIVISIONS = {"GB-ENG", "GB-SCT", "GB-WLS"}


def flag_emoji(country: str | None, subdivision: str | None = None) -> str:
    """Derive a flag from an ISO code. Never store the emoji itself.

    Regional-indicator pairs cover countries (GB -> the Union flag). The
    constituent nations of the UK need a tag sequence instead, which is why
    `subdivision` exists — England, Scotland and Wales all sit under GB.

    Windows renders these as two boxed letters rather than a flag. That is a
    degradation, not a loss: the reader still sees the country.
    """
    if subdivision and subdivision.upper() not in RGI_SUBDIVISIONS:
        subdivision = None
    if subdivision:
        parts = subdivision.lower().replace("-", "")
        if len(parts) >= 4:
            return ("\U0001F3F4"
                    + "".join(chr(0xE0000 + ord(c)) for c in parts)
                    + "\U000E007F")
    if country and len(country) == 2 and country.isalpha():
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country.upper())
    return ""


def fmt_date(value: date | None, with_year: bool = True) -> str:
    if not isinstance(value, date):
        return ""
    day = f"{value.day} {MONTHS[value.month - 1]}"
    return f"{day} {value.year}" if with_year else day


def fmt_range(start: date | None, end: date | None) -> str:
    """'17-20 Nov 2026', collapsing whatever the two dates share."""
    if not isinstance(start, date):
        return ""
    if not isinstance(end, date) or end == start:
        return fmt_date(start)
    if start.year == end.year and start.month == end.month:
        return f"{start.day}\u2013{end.day} {MONTHS[start.month - 1]} {start.year}"
    if start.year == end.year:
        return (f"{start.day} {MONTHS[start.month - 1]} \u2013 "
                f"{end.day} {MONTHS[end.month - 1]} {start.year}")
    return f"{fmt_date(start)} \u2013 {fmt_date(end)}"


def deadline_instant(value: date, tz_name: str | None) -> datetime:
    """The moment a deadline actually expires, as an instant in UTC.

    Deadlines are inclusive: the 22nd runs until the end of the 22nd. Without a
    declared zone we assume AoE, which is the latest reading and so never tells
    a reader a deadline has passed when it might not have.
    """
    end_of_day = datetime(value.year, value.month, value.day, 23, 59, 59)
    if tz_name and tz_name.upper() != "AOE":
        match = re.fullmatch(r"UTC([+-]\d{1,2})", tz_name.upper())
        if match:
            return end_of_day.replace(
                tzinfo=timezone(timedelta(hours=int(match.group(1))))).astimezone(timezone.utc)
        return end_of_day.replace(tzinfo=timezone.utc)
    return end_of_day.replace(tzinfo=AOE).astimezone(timezone.utc)


def relative_days(target: datetime, now: datetime) -> int:
    """Whole days from now until the deadline expires; negative once passed.

    Truncates towards zero, matching PHP's intdiv() in the front page. Using
    timedelta.days instead would floor towards minus infinity and report a
    deadline that closed 50 and a half days ago as 51 — and, worse, the static
    fallback and the live page would disagree by a day.
    """
    return int((target - now).total_seconds() / 86400)


def humanise(days: int) -> str:
    """Wording must match humanise() in the front page PHP, exactly.

    Past deadlines switch to years after twelve months: "closed 4251 days ago"
    is a number nobody can read, and the precision is meaningless once the
    conference is a decade gone.
    """
    if days < 0:
        n = abs(days)
        if n == 0:
            return "closed today"
        if n <= 365:
            return f"closed {n} day{'s' * (n != 1)} ago"
        years = round(n / 365.25)
        return "closed about a year ago" if years <= 1 else f"closed about {years} years ago"
    if days == 0:
        return "closes today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def step_for(days: int | None) -> str:
    """Five discrete urgency steps, deliberately not a continuous gradient."""
    if days is None or days < 0:
        return "past"
    if days <= 3:
        return "d0"
    if days <= 7:
        return "d1"
    if days <= 14:
        return "d2"
    if days <= 30:
        return "d3"
    return "d4"


def gauge_width(days: int | None) -> int:
    """Length of the 30-day gauge, as a percentage."""
    if days is None or days < 0:
        return 0
    return max(4, min(100, round(100 * days / 30)))


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass
class Deadline:
    key: str
    label: str
    dates: list[date]
    tz: str | None
    round_name: str | None = None

    @property
    def effective(self) -> date:
        return self.dates[-1]

    @property
    def announced(self) -> date:
        return self.dates[0]

    @property
    def extended(self) -> bool:
        return len(self.dates) > 1

    @property
    def extension_days(self) -> int:
        return (self.dates[-1] - self.dates[0]).days if self.extended else 0

    @property
    def steps(self) -> list[dict]:
        """Each extension as its own move, rather than one aggregate jump.

        A deadline pushed twice went 25 May → 1 June → 15 June; saying
        "extended by 21 days" throws away the two dates that were actually
        announced, which is what a reader recognises.
        """
        return [{"was": a, "now": b, "days": (b - a).days}
                for a, b in zip(self.dates, self.dates[1:])]

    # A time zone matters for what an author must upload by a cut-off, not for
    # when a committee happens to reply.
    TZ_RELEVANT = ("abstract", "paper", "camera_ready", "registration")

    @property
    def tz_shown(self) -> str:
        """Only ever shows a declared zone; the assumed one stays internal."""
        return self.tz or "" if self.key in self.TZ_RELEVANT else ""


@dataclass
class Edition:
    slug: str
    key: str
    year: int
    raw: dict
    conference: "Conference" = field(repr=False, default=None)
    deadlines: list[Deadline] = field(default_factory=list)
    previous: "Edition | None" = None
    following: "Edition | None" = None
    colocated: list["Edition"] = field(default_factory=list)
    # When the file this came from was last edited. Used as DTSTAMP, so a
    # calendar entry only changes when its data does — not on every build.
    source_mtime: datetime | None = None

    @property
    def rebuttal_windows(self) -> list[tuple[str, date, date | None]]:
        """Rebuttal periods, one per round when there are rounds.

        A rebuttal belongs to a submission cycle, not to the reviewing model:
        with two rounds there are two rebuttals, at different dates. The fact
        that a conference *has* a rebuttal stays in [review]; when it happens
        lives here, beside the deadlines it follows.
        """
        submission = self.submission
        groups: list[tuple[str, dict]] = [("", submission)]
        for index, group in enumerate(submission.get("round", []) or []):
            groups.append((group.get("name") or f"Round {index + 1}", group))

        windows = []
        for name, group in groups:
            start = group.get("rebuttal_start")
            if isinstance(start, date):
                windows.append((name, start, group.get("rebuttal_end")))
        return windows

    @property
    def has_rebuttal(self) -> bool:
        return bool(self.review.get("rebuttal")) or bool(self.rebuttal_windows)

    @property
    def deadline_groups(self) -> list[tuple[str, list[Deadline]]]:
        """Deadlines grouped by round, in chronological order within each.

        Grouped here rather than in the template because Jinja's groupby sorts
        by the key, and an unnamed round has None for a name.
        """
        buckets: dict[str, list[Deadline]] = {}
        for d in self.deadlines:
            buckets.setdefault(d.round_name or "", []).append(d)
        ordered = sorted(buckets.items(),
                         key=lambda kv: min(d.effective for d in kv[1]))
        return [(name, sorted(items, key=lambda d: d.effective))
                for name, items in ordered]

    # -- identity --------------------------------------------------------
    @property
    def acronym(self) -> str:
        return f"{self.conference.acronym} {self.key}"

    @property
    def url(self) -> str:
        return f"/{self.slug}/{self.key}/"

    @property
    def title(self) -> str:
        explicit = self.raw.get("title")
        if explicit:
            return explicit
        number = self.raw.get("edition")
        return f"{ordinal(number)} {self.conference.name}" if number else self.conference.name

    @property
    def website(self) -> str | None:
        return self.raw.get("url")

    @property
    def website_dead(self) -> bool:
        return bool(self.raw.get("url_dead"))

    @property
    def status(self) -> str | None:
        return self.raw.get("status")

    @property
    def listed(self) -> bool:
        return self.status is None or self.status == "announced"

    # -- event -----------------------------------------------------------
    @property
    def event(self) -> dict:
        return self.raw.get("event", {}) or {}

    @property
    def starts(self) -> date | None:
        return self.event.get("start")

    @property
    def held(self) -> str:
        span = fmt_range(self.starts, self.event.get("end"))
        return span or self.event.get("dates_text", "")

    @property
    def online(self) -> bool:
        return bool(self.event.get("online"))

    # -- submission ------------------------------------------------------
    @property
    def submission(self) -> dict:
        return self.raw.get("submission", {}) or {}

    @property
    def tz(self) -> str | None:
        return self.submission.get("tz")

    @property
    def paper(self) -> Deadline | None:
        """The deadline the list sorts on: the next upcoming, else the last past."""
        papers = [d for d in self.deadlines if d.key == "paper"]
        if not papers:
            return None
        today = date.today()
        upcoming = [d for d in papers if d.effective >= today]
        return min(upcoming, key=lambda d: d.effective) if upcoming else \
            max(papers, key=lambda d: d.effective)

    @property
    def current_round(self) -> str | None:
        """The round the sorting deadline belongs to, or None without rounds."""
        paper = self.paper
        return paper.round_name if paper else None

    def deadline(self, key: str) -> Deadline | None:
        """The relevant date for `key`, in the round that is actually open.

        With two rounds, round 1 having closed, the notification a reader wants
        is round 2's — not the earliest on file, which belongs to a cycle that
        has already ended.
        """
        found = [d for d in self.deadlines if d.key == key]
        if not found:
            return None

        current = self.current_round
        if current is not None:
            same_round = [d for d in found if d.round_name == current]
            if same_round:
                found = same_round

        today = date.today()
        upcoming = [d for d in found if d.effective >= today]
        if upcoming:
            return min(upcoming, key=lambda d: d.effective)
        return max(found, key=lambda d: d.effective)

    @property
    def has_rounds(self) -> bool:
        return bool(self.submission.get("round"))

    @property
    def extensions_known_undated(self) -> bool:
        return self.submission.get("extensions") is True

    @property
    def extensions_ruled_out(self) -> bool:
        return self.submission.get("extensions") is False

    # -- proceedings -----------------------------------------------------
    @property
    def proceedings(self) -> dict:
        return self.raw.get("proceedings", {}) or {}

    @property
    def dois(self) -> list[str]:
        """Proceedings DOIs. A list, because a volume can be split in two."""
        value = self.proceedings.get("doi")
        if isinstance(value, str):
            return [value]
        return [d for d in (value or []) if isinstance(d, str)]

    @property
    def post_proceedings(self) -> bool:
        return bool(self.proceedings.get("post"))

    # -- other -----------------------------------------------------------
    @property
    def review(self) -> dict:
        return self.raw.get("review", {}) or {}

    @property
    def stats(self) -> dict:
        return self.raw.get("stats", {}) or {}

    @property
    def rate(self) -> float | None:
        counts = self.counts
        if counts and counts[1]:
            return 100 * counts[0] / counts[1]
        explicit = self.stats.get("rate")
        return float(explicit) if isinstance(explicit, (int, float)) else None

    @property
    def tracks(self) -> list[dict]:
        """Per-category figures, each with its own rate."""
        result = []
        for track in self.stats.get("track", []) or []:
            accepted, submitted = track.get("accepted"), track.get("submitted")
            if not (isinstance(accepted, int) and isinstance(submitted, int) and submitted):
                continue
            result.append({
                "name": track.get("name") or "unnamed",
                "accepted": accepted,
                "submitted": submitted,
                "rate": 100 * accepted / submitted,
            })
        return result

    @property
    def cfps(self) -> list[dict]:
        """Calls for this edition, newest first.

        Order in the file is the publication order — the collected files carry
        no dates, so nothing else can tell an extension from the call it
        replaced. Dated entries sort by date; undated ones keep their position.
        """
        items = list(self.raw.get("cfp", []) or [])
        dated = [c for c in items if isinstance(c.get("retrieved"), date)]
        if len(dated) == len(items) and items:
            return sorted(items, key=lambda c: c["retrieved"], reverse=True)
        return list(reversed(items))

    @property
    def cfp_readable(self) -> list[dict]:
        """The ones worth showing as text: calls for papers in a text format."""
        return [c for c in self.cfps
                if not c.get("kind")
                and str(c.get("file", "")).rsplit(".", 1)[-1].lower() in ("txt", "md", "text")]

    @property
    def cfp_attachments(self) -> list[dict]:
        readable = {id(c) for c in self.cfp_readable}
        return [c for c in self.cfps if id(c) not in readable]

    @property
    def extra(self) -> dict:
        return self.raw.get("extra", {}) or {}

    # -- gender balance --------------------------------------------------
    @property
    def gender(self) -> dict:
        return self.review.get("gender", {}) or {}

    @staticmethod
    def _heads(counts: dict | None) -> tuple[int, int, int]:
        counts = counts or {}
        return (int(counts.get("women") or 0),
                int(counts.get("men") or 0),
                int(counts.get("other") or 0))

    @staticmethod
    def _phrase(women: int, men: int, other: int) -> str:
        """"1 man, 2 women" — alphabetical, and singular when it should be.

        Alphabetical order rather than any other: any deliberate ordering of
        the categories would be read as a ranking, and there is no reason to
        invite that reading.
        """
        parts = []
        for count, one, many in ((men, "man", "men"),
                                 (other, "other", "others"),
                                 (women, "woman", "women")):
            if count or (count == 0 and one != "other"):
                parts.append(f"{count} {one if count == 1 else many}")
        return ", ".join(parts)

    @property
    def gender_counts(self) -> dict | None:
        """Chairs and invited speakers, counted. None when nothing is recorded.

        The programme committee is deliberately excluded: the claim the site
        makes is about who was *chosen to lead* an edition, and a large mixed
        committee should not offset an all-male set of chairs and speakers.
        Committee figures are recorded and shown, but never enter the verdict.
        """
        gender = self.gender
        if not any(k in gender for k in ("chairs", "speakers")):
            return None

        cw, cm, co = self._heads(gender.get("chairs"))
        sw, sm, so = self._heads(gender.get("speakers"))
        women, men, other = cw + sw, cm + sm, co + so
        if women + men + other == 0:
            return None

        return {
            "chairs": {"women": cw, "men": cm, "other": co, "total": cw + cm + co,
                       "phrase": self._phrase(cw, cm, co)},
            "speakers": {"women": sw, "men": sm, "other": so, "total": sw + sm + so,
                         "phrase": self._phrase(sw, sm, so)},
            "women": women, "men": men, "other": other,
            "total": women + men + other,
        }

    @property
    def committee_counts(self) -> dict | None:
        women, men, other = self._heads(self.gender.get("committee"))
        total = women + men + other
        if total == 0:
            return None
        return {"women": women, "men": men, "other": other, "total": total,
                "share": round(100 * women / total),
                "phrase": self._phrase(women, men, other)}

    @property
    def gender_balance(self) -> str | None:
        """Derived from the counts when they exist, else the recorded value.

        The rule, stated so it can be checked: an edition counts as male-only
        when at least one chair or invited speaker is recorded, and none of
        them is a woman or a person of another gender.
        """
        counts = self.gender_counts
        if counts is None:
            return self.review.get("gender_balance")
        if counts["women"] == 0 and counts["other"] == 0:
            return "male-only"
        if counts["men"] == 0 and counts["other"] == 0:
            return "women-only"
        return "mixed"

    @property
    def core_rank(self) -> str | None:
        return self.conference.rank_for(self.year)

    # -- flattened accessors, so templates never reach into raw dicts ----
    @property
    def is_latest(self) -> bool:
        """The most recent edition of its series that we know about."""
        return self.following is None

    @property
    def city_name(self) -> str | None:
        return self.event.get("city")

    @property
    def format(self) -> str | None:
        return self.submission.get("format")

    @property
    def counts(self) -> tuple[int, int] | None:
        """Accepted and submitted overall.

        Falls back to the sum of the tracks when no global figure is recorded:
        a conference that publishes only per-track numbers still has an overall
        rate, and leaving it out made those editions vanish from every chart.
        """
        accepted, submitted = self.stats.get("accepted"), self.stats.get("submitted")
        if isinstance(accepted, int) and isinstance(submitted, int):
            return accepted, submitted

        tracks = self.tracks
        if tracks:
            return (sum(t["accepted"] for t in tracks),
                    sum(t["submitted"] for t in tracks))
        return None

    @property
    def counts_are_summed(self) -> bool:
        """True when the overall figure was added up rather than published."""
        return ("accepted" not in self.stats or "submitted" not in self.stats) \
               and bool(self.tracks)

    @property
    def colocated_refs(self) -> list[str]:
        refs = self.event.get("colocated_with") or []
        return [r for r in refs if isinstance(r, str)]

    @property
    def joint_target(self) -> tuple[str, str] | None:
        ref = self.raw.get("joint_with")
        if isinstance(ref, str) and "/" in ref:
            slug, _, key = ref.partition("/")
            return slug, key
        return None


@dataclass
class Conference:
    slug: str
    raw: dict
    editions: list[Edition] = field(default_factory=list)
    successors: list["Conference"] = field(default_factory=list)
    predecessors: list["Conference"] = field(default_factory=list)

    @property
    def acronym(self) -> str:
        return self.raw["acronym"]

    @property
    def name(self) -> str:
        return self.raw["name"]

    @property
    def url(self) -> str:
        return f"/{self.slug}/"

    @property
    def links(self) -> dict:
        return self.raw.get("links", {}) or {}

    @property
    def core_id(self) -> str | None:
        return (self.raw.get("core", {}) or {}).get("id")

    @property
    def core_history(self) -> list[dict]:
        core = self.raw.get("core", {}) or {}
        history = core.get("history")
        if history:
            return sorted(history, key=lambda h: h["from"])
        if "rank" in core:
            return [{"from": min((e.year for e in self.editions), default=0),
                     "rank": core["rank"], "assumed": True}]
        return []

    def rank_for(self, year: int) -> str | None:
        """Unknown before the first recorded entry — not 'absent'."""
        applicable = [h for h in self.core_history if h["from"] <= year]
        return applicable[-1]["rank"] if applicable else None

    @property
    def rank_predates_core(self) -> bool:
        """True when our earliest recorded rank goes back to the first round."""
        history = self.core_history
        return bool(history) and history[0]["from"] <= CORE_FIRST_ROUND

    @property
    def current_rank(self) -> str | None:
        history = self.core_history
        return history[-1]["rank"] if history else None

    @property
    def frequency(self) -> str | None:
        return self.raw.get("frequency")

    @property
    def scope(self) -> str | None:
        return self.raw.get("scope")

    @property
    def languages(self) -> list:
        return self.raw.get("languages", []) or []

    @property
    def core_national_of(self) -> str | None:
        return (self.raw.get("core", {}) or {}).get("national_of")

    @property
    def aliases(self) -> list:
        return self.raw.get("aliases", []) or []

    @property
    def first_year(self) -> int | None:
        return min((e.year for e in self.editions), default=None)

    @property
    def last_year(self) -> int | None:
        return max((e.year for e in self.editions), default=None)

    @property
    def defunct(self):
        return self.raw.get("defunct")

    @property
    def one_off(self) -> bool:
        return bool(self.raw.get("one_off"))

    @property
    def complete_since(self) -> int | None:
        return self.raw.get("complete_since")

    @property
    def legacy(self) -> dict:
        return self.raw.get("legacy", {}) or {}

    @property
    def listed_editions(self) -> list[Edition]:
        return sorted(self.editions, key=lambda e: e.year, reverse=True)

    @property
    def rated_editions(self) -> list[Edition]:
        return [e for e in sorted(self.editions, key=lambda e: e.year, reverse=True)
                if e.rate is not None]

    @property
    def missing_years(self) -> list[int]:
        """Years with no file, inside the range we claim to cover."""
        if not self.complete_since or not self.editions:
            return []
        present = {e.year for e in self.editions}
        latest = max(present)
        return [y for y in range(self.complete_since, latest + 1) if y not in present]

    @property
    def extension_summary(self) -> dict:
        """What an author actually wants to know: does this one extend?

        Three buckets, not two. A single-date deadline list means no earlier
        date was recorded — which is not the same as knowing there was no
        extension. Counting those as firm would inflate the denominator and
        make the conference look more reliable than the data supports; only
        `extensions = false` says so.
        """
        extended = firm = unknown = 0
        spans: list[int] = []

        for edition in self.editions:
            paper = edition.deadline("paper")
            if paper and paper.extended:
                extended += 1
                spans.append(paper.extension_days)
            elif edition.extensions_known_undated:
                extended += 1
            elif edition.extensions_ruled_out:
                firm += 1
            elif paper:
                unknown += 1

        known = extended + firm
        if spans:
            low, high = min(spans), max(spans)
            typical = f"{low} days" if low == high else f"{low}\u2013{high} days"
        else:
            typical = None

        return {
            "extended": extended,
            "firm": firm,
            "unknown": unknown,
            "known": known,
            "typical": typical,
            # Only worth a separate line when the extensions were not all the
            # same length; otherwise it just repeats `typical`.
            "varied": bool(spans) and min(spans) != max(spans),
            "longest": max(spans) if spans else None,
        }


def ordinal(n: int | None) -> str:
    if not isinstance(n, int):
        return ""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# --------------------------------------------------------------------------
# Site
# --------------------------------------------------------------------------

class Site:
    def __init__(self, config: dict, root: Path) -> None:
        self.config = config
        self.root = root
        self.data_dir = root / config["build"]["data"]
        self.out_dir = root / config["build"]["output"]

        self.enums = self._side("enums.toml")
        self.cities = self._side("cities.toml")
        self.publishers = self._side("publishers.toml")

        self.conferences: dict[str, Conference] = {}
        self.editions: list[Edition] = []
        self.now = datetime.now(timezone.utc)
        self.warnings: list[str] = []

    def _side(self, name: str) -> dict:
        path = self.data_dir / name
        return load_toml(path) if path.exists() else {}

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    # -- pass 1 ---------------------------------------------------------
    def read(self, only: str | None = None) -> None:
        for directory in sorted(p for p in self.data_dir.iterdir() if p.is_dir()):
            slug = directory.name
            if only and slug != only:
                continue
            conf_file = directory / "conference.toml"
            if not conf_file.exists():
                continue

            conference = Conference(slug=slug, raw=load_toml(conf_file))
            self.conferences[slug] = conference

            for path in sorted(directory.glob("*.toml")):
                if path.name == "conference.toml":
                    continue
                match = re.fullmatch(r"((?:19|20)\d{2})([a-z]?)\.toml", path.name)
                if not match:
                    continue
                key = match.group(1) + match.group(2)
                edition = Edition(slug=slug, key=key, year=int(match.group(1)),
                                  raw=load_toml(path), conference=conference)
                edition.source_mtime = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc)
                conference.editions.append(edition)
                self.editions.append(edition)

    # -- pass 2 ---------------------------------------------------------
    def resolve(self) -> None:
        for conference in self.conferences.values():
            for other in conference.raw.get("predecessors", []) or []:
                parent = self.conferences.get(other)
                if parent:
                    conference.predecessors.append(parent)
                    parent.successors.append(conference)

            ordered = sorted(conference.editions, key=lambda e: e.year)
            for previous, following in zip(ordered, ordered[1:]):
                previous.following = following
                following.previous = previous

        for edition in self.editions:
            edition.deadlines = self._deadlines(edition)

        self._link_colocated()

    def _link_colocated(self) -> None:
        """Resolve `event.colocated_with`, and make the relation symmetric.

        Co-location is mutual, but declaring it twice invites the two halves to
        disagree. Declare it once, on either edition, and the other side is
        derived — so a page can never claim a partnership the partner denies.
        """
        by_key: dict[str, Edition] = {}
        for edition in self.editions:
            by_key[f"{edition.slug}/{edition.key}"] = edition

        for edition in self.editions:
            for ref in edition.colocated_refs:
                other = by_key.get(ref)
                if other is None:
                    self.warn(f"{edition.slug}/{edition.key}: colocated_with "
                              f"names {ref!r}, which does not exist")
                    continue
                if other is edition:
                    self.warn(f"{edition.slug}/{edition.key}: colocated with itself")
                    continue
                if other not in edition.colocated:
                    edition.colocated.append(other)
                if edition not in other.colocated:
                    other.colocated.append(edition)

        for edition in self.editions:
            edition.colocated.sort(key=lambda e: e.acronym)

    @staticmethod
    def _deadlines(edition: Edition) -> list[Deadline]:
        submission = edition.submission
        tz = submission.get("tz")
        groups: list[tuple[str | None, dict]] = [(None, submission)]
        for index, group in enumerate(submission.get("round", []) or []):
            groups.append((group.get("name") or f"Round {index + 1}", group))

        found: list[Deadline] = []
        for name, group in groups:
            for key in DEADLINE_KEYS:
                dates = group.get(key)
                if isinstance(dates, list) and dates:
                    found.append(Deadline(key=key, label=DEADLINE_LABELS[key],
                                          dates=list(dates), tz=tz, round_name=name))
        return found

    # -- lookups used by templates --------------------------------------
    def city(self, name: str | None) -> dict:
        """Always returns the same shape, so templates can test one key."""
        if not name:
            return {"name": None, "display": "", "flag": ""}
        # Test membership, not truthiness: an entry that exists but holds no
        # keys yet is a city awaiting its coordinates, not a missing one.
        if name not in self.cities:
            self.warn(f"city not in cities.toml: {name}")
        entry = dict(self.cities.get(name) or {})
        entry.setdefault("display", name.split(",")[0].strip())
        entry["flag"] = flag_emoji(entry.get("country"), entry.get("subdivision"))
        entry["name"] = name
        return entry

    def licence(self, key: str | None) -> dict:
        if not key:
            return {"label": None, "openness": "no"}
        found = (self.enums.get("license", {}) or {}).get(key)
        if not found:
            return {"label": key, "css": ""}
        entry = dict(found)
        entry["key"] = key
        entry["openness"] = ("yes" if entry.get("open_license")
                             else "free" if entry.get("free_to_read") else "no")
        return entry

    def publisher(self, name: str | None) -> dict:
        """Always the same shape, so templates can test one key."""
        if not name:
            return {"name": None}
        entry = dict(self.publishers.get(name, {}))
        if not entry:
            for canonical, value in self.publishers.items():
                if name in (value.get("aliases") or []):
                    entry = dict(value)
                    entry["canonical"] = canonical
                    break
        entry["name"] = name
        return entry

    def enum(self, group: str, key) -> dict:
        if not isinstance(key, str):
            return {}
        return dict((self.enums.get(group, {}) or {}).get(key, {}))

    # -- countdown helpers ----------------------------------------------
    def countdown(self, deadline: Deadline | None) -> dict:
        if deadline is None:
            return {"step": "past", "width": 0, "text": "", "days": None,
                    "expires": None}
        instant = deadline_instant(deadline.effective, deadline.tz or None)
        days = relative_days(instant, self.now)
        return {"step": step_for(days), "width": gauge_width(days),
                "text": humanise(days), "days": days,
                # The exact moment, in UTC, so a browser can say "in 7 hours"
                # on a page the server only rebuilds once a day.
                "expires": instant.strftime("%Y-%m-%dT%H:%M:%SZ")}


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def asset_version(site: Site) -> str:
    """A short hash of the CSS and JavaScript, appended to their URLs.

    The server is told to cache assets for a year, which is only safe if the
    URL changes when the file does. Without this, a visitor who saw the site
    last month keeps last month's stylesheet against this month's markup.
    """
    digest = hashlib.sha256()
    folder = site.root / site.config["build"]["assets"]
    for name in sorted(("site.css", "filters.js", "map.js", "countdown.js")):
        path = folder / name
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:8]


def load_fragment(site: Site, name: str) -> Markup:
    """Read pages/<name>.html verbatim.

    These are the paragraphs you have rewritten in your own voice. Keeping them
    in pages/ rather than in a template means a new version of the site chrome
    cannot quietly replace them.
    """
    path = site.root / "pages" / f"{name}.html"
    if not path.exists():
        return Markup("")
    text = path.read_text(encoding="utf-8")
    return Markup(RE_MD_COMMENT.sub("", text).strip())


def build_environment(site: Site) -> Environment:
    env = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["date"] = fmt_date
    env.filters["daterange"] = lambda pair: fmt_range(pair[0], pair[1])
    env.filters["ordinal"] = ordinal
    env.globals.update(
        fragment=lambda name: load_fragment(site, name),
        cfp_text=lambda edition, cfp: read_cfp_text(site, edition, cfp),
        asset_version=asset_version(site),
        site=site,
        config=site.config,
        now=site.now,
        today=date.today(),
        city=site.city,
        licence=site.licence,
        publisher=site.publisher,
        enum=site.enum,
        countdown=site.countdown,
        flag=flag_emoji,
    )
    return env


# Counters, so a build can say how much actually moved.
WRITTEN = Counter()


def write(path: Path, text: str) -> None:
    """Write only when the content differs.

    Rewriting an identical file changes its modification time, and lftp mirror
    compares size and time — so a build that touches everything makes every
    deploy upload everything. Skipping unchanged files means a deploy transfers
    exactly what changed, which on this site is usually a handful of pages out
    of fifteen hundred.
    """
    data = text.encode("utf-8")
    if path.exists():
        try:
            if path.read_bytes() == data:
                WRITTEN["unchanged"] += 1
                return
        except OSError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    WRITTEN["written"] += 1


def render(site: Site, env: Environment) -> int:
    pages = 0
    edition_tpl = env.get_template("edition.html.j2")
    conference_tpl = env.get_template("conference.html.j2")

    for conference in site.conferences.values():
        out = site.out_dir / conference.slug / "index.html"
        write(out, conference_tpl.render(conference=conference))
        pages += 1

        # Renamed conferences keep their old URLs alive.
        for alias in conference.raw.get("aliases", []) or []:
            write(site.out_dir / alias / "index.html",
                  redirect_page(conference.url, conference.acronym))
            pages += 1

        for edition in conference.editions:
            out = site.out_dir / conference.slug / edition.key / "index.html"
            write(out, edition_tpl.render(edition=edition, conference=conference))
            pages += 1

    return pages


# --------------------------------------------------------------------------
# Front page
#
# The list depends on today's date, so it cannot be fully static. Rather than
# teaching PHP about the data, the build pre-renders every row with four
# markers standing in for the parts that move, and PHP substitutes them. PHP
# therefore never parses TOML, never knows what a licence is, and cannot drift
# from the generator.
# --------------------------------------------------------------------------

def tags_for(site: "Site", edition: Edition) -> str:
    """Filter tags, baked into the row so filtering is a class toggle.

    `latest` and `defunct` are what keep the default view usable: without them
    the unfiltered list is every edition ever recorded, which is thousands of
    rows and no help to anybody.
    """
    tags = []
    paper = edition.paper
    if paper and deadline_instant(paper.effective, paper.tz) > site.now:
        tags.append("upcoming")
    if edition.is_latest:
        tags.append("latest")
    if edition.conference.defunct or edition.conference.one_off:
        tags.append("defunct")
    if edition.core_rank in ("A*", "A"):
        tags.append("rank-a")
    lic = site.licence(edition.proceedings.get("license"))
    if lic.get("open_license") or lic.get("free_to_read"):
        tags.append("open-access")
    continent = site.city(edition.city_name).get("continent")
    if continent == "EU":
        tags.append("europe")
    elif continent == "AS":
        tags.append("asia")
    return " ".join(tags)


CONTINENT_NAMES = {"EU": "Europe", "AS": "Asia", "NA": "North America",
                   "SA": "South America", "AF": "Africa", "OC": "Oceania"}


def search_text(site: "Site", edition: Edition) -> str:
    """Everything a reader might type, gathered into one attribute.

    Flags replaced country names in the visible row, which silently broke
    searching for "France". Rather than putting the country back and undoing
    the space we gained, the row carries a hidden index: the full place string
    as written in cities.toml (which contains the country), its ISO code, the
    continent in words, and the conference's full title, which never appeared
    in the row at all.
    """
    place = site.city(edition.city_name)
    parts = [
        edition.acronym, edition.conference.acronym, edition.conference.name,
        edition.title, place.get("name") or "", place.get("display") or "",
        place.get("country") or "", CONTINENT_NAMES.get(place.get("continent"), ""),
        edition.proceedings.get("publisher") or "",
        site.licence(edition.proceedings.get("license")).get("label") or "",
        "online" if edition.online else "",
    ]
    for alias in edition.conference.aliases:
        parts.append(alias)
    seen, words = set(), []
    for part in " ".join(str(p) for p in parts if p).lower().split():
        word = part.strip(",.()")
        if word and word not in seen:
            seen.add(word)
            words.append(word)
    return " ".join(words)


def front_rows(site: "Site", env: Environment) -> list[dict]:
    """Every listed edition, pre-rendered, with its expiry as a UTC timestamp."""
    template = env.get_template("_row.html.j2")
    rows = []
    for edition in site.editions:
        if not edition.listed:
            continue
        paper = edition.paper
        if paper is None:
            continue
        expires = deadline_instant(paper.effective, paper.tz)
        tags = tags_for(site, edition)
        rows.append({
            "ts": int(expires.timestamp()),
            "tags": tags,
            "html": template.render(edition=edition,
                                    conference=edition.conference,
                                    tags=tags,
                                    search=search_text(site, edition),
                                    # Details are carried inline only for the
                                    # current edition of a live series: those
                                    # are the rows a reader actually opens.
                                    with_detail=("latest" in tags.split()
                                                 and "defunct" not in tags.split())),
        })
    return rows


def order_rows(rows: list[dict], now_ts: int) -> list[dict]:
    """Soonest deadline first; once past, most recently closed first.

    Sorting lives here as well as in PHP so the static fallback and the live
    page cannot disagree about the order.
    """
    upcoming = sorted((r for r in rows if r["ts"] >= now_ts), key=lambda r: r["ts"])
    past = sorted((r for r in rows if r["ts"] < now_ts), key=lambda r: -r["ts"])
    return upcoming + past


def fill_row(html: str, ts: int, now_ts: int) -> str:
    """Substitute the parts of a pre-rendered row that depend on today."""
    # Truncate towards zero, as PHP's intdiv() does. Floor division ( // )
    # would make the static fallback disagree with the live page by one day on
    # every past deadline.
    days = int((ts - now_ts) / 86400)
    expires = datetime.fromtimestamp(ts, tz=timezone.utc)
    return (html.replace("@@STEP@@", step_for(days))
                .replace("@@WIDTH@@", f"{gauge_width(days)}%")
                .replace("@@COUNT@@", humanise(days))
                .replace("@@EXPIRES@@", expires.strftime("%Y-%m-%dT%H:%M:%SZ"))
                .replace("@@PAST@@", "" if days >= 0 else " is-past"))


def render_front(site: "Site", env: Environment) -> int:
    """Build the front page: shell, row data, static fallback, and the PHP.

    Everything is keyed by a fingerprint of the generated content. Dating the
    cache alone is not enough: a rebuild on the same day — or a deploy — would
    leave yesterday's HTML in place until midnight, and the browser would pair
    it with the new JavaScript. That failure is silent and total, so the cache
    key has to move whenever the content does.
    """
    rows = front_rows(site, env)
    now_ts = int(site.now.timestamp())
    ordered = order_rows(rows, now_ts)

    counts = Counter()
    for row in ordered:
        counts["total"] += 1
        for tag in row["tags"].split():
            counts[tag] += 1
    # A plain dict, not the Counter: Counter.total is a method in Python 3.10+,
    # so `counts.total` in a template renders the bound method rather than the
    # number. `total` counts what is visible by default — the latest edition of
    # each live series — not every row in the table.
    visible = sum(1 for r in ordered
                  if "latest" in r["tags"].split() and "defunct" not in r["tags"].split())
    counts = {key: counts.get(key, 0)
              for key in ("upcoming", "open-access", "rank-a", "europe", "asia", "defunct")}
    counts["total"] = visible
    counts["earlier"] = len(ordered) - sum(
        1 for r in ordered if "latest" in r["tags"].split())

    shell = env.get_template("front.html.j2").render(counts=counts)
    name = site.config["site"]["front_page"]

    payload = shell + "".join(r["html"] for r in ordered)
    fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    site.fingerprint = fingerprint

    # 1. The shell, with a marker where the rows go.
    write(site.out_dir / "_data" / "shell.html", shell)

    # 2. The rows, as a PHP array. A .php file is never served as source, so
    #    the data cannot be fetched directly whatever the server config.
    # No build timestamp here: it would change on every run and make this file
    # the one thing a deploy always re-uploads. The stamp that matters is in
    # the page itself, where a reader can see it.
    lines = ["<?php", "// Generated by build.py — do not edit.", "return ["]
    for row in ordered:
        lines.append("  [%d, %s]," % (row["ts"], php_string(row["html"])))
    lines.append("];")
    write(site.out_dir / "_data" / "rows.php", "\n".join(lines) + "\n")
    write(site.out_dir / "_data" / "version.txt", fingerprint + "\n")

    # A shared secret that lets you force a rebuild from a browser. Without it
    # the only way to test the cache on the live server is to wait for midnight
    # UTC or delete a file over FTP. Leave `debug_token` empty in site.toml to
    # switch the feature off entirely.
    token = str(site.config.get("build", {}).get("debug_token") or "").strip()
    write(site.out_dir / "_data" / "token.txt", token + "\n")

    # Any cache from an earlier build is now wrong: its HTML predates the
    # assets sitting beside it. Remove it here as well as keying by
    # fingerprint, so a local rebuild is clean even before the first request.
    for stale in (site.out_dir / "cache").glob("front-*.html"):
        stale.unlink()

    # 3. The static fallback, correct as of the build.
    filled = "\n".join(fill_row(r["html"], r["ts"], now_ts) for r in ordered)
    fallback = (shell.replace("<!--ROWS-->", filled)
                     .replace("<!--ORDERED-->", site.now.strftime("%-d %b %Y, %H:%M") + " UTC")
                     .replace("<!--ORDERED-ISO-->", site.now.strftime("%Y-%m-%d")))
    write(site.out_dir / f"{name}.fallback.html", fallback)

    # 4. The live page.
    write(site.out_dir / f"{name}.php", front_php(name))

    return len(ordered)


FRONT_PHP = r"""<?php
/**
 * @@NAME@@.php — the front page.
 *
 * The list is ordered by what closes next, so it changes every day and cannot
 * be a static file. It is also the same for every visitor on a given day, so
 * it is built once and then served from a cache: as fast as static, always
 * correct.
 *
 * This file knows nothing about the data. The generator pre-renders each row
 * and leaves four markers for the parts that depend on today's date; all this
 * does is sort, substitute and concatenate. Nothing here can drift out of step
 * with the generator, because there is nothing here to drift.
 *
 * Any failure at all falls through to the static fallback, which the build
 * writes with the ordering as of the last deploy. The worst case is an order a
 * few days stale, never a blank page.
 */

declare(strict_types=1);

const CACHE_DIR = __DIR__ . '/cache';
const FALLBACK  = __DIR__ . '/@@NAME@@.fallback.html';
const DATA_DIR  = __DIR__ . '/_data';
const KEEP_DAYS = 7;

function serve_fallback(): void
{
    if (is_readable(FALLBACK)) {
        readfile(FALLBACK);
    } else {
        http_response_code(500);
        echo '<!DOCTYPE html><meta charset="utf-8"><title>Temporarily unavailable</title>'
           . '<p>The list is temporarily unavailable. Please try again shortly.</p>';
    }
    exit;
}

/** Days until a deadline expires; negative once it has passed. */
function days_until(int $expires, int $now): int
{
    return intdiv($expires - $now, 86400);
}

/** Five discrete urgency steps, matching step_for() in build.py. */
function step_for(int $days): string
{
    if ($days < 0)  return 'past';
    if ($days <= 3) return 'd0';
    if ($days <= 7) return 'd1';
    if ($days <= 14) return 'd2';
    if ($days <= 30) return 'd3';
    return 'd4';
}

function gauge_width(int $days): int
{
    if ($days < 0) return 0;
    return max(4, min(100, (int) round(100 * $days / 30)));
}

/** Must match humanise() in build.py, word for word. */
function humanise(int $days): string
{
    if ($days < 0) {
        $n = abs($days);
        if ($n === 0) return 'closed today';
        if ($n <= 365) return sprintf('closed %d day%s ago', $n, $n === 1 ? '' : 's');
        $years = (int) round($n / 365.25);
        return $years <= 1 ? 'closed about a year ago'
                           : sprintf('closed about %d years ago', $years);
    }
    if ($days === 0) return 'closes today';
    if ($days === 1) return 'tomorrow';
    return sprintf('in %d days', $days);
}

/** Remove yesterday's caches. Cheap, and stops the directory growing forever. */
function sweep_cache(string $keepFile): void
{
    // Anything from a previous build is dead the moment a new one lands, so
    // sweep by name as well as by age.
    $cutoff = time() - KEEP_DAYS * 86400;
    foreach (glob(CACHE_DIR . '/front-*.html') ?: [] as $old) {
        if ($old === $keepFile) continue;
        if (@filemtime($old) < $cutoff || basename($old) !== basename($keepFile)) {
            @unlink($old);
        }
    }
}

/**
 * Write atomically: a temporary file in the same directory, then rename.
 * rename() is atomic on one filesystem, so a second request arriving mid-write
 * never sees a truncated page.
 */
function cache_write(string $target, string $html): void
{
    $tmp = @tempnam(CACHE_DIR, 'front');
    if ($tmp === false) return;
    if (@file_put_contents($tmp, $html) === false) { @unlink($tmp); return; }
    @chmod($tmp, 0644);
    if (!@rename($tmp, $target)) { @unlink($tmp); }
}

// The cache key carries both the day and a fingerprint of the generated
// content. The day makes the countdowns refresh; the fingerprint makes a
// rebuild or a deploy take effect at once, instead of serving yesterday's HTML
// next to today's JavaScript until midnight.
$version = @file_get_contents(DATA_DIR . '/version.txt');
$version = is_string($version) ? trim($version) : 'x';
$cacheFile = CACHE_DIR . '/front-' . gmdate('Y-m-d') . '-' . $version . '.html';

// ?refresh=<token> rebuilds now and reports what happened, so the cache can be
// exercised on the live server without waiting for midnight UTC. The token is
// set in site.toml; an empty token disables this entirely.
$token = @file_get_contents(DATA_DIR . '/token.txt');
$token = is_string($token) ? trim($token) : '';
$forced = $token !== ''
       && isset($_GET['refresh'])
       && hash_equals($token, (string) $_GET['refresh']);
if ($forced) {
    @unlink($cacheFile);
}

if (!$forced && is_readable($cacheFile)) {
    header('Content-Type: text/html; charset=utf-8');
    header('X-Front-Cache: hit');
    readfile($cacheFile);
    exit;
}

try {
    $shell = @file_get_contents(DATA_DIR . '/shell.html');
    if ($shell === false) serve_fallback();

    /** @var array<int, array{0:int,1:string}> $rows */
    $rows = @include DATA_DIR . '/rows.php';
    if (!is_array($rows)) serve_fallback();

    $now = time();

    // Soonest first while open; once closed, most recently closed first.
    $upcoming = $past = [];
    foreach ($rows as $row) {
        if ($row[0] >= $now) { $upcoming[] = $row; } else { $past[] = $row; }
    }
    usort($upcoming, static fn(array $a, array $b): int => $a[0] <=> $b[0]);
    usort($past, static fn(array $a, array $b): int => $b[0] <=> $a[0]);

    $out = [];
    foreach (array_merge($upcoming, $past) as [$expires, $html]) {
        $days = days_until($expires, $now);
        $out[] = strtr($html, [
            '@@STEP@@'    => step_for($days),
            '@@WIDTH@@'   => gauge_width($days) . '%',
            '@@COUNT@@'   => humanise($days),
            '@@EXPIRES@@' => gmdate('Y-m-d\\TH:i:s\\Z', $expires),
            '@@PAST@@'    => $days < 0 ? ' is-past' : '',
        ]);
    }

    $page = str_replace('<!--ROWS-->', implode("\n", $out), $shell);
    // Stamp when the ordering was computed. A visitor's browser compares this
    // to today and shows a banner if it has not moved — which is the only
    // outward sign that PHP has failed and the static fallback is being served.
    $page = str_replace(
        ['<!--ORDERED-->', '<!--ORDERED-ISO-->'],
        [gmdate('j M Y, H:i') . ' UTC', gmdate('Y-m-d')],
        $page);

    if (is_dir(CACHE_DIR) && is_writable(CACHE_DIR)) {
        cache_write($cacheFile, $page);
        sweep_cache($cacheFile);
    }

    header('Content-Type: text/html; charset=utf-8');
    header('X-Front-Cache: miss');
    echo $page;

    if ($forced) {
        printf("\n<!-- refresh report\n"
             . "  php            %s (%s)\n"
             . "  utc date       %s\n"
             . "  version        %s\n"
             . "  rows           %d\n"
             . "  cache dir      %s\n"
             . "  cache writable %s\n"
             . "  cache file     %s\n"
             . "  written        %s\n"
             . "-->\n",
            PHP_VERSION, PHP_SAPI, gmdate('c'), $version, count($rows),
            CACHE_DIR,
            is_writable(CACHE_DIR) ? 'yes' : 'NO',
            basename($cacheFile),
            is_readable($cacheFile) ? 'yes, ' . filesize($cacheFile) . ' bytes' : 'NO');
    }
} catch (Throwable $e) {
    serve_fallback();
}
"""


def php_string(text: str) -> str:
    """A single-quoted PHP literal: only two characters need escaping."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def front_php(name: str) -> str:
    return FRONT_PHP.replace("@@NAME@@", name)


# --------------------------------------------------------------------------
# Hand-written pages
#
# Everything in pages/ is yours. The generator reads it and never writes there,
# so editing about.html cannot be undone by a rebuild, and adding a new file is
# all it takes to add a page.
# --------------------------------------------------------------------------

RE_PAGE_TITLE = re.compile(r"<!--\s*title:\s*(.+?)\s*-->")
RE_PAGE_DESC = re.compile(r"<!--\s*description:\s*(.+?)\s*-->")


def render_pages(site: "Site", env: Environment) -> int:
    folder = site.root / "pages"
    if not folder.is_dir():
        return 0

    template = env.get_template("page.html.j2")
    count = 0
    for path in sorted(folder.glob("*.html")):
        body = path.read_text(encoding="utf-8")
        title = RE_PAGE_TITLE.search(body)
        description = RE_PAGE_DESC.search(body)
        body = RE_PAGE_TITLE.sub("", body)
        body = RE_PAGE_DESC.sub("", body)

        slug = path.stem
        write(site.out_dir / slug / "index.html",
              template.render(body=body.strip(),
                              page_title=title.group(1) if title else slug.title(),
                              page_description=description.group(1) if description else "",
                              slug=slug))
        count += 1
    return count


# --------------------------------------------------------------------------
# Hand-written pages
#
# Files in pages/ are yours. The build renders them into the site chrome and
# never writes to them, so nothing here can overwrite your prose.
#
# A deliberately small Markdown subset, so there is no dependency to install
# and no parser to debug. Anything it does not cover, write as HTML: a line
# starting with "<" is passed through untouched.
# --------------------------------------------------------------------------

RE_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
RE_MD_CODE = re.compile(r"`([^`]+)`")
RE_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
RE_MD_ITALIC = re.compile(r"(?<![*\w])\*([^*]+)\*(?!\*)")


def inline_markdown(text: str, escape: bool = True) -> str:
    if escape:
        text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    text = RE_MD_CODE.sub(r"<code>\1</code>", text)
    text = RE_MD_BOLD.sub(r"<strong>\1</strong>", text)
    text = RE_MD_ITALIC.sub(r"<em>\1</em>", text)
    text = RE_MD_LINK.sub(r'<a href="\2">\1</a>', text)
    return text


RE_MD_COMMENT = re.compile(r"<!--.*?-->", re.S)


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_markdown(source: str) -> tuple[str, str]:
    """Return (title, html). The title is the first level-one heading."""
    # Comments are notes to the editor, not content. Strip them whole: they
    # span several lines, so a line-by-line pass would emit the middle of one
    # as if it were text.
    source = RE_MD_COMMENT.sub("", source)
    html: list[str] = []
    title = ""
    paragraph: list[str] = []
    list_kind: str | None = None
    verbatim: str | None = None   # "fence" or the tag we are waiting to close

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            html.append("<p>" + inline_markdown(" ".join(paragraph)) + "</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_kind
        if list_kind:
            html.append(f"</{list_kind}>")
            list_kind = None

    for raw in source.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        # Inside a code block, nothing is interpreted and nothing is joined:
        # blank lines, indentation and line breaks are the content.
        if verbatim == "fence":
            if stripped.startswith("```"):
                html.append("</code></pre>")
                verbatim = None
            else:
                html.append(escape_html(line))
            continue
        if verbatim:
            html.append(line)
            if f"</{verbatim}>" in stripped:
                verbatim = None
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            html.append("<pre><code>")
            verbatim = "fence"
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        # Escape hatch: raw HTML, passed through as written. When it opens a
        # block that must keep its own line breaks, stay verbatim until it
        # closes — otherwise the lines inside get folded into a paragraph.
        if stripped.startswith("<"):
            flush_paragraph()
            flush_list()
            html.append(line)
            opening = re.match(r"^<(pre|table|ul|ol|blockquote|figure|div)\b", stripped)
            if opening and f"</{opening.group(1)}>" not in stripped:
                verbatim = opening.group(1)
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            text = inline_markdown(heading.group(2))
            if level == 1 and not title:
                title = re.sub(r"<[^>]+>", "", text)
            anchor = re.sub(r"[^a-z0-9]+", "-", heading.group(2).lower()).strip("-")
            html.append(f'<h{level} id="{anchor}">{text}</h{level}>')
            continue

        if stripped in ("---", "***"):
            flush_paragraph()
            flush_list()
            html.append("<hr>")
            continue

        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        numbered = re.match(r"^\d+\.\s+(.*)$", stripped)
        if bullet or numbered:
            flush_paragraph()
            wanted = "ul" if bullet else "ol"
            if list_kind != wanted:
                flush_list()
                html.append(f"<{wanted}>")
                list_kind = wanted
            item = (bullet or numbered).group(1)
            html.append("<li>" + inline_markdown(item) + "</li>")
            continue

        if stripped.startswith("> "):
            flush_paragraph()
            flush_list()
            html.append("<blockquote>" + inline_markdown(stripped[2:]) + "</blockquote>")
            continue

        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    return title, "\n".join(html)


def render_pages(site: Site, env: Environment) -> int:
    """Render pages/*.md and pages/*.html into the site chrome.

    Reads only. Nothing in this function writes to pages/, so your prose
    survives every rebuild, every schema change and every future edit of mine.
    """
    folder = site.root / "pages"
    if not folder.is_dir():
        return 0

    template = env.get_template("page.html.j2")
    count = 0
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in (".md", ".html"):
            continue
        # Files starting with _ are fragments pulled into the chrome, not pages.
        if path.name.startswith("_"):
            continue
        source = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".md":
            title, body = render_markdown(source)
        else:
            match = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.S)
            title = re.sub(r"<[^>]+>", "", match.group(1)) if match else path.stem.title()
            body = source
        # Marked safe because this HTML is what we just produced from your
        # file, not anything a visitor supplied.
        write(site.out_dir / path.stem / "index.html",
              template.render(page_title=title, page_body=Markup(body), slug=path.stem))
        count += 1
    return count


def redirect_page(target: str, label: str) -> str:
    """A static redirect that also works if mod_rewrite is unavailable."""
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={target}">\n'
        f'<link rel="canonical" href="{target}">\n'
        '<meta name="robots" content="noindex">\n'
        f'<title>Moved to {label}</title>\n</head>\n<body>\n'
        f'<p>This conference is now at <a href="{target}">{label}</a>.</p>\n'
        '</body>\n</html>\n'
    )


# Files that belong in the repository but not on the web server.
ASSET_EXCLUDES = shutil.ignore_patterns("*.md", "*.sh", ".*", "__pycache__")


def copy_cfps(site: Site) -> int:
    """Publish the collected calls beside the edition pages that cite them."""
    copied = 0
    for conference in site.conferences.values():
        source = site.data_dir / conference.slug / "cfp"
        if not source.is_dir():
            continue
        for edition in conference.editions:
            for cfp in edition.cfps:
                name = str(cfp.get("file", "")).split("/")[-1]
                origin = source / name
                if not origin.exists():
                    site.warn(f"{conference.slug}/{edition.key}: {name} is referenced "
                              f"but not in {source}")
                    continue
                target = site.out_dir / conference.slug / edition.key / "cfp" / name
                copy_if_changed(origin, target)
                copied += 1
    return copied


def read_cfp_text(site: Site, edition: Edition, cfp: dict) -> str | None:
    name = str(cfp.get("file", "")).split("/")[-1]
    path = site.data_dir / edition.slug / "cfp" / name
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def same_file(source: Path, target: Path) -> bool:
    if not target.exists():
        return False
    a, b = source.stat(), target.stat()
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def copy_if_changed(source: Path, target: Path) -> bool:
    """Copy preserving the modification time, and only when needed."""
    if same_file(source, target):
        WRITTEN["unchanged"] += 1
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    WRITTEN["written"] += 1
    return True


def export_data(site: Site) -> dict:
    """Publish the whole corpus as JSON and CSV.

    Written flat and complete: someone taking the data should not have to know
    how this site models rounds or extensions. Dates are ISO, one row per
    edition, and the announced-versus-effective distinction survives as two
    separate columns rather than being flattened away.
    """
    rows = []
    for edition in sorted(site.editions, key=lambda e: (e.slug, e.key)):
        conference = edition.conference
        place = site.city(edition.city_name)
        paper = edition.deadline("paper")
        abstract = edition.deadline("abstract")
        notification = edition.deadline("notification")
        counts = edition.counts

        rows.append({
            "slug": edition.slug,
            "acronym": conference.acronym,
            "year": edition.key,
            "edition": edition.raw.get("edition"),
            "title": edition.title,
            "url": edition.website,
            "page": f"{site.config['site']['base_url']}{edition.url}",
            "status": edition.status,
            "abstract_deadline": abstract.effective.isoformat() if abstract else None,
            "paper_deadline": paper.effective.isoformat() if paper else None,
            "paper_deadline_announced": paper.announced.isoformat() if paper else None,
            "paper_extended_days": paper.extension_days if paper else None,
            "notification": notification.effective.isoformat() if notification else None,
            "timezone": edition.tz,
            "event_start": edition.starts.isoformat() if edition.starts else None,
            "event_end": (edition.event.get("end").isoformat()
                          if isinstance(edition.event.get("end"), date) else None),
            "city": edition.city_name,
            "country": place.get("country"),
            "continent": place.get("continent"),
            "lat": place.get("lat"),
            "lon": place.get("lon"),
            "online": bool(edition.online),
            "publisher": edition.proceedings.get("publisher"),
            "license": edition.proceedings.get("license"),
            "doi": "; ".join(edition.dois) or None,
            "core_rank": edition.core_rank,
            "submitted": counts[1] if counts else None,
            "accepted": counts[0] if counts else None,
            "acceptance_rate": round(edition.rate, 1) if edition.rate else None,
            "format": edition.format,
            "dblp": conference.links.get("dblp"),
        })

    # The date the data was last edited, not the build clock: a rebuild that
    # changes nothing should produce a byte-identical file, so a deploy has
    # nothing to send.
    latest = max((e.source_mtime for e in site.editions if e.source_mtime),
                 default=site.now)

    payload = {
        "generated": latest.isoformat(),
        "source": site.config["site"]["base_url"],
        "licence": site.config["site"].get("data_licence", ""),
        "licence_url": site.config["site"].get("data_licence_url", ""),
        "count": len(rows),
        "editions": rows,
    }
    write(site.out_dir / "data" / "conferences.json",
          json.dumps(payload, indent=1, ensure_ascii=False, default=str) + "\n")

    import csv as csv_module
    import io
    buffer = io.StringIO()
    if rows:
        writer = csv_module.DictWriter(buffer, fieldnames=list(rows[0]),
                                       lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    write(site.out_dir / "data" / "conferences.csv", buffer.getvalue())

    # One file per series as well: the conference pages link to it, and it is
    # the natural unit for anyone interested in a single venue's history.
    by_slug: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_slug[row["slug"]].append(row)

    for slug, editions in by_slug.items():
        conference = site.conferences[slug]
        write(site.out_dir / "data" / f"{slug}.json",
              json.dumps({
                  "generated": max((e.source_mtime for e in conference.editions
                                    if e.source_mtime), default=latest).isoformat(),
                  "source": f"{site.config['site']['base_url']}{conference.url}",
                  "licence": site.config["site"].get("data_licence", ""),
                  "acronym": conference.acronym,
                  "name": conference.name,
                  "count": len(editions),
                  "editions": editions,
              }, indent=1, ensure_ascii=False, default=str) + "\n")

    return {"rows": len(rows), "files": len(by_slug) + 2,
            "json_kb": len(json.dumps(payload, default=str)) // 1024}


def render_calendars(site: Site) -> int:
    """Write the .ics feeds. Paths are permanent so they can be subscribed to."""
    base = site.config["site"]["base_url"]
    written = 0
    problems: list[str] = []

    def emit(path: Path, calendar) -> None:
        nonlocal written
        text = calendar.render()
        for problem in calendars.check(text):
            problems.append(f"{path.name}: {problem}")
        write(path, text)
        written += 1

    deadlines = calendars.Calendar(
        "CS conference deadlines",
        "Submission deadlines in theoretical computer science. " + base,
        site.now)
    calendars.deadline_events(site, deadlines, site.editions)
    emit(site.out_dir / "ics" / "deadlines.ics", deadlines)

    events = calendars.Calendar(
        "CS conferences",
        "When theoretical computer science conferences actually meet. " + base,
        site.now)
    calendars.event_events(site, events, site.editions)
    emit(site.out_dir / "ics" / "events.ics", events)

    both = calendars.Calendar(
        "CS conferences and deadlines",
        "Deadlines and conference dates together. " + base,
        site.now)
    calendars.deadline_events(site, both, site.editions)
    calendars.event_events(site, both, site.editions)
    emit(site.out_dir / "ics" / "all.ics", both)

    # One per conference, with no window: subscribing to a series is a way of
    # keeping its whole history to hand.
    for conference in site.conferences.values():
        feed = calendars.Calendar(
            f"{conference.acronym} — deadlines and dates",
            f"Every recorded edition of {conference.acronym}. {base}{conference.url}",
            site.now)
        calendars.deadline_events(site, feed, conference.editions, window_days=36500)
        calendars.event_events(site, feed, conference.editions, window_days=36500)
        if len(feed):
            emit(site.out_dir / conference.slug / f"{conference.slug}.ics", feed)

    for problem in problems:
        site.warn(f"calendar: {problem}")
    return written


def render_server_files(site: Site, env: Environment) -> None:
    """The 404 page and the .htaccess, generated so they are deployed.

    Both were previously left for hand-installation, which is why a mistyped
    URL fell through to the host's own error page: nothing on the server told
    Apache otherwise.
    """
    template = env.get_template("page.html.j2")
    body = (
        '<h1 id="not-found">Not found</h1>'
        '<p>There is no page at that address. It may never have existed, or a '
        'conference may have been renamed since you followed the link.</p>'
        '<p><a href="/">Back to the list of deadlines</a>, or try the search box '
        'there &mdash; it matches acronyms, full titles, cities and countries.</p>'
        '<p>If a link on this site brought you here, that is a bug worth '
        f'<a href="{site.config["contact"]["form"]}">reporting</a>.</p>'
    )
    write(site.out_dir / "404.html",
          template.render(page_title="Not found", page_body=Markup(body), slug="404"))

    front = site.config["site"]["front_page"]
    rules = HTACCESS.replace("@@FRONT@@", front)

    # Your own directives — redirects for pages kept from the old site, and
    # anything else Apache needs to know that the generator cannot infer.
    # Appended last so they can override what precedes them.
    extra = site.root / "pages" / "_htaccess.conf"
    if extra.exists():
        rules += ("\n# ---- from pages/_htaccess.conf ----\n"
                  + RE_MD_COMMENT.sub("", extra.read_text(encoding="utf-8")).strip()
                  + "\n")

    write(site.out_dir / ".htaccess", rules)


HTACCESS = """# Generated by build.py — edit the template in build.py, not this file.

# Every page is a directory holding index.html, so no URL shows a file
# extension. Apache appends the missing trailing slash by itself.
DirectoryIndex @@FRONT@@.php index.php index.html
DirectorySlash On
Options -Indexes

# A mistyped URL should land on our own page, not the host's.
ErrorDocument 404 /404.html

# If PHP fails, fall back to the static snapshot of the front page: a slightly
# stale ordering beats a blank page.
ErrorDocument 500 /@@FRONT@@.fallback.html

# Sources and build artefacts are not for serving.
<IfModule mod_authz_core.c>
    <FilesMatch "\\.(toml|tsv)$">
        Require all denied
    </FilesMatch>
</IfModule>
<IfModule !mod_authz_core.c>
    <FilesMatch "\\.(toml|tsv)$">
        Order allow,deny
        Deny from all
    </FilesMatch>
</IfModule>

AddDefaultCharset UTF-8
AddType text/calendar .ics
AddType application/json .json

<IfModule mod_deflate.c>
    AddOutputFilterByType DEFLATE text/html text/css text/plain \\
        application/javascript application/json text/calendar
</IfModule>

<IfModule mod_expires.c>
    ExpiresActive On
    # Assets carry a ?v= fingerprint, so they can be cached hard.
    ExpiresByType text/css "access plus 1 year"
    ExpiresByType application/javascript "access plus 1 year"
    ExpiresByType image/svg+xml "access plus 1 month"
    ExpiresByType font/woff2 "access plus 1 year"
    # Calendars are polled by subscribers: an extension must reach them soon.
    ExpiresByType text/calendar "access plus 1 hour"
    ExpiresByType text/html "access plus 1 hour"
</IfModule>
"""


def copy_assets(site: Site) -> None:
    """Mirror assets/ into the output, file by file.

    Deleting the directory and copying it back would reset every modification
    time, which is exactly what makes a deploy re-upload the fonts every time.
    """
    source = site.root / site.config["build"]["assets"]
    if not source.is_dir():
        return
    target = site.out_dir / "assets"

    wanted: set[Path] = set()
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.suffix.lower() in (".md", ".sh"):
            continue
        destination = target / relative
        wanted.add(destination)
        copy_if_changed(path, destination)

    # Anything left behind from an earlier build no longer belongs here.
    if target.exists():
        for path in sorted(target.rglob("*"), reverse=True):
            if path.is_file() and path not in wanted:
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=HERE / "site.toml")
    parser.add_argument("--only", metavar="SLUG")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    config = load_toml(args.config)
    site = Site(config, args.config.parent)

    if not site.data_dir.is_dir():
        return fail(f"no data directory at {site.data_dir}")

    if args.clean and site.out_dir.exists():
        shutil.rmtree(site.out_dir)

    started = datetime.now()
    site.read(args.only)
    if not site.conferences:
        return fail("no conferences found" + (f" for --only {args.only}" if args.only else ""))
    site.resolve()

    env = build_environment(site)
    pages = render(site, env)
    listed = render_front(site, env)
    calls = copy_cfps(site)
    prose = render_pages(site, env)
    feeds = render_calendars(site)
    exported = export_data(site)
    render_server_files(site, env)
    handwritten = render_pages(site, env)
    copy_assets(site)

    # The cache directory must exist and be writable before the first request,
    # and must never serve its contents directly.
    cache = site.out_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    write(cache / ".htaccess",
          "# Generated pages: internal build artefacts, never served directly.\n"
          "<IfModule mod_authz_core.c>\n    Require all denied\n</IfModule>\n"
          "<IfModule !mod_authz_core.c>\n    Order allow,deny\n    Deny from all\n</IfModule>\n")
    write(site.out_dir / "_data" / ".htaccess",
          "# Pre-rendered fragments, read by PHP only.\n"
          "<IfModule mod_authz_core.c>\n    Require all denied\n</IfModule>\n"
          "<IfModule !mod_authz_core.c>\n    Order allow,deny\n    Deny from all\n</IfModule>\n")

    elapsed = (datetime.now() - started).total_seconds()

    if not args.quiet:
        print(f"  conferences : {len(site.conferences)}", file=sys.stderr)
        print(f"  editions    : {len(site.editions)}", file=sys.stderr)
        print(f"  pages       : {pages}", file=sys.stderr)
        print(f"  calls filed : {calls}", file=sys.stderr)
        print(f"  pages/      : {handwritten}", file=sys.stderr)
        print(f"  calendars   : {feeds}", file=sys.stderr)
        print(f"  open data   : {exported['rows']} rows in "
              f"{exported['files']} files", file=sys.stderr)
        print(f"  front page  : {listed} editions listed "
              f"({config['site']['front_page']}.php)", file=sys.stderr)
        print(f"  changed     : {WRITTEN['written']} file(s), "
              f"{WRITTEN['unchanged']} left alone", file=sys.stderr)
        print(f"  output      : {site.out_dir}", file=sys.stderr)
        print(f"  took        : {elapsed:.2f}s", file=sys.stderr)
        if config["site"].get("draft"):
            print("  NOTE: draft mode — every page carries noindex", file=sys.stderr)
        unique = sorted(set(site.warnings))
        if unique:
            print(f"  warnings    : {len(unique)}", file=sys.stderr)
            for message in unique[:10]:
                print(f"      {message}", file=sys.stderr)
            if len(unique) > 10:
                print(f"      … and {len(unique) - 10} more", file=sys.stderr)

    if args.serve:
        serve(site, args.port)
    return 0


def serve(site: "Site", port: int) -> None:
    """Preview locally.

    PHP's own development server, not Python's: the front page is a .php file,
    and Python would serve it as source text. It also resolves index.html for
    directory URLs, which is how every page on this site is addressed.
    """
    import shutil as _shutil
    import subprocess

    php = _shutil.which("php")
    front = site.config["site"]["front_page"]

    if php is None:
        print("\n  error: php not found on PATH.\n"
              "  Every page except the front one is plain HTML, so you can still\n"
              "  preview those with:  python3 -m http.server -d public 8000\n"
              "  but the front page needs PHP.", file=sys.stderr)
        return

    print(f"\n  http://localhost:{port}/{front}.php   the front page", file=sys.stderr)
    print(f"  http://localhost:{port}/icfem/2026/    an edition, for example",
          file=sys.stderr)
    print("  ctrl-c to stop\n", file=sys.stderr)

    try:
        subprocess.run([php, "-S", f"localhost:{port}", "-t", str(site.out_dir)],
                       check=False)
    except KeyboardInterrupt:
        pass


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
