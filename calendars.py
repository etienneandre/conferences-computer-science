"""
calendars.py — iCalendar feeds.

Everything is an all-day event: a VEVENT with DATE values rather than
DATE-TIME. That is deliberate and it is what calendar clients handle best. A
deadline is a moment, not a day, but expressing it as one would force a time
zone on every subscriber, and "23:59 AoE" shown in the reader's local time is
more confusing than useful. The zone is stated in the description instead,
where it can be read rather than silently applied.

Two properties matter more than the rest:

    UID       must never change for a given event, or every client duplicates
              the whole feed each time it refreshes.
    SEQUENCE  must increase when an event moves, or subscribers keep the old
              date forever.

So the UID is derived from what the event *is* — conference, year, which
deadline — and the SEQUENCE from how many times that date has been revised,
which the deadline lists already record.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

PRODID = "-//conferences-computer.science//EN"

# Only these deadlines go into a calendar. A camera-ready date matters to
# authors who have already been accepted, and they know it without a feed.
FEED_DEADLINES = ("abstract", "paper", "notification")

FEED_LABELS = {
    "abstract": "abstract deadline",
    "paper": "paper deadline",
    "notification": "notification",
}


def fold(line: str) -> str:
    """Wrap at 75 octets, as RFC 5545 requires.

    Long descriptions are the norm here, and a client that enforces the limit
    will reject an unfolded file outright.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line

    out, current = [], b""
    for char in line:
        chunk = char.encode("utf-8")
        limit = 75 if not out else 74      # continuation lines start with a space
        if len(current) + len(chunk) > limit:
            out.append(current.decode("utf-8"))
            current = b""
        current += chunk
    out.append(current.decode("utf-8"))
    return "\r\n ".join(out)


def escape(text: str) -> str:
    """RFC 5545 text escaping. Order matters: backslash first."""
    return (str(text).replace("\\", "\\\\")
                     .replace(";", "\\;")
                     .replace(",", "\\,")
                     .replace("\r\n", "\\n")
                     .replace("\n", "\\n"))


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


class Calendar:
    def __init__(self, name: str, description: str, now: datetime) -> None:
        self.name = name
        self.description = description
        self.now = now
        self.events: list[list[str]] = []

    def add(self, *, uid: str, start: date, end: date | None, summary: str,
            description: str, url: str, sequence: int = 0,
            modified: datetime | None = None,
            categories: list[str] | None = None) -> None:
        # DTEND is exclusive for all-day events: a one-day event ends the next
        # day. Getting this wrong shows the event a day short in every client.
        finish = (end or start) + timedelta(days=1)

        lines = [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            # When this event's data was last edited, not when the file was
            # generated. Using the build clock would change every entry on
            # every build, so every deploy would re-upload every feed — and,
            # worse, tell subscribers something had changed when nothing had.
            f"DTSTAMP:{stamp(modified or self.now)}",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{finish:%Y%m%d}",
            f"SUMMARY:{escape(summary)}",
            f"DESCRIPTION:{escape(description)}",
            f"URL:{url}",
            f"SEQUENCE:{sequence}",
            "TRANSP:TRANSPARENT",
        ]
        if categories:
            lines.append("CATEGORIES:" + ",".join(escape(c) for c in categories))
        lines.append("END:VEVENT")
        self.events.append(lines)

    def render(self) -> str:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:{PRODID}",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{escape(self.name)}",
            f"X-WR-CALDESC:{escape(self.description)}",
            "X-PUBLISHED-TTL:PT12H",
            "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        ]
        for event in self.events:
            lines.extend(event)
        lines.append("END:VCALENDAR")
        # CRLF throughout, and a trailing one: some parsers insist.
        return "\r\n".join(fold(line) for line in lines) + "\r\n"

    def __len__(self) -> int:
        return len(self.events)


