# FCA Policy & Guidance Scraper

Downloads FCA Policy Statements (PS), Consultation Papers (CP), Finalised
Guidance (FG) and Handbook notices published 2023-01-01 to the run date.

## Layout

```
scraper/
  config.py         URLs, category slugs, date window, paths
  fetch.py          rate-limited, retrying HTTP session (1s delay, UA)
  parse_search.py   Level 1: search-results page -> records
  index.py          Level 1 orchestrator: paginate, dedupe, write index
  parse_landing.py  Level 2: landing page -> primary PDF URL
  download.py       Level 3: download PDFs + JSON sidecars
  extract.py        PDF/HTML -> plain text (data/text/)
  sample.py         stratified labelling sample (data/labelling/)
  label_draft.py    heuristic draft labels for the sample
  storage.py        optional GCS upload (off by default)
data/
  index/            index_all.jsonl / .csv   (source of truth)
  pdfs/             <REF>.pdf (e.g. PS25_20.pdf) or <url-slug>.pdf
  html/             HTML snapshots (PMBs, Q&As, external-hosted docs)
  metadata/         one .json sidecar per capture (provenance + sha256)
  text/             one .txt per capture (plain-text corpus for the classifier)
  labelling/        sample + taxonomy + draft labels for the labelling step
  logs/             excluded.jsonl
```

## Commands

```bash
# Build / refresh the index (Level 1). Does NOT download anything.
python -m scraper.index

# Download the PDFs (Levels 2+3). Idempotent — safe to re-run (skips).
python -m scraper.download            # all
python -m scraper.download --limit 5  # subset for a pilot

# Extract plain text from every capture (PDF + HTML) into data/text/.
python -m scraper.extract

# Draw a stratified labelling sample (180 docs) into data/labelling/.
python -m scraper.sample --size 180

# Heuristic draft labels for the sample (human review still required).
python -m scraper.label_draft

# Optional GCS upload (OFF by default — pass --upload to act).
python -m scraper.storage --bucket my-bucket
```

## How the scrapers work

**Level 1 (indexing).** For each of the four types, paginate
`/publications/search-results` with `category=<doc type>`, `sort_by=dmetaZ`
(date desc), `p_search_term=+`, and `start = 1, 11, 21, ...` (1-indexed; 10 rows
per page; stops when a page is empty or earlier than the window). Each result
row is `<li class="search-item">`. The reference (`PS25/20`) is read from the
headline; dates from `.search-item__meta .published-date`. Records are deduped
by reference and filtered to the date window. Records with no reference are
kept (URL slug is used as their key and filename).

**Level 2 (landing → asset).** If a landing URL is already a `.pdf`, use it
directly. Otherwise fetch the page and look for the `Read <REF> (PDF)` anchor;
a PDF is only taken as *definitive* if its link text carries the reference or
it is the page's only non-annex PDF. Otherwise, in order: try a predictable
`/publication/<type>/<ref>.pdf` URL, follow an external "Read" link (joint
FCA/PRA or FCA/gov.uk publications) to its PDF, and finally fall back to an
HTML snapshot of the page (`data/html/`, flagged `format: html`).

**Level 3 (download).** Download via the rate-limited session, verify the
bytes (PDF magic / HTML), write `data/pdfs/<name>.pdf` or `data/html/<name>.html`,
and emit a JSON sidecar with title, reference, type, dates, URLs, source
(local/external), format, filename and SHA-256. Anything already present is
skipped; `.xlsx`/spreadsheet attachments are logged as excluded.

## Design decisions (worth defending)

- **One worker + 1s delay** — respectful, low-load scraping; avoids rate limits.
- **Idempotent** — a record is skipped once any artifact (PDF or HTML) or its
  sidecar exists, so re-runs resume cleanly and never re-format a capture.
- **Resilient** — every record/page is try/except'd; one bad page never kills a
  run; failures go to `data/logs/`.
- **Auditable** — the JSONL index is the source of truth; each capture has a
  checksummed sidecar with full provenance.
- **Unambiguous types** — each category is scraped separately, so a document's
  type (PS/CP/FG/HN) is known from the query, not inferred from free text.
- **HTML-only + external docs kept** — rather than silently dropping documents
  the FCA publishes only as HTML (Primary Market Bulletins, some Q&As) or hosts
  jointly on BoE/gov.uk, we snapshot the page and mark `source: external`.
- **Sub-documents don't shadow parents** — annex/appendix/template records
  (whose titles start with the parent ref, e.g. "CP26/6: Annex 2…") are treated
  as reference-less so they can't collide with and dedupe out the parent doc.

## Caveats

- ~15 spreadsheet attachments (`.xlsx` reporting/exposure templates) are
  excluded by design and logged in `data/logs/excluded.jsonl`.
- **HTML-only documents that render content via JavaScript** (Primary Market
  Bulletins, some Q&As) are captured as HTTP snapshots that contain only the
  page shell (~11 docs in `data/text/` have near-empty text). Extracting their
  real content requires a browser renderer (Playwright/Selenium).
- Excludes speeches, newsletters, Dear-CEO letters and research notes by
  design (they muddy change-type classification); noted as future work.