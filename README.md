# FCA Policy & Guidance Scraper — Automated Regulatory Change Detection

Downloads FCA Policy Statements (PS), Consultation Papers (CP), Finalised
Guidance (FG) and Handbook notices published 2023-01-01 to the run date, and
classifies each by **type of regulatory change** (`new_rule`, `amendment`,
`consultation`, `guidance`, `no_change`).

**Positioning (fintech).** The pipeline monitors the FCA — the UK regulator —
as the source of truth for changes firms must track. Fintech is the
highest-exposure sector: the corpus includes the cryptoasset regime, stablecoin
rules, tokenisation, open banking, payments and consumer-credit documents.
The monitoring pipeline and its RQ2 classifier comparison are the research
deliverables; the fintech lens is the application narrative, not a separate
dataset.

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
  run_pipeline.py   one-command detect -> capture -> extract -> classify
classifiers/
  keywords.py       user-owned keyword lists (rule-based baseline)
  rule_based.py     Method A: deterministic keyword/taxonomy classifier
  zero_shot.py      Method B: Groq LLM zero-shot classifier (default)
  evaluate.py       shared evaluation harness -> REPORT_RQ2.md
  data_utils.py     shared loading / prediction IO
notebooks/
  fine_tune_colab.ipynb   Method C: DistilBERT fine-tune (runs on Colab)
scripts/
  fca_pipeline.sh   cron wrapper around run_pipeline.py
.github/workflows/
  scheduled_pipeline.yml   cloud-native alternative (workflow_dispatch only)
data/
  index/            index_all.jsonl / .csv   (source of truth)
  pdfs/             <REF>.pdf (e.g. PS25_20.pdf) or <url-slug>.pdf
  html/             HTML snapshots (PMBs, Q&As, external-hosted docs)
  metadata/         one .json sidecar per capture (provenance + sha256)
  text/             one .txt per capture (plain-text corpus for the classifier)
  labelling/        sample + taxonomy + labels.csv (180 labelled docs)
  predictions/      per-method predictions, metrics, latency_log.jsonl
  logs/             excluded.jsonl
```

## Commands

```bash
# Build / refresh the index (Level 1). Does NOT download anything.
python -m scraper.index

# Incremental: only new publications since the last index (delta -> index_new).
python -m scraper.index --incremental

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
python -m scraper.storage --upload --bucket my-bucket [--prefix fca-corpus]

# --- RQ2 classifiers ---
python -m classifiers.rule_based              # Method A: full run -> data/predictions/rule_based.csv
GROQ_API_KEY=... python -m classifiers.zero_shot   # Method B: full run (see --models to list your tier)
python -m classifiers.evaluate                # regenerate REPORT_RQ2.md comparison

# --- Automated monitoring (Phase 2) ---
python -m scraper.run_pipeline                # detect -> capture -> extract -> classify
python -m scraper.run_pipeline --method rule_based --upload --bucket my-bucket
```

## One-command monitoring pipeline

`python -m scraper.run_pipeline` chains the existing stages as subprocesses and
**stops when there is nothing new**:

```
index --incremental -> download (delta only) -> extract -> predict (zero_shot)
```

- Prediction is **idempotent**: stems already in `data/predictions/<method>.csv`
  are skipped, so re-runs never duplicate.
- Per-document failures are handled inside each stage (logged to
  `data/logs/`, run continues); only a stage-level failure aborts.
- **Latency instrumentation (RQ3):** every newly detected document is appended
  to `data/predictions/latency_log.jsonl` with `{stem, reference,
  published_date, detected_at, classified_at}` (UTC), so detection-to-
  classification latency can be computed and compared against a manual
  weekly-monitoring baseline.

### Scheduling

**Option 1 — local cron** (`scripts/fca_pipeline.sh`):

```cron
0 */6 * * *  cd /home/you/fca_project && ./scripts/fca_pipeline.sh >> data/logs/cron.out 2>&1
```

**Why 6-hourly:** the FCA publishes only a few documents per week, on business
days. 6-hourly polling bounds detection latency to a few hours while keeping
load and Groq cost negligible.

**Option 2 — GitHub Actions** (`scheduled_pipeline.yml`): the cloud-native
alternative. It is shipped **`workflow_dispatch`-only** (the 6-hourly `schedule`
is commented out) so it never fires unattended and burns Actions minutes. To
enable production cron, follow the steps in the workflow file's header: the
runner starts from an empty `data/` (gitignored), so you must commit the index
and set `GROQ_API_KEY`/`GCS_BUCKET`/`GCS_KEY` secrets first.

> **Verified limitation (2026-08-18):** the FCA returns **HTTP 403 to
> GitHub-hosted runner IP ranges** — the identical request (same URL, same
> User-Agent) returns 200 from a residential IP. A `workflow_dispatch` run
> executes the full plumbing (checkout, deps, GCS credential wiring, pipeline,
> artifact upload) but the index step fetches 0 records. Real cloud polling
> needs a self-hosted runner on a non-blocked IP or an FCA-permitted proxy;
> local cron (Option 1) is the production detection path.

## Classifier comparison (RQ2)

Three methods are compared on 179 labelled docs; the report is `REPORT_RQ2.md`.

| method | accuracy | macro-F1 | notes |
|---|---|---|---|
| majority baseline | 0.436 | — | naive reference |
| rule_based | 0.816 | 0.596 | keyword matching (`keywords.py`, user-owned) |
| zero_shot | 0.872 | 0.680 | Groq `openai/gpt-oss-120b`, taxonomy prompt |
| fine_tuned | 0.693 | 0.316 | DistilBERT 5-fold CV (Colab) — attempted third method |

Evaluation protocol is deliberately asymmetric and documented: rule_based and
zero_shot use no labels at inference and are scored on all usable docs; the
fine-tuned model trains on labels so it is scored out-of-fold via stratified
5-fold CV. The pre-committed fallback (two rigorous methods answer RQ2) is
honoured in the report.

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