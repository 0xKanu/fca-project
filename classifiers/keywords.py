"""Seed keyword lists for the rule-based baseline.

USER OWNS THESE LISTS. They are scaffolded from TAXONOMY.md and the label
'basis' notes in data/labelling/labels.csv, and are meant to be refined by hand
— the rule-based classifier is only as good as this domain knowledge.

Each keyword/phrase is matched case-insensitively as a substring of the
document's first ~2000 chars. Longer phrases trump shorter ones: prefer
distinctive phrases (e.g. "we are asking for comments") over single words
(e.g. "propose", which appears in every Policy Statement).

Editing rules:
- Add a phrase to the list of the label you believe the phrase signals.
- Do NOT add a phrase to more than one list unless you weight it (weights are
  applied additively per hit; 2.0 phrases beat a pile of 1.0 single words).
"""
from __future__ import annotations

# label -> list of (phrase, weight)
KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "consultation": [
        ("consultation paper", 3.0),
        ("we are asking for comments", 3.0),
        ("we are consulting", 2.5),
        ("we welcome your views", 2.5),
        ("we welcome comments", 2.5),
        ("seeking your views", 2.5),
        ("seeking comments", 2.5),
        ("invite you to comment", 2.5),
        ("your comments by", 2.0),
        ("respond by", 2.0),
        ("please respond", 2.0),
        ("draft instrument", 2.0),
        ("discussion paper", 2.5),
        ("questions for consultation", 2.0),
        ("this consultation", 1.5),
        ("consult on", 1.5),
    ],
    "amendment": [
        ("amends the handbook", 2.5),
        ("amend the handbook", 2.5),
        ("amending the handbook", 2.5),
        ("updates the handbook", 2.0),
        ("update the handbook", 2.0),
        ("changes to the handbook", 2.0),
        ("amend", 1.0),
        ("amends", 1.5),
        ("amended", 1.0),
        ("revises", 1.5),
        ("revised", 1.0),
        ("modifies", 1.2),
        ("modify", 1.0),
        ("updates", 1.0),
        ("changes to", 0.8),
        # Non-discriminative "rules were made" phrases occur in BOTH amendment
        # and new_rule PSs; the PS doc_type prior already separates them from
        # consultations, so keep them low-weight.
        ("final rules", 0.8),
        ("legal instrument", 0.8),
        ("instrument", 0.4),
        ("we have made", 0.8),
        ("we have decided", 0.8),
    ],
    "new_rule": [
        ("introducing", 2.0),
        ("introduces", 2.0),
        ("introduce", 1.5),
        ("new regime", 2.5),
        ("new rules", 2.0),
        ("new obligation", 2.0),
        ("new authorisation", 2.0),
        ("new reporting requirement", 2.0),
        ("new reporting", 1.5),
        ("new regulatory return", 2.0),
        ("new framework", 1.8),
        ("regulatory framework for", 1.8),
        ("prudential regime", 2.0),
        ("regulatory regime", 2.0),
        ("registration regime", 1.5),
        ("creates a new", 2.0),
        ("creating a new", 2.0),
        ("establish", 1.5),
        ("establishes", 1.8),
        ("gateway", 2.0),
        ("for the first time", 1.5),
        ("does not exist before", 1.5),
        # named regimes introduced by PSs
        ("crypto regime", 2.0),
        ("stablecoin", 1.0),
        ("tokenisation", 1.0),
        ("pensions dashboard", 1.0),
        ("critical third parties", 1.0),
        ("overseas funds regime", 1.5),
        ("baseline financial resilience", 1.5),
    ],
    "guidance": [
        ("finalised guidance", 3.0),
        ("guidance", 1.0),
        ("draft guidance", 2.0),
        ("non-handbook guidance", 2.5),
        ("good practice", 2.0),
        ("our expectations", 2.0),
        ("we expect firms", 1.5),
        ("expectations for firms", 1.8),
        ("clarifies", 1.5),
        ("clarify", 1.2),
        ("how we interpret", 1.5),
        ("interpretation", 1.2),
        ("technical annex", 2.0),
        ("q&a", 1.5),
        ("questions and answers", 1.5),
        ("frequently asked questions", 1.5),
        ("should consider", 1.2),
    ],
    "no_change": [
        ("feedback statement", 3.0),
        ("no further action", 2.5),
        ("we have decided not to", 2.0),
        ("decided not to proceed", 2.5),
        ("will not proceed", 2.0),
        ("no change", 2.0),
        ("withdrawn", 1.5),
        ("superseded", 1.5),
        ("no rule change", 2.0),
    ],
}

# doc_type priors applied multiplicatively to the keyword score.
# rationale (TAXONOMY.md rules 1-5): CP->consultation; FG->guidance; HN->amendment;
# PS->keyword-driven (rules are made), so only a mild amendment bias.
DOC_TYPE_PRIOR: dict[str, dict[str, float]] = {
    "CP": {"consultation": 3.0, "guidance": 1.0, "amendment": 0.8, "new_rule": 0.8, "no_change": 0.5},
    "FG": {"guidance": 3.0, "amendment": 1.0, "consultation": 0.8, "new_rule": 0.8, "no_change": 0.5},
    "HN": {"amendment": 3.0, "new_rule": 1.0, "guidance": 1.0, "consultation": 0.5, "no_change": 0.5},
    "PS": {"amendment": 1.0, "new_rule": 1.0, "guidance": 1.0, "consultation": 0.6, "no_change": 0.5},
}

# Tie-break / no-signal default per doc_type.
DOC_TYPE_DEFAULT: dict[str, str] = {
    "CP": "consultation",
    "FG": "guidance",
    "HN": "amendment",
    "PS": "amendment",
}