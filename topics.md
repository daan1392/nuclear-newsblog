---
layout: page
title: Topics
permalink: /topics/
---

Browse articles by topic.

{% include topic-chips.html %}

{% for c in site.data.categories %}
<section class="topic-section" id="{{ c.name | slugify }}">
<h2>{{ c.name | escape }}</h2>
<p class="desc">{{ c.description | escape }}</p>
{% assign posts = site.categories[c.name] %}
{% if posts.size > 0 %}
<ul>
{% for post in posts %}
  <li><a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a> <small>{{ post.date | date: "%-d %b %Y" }}</small></li>
{% endfor %}
</ul>
{% else %}
<p><em>No articles yet.</em></p>
{% endif %}
</section>
{% endfor %}
