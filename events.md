---
layout: page
title: Events
permalink: /events/
---

Upcoming summer schools, trainings, technical visits and community events in the nuclear sector. Collected weekly from the organisers' pages (BNS, ENS, ENEN, SCK CEN, IAEA, OECD/NEA) and reviewed by a human before publication. Always confirm details and registration on the organiser's page.

{% assign today = site.time | date: "%Y-%m-%d" %}
{% assign upcoming = site.data.events | where_exp: "e", "e.end_date >= today" | sort: "start_date" %}
{% assign groups = "summer-school|Summer schools,training|Trainings and courses,technical-visit|Technical visits,social|Social and fun" | split: "," %}

{% if upcoming.size == 0 %}
*No upcoming events listed right now. Check back after the next weekly update.*
{% endif %}

{% for g in groups %}
{% assign parts = g | split: "|" %}
{% assign items = upcoming | where: "type", parts[0] %}
{% if items.size > 0 %}
## {{ parts[1] }}

{% for e in items %}
- **[{{ e.title }}]({{ e.url }})**: {{ e.start_date | date: "%-d %b %Y" }}{% if e.end_date != e.start_date %} to {{ e.end_date | date: "%-d %b %Y" }}{% endif %}{% if e.location and e.location != "" %}, {{ e.location }}{% endif %}  
  {{ e.summary }} *({{ e.organizer }})*
{% endfor %}
{% endif %}
{% endfor %}

Know of an event that's missing? Open a pull request adding it to `_data/events.json`.
