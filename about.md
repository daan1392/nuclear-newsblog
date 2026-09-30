---
layout: page
title: About
permalink: /about/
---

**Nuclear Newswire** is an experiment in automated science journalism about the nuclear sector: power, medicine, radiation protection, fuel and waste, fusion, research, policy and industry.

## How it works

1. **News.** Every day a GitHub Action reads a curated list of nuclear-sector news feeds (see the source list in the repository). Stories are grouped and passed to Claude, which writes a short, original brief for each, in its own words, with links to every source used.
2. **Events.** Every week the same pipeline reads the event pages of national societies and organisations (BNS, SFEN, ANS, SCK CEN, ENS, ENEN and others), extracts conferences, schools, trainings, lectures and visits with their country, and keeps an events calendar. Anyone can submit an event through a form.
3. **Review.** Everything is opened as a **pull request**. Nothing is published until a human editor reviews and merges it.
4. **Publishing.** GitHub Pages rebuilds the site on merge. A weekly roundup post collects the week's articles and upcoming events.

## How AI is used

- The model only sees the feed summaries and page text it is given, and is instructed to use only facts present in them, to avoid copying sentences, and to skip stories that are too thin to support a brief.
- Every article lists its sources and carries an AI-generated disclosure.
- Automated checks reject posts without sources, with missing metadata, or with long quotations.

## Caveats

Articles are machine-written summaries of other outlets' reporting. They can contain mistakes, and event details can change. Always check the linked original sources before relying on any figure, date or claim.

Corrections and event suggestions are welcome: open an issue or a pull request on the [repository](https://github.com/daan1392/nuclear-newsblog).
