/* The deadline timeline above the front-page list.
 *
 * Drawn here rather than at build time for one reason: the axis starts at
 * today, and the front page is served from a day-old cache. Pre-rendering it
 * would freeze the origin and quietly slide every marker as the cache aged.
 * Doing it here also lets the set re-filter itself — a call that closed since
 * the last deploy drops out, a predicted window that has come inside the
 * horizon appears — so the picture is right between deploys, not just after
 * them.
 *
 * Nothing runs until the <details> is opened. The list below is the page;
 * this is a second way of looking at the same rows, and it is allowed to be
 * absent.
 */
(function () {
  'use strict';

  var DAY = 86400000;
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function parse(iso) {
    if (!iso) return null;
    var p = iso.split('-');
    return Date.UTC(+p[0], +p[1] - 1, +p[2]);
  }

  function fmt(ts) {
    var d = new Date(ts);
    return d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()] + ' ' + d.getUTCFullYear();
  }

  /* "5 days", "9 weeks", "3 months" — the same ladder the list uses, so the
     two cannot describe the same deadline differently. */
  function away(days) {
    if (days <= 0) return 'today';
    if (days < 21) return days + (days === 1 ? ' day' : ' days');
    if (days < 70) {
      var w = Math.round(days / 7);
      return w + (w === 1 ? ' week' : ' weeks');
    }
    var m = Math.round(days / 30.4);
    return m + (m === 1 ? ' month' : ' months');
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  /* The month axis, shared by both strips. The step comes from the width the
     strip actually has: eight month labels fit a desk and collide into one
     grey smear on a phone, and a label nobody can read is worse than a gap.
     Every marker carries its own date in a title, so thinning loses nothing.
  */
  function monthAxis(holder, from, to, pct, nowTs) {
    var axis = el('div', 'timeline-axis');
    var months = [];
    var cursor = new Date(from);
    cursor.setUTCDate(1);
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    while (cursor.getTime() <= to) {
      months.push(cursor.getTime());
      cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    }
    var room = Math.max((holder.clientWidth || 700) - 210, 140);
    var step = Math.max(1, Math.ceil(months.length / Math.max(1, Math.floor(room / 46))));
    months.forEach(function (ts, i) {
      if (i % step) return;
      var at = pct(ts);
      if (at < 0 || at > 100) return;
      var tick = el('span', 'timeline-tick', MONTHS[new Date(ts).getUTCMonth()]);
      tick.style.left = at + '%';
      axis.appendChild(tick);
    });
    if (nowTs != null) {
      /* A month tick under the "today" label is unreadable, and today is the
         more useful of the two. */
      var here = pct(nowTs);
      axis.querySelectorAll('.timeline-tick').forEach(function (t) {
        if (Math.abs(parseFloat(t.style.left) - here) < 5) t.remove();
      });
      var now = el('span', 'timeline-now', 'today');
      now.style.left = here + '%';
      axis.appendChild(now);
    }
    return axis;
  }

  function build(holder, data) {
    var today = new Date();
    var origin = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
    var nowSec = Math.floor(Date.now() / 1000);
    var limit = origin + data.horizon * DAY;

    var calls = (data.calls || []).filter(function (c) {
      return c.closes > nowSec && parse(c.paper) <= limit;
    });
    var predicted = (data.predicted || []).filter(function (p) {
      return parse(p.to) >= origin && parse(p.from) <= limit;
    });

    var rows = calls.map(function (c) { return { kind: 'call', d: c, at: parse(c.paper) }; })
      .concat(predicted.map(function (p) {
        return { kind: 'guess', d: p, at: parse(p.to) };
      }))
      .sort(function (a, b) { return a.at - b.at; });

    holder.textContent = '';
    if (!rows.length) {
      holder.appendChild(el('p', 'timeline-empty',
        'No call closes in the next ' + Math.round(data.horizon / 30.4) + ' months.'));
      return;
    }

    /* The axis ends at the last thing drawn, never at the horizon: an empty
       right-hand third would suggest a quiet period that is really just the
       edge of what the window covers. */
    var last = rows[rows.length - 1].at;
    rows.forEach(function (r) {
      if (r.kind === 'call') {
        var tail = parse(r.d.end) || parse(r.d.start) || parse(r.d.notification);
        if (tail && tail <= limit && tail > last) last = tail;
      }
    });
    var span = Math.max(last - origin, 30 * DAY);
    var pct = function (ts) { return ((ts - origin) / span) * 100; };

    var table = el('div', 'timeline');

    table.appendChild(monthAxis(holder, origin, last, pct, null));

    rows.forEach(function (r) {
      var row = el('div', 'timeline-row' + (r.kind === 'guess' ? ' is-guess' : ''));

      var name = el('div', 'timeline-name');
      var link = el('a', null, r.d.label);
      link.href = r.d.url;
      name.appendChild(link);
      row.appendChild(name);

      var track = el('div', 'timeline-track');
      var title;

      if (r.kind === 'call') {
        var paper = parse(r.d.paper);
        var abstract = parse(r.d.abstract);
        var notice = parse(r.d.notification);
        var start = parse(r.d.start);
        var end = parse(r.d.end) || start;

        /* The review period, drawn as a line from the deadline to the
           notification: the wait is the part an author feels. */
        if (notice && notice > paper) {
          var wait = el('i', 'timeline-wait');
          wait.style.left = pct(paper) + '%';
          wait.style.width = Math.max(pct(Math.min(notice, last)) - pct(paper), 0) + '%';
          track.appendChild(wait);
        }
        if (start && end >= start && start <= last) {
          var meet = el('i', 'timeline-meet');
          meet.style.left = pct(start) + '%';
          meet.style.width = Math.max(pct(Math.min(end, last)) - pct(start), 0.6) + '%';
          track.appendChild(meet);
        }
        if (abstract && abstract < paper) {
          var dot = el('i', 'timeline-abstract');
          dot.style.left = pct(abstract) + '%';
          track.appendChild(dot);
        }
        var mark = el('i', 'timeline-paper');
        mark.style.left = pct(paper) + '%';
        track.appendChild(mark);
        if (notice) {
          var noticeMark = el('i', 'timeline-notice');
          noticeMark.style.left = pct(Math.min(notice, last)) + '%';
          track.appendChild(noticeMark);
        }

        title = r.d.label + ' — papers ' + fmt(paper) + ' ' + r.d.tz
          + (abstract && abstract < paper ? ', abstracts ' + fmt(abstract) : '')
          + (notice ? ', notification ' + fmt(notice) : '')
          + (start ? ', meets ' + fmt(start) : '')
          + (r.d.where ? ' in ' + r.d.where : '');
      } else {
        var from = Math.max(parse(r.d.from), origin);
        var to = parse(r.d.to);
        var band = el('i', 'timeline-band');
        band.style.left = pct(from) + '%';
        band.style.width = Math.max(pct(to) - pct(from), 0.8) + '%';
        track.appendChild(band);
        var centre = el('i', 'timeline-guessmark');
        centre.style.left = pct((from + to) / 2) + '%';
        track.appendChild(centre);

        var every = r.d.cadence === 1 ? 'yearly'
          : r.d.cadence === 2 ? 'every two years'
          : 'every ' + r.d.cadence + ' years';
        title = r.d.label + ' — no call announced. It has met ' + every
          + ', so the next edition is due in ' + r.d.year + '. Its last '
          + r.d.editions + ' editions (' + r.d.first_year + '–' + r.d.last_year
          + ') closed between ' + fmt(parse(r.d.from)) + ' and ' + fmt(parse(r.d.to))
          + '. This band is that habit, not a date.';
      }

      row.appendChild(track);

      var when = el('div', 'timeline-when');
      if (r.kind === 'call') {
        when.textContent = away(Math.round((r.at - origin) / DAY));
      } else {
        when.appendChild(el('span', 'timeline-maybe', '~' + away(
          Math.round((((Math.max(parse(r.d.from), origin) + parse(r.d.to)) / 2) - origin) / DAY))));
      }
      row.appendChild(when);

      row.title = title;
      table.appendChild(row);
    });

    holder.appendChild(table);

    var legend = el('p', 'timeline-legend');
    /* Each entry is a marker and one text node: two flex items, never three,
       or the gap between them opens up mid-sentence and the longest entry
       wraps into a column on a phone. */
    legend.innerHTML =
      '<span><i class="timeline-paper"></i><span>paper deadline</span></span>' +
      '<span><i class="timeline-abstract"></i><span>abstract</span></span>' +
      '<span><i class="timeline-wait"></i><span>wait for notification</span></span>' +
      '<span><i class="timeline-meet"></i><span>the conference, where it falls' +
      ' inside the window</span></span>' +
      '<span><i class="timeline-guessmark"></i><span><b>no call yet</b> — the window' +
      ' this series has closed in recently, a habit and not a date</span></span>';
    holder.appendChild(legend);

    var note = el('p', 'timeline-note',
      calls.length + ' open call' + (calls.length === 1 ? '' : 's')
      + (predicted.length
         ? ', and ' + predicted.length + ' series with no call announced yet'
         : '')
      + '. Hover a row for its dates.');
    holder.appendChild(note);
  }

  /* The same projection the front page draws, read backwards: windows that
   * have gone by with nothing recorded against them, plus the couple of
   * months ahead so a call due any week is in view before it is late. The
   * axis is fixed to the range rather than fitted to the data, because the
   * whole point is reading each band against today.
   */
  function buildOverdue(holder, data) {
    var today = new Date();
    var origin = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
    var from = origin - data.back * DAY;
    var to = origin + data.ahead * DAY;
    var span = to - from;
    var pct = function (ts) { return ((ts - from) / span) * 100; };

    var rows = (data.rows || []).filter(function (r) {
      var closes = parse(r.to);
      return closes >= from && closes <= to;
    }).sort(function (a, b) { return parse(a.to) - parse(b.to); });

    holder.textContent = '';
    if (!rows.length) {
      holder.appendChild(el('p', 'timeline-empty',
        'Nothing is overdue: every series whose habits can be read has either '
        + 'announced its next call or is not due one yet.'));
      return;
    }

    var table = el('div', 'timeline is-overdue');

    table.appendChild(monthAxis(holder, from, to, pct, origin));

    rows.forEach(function (r) {
      var opens = Math.max(parse(r.from), from);
      var closes = parse(r.to);
      var late = closes < origin;
      var row = el('div', 'timeline-row' + (late ? ' is-late' : ' is-guess'));

      var name = el('div', 'timeline-name');
      var link = el('a', null, r.label);
      link.href = r.url;
      name.appendChild(link);
      row.appendChild(name);

      var track = el('div', 'timeline-track');
      var rule = el('i', 'timeline-nowline');
      rule.style.left = pct(origin) + '%';
      track.appendChild(rule);
      var band = el('i', late ? 'timeline-lateband' : 'timeline-band');
      band.style.left = pct(opens) + '%';
      band.style.width = Math.max(pct(closes) - pct(opens), 0.8) + '%';
      track.appendChild(band);
      var mark = el('i', late ? 'timeline-latemark' : 'timeline-guessmark');
      mark.style.left = pct((opens + closes) / 2) + '%';
      track.appendChild(mark);
      row.appendChild(track);

      var days = Math.round((closes - origin) / DAY);
      var when = el('div', 'timeline-when');
      when.textContent = late ? away(-days) + ' ago' : 'in ' + away(days);
      row.appendChild(when);

      var every = r.cadence === 1 ? 'yearly'
        : r.cadence === 2 ? 'every two years'
        : 'every ' + r.cadence + ' years';
      row.title = r.label + ' — ' + r.name + '. It has met ' + every
        + ', last in ' + r.last_held + ', so an edition was due in ' + r.year
        + ' and its call would have closed between ' + fmt(parse(r.from))
        + ' and ' + fmt(parse(r.to)) + '. Nothing is recorded for it'
        + (r.skipped > 1 ? ', nor for the ' + (r.skipped - 1) + ' expected before it'
           : '')
        + '. Either the call went out and was never entered here, or the series '
        + 'has stopped — this cannot tell which.';
      table.appendChild(row);
    });

    holder.appendChild(table);

    var legend = el('p', 'timeline-legend');
    legend.innerHTML =
      '<span><i class="timeline-latemark"></i><span>its window has passed and '
      + 'nothing is recorded</span></span>' +
      '<span><i class="timeline-guessmark"></i><span>due within the next couple '
      + 'of months</span></span>';
    holder.appendChild(legend);

    var over = rows.filter(function (r) { return parse(r.to) < origin; }).length;
    holder.appendChild(el('p', 'timeline-note',
      over + ' series ' + (over === 1 ? 'has' : 'have')
      + ' passed an expected deadline with nothing on record, and '
      + (rows.length - over) + ' more fall due shortly. Hover a row for what it '
      + 'rests on.'));
  }

  function start(holder) {
    if (holder.dataset.drawn) return;
    holder.dataset.drawn = '1';
    var data;
    try {
      data = JSON.parse(holder.dataset.timeline || '{}');
    } catch (e) {
      holder.textContent = '';
      return;                  // the list below says everything this would
    }
    var draw = holder.dataset.mode === 'overdue' ? buildOverdue : build;
    draw(holder, data);
    /* Redrawing recomputes no position — they are percentages — but the month
       ticks can collide at a new width, so the axis is rebuilt. Debounced,
       because resize fires continuously. */
    var pending;
    window.addEventListener('resize', function () {
      clearTimeout(pending);
      pending = setTimeout(function () { draw(holder, data); }, 200);
    });
  }

  function init() {
    document.querySelectorAll('[data-timeline]').forEach(function (holder) {
      var drop = holder.closest('details');
      if (!drop) { start(holder); return; }
      if (drop.open) start(holder);
      drop.addEventListener('toggle', function () {
        if (drop.open) start(holder);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
