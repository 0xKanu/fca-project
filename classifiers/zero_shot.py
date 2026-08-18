"""Zero-shot LLM classifier via Groq (llama-3.3-70b-versatile).

USER OWNS THE PROMPT (the intellectual part); this module owns the mechanical
JSON handling (structured output, validation, retries, rate-limiting).

Run:
    GROQ_API_KEY=... python -m classifiers.zero_shot [--limit 5] [--sleep 1.0]

Output: data/predictions/zero_shot.csv  (stem, label, confidence)
"""
from __future__ import annotations

import argparse
import json
import os
import time

from .data_utils import LABELS, load_meta, load_text, usable_stems, write_predictions

MODEL = os.environ.get("ZERO_SHOT_MODEL", "llama-3.3-70b-versatile")

SYSTEM_PROMPT = (
    "You are a regulatory analyst classifying Financial Conduct Authority (FCA) "
    "documents by the type of regulatory change they represent. Your task is to "
    "assign exactly one label. Reply with JSON only."
)

# v1 prompt - USER OWNS THIS. Edit freely; keep the JSON contract.
USER_PROMPT_TEMPLATE = """Classify the FCA document below into exactly one of these change types:

- new_rule: creates a NEW obligation, permission, regime or reporting requirement that did not exist before.
- amendment: ALTERS an existing rule, Handbook provision, form or process.
- consultation: SEEKS VIEWS on proposed changes; nothing is final or binding yet.
- guidance: non-binding expectations, interpretation, good/bad practice, or clarification of how rules apply.
- no_change: confirms NO rule change results (feedback statements, withdrawals, outcome summaries).

Decision rules:
1. A Consultation Paper is consultation even if it describes proposed rules.
2. A Policy Statement that changes rules is amendment UNLESS it introduces a brand-new obligation/regime (then new_rule). Use the paper's own wording: "amends"/"changes"/"updates" -> amendment; "introduces"/"creates"/"establishes" -> new_rule.
3. Finalised Guidance is guidance UNLESS the same document contains binding rule changes (then amendment).
4. A feedback statement with no resulting rule is no_change.
5. Handbook Notices are almost always amendment.
6. Draft Q&As and technical annexes are guidance.

Document type: {doc_type}

Document text (first ~2000 characters):
{text}

Return ONLY a JSON object with this exact shape:
{{"label": "<one of: new_rule, amendment, consultation, guidance, no_change>", "confidence": <number 0-1>, "evidence": "<one short sentence>"}}"""


def build_prompt(doc_type: str, text: str) -> str:
    return USER_PROMPT_TEMPLATE.format(doc_type=doc_type, text=text)


def _extract_label(payload: str) -> tuple[str, float, str]:
    """Robustly extract (label, confidence, evidence) from a model payload."""
    payload = payload.strip()
    if payload.startswith("```"):
        payload = payload.strip("`")
        if payload.startswith("json"):
            payload = payload[4:]
    data = json.loads(payload)
    if isinstance(data, dict):
        label = str(data.get("label", "")).strip().lower()
        conf = float(data.get("confidence", 0.0))
        ev = str(data.get("evidence", ""))
        return label, conf, ev
    raise ValueError(f"payload is not an object: {payload[:120]!r}")


def classify_doc(client, doc_type: str, text: str) -> tuple[str, float, str]:
    """One zero-shot call with one retry on malformed/off-label output."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(doc_type, text)},
    ]
    for attempt in range(2):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        try:
            label, conf, ev = _extract_label(content)
            if label in LABELS:
                return label, conf, ev
            # off-label: ask again with a strict nudge
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {"role": "user", "content": "That label is not one of the five allowed values. "
                 "Return ONLY {\"label\": <one of new_rule, amendment, consultation, guidance, no_change>, "
                 "\"confidence\": <0-1>, \"evidence\": \"<short sentence>\"}."}
            )
        except (json.JSONDecodeError, ValueError):
            time.sleep(1.0)
    return "unknown", 0.0, "failed to produce a valid label"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-chars", type=int, default=2000)
    ap.add_argument("--limit", type=int, default=0, help="0 = all usable docs")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between calls")
    args = ap.parse_args()

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise SystemExit("GROQ_API_KEY is not set. Run with: GROQ_API_KEY=... python -m classifiers.zero_shot")

    from groq import Groq

    client = Groq(api_key=key)

    meta = load_meta()
    stems = usable_stems()
    if args.limit:
        stems = stems[: args.limit]

    preds, confs = {}, {}
    for i, stem in enumerate(stems, 1):
        text = load_text(stem, args.max_chars)
        doc_type = meta[stem].get("doc_type", "PS")
        label, conf, ev = classify_doc(client, doc_type, text)
        preds[stem] = label
        confs[stem] = conf
        print(f"[{i}/{len(stems)}] {stem:36s} -> {label:12s} conf={conf:.2f} | {ev[:60]}")
        if i < len(stems):
            time.sleep(args.sleep)

    out = write_predictions("zero_shot", preds, confs)
    print(f"\nWrote {len(preds)} predictions -> {out}")


if __name__ == "__main__":
    main()