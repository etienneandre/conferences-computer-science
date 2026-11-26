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

    var axis = el('div', 'timeline-axis');
    var cursor = new Date(origin);
    cursor.setUTCDate(1);
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    while (cursor.getTime() <= last) {
      var at = pct(cursor.getTime());
      if (at >= 0 && at <= 100) {
        var tick = el('span', 'timeline-tick', MONTHS[cursor.getUTCMonth()]);
        tick.style.left = at + '%';
        axis.appendChild(tick);
      }
      cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    }
    table.appendChild(axis);

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

        title = r.d.label + ' — no call announced. Its last ' + r.d.editions
          + ' editions (' + r.d.first_year + '–' + r.d.last_year + ') closed between '
          + fmt(parse(r.d.from)) + ' and ' + fmt(parse(r.d.to))
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
    build(holder, data);
    /* Redraw on a resize only to recompute nothing — positions are
       percentages — but the month ticks can collide, so the axis is rebuilt
       at a new width. Debounced, because resize fires continuously. */
    var pending;
    window.addEventListener('resize', function () {
      clearTimeout(pending);
      pending = setTimeout(function () { build(holder, data); }, 200);
    });
  }

  function init() {
    var holder = document.querySelector('[data-timeline]');
    if (!holder) return;
    var drop = holder.closest('details');
    if (!drop) { start(holder); return; }
    if (drop.open) start(holder);
    drop.addEventListener('toggle', function () {
      if (drop.open) start(holder);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
