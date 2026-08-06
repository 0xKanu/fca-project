# FCA Scraper — Engineering Report

Full review of every module, the rationale behind each decision, and a frank
account of what went right vs. what derailed mid-build. Drawn from the actual
source in `scraper/`.

---

## 1. Project overview

A three-level scraping pipeline that collects FCA Policy Statements (PS),
Consultation Papers (CP), Finalised Guidance (FG) and Handbook notices (HN)
published **2023-01-01 → run date (2026-08-05)**, to feed a classifier that
separates change types (new rule / amendment / consultation / guidance).

Final outcome: **320 records** = 286 PDFs + 19 HTML snapshots + 15
intentionally-excluded `.xlsx` attachments, all checksummed and
provenance-tracked, **0 failures, 0 duplicates, 0 missing**.

Dependency stack (`requirements.txt`): `requests`, `lxml`, `beautifulsoup4`,
`tenacity`, `python-dateutil`, `tqdm`.

## 2. Module-by-module review

**`config.py` — single source of configuration.** Holds FCA URLs, the four
category slugs, the date window, `REQUEST_DELAY=1`, and all output paths. Two
decisions matter:

- **Each type is scraped separately** (one query per category slug) so the
  document type is known *from the query*, not inferred from free text — a
  deliberate design choice to make labelling unambiguous.
- **Paths derive from `__file__`** (`BASE_DIR = dirname(dirname(__file__))`)
  so the project is relocatable and the layout doesn't depend on CWD.

**`fetch.py` — the HTTP layer.** A `requests.Session` wrapper with three pillars:

- **Rate limiting** (`_throttle`, min 1s between calls, single worker) —
  respectful scraping and avoidance of 429s.
- **Retry with exponential backoff** via `tenacity` (3 attempts, 1–8s),
  explicitly retrying `ConnectionError`, `Timeout`, and a custom
  `RateLimitExceeded` (raised on HTTP 429).
- **Identifiable UA** so the FCA can see who we are and contact us.

This is the "polite-but-robust" contract reused by every phase.

**`parse_search.py` — Level 1 parser (search row → record).** Selectors pinned
against the live page (`li.search-item`, title/dates/type meta). Key details:

- Reference regex with an optional space (`CP 26/11` vs `CP26/11`), normalised
  by stripping spaces so dedupe + filenames are consistent.
- `_is_sub_document()` — see the major pitfall below.
- `in_date_range()` **drops records with no parseable date** rather than
  silently admitting out-of-window or undated items.

**`index.py` — Level 1 orchestrator.** Paginates with `start = 1, 11, 21…`
(1-indexed, 10 per page), stops when a page is empty **or** when the
descending-date ordering makes the whole page older than the window (early-exit
optimization). Dedupes per-category *and* globally by reference. Writes
**JSONL + CSV** — JSONL is the auditable source of truth; CSV is human-readable.
A `try/except` per page prevents a single flaky fetch from killing the index.

**`parse_landing.py` — Level 2 parser (landing → primary asset).** The subtle
board. It distinguishes:

- `extract_pdf_url` / `_extract_pdf` — the loose browser of PDFs on a landing
  page (used for the external follow-up).
- `extract_primary_pdf` — the *definitive* extractor, preferring the link whose
  **text carries the reference** (e.g. `Read PS25/20 (PDF)`), else the only
  non-annex PDF, else the sole PDF under the type's `/publication/<type>/`
  folder. Multi-document round-ups (Primary Market Bulletins, overviews)
  correctly return `None` so the caller snapshots HTML instead of grabbing an
  arbitrary PDF.
- `external_read_link` — surfaces off-FCA "Read …" anchors (BoE/gov.uk) for
  joint FCA/PRA and FCA/gov.uk publications.
- `_normalise_ref` folds whitespace so refs match even when the human-facing
  text differs.

The `exclude_appendix` flag removes `appendix`/`annex`/technical-notice links so
the *main* instrument wins.

**`download.py` — Levels 2+3 orchestration.** Implements a 5-step resolution
ladder in `resolve_pdf_asset`:

1. landing URL already `.pdf` → download directly;
2. primary PDF on the FCA host → download;
3. predictable `/publication/{type}/ref.pdf` **only if a probe confirms real
   `%PDF`** → download;
