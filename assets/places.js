// places.js — make the city and country tables sortable.
//
// Four hundred rows is too many to read and too few to paginate. Sorting is
// what turns it into something you can ask questions of: which city has
// hosted most, which country stopped appearing after 2015.
//
// Progressive, as everything here is: without JavaScript the table is already
// sorted by edition count, which is the order most people want anyway. The
// headers only become buttons once this runs, so nothing invites a click that
// would do nothing.

(function () {
  'use strict';

  function cell(row, index) {
    var td = row.cells[index];
    return td ? td.textContent.trim() : '';
  }

  function compare(kind, index, descending) {
    return function (a, b) {
      var x = cell(a, index), y = cell(b, index);
      var result;
      if (kind === 'number') {
        // An empty cell is "not known", which belongs at the bottom either
        // way round rather than pretending to be zero.
        var nx = parseFloat(x), ny = parseFloat(y);
        if (isNaN(nx) && isNaN(ny)) result = 0;
        else if (isNaN(nx)) return 1;
        else if (isNaN(ny)) return -1;
        else result = nx - ny;
      } else {
        result = x.localeCompare(y, undefined, { sensitivity: 'base' });
      }
      return descending ? -result : result;
    };
  }

  Array.prototype.forEach.call(
    document.querySelectorAll('table.sortable'), function (table) {
      var body = table.tBodies[0];
      if (!body) return;
      var headers = Array.prototype.slice.call(
        table.querySelectorAll('thead th[data-sort]'));

      headers.forEach(function (header, index) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'sortbtn';
        button.innerHTML = header.innerHTML;
        header.innerHTML = '';
        header.appendChild(button);

        button.addEventListener('click', function () {
          // Text sorts A-Z first, numbers largest first: in both cases the
          // end people want to look at.
          var was = header.getAttribute('aria-sort');
          var descending = was === 'ascending' ? true
                         : was === 'descending' ? false
                         : header.dataset.sort === 'number';

          headers.forEach(function (other) { other.removeAttribute('aria-sort'); });
          header.setAttribute('aria-sort', descending ? 'descending' : 'ascending');

          var rows = Array.prototype.slice.call(body.rows);
          rows.sort(compare(header.dataset.sort, index, descending));
          // One reflow, not one per row.
          var holder = document.createDocumentFragment();
          rows.forEach(function (row) { holder.appendChild(row); });
          body.appendChild(holder);
        });
      });

    });
})();
