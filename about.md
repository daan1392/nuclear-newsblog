---
layout: page
title: About
permalink: /about/
---

**Nuclear Newswire** is an experiment in automated science journalism.

## How it works

1. Once a day, a GitHub Action reads a curated list of nuclear-sector news feeds.
2. New stories are grouped and passed to Claude, which writes a short, original brief for each — in its own words, with links to every source used.
3. The briefs are opened as a **pull request**. Nothing is published until a human editor reviews and merges it.
4. GitHub Pages rebuilds the site on merge.

## Caveats

Articles are machine-written summaries of other outlets' reporting. They can contain mistakes. Always check the linked original sources before relying on any figure or claim.

Corrections are welcome — open an issue or a pull request on the repository.