4. external "Read" link (BoE/gov.uk), PDF else HTML snapshot;
5. fallback → `.html` snapshot.

Design pillars: **idempotency** (skip when any artifact *or* sidecar for the
stem already exists), **resilience** (per-record `try/except`, failures routed
to `failures.jsonl`/`no_pdf.jsonl`), **auditability** (`_write_resource` emits a
sidecar with title, ref, dates, URLs, `source` local/external, `format`,
`filename`, `sha256`, `downloaded_at`), and **exclusion** of non-PDF
attachments via `NON_PDF_EXT = {.xlsx, .xls, .csv, .ods, .docx, .doc}` logged to
`excluded.jsonl`. A **`%PDF` magic check** rejects mislabeled downloads.

**`README.md`** documents layout, commands, the pipeline, the defensible
decisions, and caveats.

**`extract.py` — text extraction.** Converts every capture to plain text in
`data/text/<stem>.txt`, keyed by the same stem as the sidecars (the join key).
PDFs use `pypdf` with an empty-password decrypt — the FCA encrypts its PDFs with
AES, so `cryptography` is required (a missing dep initially caused ~280 PDFs to
"fail", which was actually pypdf declining to decrypt). HTML snapshots are
cleaned of nav/footer/script chrome via `html_to_text`. Idempotent (existing
.txt skipped); low-text outputs are flagged, not silently dropped.

**`sample.py` — stratified labelling sample.** Draws a reproducible
(`random.Random(seed=42)`) sample stratified by doc_type × publication year,
with proportional allocation and a floor of one per non-empty stratum. Writes
`data/labelling/sample.csv` (empty `label` column) + JSONL.

**`label_draft.py` — heuristic pre-labels.** Doc-type + title-keyword rules
that produce a best-guess label per sampled document (CP→consultation, FG→
guidance, HN→amendment, PS→amendment/new_rule by keyword, plus Q&A/feedback/
withdrawal rules). Outputs `draft_labels.jsonl`; explicitly a starting point
for humans to confirm, not ground truth.

**`storage.py` — GCS upload (Phase 4).** OFF by default (`--upload` or
`FCA_GCS_UPLOAD=1` required). `google-cloud-storage` is an optional
extra (deferred import with a friendly error); uploads `data/text` and
optionally `data/pdfs`/`data/html` mirroring the local layout.

## 3. Engineering decisions worth defending

| Decision | Rationale |
|---|---|
| One worker, 1s delay, identifiable UA | Respectful scraping; fewer 429s; reproducibility |
| Retry w/ exponential backoff + 429 handling | Survives transient DNS/network failure |
| Index-first, download-later | Lets a human inspect the index before spending requests |
| JSONL index = source of truth + sha256 sidecar | Fully auditable/reproducible; corruption detectable |
| Type from query category, not text | Zero ambiguity at labelling time |
| Stable REF filenames (`PS25_20.pdf`), URL-slug fallback | Human-readable, dedupe-friendly, stable across re-runs |
| `%PDF` magic probe before trusting a guessed URL | Never writes garbage for hopeful but wrong URLs |
| HTML snapshot instead of silently dropping | Preserves coverage of PMBs/Q&As/external joint docs |
| Exclude `.xlsx` attachments | Keeps the corpus a *documents* corpus, not misc attachments |
| Idempotency **before** resolution | Re-runs never re-render/re-format an already-captured doc |

## 4. What did NOT go to plan

1. **The `BASE_DIR` path bug.** Early code used **three** `dirname()` calls for
   a file living at `<project>/scraper/config.py`; the root is **two** levels
   up. Output paths were silently created in the wrong place until the
   arithmetic was fixed.

2. **Wrong pagination assumption (0- vs 1-indexed).** The FCA search is
   **`start = 1` → page 1**, not `start = 0`. Corrected to `START_OFFSET = 1`,
   step `10`.

3. **`CP 20/11` vs `CP20/11` space variant.** Titles print the reference
   sometimes with, sometimes without a space. Without normalising it, dedupe
   and filenames would have diverged. Added `reference = raw.replace(" ", "")`.

