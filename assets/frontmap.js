// frontmap.js — every open call for papers, on one map.
//
// The panel is a <details>, closed on load. Opening it is what asks for the
// map, so that one gesture is also the consent: no tile is fetched from
// openstreetmap.org, and so no IP address is revealed, until the reader
// decides to look. Same policy as map.js and seriesmap.js, one click instead
// of two.
//
// The points are written into data-points at build time and hold every call
// that was still open then. Which of them are open *now* is decided here,
// from each call's expiry: the page can be served from a cache for a day, or
// fall back to a snapshot for rather longer, and a closed call must not go on
// showing a pin either way. Nothing ever needs adding to the set, because a
// call that has closed cannot reopen without a rebuild.

(function () {
  'use strict';

  var panel = document.getElementById('mapdrop');
  var holder = document.getElementById('frontmap');
  if (!panel || !holder) return;

  var points;
  try {
    points = JSON.parse(holder.dataset.points || '[]');
  } catch (e) {
    points = [];
  }
  if (!points.length) return;

  // Never closer than the edition map: the question here is which parts of
  // the world are busy, not which street.
  var zoom = parseInt(holder.dataset.zoom, 10) || 5;
  var caption = document.getElementById('frontmap-caption');
  var map = null;

  // The same five urgency steps as the list, read from the stylesheet rather
  // than repeated here — so the pin beside a city and the countdown beside
  // its row are the same colour, in light mode and in dark.
  function stepColour(days) {
    var name = days <= 3 ? '--d0' : days <= 7 ? '--d1'
             : days <= 14 ? '--d2' : days <= 30 ? '--d3' : '--d4';
    var value = getComputedStyle(document.documentElement)
                  .getPropertyValue(name).trim();
    return value || '#1f6f5c';
  }

  function escape(text) {
    return String(text).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  // Only the calls still open, grouped as they were built: one pin per city.
  function live() {
    var now = Date.now() / 1000;
    var kept = [];
    points.forEach(function (point) {
      var calls = point.calls.filter(function (c) { return c.ts >= now; });
      if (!calls.length) return;
      calls.sort(function (a, b) { return a.ts - b.ts; });
      kept.push({
        lat: point.lat, lon: point.lon, city: point.city, flag: point.flag,
        calls: calls,
        // The pin speaks for the soonest deadline in that city: that is the
        // one a reader still has to act on.
        days: Math.floor((calls[0].ts - now) / 86400)
      });
    });
    // Soonest last, so the urgent pins are drawn on top where they overlap.
    kept.sort(function (a, b) { return b.days - a.days; });
    return kept;
  }

  function popup(point) {
    var rows = point.calls.map(function (c) {
      return '<a href="' + escape(c.url) + '">' + escape(c.label) + '</a> ' +
             '<span class="pin-when">' + escape(c.date) + '</span>';
    }).join('<br>');
    return '<b>' + escape(point.city) + '</b> ' + escape(point.flag) +
           '<div class="pin-calls">' + rows + '</div>';
  }

  function say(text) {
    if (caption) caption.textContent = text;
  }

  function plural(n, one, many) {
    return n + ' ' + (n === 1 ? one : many);
  }

  function draw() {
    var live_points = live();
    if (!live_points.length) {
      holder.innerHTML = '<p class="map-missing">Nothing is open for submission ' +
        'right now — or this page is older than its last deadline.</p>';
      return;
    }

    holder.innerHTML = '';
    holder.classList.add('is-live');
    map = L.map(holder, {
      scrollWheelZoom: false,
      zoomControl: true,
      attributionControl: true
    });

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 17,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    var bounds = [];
    var calls = 0;
    live_points.forEach(function (point) {
      bounds.push([point.lat, point.lon]);
      calls += point.calls.length;
      L.circleMarker([point.lat, point.lon], {
        radius: 7,
        weight: 2,
        color: '#ffffff',
        opacity: 1,
        fillColor: stepColour(point.days),
        fillOpacity: 1
      }).addTo(map)
        .bindTooltip(point.city + ' · ' +
                     plural(point.calls.length, 'open call', 'open calls'), { direction: 'top' })
        .bindPopup(popup(point));
    });

    if (bounds.length === 1) {
      map.setView(bounds[0], zoom);
    } else {
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: zoom });
    }

    say(plural(calls, 'open call', 'open calls') + ' in ' +
        plural(live_points.length, 'city', 'cities') +
        '. Colour follows the deadline, as in the list. Calls held online, and ' +
        'venues with no coordinates on file, have no pin. The filters above do ' +
        'not apply here.');
  }

  function load() {
    say('Loading map…');
    var css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);

    var js = document.createElement('script');
    js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    js.onload = draw;
    js.onerror = function () { say('The map could not load.'); };
    document.head.appendChild(js);
  }

  var started = false;
  panel.addEventListener('toggle', function () {
    if (!panel.open) return;
    if (!started) {
      started = true;
      load();
      return;
    }
    // Reopened: the window may have been resized while the panel was shut,
    // and Leaflet sizes itself from a container it could not measure then.
    if (map) map.invalidateSize();
  });
})();
