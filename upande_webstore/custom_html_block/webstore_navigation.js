(function() {
  // Some tiles link to a doctype that only exists on farms running another
  // app alongside this one (Box Type ships with upande_harvest, not with
  // this app). A tile pointing at a missing doctype 404s the moment someone
  // clicks it, so any tile carrying data-doctype is hidden unless that
  // doctype is both installed and readable by the current user.
  //
  // frappe.boot.user.can_read is already built from the site's real DocType
  // rows for this session — a doctype that does not exist on this site can
  // never appear in it — so this is a free check: no extra request, and it
  // degrades to "hidden" for the same reason whether the doctype is absent
  // or just not permitted to this user.
  var canRead = (window.frappe && frappe.boot && frappe.boot.user && frappe.boot.user.can_read) || [];
  root_element.querySelectorAll('.wsn-tile[data-doctype]').forEach(function(tile) {
    var doctype = tile.getAttribute('data-doctype');
    if (doctype && canRead.indexOf(doctype) < 0) {
      tile.classList.add('wsn-hide');
    }
  });

  // A group heading whose entire grid ended up hidden should not sit above
  // an empty box.
  root_element.querySelectorAll('.wsn-grid').forEach(function(grid) {
    var visible = grid.querySelectorAll('.wsn-tile:not(.wsn-hide)').length;
    if (visible === 0) {
      grid.classList.add('wsn-hide');
      var title = grid.previousElementSibling;
      if (title && title.classList.contains('wsn-title')) {
        title.classList.add('wsn-hide');
      }
    }
  });
})();
