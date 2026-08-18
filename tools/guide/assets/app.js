/* Router, copy, progress. Vanilla JS, no dependencies. Everything
   degrades: no JS = a scrollable document, no localStorage = no resume
   ticks, no clipboard API = execCommand fallback. */
(function () {
  'use strict';

  /* ---- storage, tolerant of file:// profiles that forbid it ---- */
  var KEY = 'resops-guide';
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; }
    catch (e) { return {}; }
  }
  function save(state) {
    try { localStorage.setItem(KEY, JSON.stringify(state)); }
    catch (e) { /* private mode: resume off, everything else works */ }
  }

  /* ---- router ---- */
  var pages = Array.prototype.slice.call(
    document.querySelectorAll('main > .page'));
  var routes = pages.map(function (p) { return p.dataset.route; });
  var navRows = Array.prototype.slice.call(
    document.querySelectorAll('.nav-row'));
  var segments = Array.prototype.slice.call(
    document.querySelectorAll('#progress span'));
  var here = document.getElementById('topbar-here');
  var brandName = document.querySelector('.brand-name').textContent;

  document.documentElement.classList.add('routed');

  function currentIndex() {
    return routes.indexOf(location.hash);
  }

  function markVisited(visited) {
    navRows.forEach(function (r) {
      r.classList.toggle('visited', visited.indexOf(r.dataset.route) !== -1);
    });
    segments.forEach(function (s) {
      s.classList.toggle('done', visited.indexOf(s.dataset.route) !== -1);
    });
  }

  function show(index) {
    pages.forEach(function (p, k) {
      p.classList.toggle('active', k === index);
    });
    var page = pages[index];
    navRows.forEach(function (r) {
      var active = r.dataset.route === page.dataset.route;
      r.classList.toggle('active', active);
      if (active) { r.setAttribute('aria-current', 'page'); }
      else { r.removeAttribute('aria-current'); }
    });
    here.textContent = page.dataset.title;
    document.title = page.dataset.title + ' · ' + brandName;
    var state = load();
    state.visited = state.visited || [];
    if (state.visited.indexOf(page.dataset.route) === -1) {
      state.visited.push(page.dataset.route);
    }
    state.last = page.dataset.route;
    save(state);
    markVisited(state.visited);
    window.scrollTo(0, 0);
  }

  function route() {
    var i = currentIndex();
    if (i === -1) {
      /* no or unknown hash: resume where they were, else start */
      var last = load().last;
      var k = routes.indexOf(last);
      location.replace(routes[k === -1 ? 0 : k]);
      return;
    }
    show(i);
  }

  window.addEventListener('hashchange', route);
  route();

  /* ---- keyboard: mirrors the pager ---- */
  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) { return; }
    var i = currentIndex();
    if (i === -1) { return; }
    if (e.key === 'ArrowRight' && i < routes.length - 1) {
      location.hash = routes[i + 1];
    } else if (e.key === 'ArrowLeft' && i > 0) {
      location.hash = routes[i - 1];
    }
  });

  /* ---- copy: the whole command block is the target; the button is the
     affordance, the button text and a border pulse are the feedback. A
     manual text selection never triggers it. ---- */
  function copyText(text, block, button) {
    function done() {
      button.textContent = 'copied';
      block.classList.remove('copied');
      void block.offsetWidth;  /* restart the pulse animation */
      block.classList.add('copied');
      setTimeout(function () { button.textContent = 'copy'; }, 1200);
    }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch (e) { /* quiet */ }
      document.body.removeChild(ta);
      done();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
  }

  Array.prototype.slice.call(document.querySelectorAll('[data-copy]'))
    .forEach(function (block) {
      var button = block.querySelector('.copy');
      var code = block.querySelector('code');
      block.addEventListener('click', function (e) {
        var selection = window.getSelection();
        if (selection && selection.toString().length > 0 &&
            e.target !== button) { return; }
        copyText(code.innerText, block, button);
      });
    });
})();