4. **A single flaky page crashed the whole index build.** Added per-page
   `try/except` in `index.py` → log-and-continue, per "one bad page never kills
   a run".

5. **THE major one — annex/sub-documents shadowed their parents.** Records
   titled `CP26/6: Annex 2…`, `Annex to CP23/29…` **begin with the parent's
   reference**, so `dedupe_by_reference` kept only the annex and **deleted the
   main document from the index** — the main `CP26/6` (Securitisation
   Framework) and `CP23/29` (Access to cash) were genuinely lost. Fixed with
   `_is_sub_document()` → reference-less for annex/appendix/template
   attachments, giving them stable URL-slug keys.

6. **Stale artifacts contaminated the recovered parent docs.** Because run 1
   used the buggy reference scheme, `CP23_29.pdf` and `CP26_6.pdf` actually
   held the *annex* files (the annex had collided and won the stem), and the
   *main* docs were never downloaded. Worse, the idempotency guard obscured it
   (an old sidecar said "done"). Detected only by comparing sidecar titles to
   the corrected index; fixed by deleting the 2 stale pairs and re-downloading
   the main docs.

7. **Idempotency ran too late.** Originally the existence check ran *after*
   resolution → a re-run could **re-resolve and re-format** an existing capture
   (e.g. fetch the landing again, land on HTML instead of PDF, and
   rewrite/split it). Moved the check to the top of `process_record`.

8. **~18 records couldn't be resolved as PDF at all.** This forced a redesign
   rather than a hack: joint FCA/PRA & FCA/gov.uk docs live on **external**
   hosts (added `external_read_link` + `source: external`), PMBs and some Q&As
   are **HTML-only** (→ `data/html/` snapshots), and several annexes are
   **`.xlsx`** (→ excluded + logged).

9. **A red-herring audit scare.** Decomposing the data returned 15 "missing"
   records that were actually the 15 excluded attachments — a **normalisation
   bug in the audit script** (excluded keys held the raw URL basename
   `cp26-6-annex-2`, but `stem()` produces `cp26_6_annex_2`). Not a data loss,
   but it produced a misleading "missing" flag until the comparison was
   normalised on both sides.

10. **Duplicate exclusion log entries.** `excluded.jsonl` is **append-mode**,
    so re-runs logged each excluded record twice (30 lines → 15 unique).
    Cosmetic but confusing when reading logs. Fixed with `log_excluded_if_new`,
    which dedupes on `landing_url` before appending.

11. **Extraction: pypdf silently "failed" on ~280 PDFs.** The FCA encrypts its
    PDFs with AES; without `cryptography` installed pypdf raises
    `DependencyError` on the first decrypt. All 286 PDFs extracted cleanly
    once `cryptography` was installed and `reader.decrypt("")` was applied.

12. **Extraction: `Tag.attrs` can be `None`.** The HTML cleaner used
    `el.get("class", [])`, which crashes on real FCA pages (lxml builder
    produces some tags with `attrs=None`). Fixed with `(el.attrs or {}).get(...)`;
    the unit test's hand-written HTML never hit this — only the live pages did.

13. **Extraction: a summary-regex bug flagged 234 "scanned" PDFs.** The low-text
    check used `(\d+),?\d* chars`, so for "12,345 chars" it read group(1)="12"
    and flagged everything ≥1000 chars as low-text. Fixed to `([\d,]+)` with
    comma-stripping.

14. **JS-rendered HTML snapshots are content-empty.** 11 of the 19 HTML-only
    docs (Primary Market Bulletins, some Q&As) render their content via
    JavaScript, so the HTTP snapshot holds only the page shell (e.g. FG25/6
    → 44 chars). Capturing their real text needs a browser renderer
    (Playwright/Selenium); documented as an open caveat rather than silently
    dropped.

Also worth noting: **UTF-8/encoding** was explicitly handled
(`ensure_ascii=False`, `encoding="utf-8"`) after titles with non-ASCII
characters (em-dashes, etc.) risked corruption.

## 5. What went to plan

- **The 3-level architecture held and scaled** cleanly from first index to
  final download.
