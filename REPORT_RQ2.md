# RQ2 - Three-way classifier comparison

## Question
Which method best classifies FCA policy documents by *type of regulatory
change* (new_rule / amendment / consultation / guidance / no_change), and how
does each compare against a trivial majority-class baseline?

## Methods
1. **rule_based** - deterministic keyword/taxonomy matching
   (`classifiers/keywords.py`, user-owned lists). No training.
2. **zero_shot** - Groq `llama-3.3-70b-versatile` prompted with the taxonomy
   (`classifiers/zero_shot.py`, user-owned prompt). No training.
3. **fine_tuned** - DistilBERT fine-tuned on the 180-doc labelled sample
   (`notebooks/fine_tune_colab.ipynb`). Trains on labels.

## Evaluation protocol (declared asymmetry)
- rule_based and zero_shot use no labels at inference -> evaluated on all
  usable docs (179).
- fine_tuned trains on labels -> evaluated with stratified 5-fold CV;
  its predictions are out-of-fold (each doc predicted by a model that never
  saw it during training).
- All three are scored on the identical document set. `no_change` has no
  representative in the sample, so it cannot be learned/evaluated; the single
  `unknown` row (cryptoasset_regime, JS-rendered) is excluded from all methods.

## Results
| method | status | accuracy | macro-F1 |
|---|---|---|---|
| rule_based | acc 0.816 | 0.816 | 0.596 |
| zero_shot | acc 0.872 | 0.872 | 0.680 |
| fine_tuned | acc 0.693 | 0.693 | 0.316 |
| *majority-class baseline* | - | 0.436 | - |

Per-class F1:

**rule_based** (n=179):
- `new_rule` F1=0.538
- `amendment` F1=0.746
- `consultation` F1=0.917
- `guidance` F1=0.778
- `no_change` F1=0.000
**zero_shot** (n=179):
- `new_rule` F1=0.811
- `amendment` F1=0.843
- `consultation` F1=0.975
- `guidance` F1=0.769
- `no_change` F1=0.000
**fine_tuned** (n=179):
- `new_rule` F1=0.000
- `amendment` F1=0.667
- `consultation` F1=0.915
- `guidance` F1=0.000
- `no_change` F1=0.000

## Error analysis

**rule_based**: 33/179 misclassified - `CP23_17`, `PS23_15`, `PS23_3`, `PS23_4`, `PS23_6`, `PS23_8`, `PS24_13`, `PS24_14`, `PS24_16`, `PS24_6`, `PS24_8`, `PS25_14`...
**zero_shot**: 23/179 misclassified - `PS23_18`, `PS23_5`, `PS24_13`, `PS24_14`, `PS24_18`, `PS24_2`, `PS24_9`, `PS25_14`, `PS25_23`, `PS25_4`, `PS25_8`, `PS26_13`...
**fine_tuned**: 55/179 misclassified - `CP23_21`, `CP24_1`, `CP26_25`, `FG23_2`, `FG23_4`, `FG23_5`, `FG23_6`, `FG24_1`, `FG24_3`, `FG24_5`, `FG24_6`, `FG25_1`...

## Caveats (read before citing)
- `new_rule` has only 16 samples; recall for it is weak in every method.
  The small-N classes are the binding constraint, not the modelling.
- `no_change` (0 samples) cannot be evaluated - none of the methods can learn
  or be scored on it.
- **fine_tuned macro-F1** is 0.316 as scored here (macro-F1 over the full
  5-label set on concatenated out-of-fold predictions). The Colab notebook's
  own per-fold macro-F1 averaged 0.395 - the difference is that the notebook
  averages per-fold macro-F1 (classes with zero recall are folded in only if
  present in that fold's validation), while this harness averages the class
  F1s (new_rule=0, guidance=0, no_change=0) across all 179 predictions. Both
  are reported; this harness is the canonical scorer for the comparison.
- fine_tuned never predicts `new_rule` or `guidance` - with 179 docs it
  collapses to the two majority classes (amendment/consultation), the classic
  small-data overfit. This is why Method C is presented as an *attempted*
  third method.
- 5 labelled rows are low-confidence (3 JS-rendered PMBs, 1 overview doc,
  1 text-mismatch) - see `data/labelling/labels.csv` notes.
- Methods are compared as-is; no hyperparameter search beyond defaults.

## Pre-committed fallback (decided before running, not after)
If fine-tuning is not working by the deadline, the shipped comparison is
rule_based vs zero_shot (a valid two-way answer to RQ2), with fine_tuned
presented as an attempted third method with honest analysis of why it was
hard. Two working methods rigorously compared answer RQ2; a half-understood
third method that cannot be defended is worse.
