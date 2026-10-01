// maps.js — every map on the site.
//
// There are four of them and they differ only in what a pin means:
//
//   one      a single venue            (an edition page, a city page)
//   series   where a conference met    (darker = more recent)
//   calls    what is open right now    (the deadline colours from the list)
//   places   cities, linked            (darker = more editions held there)
//
// Everything else — asking before fetching a tile, loading Leaflet once,
// fitting the view without zooming past country level, drawing a pin and
// hanging a popup on it — is the same for all four, and used to be copied
// into three separate files. One file, four small mode objects.
//
// Every holder carries its points as JSON in data-points, written at build
// time. There is no geocoding here: the gazetteer already has coordinates,
// and querying a geocoder on each page view would breach Nominatim's usage
// policy. Each point looks like
//
//   { lat, lon, title, note, tip, rank, links: [{label, url, note, ts}] }
//
// where `rank` is the number the mode colours by, and `ts` is a UNIX time
// after which a link should no longer be shown.

(function () {
  'use strict';

  var LEAFLET = 'https://unpkg.com/leaflet@1.9.4/dist/';

  function escape(text) {
    return String(text).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function plural(n, one, many) {
    return n + ' ' + (n === 1 ? one : many);
  }

  // Constant hue, varying lightness: the ramp shared by `series` and
  // `places`. Keep the stops in step with .map-scale .ramp in site.css, which
  // is the legend that tells a reader what the shades mean.
  var HUE = 212, SAT = 60, LIGHT_LOW = 72, LIGHT_HIGH = 24;

  function ramp(value, low, high) {
    var t = high > low ? (value - low) / (high - low) : 1;
    return 'hsl(' + HUE + ', ' + SAT + '%, ' +
           (LIGHT_LOW + (LIGHT_HIGH - LIGHT_LOW) * t).toFixed(1) + '%)';
  }

  // The five urgency steps of the list, read from the stylesheet rather than
  // repeated here, so a pin and the countdown beside its row are the same
  // colour in light mode and in dark.
  function stepColour(days) {
    var name = days <= 3 ? '--d0' : days <= 7 ? '--d1'
             : days <= 14 ? '--d2' : days <= 30 ? '--d3' : '--d4';
    var value = getComputedStyle(document.documentElement)
                  .getPropertyValue(name).trim();
    return value || '#1f6f5c';
  }

  function links_html(point) {
    if (!point.links || !point.links.length) return '';
    return '<div class="pin-calls">' + point.links.map(function (l) {
      return '<a href="' + escape(l.url) + '">' + escape(l.label) + '</a>' +
             (l.note ? ' <span class="pin-when">' + escape(l.note) + '</span>' : '');
    }).join('<br>') + '</div>';
  }

  function popup(point) {
    return '<b>' + escape(point.title) + '</b>' +
           (point.note ? ' ' + escape(point.note) : '') +
           links_html(point);
  }

  // -- the four modes -----------------------------------------------------
  //
  // prepare() may drop or reorder points; colour() is given the point and the
  // low/high of all ranks on the map; caption() has the last word under it.

  var MODES = {
    one: {
      colour: function () {
        var accent = getComputedStyle(document.documentElement)
                       .getPropertyValue('--accent').trim();
        return accent || '#1f4f8f';
      }
    },

    series: {
      // Oldest first, so recent pins sit on top where cities overlap.
      prepare: function (points) {
        return points.slice().sort(function (a, b) { return a.rank - b.rank; });
      },
      colour: function (point, low, high) { return ramp(point.rank, low, high); }
    },

    calls: {
      // Which calls are open *now*, not at build time: this page can be served
      // from a cache for a day, or from a static snapshot for rather longer,
      // and a closed call must not go on showing a pin either way. Nothing
      // ever needs adding back, because a call that has closed cannot reopen
      // without a rebuild.
      prepare: function (points) {
        var now = Date.now() / 1000;
        var kept = [];
        points.forEach(function (point) {
          var links = point.links.filter(function (l) { return l.ts >= now; });
          if (!links.length) return;
          links.sort(function (a, b) { return a.ts - b.ts; });
          var copy = {};
          for (var k in point) copy[k] = point[k];
          copy.links = links;
          // The pin speaks for the soonest deadline in that city: that is the
          // one a reader still has to act on.
          copy.days = Math.floor((links[0].ts - now) / 86400);
          copy.tip = point.title + ' · ' + plural(links.length, 'open call', 'open calls');
          kept.push(copy);
        });
        // Soonest last, so the urgent pins are drawn on top.
        return kept.sort(function (a, b) { return b.days - a.days; });
      },
      colour: function (point) { return stepColour(point.days); },
      caption: function (points) {
        var calls = points.reduce(function (n, p) { return n + p.links.length; }, 0);
        return plural(calls, 'open call', 'open calls') + ' in ' +
               plural(points.length, 'city', 'cities') +
               '. Colour follows the deadline, as in the list. Calls held online, ' +
               'and venues with no coordinates on file, have no pin. The filters ' +
               'above do not apply here.';
      },
      empty: 'Nothing is open for submission right now — or this page is ' +
             'older than its last deadline.'
    },

    places: {
      prepare: function (points) {
        return points.slice().sort(function (a, b) { return a.rank - b.rank; });
      },
      colour: function (point, low, high) { return ramp(point.rank, low, high); },
      caption: function (points) {
        var held = points.reduce(function (n, p) { return n + p.rank; }, 0);
        return plural(points.length, 'city', 'cities') + ', ' +
               plural(held, 'edition', 'editions') +
               '. Darker means more editions held there. Editions held online, ' +
               'and venues with no coordinates on file, have no pin.';
      }
    }
  };

  // -- loading Leaflet, once per page -------------------------------------

  var waiting = [];
  var state = 'cold';

  function withLeaflet(callback, onError) {
    if (state === 'ready') { callback(); return; }
    waiting.push({ ok: callback, fail: onError });
    if (state === 'loading') return;
    state = 'loading';

    var css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = LEAFLET + 'leaflet.css';
    document.head.appendChild(css);

    var js = document.createElement('script');
    js.src = LEAFLET + 'leaflet.js';
    js.onload = function () {
      state = 'ready';
      waiting.splice(0).forEach(function (w) { w.ok(); });
    };
    js.onerror = function () {
      state = 'cold';
      waiting.splice(0).forEach(function (w) { w.fail(); });
    };
    document.head.appendChild(js);
  }

  // -- one map ------------------------------------------------------------

  function setup(holder) {
    var mode = MODES[holder.dataset.map];
    if (!mode) return;

    var points;
    try {
      points = JSON.parse(holder.dataset.points || '[]');
    } catch (e) {
      points = [];
    }
    if (!points.length) return;

    // Never closer than one venue's map: the question these answer is which
    // part of the world, not which junction.
    var zoom = parseInt(holder.dataset.zoom, 10) || 5;
    var caption = holder.parentNode.querySelector('.map-caption[data-live]');
    var map = null;

    function say(text) {
      if (!caption) return;
      caption.textContent = text;
      caption.hidden = !text;
    }

    function message(text) {
      holder.innerHTML = '<p class="map-missing">' + escape(text) + '</p>';
    }

    function draw() {
      var shown = mode.prepare ? mode.prepare(points) : points;
      if (!shown.length) {
        message(mode.empty || 'Nothing to show on a map.');
        say('');
        return;
      }

      var ranks = shown.map(function (p) { return p.rank; });
      var low = Math.min.apply(null, ranks), high = Math.max.apply(null, ranks);

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
      shown.forEach(function (point) {
        bounds.push([point.lat, point.lon]);
        var marker = L.circleMarker([point.lat, point.lon], {
          radius: 7,
          weight: 2,
          color: '#ffffff',
          opacity: 1,
          fillColor: mode.colour(point, low, high),
          fillOpacity: 1
        }).addTo(map);
        if (point.tip) marker.bindTooltip(point.tip, { direction: 'top' });
        if (point.title) marker.bindPopup(popup(point));
      });

      if (bounds.length === 1) {
        map.setView(bounds[0], zoom);
      } else {
        map.fitBounds(bounds, { padding: [32, 32], maxZoom: zoom });
      }

      if (mode.caption) say(mode.caption(shown));
    }

    function load() {
      say('Loading map…');
      withLeaflet(draw, function () { say('The map could not load.'); });
    }

    // How the reader asks for it. Inside a <details>, opening the panel is
    // the request — one gesture instead of two, and the privacy note sits in
    // the summary where it is read before the click.
    var panel = holder.closest('details');
    if (panel) {
      var started = false;
      panel.addEventListener('toggle', function () {
        if (!panel.open) return;
        if (!started) { started = true; load(); return; }
        // Reopened: the window may have been resized while it was shut, and
        // Leaflet sizes itself from a container it could not measure then.
        if (map) map.invalidateSize();
      });
      return;
    }

    if (holder.dataset.autoload === 'true') {
      // Still only when it comes into view: no point fetching tiles for a
      // panel the reader never scrolls to.
      if ('IntersectionObserver' in window) {
        var watcher = new IntersectionObserver(function (entries) {
          if (entries.some(function (e) { return e.isIntersecting; })) {
            watcher.disconnect();
            load();
          }
        }, { rootMargin: '200px' });
        watcher.observe(holder);
      } else {
        load();
      }
      return;
    }

    var button = holder.querySelector('.map-prompt button');
    if (button) button.addEventListener('click', load);
  }

  Array.prototype.forEach.call(
    document.querySelectorAll('.map-holder[data-map]'), setup);
})();
