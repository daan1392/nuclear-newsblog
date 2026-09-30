# Nuclear Newswire

A nuclear-sector news blog written by AI, reviewed through pull requests, and hosted on GitHub Pages.

```
 RSS feeds ──► GitHub Action (daily) ──► Claude writes briefs ──► Pull request ──► you review & merge ──► GitHub Pages publishes
```

## Setup (about 10 minutes)

1. **Create the repo.** Push this folder to a new GitHub repository.
   - Repo named `<username>.github.io` → site at `https://<username>.github.io/`, keep `baseurl: ""`.
   - Any other name (e.g. `nuclear-newswire`) → set `baseurl: "/nuclear-newswire"` in `_config.yml`.
2. **Turn on Pages.** *Settings → Pages → Build and deployment → Source: Deploy from a branch → `main` / root.*
3. **Add your API key.** *Settings → Secrets and variables → Actions → New repository secret*: `ANTHROPIC_API_KEY` (from console.anthropic.com).
4. **Let Actions open PRs.** *Settings → Actions → General → Workflow permissions*: select **Read and write** and tick **Allow GitHub Actions to create and approve pull requests**.
5. **Create the label** `articles` (*Issues → Labels*) — optional, the PR is tagged with it.
6. **Test it.** *Actions → Generate articles → Run workflow.* A PR with today's articles appears within a minute or two.

### Optional: automatic checks on the article PRs
PRs opened with the default `GITHUB_TOKEN` don't trigger other workflows, so the *Check posts* workflow won't run on them (the generator already validates before opening the PR). To get the check on the PR itself, create a fine-grained personal access token with *Contents* and *Pull requests* read/write on this repo and save it as the secret `PR_TOKEN`.

## Daily workflow

Each morning (06:17 UTC) you get a PR titled *📰 New articles — YYYY-MM-DD*. Open *Files changed*, then:
- **Fix** anything directly in the PR (pencil icon on a file),
- **Drop** an article by deleting its file,
- **Merge** to publish; Pages rebuilds in ~1 minute.

No new stories → no PR. Unmerged PRs can simply be closed; their items stay marked as seen.

## Configuration

| What | Where |
|---|---|
| News sources | `scripts/feeds.yml` (`enabled: false` to pause one) |
| Articles per day, look-back window | `max_articles`, `max_age_hours` in `scripts/feeds.yml` |
| Schedule | `cron` in `.github/workflows/generate.yml` |
| Editorial voice and rules | `SYSTEM_PROMPT` in `scripts/generate_articles.py` |
| Model | `NEWSBLOG_MODEL` env var (default `claude-sonnet-5-5`) |
| Site title, theme | `_config.yml` |

Check the feed URLs once with a dry run — some outlets move their RSS endpoints:

```bash
pip install -r requirements.txt
python scripts/generate_articles.py --dry-run
```

## Writing articles yourself

Human-written posts go through the same flow: add `_posts/YYYY-MM-DD-your-slug.md` with front matter like the generated ones (`title`, `date`, `categories`, `sources`) on a branch and open a PR.

## Local preview

```bash
bundle install
bundle exec jekyll serve   # http://localhost:4000
```

## Editorial safeguards built in

- Articles are written only from the feed summaries, in the model's own words; one short quote per article at most.
- Every article lists and links its sources and carries an AI-generated disclosure.
- `scripts/validate_posts.py` rejects posts without sources, too-short bodies, or long quotations.
- Nothing goes live without a human merge.

## Cost

A run sends ~20–60 short feed items and gets back up to 5 briefs — typically a few cents per day.

## Events page

`/events/` lists upcoming summer schools, trainings, technical visits and social events. Every Monday the *Update events* workflow reads the pages in `scripts/event_sources.yml` (BNS, ENS, ENEN, SCK CEN), has Claude extract the events they list, and opens a PR that edits `_data/events.json`. Review and merge like the article PRs; past events drop off automatically.

- IAEA and OECD/NEA block automated requests, and LinkedIn cannot be scraped, so add events from those by hand to `_data/events.json` (fields: `title`, `type` = `summer-school` | `training` | `technical-visit` | `social`, `start_date`, `end_date`, `location`, `organizer`, `summary`, `url`, `source`). Hand-added entries are kept.
- Test fetching locally with `python scripts/generate_events.py --dry-run`.

## Topics, archive and backfill

- Categories live in `_data/categories.yml` (nuclear power, nuclear medicine, NORM & radiation protection, waste & decommissioning, fuel cycle, fusion, research, policy, regulation, safety & security, industry). The generator, the validator and the **Topics** page all read that file; add a category there and it is available everywhere.
- The home page shows the 20 latest articles; **Archive** lists everything by month.
- **Backfill:** *Actions → Generate articles → Run workflow*, and enter a date in `since` (e.g. `2026-09-01`). It covers that period week by week (feeds page back where possible, plus the World Nuclear News sitemap), dates each article by its sources, and opens a separate PR titled *Backfill articles*. Feeds only keep a few weeks of history, so older periods have thinner coverage.
- Daily volume is set by `max_articles` in `scripts/feeds.yml` (now 12). Short feed items (IAEA, NRC) are enriched with text from the linked page before writing.
