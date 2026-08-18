"""Write the canonical labels file for the labelling sample.

Labels were assigned by reading each document's abstract/first pages against
data/labelling/TAXONOMY.md. Each row carries a short basis and a high/med/low
confidence marker. Rows marked 'unknown' (JS-rendered HTML with no text layer)
need human review of the live page.

Reads data/labelling/sample.jsonl, applies the curated label map below, and
writes data/labelling/labels.csv (canonical training file).
"""

from __future__ import annotations

import csv
import json
import os
import re
from urllib.parse import urlparse

LABELLING_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "labelling")

# stem -> (label, confidence, basis, notes)
LABELS = {
    "PS23_5": ("amendment", "high", "PS final rules on debt packagers (feedback + made rules)", ""),
    "PS23_13": ("new_rule", "high", "Introduces new s21 financial promotions approval gateway", ""),
    "cp25_27_technical_annex_3": ("guidance", "med", "Technical annex to CP25/27 (market-impact analysis, no rules)", ""),
    "PS24_14": ("amendment", "high", "PS with final transparency rules for bonds/derivatives + DP", ""),
    "CP23_28": ("consultation", "high", "CP proposing updates to Money Market Funds regime", ""),
    "CP25_38": ("consultation", "high", "CP on fund liquidity risk management", ""),
    "PS25_11": ("amendment", "high", "PS final rules simplifying mortgage rules (made rules instrument)", ""),
    "cp24_12": ("consultation", "high", "CP on new POATRs regime", ""),
    "CP26_25": ("consultation", "high", "Open consultation (DWP joint) on Value for Money Framework", ""),
    "CP24_18": ("consultation", "high", "Quarterly consultation paper No. 45", ""),
    "CP25_9": ("consultation", "high", "CP on CCI product information", ""),
    "CP26_20": ("consultation", "high", "CP adapting rules for SIPP providers", ""),
    "CP24_19": ("consultation", "high", "CP on consumer credit regulatory returns", ""),
    "handbook_notice_133": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "PS24_6": ("amendment", "high", "PS final UK Listing Rules (restructure/replace LR)", ""),
    "CP26_22": ("consultation", "high", "CP simplifying insurance rules", ""),
    "handbook_notice_112": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP24_7": ("consultation", "high", "CP on payment optionality for research", ""),
    "FG24_5": ("guidance", "high", "Finalised guidance on prudential assessments", ""),
    "CP24_11": ("consultation", "high", "Quarterly consultation paper No. 44", ""),
    "CP25_17": ("consultation", "high", "CP on targeted pensions/investment support", ""),
    "PS22_14": ("amendment", "med", "Addendum amending CBA text of existing PS22/14", ""),
    "handbook_notice_136": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "PS25_23": ("amendment", "high", "PS made rules/guidance in COCON & FIT on non-financial misconduct", ""),
    "CP24_3": ("consultation", "high", "Quarterly consultation paper No. 43", ""),
    "CP24_9": ("consultation", "high", "CP updating the Financial Crime Guide", ""),
    "CP23_22": ("consultation", "high", "CP on fees and levies proposals", ""),
    "PS23_15": ("amendment", "high", "Joint PS with final remuneration ratio rules (bonus cap)", ""),
    "CP25_36": ("consultation", "high", "CP on client categorisation and conflicts", ""),
    "FG24_1": ("guidance", "high", "Finalised guidance on social media financial promotions", ""),
    "PS23_3": ("new_rule", "high", "Creates new baseline financial resilience regulatory return", ""),
    "PS24_7": ("new_rule", "med", "Implements new Overseas Funds Regime recognition framework", ""),
    "CP24_24": ("consultation", "high", "CP on MiFID Organisational Regulation", ""),
    "handbook_notice_129": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "PS25_2": ("amendment", "high", "PS final rules on DTO classes/exemptions", ""),
    "CP24_20": ("consultation", "high", "CP on payments/e-money safeguarding regime", ""),
    "PS23_2": ("amendment", "high", "PS final rules amending UK EMIR reporting requirements", ""),
    "handbook_notice_125": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "PS25_20": ("new_rule", "high", "Final rules introducing Consumer Composite Investments product regime", ""),
    "CP26_28": ("consultation", "high", "CP on the UK AIFM regime", ""),
    "PS24_2": ("amendment", "high", "PS final rules strengthening borrower protections", ""),
    "PS26_16": ("amendment", "high", "PS final rules amending equity IPO information flows", ""),
    "fca_approach_payment_services_electronic_money_2017_november_2024_tracked_changes": ("guidance", "med", "Approach document (tracked changes) - non-binding guidance", ""),
    "changes_uk_emir_reporting_requirements_draft_questions_answers": ("guidance", "low", "Draft Q&A (interpretive)", "captured text appears to be PS23/2; check live page"),
    "CP25_22": ("consultation", "high", "CP modernising the redress system", ""),
    "CP25_32": ("consultation", "high", "CP improving transaction reporting regime", ""),
    "CP26_17": ("consultation", "high", "Quarterly consultation paper No. 52", ""),
    "PS25_14": ("amendment", "high", "PS final rules simplifying/consolidating own-funds definition", ""),
    "FG23_6": ("guidance", "high", "General guidance on ex-post risk adjustment", ""),
    "CP24_21": ("consultation", "high", "CP on research payment optionality for fund managers", ""),
    "CP25_19": ("consultation", "high", "CP on the Ancillary Activities Test", ""),
    "PS24_13": ("amendment", "high", "Joint PS: consequential amendments to BTS 2016/2251", ""),
    "PS26_12": ("new_rule", "high", "Final prudential regime for cryptoasset firms", ""),
    "CP25_21": ("consultation", "high", "CP reviewing SM&CR", ""),
    "FG25_1": ("guidance", "low", "Primary Market Bulletin (FCA guidance)", "JS-rendered; text unavailable"),
    "handbook_notice_142": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP25_4": ("consultation", "high", "Quarterly consultation paper No. 47", ""),
    "PS26_13": ("new_rule", "med", "Extends FCA Handbook to new regulated cryptoasset activities", ""),
    "ps26_2_amendments_approach_document_annex_2": ("guidance", "med", "Annex amending Payment Services/EMI Approach guidance", ""),
    "cp25_27_technical_annex_2": ("guidance", "med", "Technical annex to CP25/27 (competition analysis, no rules)", ""),
    "CP25_8": ("consultation", "high", "CP on removing reporting/notification requirements", ""),
    "CP25_12": ("consultation", "high", "CP simplifying insurance rules", ""),
    "PS24_15": ("new_rule", "med", "New regulatory framework for pensions dashboard service firms", ""),
    "FG26_4": ("guidance", "high", "Finalised guidance on material third party reporting", ""),
    "handbooknotice123": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "handbook_notice_109": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "PS23_8": ("amendment", "high", "PS amending MCOB to enable Mortgage Charter", ""),
    "CP24_17": ("consultation", "high", "CP enhancing the National Storage Mechanism", ""),
    "CP25_34": ("consultation", "high", "CP on proposed ESG ratings regulation", ""),
    "CP25_11": ("consultation", "high", "CP on Mortgage Rule Review", ""),
    "PS24_8": ("new_rule", "med", "Final rules introducing new cash access assessment regime", ""),
    "CP23_8": ("consultation", "high", "CP on multi-occupancy building insurance", ""),
    "PS25_8": ("amendment", "high", "PS made rules updating fees and levies", ""),
    "CP25_13": ("consultation", "high", "CP improving complaints reporting process", ""),
    "handbook_notice_111": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP23_24": ("consultation", "high", "CP on capital deduction for redress", ""),
    "PS24_18": ("amendment", "high", "PS final rules on temporary motor finance handling rules", ""),
    "FG23_4": ("guidance", "high", "FAQ guidance on remuneration (SYSC 19D)", ""),
    "FG26_5": ("guidance", "high", "Finalised guidance on Consumer Duty for crypto firms", ""),
    "PS23_4": ("amendment", "high", "PS final rules on equity secondary markets transparency", ""),
    "ps26_2_changes_incident_reporting_templates_annex_2": ("amendment", "med", "Annex detailing incident reporting template changes", ""),
    "handbook_notice_128": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP25_41": ("consultation", "high", "CP on crypto admissions/disclosures and MAR", ""),
    "vote_reporting_consultation_discussion_paper": ("consultation", "high", "Consultation + discussion paper on vote reporting", ""),
    "CP23_5": ("consultation", "high", "CP: feedback on CP21/30 plus further consultation on new rules", ""),
    "PS25_7": ("amendment", "high", "PS final rules removing reporting/notification requirements", ""),
    "CP26_7": ("consultation", "high", "CP on credit information market study remedies", ""),
    "handbook_notice_106": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "cp23_29_annex": ("guidance", "med", "Technical annex to CP23/29 (coverage/methodology analysis)", ""),
    "PS25_4": ("amendment", "high", "PS final rules extending joint payment option to fund managers", ""),
    "explanatory_statement_direction_derivatives_trading_obligation_article_28a9_mifir": ("guidance", "med", "Explanatory statement accompanying DTO direction", ""),
    "PS26_15": ("amendment", "high", "PS final rules improving transaction reporting regime", ""),
    "FG23_2": ("guidance", "high", "Finalised guidance for firms supporting mortgage borrowers", ""),
    "CP26_14": ("consultation", "high", "CP on equity IPO information flows", ""),
    "CP23_27": ("consultation", "high", "CP reforming commodity derivatives framework", ""),
    "CP23_18": ("consultation", "high", "Quarterly consultation paper No. 41", ""),
    "CP23_21": ("consultation", "med", "Supporting diagram for CP23/21 proposals", ""),
    "CP25_28": ("consultation", "high", "CP progressing fund tokenisation", ""),
    "explanatory_statement_direction_derivatives_trading_obligation_direction_renewal": ("guidance", "med", "Explanatory statement on DTO direction renewal", ""),
    "PS26_7": ("new_rule", "med", "Final framework enabling fund tokenisation (direct dealing model)", ""),
    "handbook_notice_124": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP23_31": ("consultation", "high", "CP: feedback + detailed listing rules proposals", ""),
    "PS24_1": ("amendment", "high", "PS final rules (made without consultation) on motor finance handling", ""),
    "PS25_21": ("amendment", "high", "PS final rules simplifying insurance rules", ""),
    "FG25_2": ("guidance", "high", "Finalised guidance for insolvency practitioners", ""),
    "FG24_3": ("guidance", "high", "Finalised guidance on the anti-greenwashing rule", ""),
    "handbook_notice_127": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP26_16": ("consultation", "high", "CP on registration of authorised fund assets", ""),
    "CP24_22": ("consultation", "high", "CP on temporary motor finance handling rules", ""),
    "CP23_11": ("consultation", "high", "CP on remuneration proportionality for dual-regulated firms", ""),
    "PS24_11": ("amendment", "high", "PS final rules extending temporary motor finance rules", ""),
    "PS26_10": ("new_rule", "high", "Final regime for stablecoin issuance", ""),
    "handbook_notice_108": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "explanatory_statement_direction_derivatives_trading_obligation_article_28a_mifir": ("guidance", "med", "Explanatory statement for DTO direction under Art 28a(6)", ""),
    "PS23_18": ("amendment", "med", "Final rules transferring IDD regulations into Handbook", ""),
    "CP23_19": ("consultation", "high", "CP on Future Regulatory Framework - IDD", ""),
    "handbook_notice_118": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "ps26_2_changes_third_party_reporting_templates_annex_3": ("amendment", "med", "Annex detailing MTP reporting template changes", ""),
    "cryptoasset_regime": ("unknown", "low", "Overview page of crypto PS suite", "JS-rendered; content unavailable"),
    "CP25_2": ("consultation", "high", "CP on public offers regime and UK Listing Rules", ""),
    "CP25_27": ("consultation", "high", "CP on motor finance consumer redress scheme", ""),
    "handbook_notice_134": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "PS26_9": ("new_rule", "high", "Final admissions/disclosures and MAR regime for cryptoassets", ""),
    "CP25_30": ("consultation", "high", "CP streamlining UK EMIR intragroup regime", ""),
    "CP23_17": ("consultation", "med", "Addendum to CP23/17 (securitisation rules)", ""),
    "CP26_23": ("consultation", "high", "CP on Consumer Duty scope and proportionality", ""),
    "CP26_13": ("consultation", "high", "CP on cryptoasset perimeter guidance", ""),
    "handbook_notice_113": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP25_35": ("consultation", "high", "Quarterly consultation paper No. 50", ""),
    "CP24_13": ("consultation", "high", "CP on new public offer platform regime", ""),
    "FG24_6": ("guidance", "high", "Finalised guidance on risk-based payments approach", ""),
    "PS25_5": ("amendment", "med", "PS revising Enforcement Guide and investigation transparency", ""),
    "PS23_6": ("new_rule", "med", "Brings cryptoasset promotions within financial promotion rules", ""),
    "CP24_16": ("consultation", "high", "CP on Value for Money Framework", ""),
    "FG26_1": ("guidance", "low", "Primary Market Bulletin (FCA guidance)", "JS-rendered; text unavailable"),
    "CP26_27": ("consultation", "high", "CP reforming solo-regulated firms remuneration rules", ""),
    "dto_direction_variation_note": ("guidance", "med", "Explanatory note on DTO transitional direction variation", ""),
    "PS24_16": ("new_rule", "med", "New rules establishing critical third parties regime", ""),
    "handbook_notice_117": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "handbook_notice_119": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP23_33": ("consultation", "med", "CP incl. PS element on consolidated tape framework", ""),
    "CP25_3": ("consultation", "high", "CP on further public offer platform proposals", ""),
    "CP26_4": ("consultation", "high", "CP applying Handbook to crypto activities (part 2)", ""),
    "CP23_2": ("consultation", "high", "CP on structured digital reporting transparency rules", ""),
    "handbook_notice_140": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP25_25": ("consultation", "high", "CP applying FCA Handbook to crypto activities", ""),
    "PS26_8": ("new_rule", "med", "Introduces new annual retail banking data return", ""),
    "PS25_18": ("amendment", "high", "PS final rules on motor finance complaint handling", ""),
    "crypto_relevant_application_period_direction": ("guidance", "med", "Direction setting application period (administrative)", ""),
    "PS25_24": ("amendment", "high", "PS final rules on Ancillary Activities Test", ""),
    "PS25_17": ("amendment", "high", "PS final rules removing SI regime for bonds/derivatives", ""),
    "cba_aggregate_cryptoasset": ("guidance", "med", "Cost benefit analysis document supporting crypto PS suite", ""),
    "CP26_31": ("consultation", "med", "CP incl. policy statement element on UK consolidated tape", ""),
    "explanatory_statement_direction_derivatives_trading_obligation_article_28a9_mifir_2026": ("guidance", "med", "Explanatory statement for DTO direction (2026)", ""),
    "CP26_24": ("consultation", "high", "CP simplifying consumer investment disclosures", ""),
    "FG25_5": ("guidance", "low", "Primary Market Bulletin (FCA guidance)", "JS-rendered; text unavailable"),
    "FG23_5": ("guidance", "high", "General guidance on proportionality (SYSC 19D)", ""),
    "PS26_2": ("new_rule", "med", "Final rules introducing operational incident and third party reporting", ""),
    "CP25_20": ("consultation", "high", "CP on SI regime for bonds/derivatives", ""),
    "PS25_22": ("new_rule", "med", "New rules for targeted support for pensions/investment decisions", ""),
    "CP26_10": ("consultation", "high", "CP simplifying pensions and investment advice rules", ""),
    "CP26_19": ("consultation", "high", "CP updating Decision Procedure and Penalties Manual", ""),
    "PS24_9": ("amendment", "high", "PS final rules enabling joint payment for research", ""),
    "CP23_6": ("consultation", "high", "Quarterly consultation paper No. 39", ""),
    "CP23_26": ("consultation", "high", "CP implementing Overseas Funds Regime", ""),
    "CP24_1": ("consultation", "high", "CP on FSCS Management Expenses Levy Limit", ""),
    "CP25_42": ("consultation", "high", "CP on prudential regime for cryptoasset firms", ""),
    "handbook_notice_122": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "CP24_2": ("consultation", "high", "CP on transparency of enforcement investigations", ""),
    "CP25_7": ("consultation", "high", "CP on fees and levies rates", ""),
    "PS23_14": ("amendment", "high", "PS final rules on multi-occupancy building insurance", ""),
    "payment_services_electronic_money_approach_march_2026": ("guidance", "high", "Our Approach document (version 7) - guidance", ""),
    "CP26_9": ("consultation", "high", "CP modernising the redress system", ""),
    "CP24_26": ("consultation", "high", "Quarterly consultation paper No. 46", ""),
    "handbook_notice_141": ("amendment", "high", "Handbook Notice enacting instrument changes", ""),
    "FG26_2": ("guidance", "high", "Primary Market Bulletin with technical note (FCA guidance)", ""),
    "CP26_26": ("consultation", "high", "CP on fund reporting for asset management entities", ""),
    "PS23_11": ("guidance", "med", "PS making trading venue perimeter guidance (made guidance, no rules)", ""),
    "FG25_3": ("guidance", "high", "Finalised guidance on treatment of PEPs", ""),
    "CP23_29": ("consultation", "high", "CP on access to cash", ""),
}