def deadline_events(site, calendar: Calendar, editions, window_days: int = 365) -> None:
    """One event per deadline, for editions inside the window."""
    today = date.today()
    horizon = today - timedelta(days=window_days)

    for edition in editions:
        if not edition.listed:
            continue
        conference = edition.conference
        url = f"{site.config['site']['base_url']}{edition.url}"
        place = site.city(edition.city_name)
        where = "Online" if edition.online else (place.get("name") or "")

        for deadline in edition.deadlines:
            if deadline.key not in FEED_DEADLINES:
                continue
            when = deadline.effective
            if when < horizon:
                continue

            label = FEED_LABELS[deadline.key]
            if deadline.round_name:
                label = f"{deadline.round_name} {label}"

            # Stable for the life of the event: it names what the event is,
            # never when it is. Moving the date must not mint a new UID.
            uid = (f"{edition.slug}-{edition.key}-{deadline.key}"
                   f"{'-' + deadline.round_name.lower().replace(' ', '') if deadline.round_name else ''}"
                   f"@conferences-computer.science")

            details = []
            if edition.title:
                details.append(edition.title)
            if deadline.tz_shown:
                details.append(f"Deadline stated in {deadline.tz_shown}.")
            else:
                details.append("No time zone stated by the organisers; "
                               "this site assumes Anywhere on Earth.")
            details.append("Shown as an all-day event: the deadline is a moment, "
                           "not a day, so check the exact time on the conference site.")
            if deadline.extended:
                details.append(f"Extended from {deadline.announced:%d %B %Y}.")
            if where:
                details.append(f"Held in {where}.")
            if edition.held:
                details.append(f"Conference dates: {edition.held}.")
            details.append(url)

            calendar.add(
                uid=uid,
                start=when,
                end=None,
                summary=f"{edition.acronym} — {label}",
                description="\n".join(details),
                url=url,
                # Each recorded revision of the date is one revision of the
                # event, which is exactly what SEQUENCE is for.
                sequence=len(deadline.dates) - 1,
                modified=edition.source_mtime,
                categories=["Deadline", conference.acronym],
            )


def event_events(site, calendar: Calendar, editions, window_days: int = 365) -> None:
    """One event per conference, for the days it actually runs."""
    today = date.today()
    horizon = today - timedelta(days=window_days)

    for edition in editions:
        if not edition.listed or not edition.starts:
            continue
        if edition.starts < horizon:
            continue

        url = f"{site.config['site']['base_url']}{edition.url}"
        place = site.city(edition.city_name)
        where = "Online" if edition.online else (place.get("name") or "")

        details = []
        if edition.title:
            details.append(edition.title)
        if where:
            details.append(f"Held in {where}.")
        paper = edition.deadline("paper")
        if paper:
            details.append(f"Paper deadline was {paper.effective:%d %B %Y}.")
        details.append(url)

        calendar.add(
            uid=f"{edition.slug}-{edition.key}-event@conferences-computer.science",
            start=edition.starts,
            end=edition.event.get("end"),
            summary=f"{edition.acronym}{' — ' + where if where else ''}",
            description="\n".join(details),
            url=url,
            modified=edition.source_mtime,
            categories=["Conference", edition.conference.acronym],
        )


def check(text: str) -> list[str]:
    """Structural checks, run at build time.

    Not a full RFC 5545 parser — enough to catch the mistakes that actually
    happen: unbalanced blocks, a line too long, a bare LF, a missing UID.
    """
    problems = []

    if not text.endswith("\r\n"):
        problems.append("does not end with CRLF")
    if "\n" in text.replace("\r\n", ""):
        problems.append("contains a bare LF")

    lines = text.split("\r\n")
    for name in ("VCALENDAR",):
        if lines[0] != f"BEGIN:{name}":
            problems.append(f"does not begin with BEGIN:{name}")

    depth = 0
    uids = set()
    for number, line in enumerate(lines, start=1):
        if len(line.encode("utf-8")) > 75 and not line.startswith(" "):
            problems.append(f"line {number} exceeds 75 octets unfolded")
        if line.startswith("BEGIN:VEVENT"):
            depth += 1
        elif line.startswith("END:VEVENT"):
            depth -= 1
            if depth < 0:
                problems.append(f"line {number}: END:VEVENT without BEGIN")
        elif line.startswith("UID:"):
            uid = line[4:]
            if uid in uids:
                problems.append(f"duplicate UID {uid}")
            uids.add(uid)
    if depth:
        problems.append(f"{depth} VEVENT block(s) left open")

    return problems
