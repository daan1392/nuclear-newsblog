---
layout: page
title: Archive
permalink: /archive/
---

{% assign by_month = site.posts | group_by_exp: "p", "p.date | date: '%B %Y'" %}
{% for m in by_month %}
<section class="archive-month">
<h2>{{ m.name }} <small>({{ m.items.size }})</small></h2>
<ul>
{% for post in m.items %}
  <li><small>{{ post.date | date: "%-d %b" }}</small> <a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a>{% if post.categories.first %} <small>&middot; {{ post.categories.first | escape }}</small>{% endif %}</li>
{% endfor %}
</ul>
</section>
{% endfor %}