def stem(rec: dict) -> str:
    ref = rec.get("reference")
    if ref:
        return re.sub(r"\W", "_", ref)
    base = os.path.splitext(os.path.basename(urlparse(rec.get("landing_url") or "").path))[0]
    return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_") or "doc"


def main() -> None:
    with open(os.path.join(LABELLING_DIR, "sample.jsonl"), encoding="utf-8") as f:
        sample = [json.loads(l) for l in f if l.strip()]

    out_path = os.path.join(LABELLING_DIR, "labels.csv")
    fields = ["stem", "title", "reference", "doc_type", "published_date", "label", "confidence", "basis", "notes"]
    rows = []
    for rec in sample:
        s = stem(rec)
        label, conf, basis, notes = LABELS.get(s, ("unknown", "low", "not in curated map", ""))
        rows.append(
            {
                "stem": s,
                "title": rec.get("title"),
                "reference": rec.get("reference") or "",
                "doc_type": rec.get("doc_type"),
                "published_date": rec.get("published_date") or "",
                "label": label,
                "confidence": conf,
                "basis": basis,
                "notes": notes,
            }
        )

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    from collections import Counter

    dist = Counter(r["label"] for r in rows)
    conf = Counter((r["label"], r["confidence"]) for r in rows)
    print(f"Wrote {len(rows)} rows -> {out_path}")
    print("\nLabel distribution:")
    for k, v in sorted(dist.items()):
        print(f"  {k}: {v}")
    print("\nLow-confidence / unknown rows (for spot-check):")
    for r in rows:
        if r["confidence"] == "low" or r["label"] == "unknown":
            print(f"  {r['stem']:45s} {r['label']:12s} {r['notes']}")


if __name__ == "__main__":
    main()
