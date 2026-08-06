# Labelling Instructions

1. Open `data/labelling/sample.csv` (180 rows, stratified by type and year).
2. For each row, open the document text at `data/text/<stem>.txt` (fall back to
   `data/pdfs/<stem>.pdf` / `data/html/<stem>.html` if the text is missing).
3. Assign **exactly one** label from the taxonomy in `TAXONOMY.md`:
   `new_rule`, `amendment`, `consultation`, `guidance`, `no_change`.
4. Read the **first ~2 pages** (abstract + feedback summary) — the dominant
   effect is stated there. Only scan deeper for ambiguous cases.
5. Put the label in the `label` column; add a short justification to `notes`
   only when the choice was not obvious (e.g. "mixed doc, amendment dominates").
6. Do **not** change any other column. Do **not** reorder rows.

## Pre-filled drafts

A heuristic draft (`data/labelling/draft_labels.jsonl`) has been generated from
title/doc_type and simple keywords. It is a **starting point only** — treat
every row as unlabelled until a human confirms it. The `label` column in
`sample.csv` is intentionally empty.

## When done

Save the filled CSV as `data/labelling/labels.csv` (same schema). That file is
the training set for the classifier.
