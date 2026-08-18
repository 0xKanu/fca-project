"""Classifiers for FCA change-type prediction (RQ2 three-way comparison).

Methods:
- rule_based: deterministic keyword/taxonomy matching (no training).
- zero_shot: Groq LLM (llama-3.3-70b-versatile) prompted with the taxonomy.
- fine_tuned: DistilBERT fine-tuned on the 180-doc labelled sample (Colab).
"""