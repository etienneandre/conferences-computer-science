// countdown.js — refine the countdown when a deadline is close.
//
// The server rebuilds the front page once a day, so it can only ever say "in 1
// day". Under two days that is not good enough: a reader on the morning of the
// deadline wants to know whether they have nine hours or thirty.
//
// Each countdown carries data-expires, the exact moment in UTC — already
// adjusted for the conference's time zone, or for Anywhere on Earth where the
// organisers stated none. This recomputes from it in the browser, where "now"
// is genuinely now.
//
// Without JavaScript the server's wording stands, which is correct if coarse.

(function () {
  'use strict';

  var TWO_DAYS = 48 * 3600 * 1000;

  function phrase(remaining) {
    if (remaining <= 0) return null;               // leave the server's wording

    var minutes = Math.floor(remaining / 60000);
    if (minutes < 60) {
      return minutes <= 1 ? 'in a minute or two'
                          : 'in ' + minutes + ' minutes';
    }

    var hours = Math.floor(remaining / 3600000);
    if (hours < 48) {
      return hours === 1 ? 'in about an hour' : 'in ' + hours + ' hours';
    }
    return null;                                   // far enough away: days will do
  }

  function refresh() {
    var now = Date.now();
    var elements = document.querySelectorAll('.countdown[data-expires]');

    // Type ccsCountdown() in the console to see whether this ran and what it
    // found. A silent no-op and a script that never loaded look identical
    // otherwise.
    window.ccsCountdown = function () {
      return { found: elements.length, now: new Date(now).toISOString() };
    };

    Array.prototype.forEach.call(elements, function (element) {
      // getAttribute rather than dataset: one element with an odd attribute
      // should not abort the loop for all the others.
      var raw = element.getAttribute('data-expires') || '';
      var expires = Date.parse(raw);
      if (isNaN(expires)) return;

      var remaining = expires - now;
      if (remaining > TWO_DAYS) return;

      var text = phrase(remaining);
      if (text) {
        element.textContent = text;
        element.title = 'Closes ' + new Date(expires).toLocaleString();
      } else if (remaining <= 0 && !/closed/.test(element.textContent)) {
        // The page was built while it was still open; it no longer is.
        element.textContent = 'closed';
        var row = element.closest('.row');
        if (row) row.classList.add('is-past');
      }
    });
  }

  // Anywhere on Earth is UTC-12, which is the whole point of it: a deadline
  // stated in AoE is still open everywhere until it is closed everywhere. But
  // "23:59 AoE" is not a time anybody can act on without doing the arithmetic,
  // and the arithmetic is where people get it wrong by a day.
  //
  // So we say it again in the reader's own zone. This can only be done here —
  // the server has no idea where the reader is, and the page is cached for
  // everybody alike. Written only when it succeeds, and the element stays
  // hidden otherwise: without JavaScript the page claims nothing about where
  // anyone is.
  function localise() {
    var now = Date.now();
    Array.prototype.forEach.call(
      document.querySelectorAll('.localtime[data-expires]'),
      function (element) {
        var expires = Date.parse(element.getAttribute('data-expires') || '');
        if (isNaN(expires)) return;
        // A deadline that has gone needs no translating.
        if (expires < now) return;

        var text;
        try {
          text = new Date(expires).toLocaleString(undefined, {
            day: 'numeric', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit', timeZoneName: 'short'
          });
        } catch (e) {
          return;
        }
        element.textContent = text;

        // Unhide whatever wrapper was holding it back — a grid cell on the
        // front page, a sentence on an edition page.
        var holder = element.closest('[hidden]');
        if (holder) holder.hidden = false;
      });
  }

  refresh();
  localise();
  // A page left open on the morning of a deadline should not keep saying
  // "in 9 hours" all afternoon.
  setInterval(refresh, 60000);
})();
