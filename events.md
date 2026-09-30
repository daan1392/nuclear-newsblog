---
layout: page
title: Events
permalink: /events/
---

Upcoming conferences, summer schools, trainings, lectures, technical visits, contests and community events in the nuclear sector, grouped by country. Collected weekly from the organisers' pages (BNS, SFEN, Nuclear Institute, ANS, SCK CEN, ENS, ENEN) and reviewed by a human before publication. Always confirm details and registration on the organiser's page.

<p class="ev-actions">
<a class="chip" href="{{ '/events.ics' | relative_url }}">Subscribe (calendar .ics)</a>
<a class="chip" href="{{ '/events.json' | relative_url }}">JSON data</a>
<a class="chip" href="https://github.com/daan1392/nuclear-newsblog/issues/new?template=submit-event.yml">Submit an event</a>
</p>

{% assign today = site.time | date: "%Y-%m-%d" %}
{% assign upcoming = site.data.events | where_exp: "e", "e.end_date >= today" | sort: "start_date" %}
{% assign past = site.data.events | where_exp: "e", "e.end_date < today" | sort: "start_date" | reverse %}
{% assign countries = site.data.countries | sort: "name" %}

{% if upcoming.size == 0 %}
*No upcoming events listed right now. Check back after the next weekly update.*
{% else %}

<div id="ev-map" class="ev-map" aria-label="Map of upcoming events by country"></div>

<div class="ev-filters">
  <input type="search" id="ev-q" placeholder="Search title, organiser, city" aria-label="Search events">
  <select id="ev-country" aria-label="Country">
    <option value="">All countries</option>
    {% for c in countries %}{% assign n = upcoming | where: "country", c.code %}{% if n.size > 0 %}<option value="{{ c.code }}">{{ c.name }} ({{ n.size }})</option>{% endif %}{% endfor %}
    {% assign n = upcoming | where: "country", "ONLINE" %}{% if n.size > 0 %}<option value="ONLINE">Online ({{ n.size }})</option>{% endif %}
    {% assign n = upcoming | where: "country", "UNKNOWN" %}{% if n.size > 0 %}<option value="UNKNOWN">Location unclear ({{ n.size }})</option>{% endif %}
  </select>
  <select id="ev-type" aria-label="Type">
    <option value="">All types</option>
    <option value="conference">Conferences</option>
    <option value="summer-school">Summer schools</option>
    <option value="training">Trainings</option>
    <option value="lecture">Lectures</option>
    <option value="technical-visit">Technical visits</option>
    <option value="contest">Contests</option>
    <option value="social">Social</option>
  </select>
  <span id="ev-count" class="ev-meta"></span>
</div>

<div id="ev-groups">
{% assign home = site.home_country %}
{% for c in countries %}{% if c.code == home %}{% include event-section.html code=c.code name=c.name %}{% endif %}{% endfor %}
{% for c in countries %}{% if c.code != home %}{% include event-section.html code=c.code name=c.name %}{% endif %}{% endfor %}
{% include event-section.html code="ONLINE" name="Online" %}
{% include event-section.html code="UNKNOWN" name="Location unclear" %}
</div>

{% endif %}

{% if past.size > 0 %}
<details class="ev-past">
<summary>Recently past events ({{ past.size }})</summary>
<ul class="ev-list">
{% for e in past %}{% assign cn = "" %}{% for c in countries %}{% if c.code == e.country %}{% assign cn = c.name %}{% endif %}{% endfor %}{% include event-item.html e=e show_country=true country_name=cn %}{% endfor %}
</ul>
</details>
{% endif %}

<p>Know of an event that is missing? <a href="https://github.com/daan1392/nuclear-newsblog/issues/new?template=submit-event.yml">Submit it here</a>, or open a pull request adding it to <code>_data/events.json</code>.</p>

<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<script>
(function () {
  var EVENTS = {{ upcoming | jsonify | replace: "</", "<\/" }};
  var COUNTRIES = {{ site.data.countries | jsonify | replace: "</", "<\/" }};
  var q = document.getElementById('ev-q'), sc = document.getElementById('ev-country'),
      st = document.getElementById('ev-type'), out = document.getElementById('ev-count');
  if (!q) return;

  function apply() {
    var text = q.value.trim().toLowerCase(), shown = 0;
    document.querySelectorAll('#ev-groups .event').forEach(function (li) {
      var ok = (!sc.value || li.dataset.country === sc.value) &&
               (!st.value || li.dataset.type === st.value) &&
               (!text || li.dataset.text.indexOf(text) !== -1);
      li.hidden = !ok; if (ok) shown++;
    });
    document.querySelectorAll('#ev-groups .ev-country').forEach(function (s) {
      s.hidden = !s.querySelector('.event:not([hidden])');
    });
    out.textContent = shown + ' event' + (shown === 1 ? '' : 's');
  }
  [q, sc, st].forEach(function (el) { el.addEventListener('input', apply); });
  apply();

  // Map: one marker per country, sized by number of events.
  if (window.L && EVENTS.length) {
    var map = L.map('ev-map', { scrollWheelZoom: false }).setView([30, 10], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 6, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    var by = {};
    EVENTS.forEach(function (e) { (by[e.country] = by[e.country] || []).push(e); });
    COUNTRIES.forEach(function (c) {
      var list = by[c.code]; if (!list) return;
      var m = L.circleMarker([c.lat, c.lon], { radius: 7 + Math.min(list.length, 12) * 1.5,
        color: '#1f4d2b', fillColor: '#3f9b5a', fillOpacity: 0.7 }).addTo(map);
      var box = document.createElement('div');
      var h = document.createElement('strong'); h.textContent = c.name + ' (' + list.length + ')'; box.appendChild(h);
      list.slice(0, 8).forEach(function (e) {
        var p = document.createElement('div'), a = document.createElement('a');
        a.href = e.url; a.textContent = e.title; a.rel = 'noopener';
        p.appendChild(document.createTextNode(e.start_date + ' '));
        p.appendChild(a); box.appendChild(p);
      });
      var more = document.createElement('a'); more.href = '#c-' + c.code.toLowerCase();
      more.textContent = 'Show all in list'; box.appendChild(more);
      m.bindPopup(box);
    });
  }
})();
</script>

<script type="application/ld+json">
[{% for e in upcoming %}{"@context":"https://schema.org","@type":"Event","name":{{ e.title | jsonify }},"startDate":{{ e.start_date | jsonify }},"endDate":{{ e.end_date | jsonify }},"eventAttendanceMode":"https://schema.org/{% if e.country == 'ONLINE' %}OnlineEventAttendanceMode{% else %}OfflineEventAttendanceMode{% endif %}","url":{{ e.url | jsonify }},"description":{{ e.summary | jsonify }},"organizer":{"@type":"Organization","name":{{ e.organizer | jsonify }}}{% if e.country != 'ONLINE' and e.country != 'UNKNOWN' %},"location":{"@type":"Place","name":{{ e.city | default: e.location | jsonify }},"address":{"@type":"PostalAddress","addressCountry":{{ e.country | jsonify }}}}{% endif %}}{% unless forloop.last %},{% endunless %}{% endfor %}]
</script>
