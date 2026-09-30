---
layout: page
title: Search
permalink: /search/
---

<input type="search" id="q" class="search-box" placeholder="Search articles, e.g. Borssele, isotopes, SMR" autofocus aria-label="Search articles">
<p id="search-status" class="ev-meta"></p>
<ul id="results" class="post-list"></ul>

<script src="https://cdnjs.cloudflare.com/ajax/libs/lunr.js/2.3.9/lunr.min.js"></script>
<script>
(function () {
  var box = document.getElementById('q'), list = document.getElementById('results'),
      status = document.getElementById('search-status'), idx, docs = {};
  fetch('{{ "/search.json" | relative_url }}').then(function (r) { return r.json(); }).then(function (data) {
    data.forEach(function (d) { docs[d.id] = d; });
    idx = lunr(function () {
      this.ref('id');
      this.field('title', { boost: 10 }); this.field('tags', { boost: 4 });
      this.field('category', { boost: 3 }); this.field('countries', { boost: 3 });
      this.field('excerpt'); this.field('body');
      data.forEach(function (d) { this.add(d); }, this);
    });
    var q = new URLSearchParams(location.search).get('q');
    if (q) { box.value = q; run(); }
  });
  function run() {
    var term = box.value.trim();
    list.textContent = '';
    if (!idx || !term) { status.textContent = ''; return; }
    var hits;
    try { hits = idx.search(term + ' ' + term.split(/\s+/).map(function (w) { return w + '*'; }).join(' ')); }
    catch (e) { hits = []; }
    status.textContent = hits.length + ' result' + (hits.length === 1 ? '' : 's');
    hits.slice(0, 30).forEach(function (h) {
      var d = docs[h.ref], li = document.createElement('li'), a = document.createElement('a'),
          m = document.createElement('span'), p = document.createElement('p');
      a.href = d.url; a.textContent = d.title; a.className = 'post-link';
      m.className = 'post-meta'; m.textContent = d.date + (d.category ? ' · ' + d.category : '');
      p.textContent = d.excerpt;
      li.appendChild(m); li.appendChild(document.createElement('br')); li.appendChild(a); li.appendChild(p);
      list.appendChild(li);
    });
  }
  box.addEventListener('input', run);
})();
</script>
