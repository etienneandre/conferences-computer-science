// filters.js — narrowing the front-page list.
//
// Every row carries its own tags in the HTML, so filtering is a visibility
// toggle: nothing is fetched, nothing re-renders, and the page is complete and
// indexable with JavaScript switched off.
//
// Two kinds of control, and the distinction is the point:
//
//   restrictive  ("Only ...")  narrow what is shown; combined with AND
//   additive     ("Also ...")  bring back rows hidden by default
//
// By default the table shows one row per live conference: the most recent
// edition we know of. Everything else — earlier editions, discontinued series —
// is present in the HTML but hidden, because showing every edition ever
// recorded means thousands of rows and answers nobody's question.

(function () {
  'use strict';

  var rows = document.getElementById('rows');
  if (!rows) return;

  var all = Array.prototype.slice.call(rows.querySelectorAll('.row'));
  var restrictive = Array.prototype.slice.call(
    document.querySelectorAll('.chip[data-filter]'));
  var additive = Array.prototype.slice.call(
    document.querySelectorAll('.chip[data-include]'));
  var search = document.querySelector('.searchbox input');
  var counter = document.getElementById('count');
  var noun = document.getElementById('countnoun');
  var empty = document.getElementById('empty');
  var reset = document.getElementById('reset');

  function tagsOf(row) {
    if (!row._tags) row._tags = (row.dataset.tags || '').split(' ');
    return row._tags;
  }

  // Expanding a row reveals the detail row that follows it.
  rows.addEventListener('click', function (event) {
    var button = event.target.closest('.expander button');
    if (!button) return;
    var detail = button.closest('tr').nextElementSibling;
    if (!detail || !detail.classList.contains('detail')) return;
    var open = button.getAttribute('aria-expanded') === 'true';
    button.setAttribute('aria-expanded', String(!open));
    button.innerHTML = open ? '&#9662;' : '&#9652;';
    detail.hidden = open;
  });

  function pressed(list) {
    return list.filter(function (c) {
      return c.getAttribute('aria-pressed') === 'true';
    });
  }

  function apply() {
    var wanted = pressed(restrictive).map(function (c) { return c.dataset.filter; });
    var included = pressed(additive).map(function (c) { return c.dataset.include; });
    var showEarlier = included.indexOf('earlier') !== -1;
    var showDefunct = included.indexOf('defunct') !== -1;
    var needle = ((search && search.value) || '').trim().toLowerCase();
    var shown = 0;

    all.forEach(function (row) {
      var tags = tagsOf(row);
      var ok = wanted.every(function (t) { return tags.indexOf(t) !== -1; });

      // Hidden unless asked for: older editions, and dead series.
      if (ok && !showEarlier && tags.indexOf('latest') === -1) ok = false;
      if (ok && !showDefunct && tags.indexOf('defunct') !== -1) ok = false;

      // data-search holds the country, the full title and the continent in
      // words — none of which appear in the visible row, now that flags stand
      // in for country names.
      if (ok && needle) {
        var haystack = (row.dataset.search || '') + ' ' + row.textContent.toLowerCase();
        ok = needle.split(/\s+/).every(function (word) {
          return haystack.indexOf(word) !== -1;
        });
      }

      row.hidden = !ok;
      var detail = row.nextElementSibling;
      if (detail && detail.classList.contains('detail')) {
        detail.style.display = ok ? '' : 'none';
      }
      if (ok) shown++;
    });

    if (counter) counter.textContent = String(shown);
    if (noun) noun.textContent = shown === 1 ? 'edition' : 'editions';
    if (empty) empty.hidden = shown !== 0;
    remember(wanted, included, needle);
  }

  // The chosen filters live in the URL, so a narrowed list can be bookmarked
  // and shared. replaceState keeps the back button free of noise.
  function remember(wanted, included, needle) {
    if (!window.history || !window.history.replaceState) return;
    var params = new URLSearchParams();
    if (wanted.length) params.set('only', wanted.join(','));
    if (included.length) params.set('also', included.join(','));
    if (needle) params.set('q', needle);
    var query = params.toString();
    window.history.replaceState(null, '', query ? '?' + query : location.pathname);
  }

  function restore() {
    var params = new URLSearchParams(location.search);
    var wanted = (params.get('only') || 'upcoming').split(',').filter(Boolean);
    var included = (params.get('also') || '').split(',').filter(Boolean);
    restrictive.forEach(function (c) {
      c.setAttribute('aria-pressed', String(wanted.indexOf(c.dataset.filter) !== -1));
    });
    additive.forEach(function (c) {
      c.setAttribute('aria-pressed', String(included.indexOf(c.dataset.include) !== -1));
    });
    if (search && params.get('q')) search.value = params.get('q');
  }

  restrictive.concat(additive).forEach(function (chip) {
    chip.addEventListener('click', function () {
      chip.setAttribute('aria-pressed',
        chip.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
      apply();
    });
  });

  if (search) {
    search.addEventListener('input', apply);
    search.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { search.value = ''; apply(); }
    });
  }

  if (reset) {
    reset.addEventListener('click', function () {
      restrictive.forEach(function (c) {
        c.setAttribute('aria-pressed', String(c.dataset.filter === 'upcoming'));
      });
      additive.forEach(function (c) { c.setAttribute('aria-pressed', 'false'); });
      if (search) search.value = '';
      apply();
    });
  }

  // The ordering is computed once a day by the server. If the stamp has not
  // moved, the static fallback is being served and every countdown on the page
  // is wrong — which is worth saying plainly rather than leaving to be noticed.
  function checkFreshness() {
    var meta = document.querySelector('meta[name="ordered-as-of"]');
    var banner = document.getElementById('stale');
    if (!meta || !banner) return;
    var stamped = Date.parse(meta.content + 'T00:00:00Z');
    if (isNaN(stamped)) return;
    var days = Math.floor((Date.now() - stamped) / 86400000);
    if (days < 2) return;               // one day of slack for time zones
    banner.hidden = false;
    banner.innerHTML = '<b>This list has not refreshed.</b> It was last ordered ' +
      days + ' days ago, so the countdowns below are out of date and the order ' +
      'is wrong. The dates themselves are still what was recorded.';
  }

  restore();
  apply();
  checkFreshness();
})();