- **The happy path was the common path**: most records resolved as a direct
  FCA-hosted PDF via `extract_primary_pdf`, and the predictable type-folder URL
  worked only when it genuinely returned `%PDF` (no garbage written).
- **Replaceability**: idempotency + JSONL-index meant `index.py` ⇒
  `download.py` could be re-run repeatedly and resume cleanly.
- **The audit controls landed end-to-end**: final audit showed **320/320 =
  305 captures + 15 excluded** with 0 failures / duplicates / checksum
  failures, in one command.
- **Date windowing, 1-indexed pagination, global dedupe, and unambiguous
  type-separation all worked as intended.**

## 6. Residual caveats (still open)

- **11 HTML-only docs (PMBs, some Q&As) have near-empty text** — JS-rendered
  content that HTTP snapshots can't capture; needs a browser renderer.
- **`construct_pdf_url` performs an extra probe request per record** —
  acceptable given the rate limit, but a known request-count cost.
- **Heuristics are best-effort**: `_is_sub_document`, `external_read_link` and
  the draft label rules are path/title/keyword based; edge cases need human
  confirmation (which is exactly what the labelling step is for).
- **GCS upload is written but not exercised** — no credentials/bucket in this
  environment; `google-cloud-storage` is an optional extra.

## 7. Recommended next steps (and why)

Priority-ordered. The first two unblock the project's actual goal (a change-type
classifier); the rest are hygiene.

1. **Text extraction (PDF + HTML → plain text).**
   *Why:* a classifier cannot read PDFs/HTML. This is the critical path — every
   downstream step (sampling, labelling, training) needs clean text. Use
   `pdfplumber`/`pypdf` for the 286 PDFs and a BeautifulSoup text-cleaner for
   the 19 HTML snapshots (strip nav/boilerplate). Emit one `.txt` per record
   keyed by the same stem used in `data/metadata/` so sidecars stay the join key.
   This also gives an early quality signal (e.g. scanned/image-only PDFs).

2. **Sample 150–200 documents for labelling.**
   *Why:* the training set must be balanced across the four types (PS/CP/FG/HN)
   **and** across the 2023–2026 years, otherwise the classifier learns type
   distribution instead of change types. Stratified random sampling from the
   extracted corpus is the cheap, statistically sound way to do that.

3. **Define the change-type taxonomy and label the sample.**
   *Why:* the whole pipeline feeds this step. Nail down the label set
   (new rule / amendment / consultation / guidance, + edge cases like
   "no change"/"clarification") before anyone labels, and write labelling
   instructions so the labels are consistent.

4. **GCS upload (Phase 4 — `storage.py`, flag off by default).**
   *Why:* durable, shareable archive for the ML pipeline. Lower urgency than
   extraction because local copies already exist; it is a portability/backup
   win, not a blocker.

5. **Housekeeping (cheap, de-risks existing work):**
   - `git init` + commit (data/ ignored via `.gitignore`);
   - fill in the empty test suite (parser unit tests with captured HTML
     fixtures);
   - make `excluded.jsonl` idempotent (dedupe on write) so logs stay readable.

**Bottom line:** the corpus (320 docs, 305 plain-text captures) is built,
extracted, sampled and pre-labelled. The remaining human-in-the-loop step is
confirming/refining the 180 draft labels in `data/labelling/sample.csv` against
the taxonomy, then committing them as `data/labelling/labels.csv` — the
training set for the classifier.

## Status of the five recommended steps

| # | Step | Status |
|---|---|---|
| 1 | Text extraction (PDF+HTML → `data/text/`) | Done — 305/305, 0 failures (11 JS-rendered HTML docs near-empty, flagged) |
| 2 | Stratified sample 150–200 docs for labelling | Done — 180 docs in `data/labelling/sample.csv` |
| 3 | Change-type taxonomy + labelling schema + draft labels | Done — `TAXONOMY.md`, `labelling_instructions.md`, `draft_labels.jsonl` (heuristic, needs human review) |
| 4 | GCS upload (`storage.py`, off by default) | Done — written + tested off; needs bucket/creds to run |
| 5 | Housekeeping (git init, tests, idempotent excluded log) | Done — committed `29b3713`, 15 unittest cases, excluded-log dedup |
