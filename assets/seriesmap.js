// seriesmap.js — every venue of one conference series, on a single map.
//
// Same policy as map.js: no geocoding at page view, and no tile request until
// the reader asks for one (or scrolls to it, when site.toml allows autoload).
//
// The points are written into data-points at build time, already grouped by
// city: a series that met three times in Paris gets one pin, not three
// stacked on the same spot. Colour carries the chronology — the lighter the
// pin, the older the most recent visit.

(function () {
  'use strict';

  var holder = document.getElementById('seriesmap');
  if (!holder) return;

  var points;
  try {
    points = JSON.parse(holder.dataset.points || '[]');
  } catch (e) {
    points = [];
  }
  if (!points.length) return;

  // Never closer than the edition map: the question a reader asks of this map
  // is "which parts of the world", not "which street".
  var zoom = parseInt(holder.dataset.zoom, 10) || 5;

  // Constant hue, varying lightness. Keep these in step with .map-scale .ramp
  // in site.css, which shows the reader what the shades mean.
  var HUE = 212, SAT = 60, LIGHT_OLD = 72, LIGHT_NEW = 24;

  var years = points.map(function (p) { return p.newest; });
  var oldest = Math.min.apply(null, years);
  var newest = Math.max.apply(null, years);

  function shade(year) {
    // A single year, or all editions in one year: use the darkest shade
    // rather than dividing by zero.
    var t = newest > oldest ? (year - oldest) / (newest - oldest) : 1;
    return 'hsl(' + HUE + ', ' + SAT + '%, ' +
           (LIGHT_OLD + (LIGHT_NEW - LIGHT_OLD) * t).toFixed(1) + '%)';
  }

  function escape(text) {
    return String(text).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function popup(point) {
    var links = point.editions.map(function (e) {
      return '<a href="' + escape(e.url) + '">' + escape(e.label) + '</a>';
    }).join(', ');
    return '<b>' + escape(point.city) + '</b> ' + escape(point.flag) +
           '<br>' + escape(point.acronym) + ' ' + links;
  }

  function message(text) {
    holder.innerHTML = '<p class="map-missing">' + text + '</p>';
  }

  function draw() {
    holder.innerHTML = '';
    holder.classList.add('is-live');
    var map = L.map(holder, {
      scrollWheelZoom: false,
      zoomControl: true,
      attributionControl: true
    });

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 17,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    var bounds = [];
    // Oldest first, so the recent pins are drawn on top where they overlap.
    points.forEach(function (point) {
      bounds.push([point.lat, point.lon]);
      L.circleMarker([point.lat, point.lon], {
        radius: 7,
        weight: 2,
        color: '#ffffff',
        opacity: 1,
        fillColor: shade(point.newest),
        fillOpacity: 1
      }).addTo(map)
        .bindTooltip(point.label + ' · ' + point.city, { direction: 'top' })
        .bindPopup(popup(point));
    });

    if (bounds.length === 1) {
      map.setView(bounds[0], zoom);
    } else {
      map.fitBounds(bounds, { padding: [24, 24], maxZoom: zoom });
    }
  }

  function load() {
    message('Loading map…');
    var css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);

    var js = document.createElement('script');
    js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    js.onload = draw;
    js.onerror = function () { message('The map could not load.'); };
    document.head.appendChild(js);
  }

  if (holder.dataset.autoload === 'true') {
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

  var button = document.getElementById('loadseriesmap');
  if (button) button.addEventListener('click', load);
})();
