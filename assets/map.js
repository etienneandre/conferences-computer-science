// map.js — the venue map on an edition page.
//
// Coordinates come from cities.toml and are written into data-lat / data-lon
// at build time. There is no geocoding here: every city in the gazetteer has
// its coordinates, and querying a geocoder on each page view would breach
// Nominatim's usage policy anyway.
//
// Loading tiles reveals the reader's IP address to openstreetmap.org, so the
// map waits to be asked unless the site is configured otherwise. See
// data-autoload, set from site.toml.

(function () {
  'use strict';

  var holder = document.getElementById('map');
  if (!holder) return;

  var lat = parseFloat(holder.dataset.lat);
  var lon = parseFloat(holder.dataset.lon);
  var city = holder.dataset.city || 'this city';
  // Country-level rather than street-level: the useful question is "which
  // corner of the world is this in", not "which junction".
  var zoom = parseInt(holder.dataset.zoom, 10) || 5;

  if (isNaN(lat) || isNaN(lon)) {
    holder.innerHTML = '<p class="map-missing">No coordinates recorded for ' + city +
      '. <a href="https://www.openstreetmap.org/search?query=' +
      encodeURIComponent(city) + '">Look it up on OpenStreetMap</a>.</p>';
    return;
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
    }).setView([lat, lon], zoom);

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 17,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    L.marker([lat, lon]).addTo(map).bindPopup(city);
  }

  function load() {
    message('Loading map\u2026');
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
    // Still only when it comes into view: no point fetching tiles for a panel
    // the reader never scrolls to.
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

  var button = document.getElementById('loadmap');
  if (button) button.addEventListener('click', load);
})();
