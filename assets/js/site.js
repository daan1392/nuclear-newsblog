(function () {
  var root = document.documentElement;

  // Theme switcher: auto -> light -> dark
  var btn = document.getElementById('mode-btn');
  function apply(mode) {
    root.dataset.mode = mode;
    root.dataset.theme = mode === 'auto' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : mode;
  }
  if (btn) {
    btn.addEventListener('click', function () {
      var next = { auto: 'light', light: 'dark', dark: 'auto' }[root.dataset.mode || 'auto'];
      try { localStorage.setItem('nn-mode', next); } catch (e) {}
      apply(next);
    });
  }
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
    if ((root.dataset.mode || 'auto') === 'auto') apply('auto');
  });

  // Ctrl/Cmd+K opens search
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      var s = document.querySelector('.search-btn');
      if (s) location.href = s.href;
    }
  });

  // "On this page" table of contents from h2/h3 in the article
  var toc = document.getElementById('toc');
  var prose = document.querySelector('.prose');
  if (toc && prose) {
    var heads = prose.querySelectorAll('h2[id], h3[id]');
    if (heads.length >= 2) {
      var h = document.createElement('h4'); h.textContent = 'On this page'; toc.appendChild(h);
      heads.forEach(function (el) {
        var a = document.createElement('a');
        a.href = '#' + el.id; a.textContent = el.textContent;
        if (el.tagName === 'H3') a.className = 'sub';
        toc.appendChild(a);
      });
      var links = toc.querySelectorAll('a');
      var spy = function () {
        var cur = null;
        heads.forEach(function (el, i) { if (el.getBoundingClientRect().top < 140) cur = i; });
        links.forEach(function (a, i) { a.classList.toggle('active', i === cur); });
      };
      document.addEventListener('scroll', spy, { passive: true });
      spy();
    }
  }


  // Pages without enough headings: drop the empty TOC column so content uses the full width
  var aside = document.querySelector('aside.toc');
  if (aside && !aside.querySelector('a')) aside.remove();

  // Back to top
  var top = document.getElementById('to-top');
  if (top) {
    document.addEventListener('scroll', function () { top.classList.toggle('show', window.scrollY > 600); }, { passive: true });
    top.addEventListener('click', function (e) { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
  }
})();
