# Summarisation Eval Suite — Key Decisions

## Multi-layer AI evaluation pipeline
The eval system uses three complementary layers: (1) deterministic rule-based checks targeting six failure modes (truncation, vagueness, wrong_document, factual_inversion, contradiction, hallucination) derived through systematic analysis of model output divergences from reference summaries; (2) continuous ROUGE-1/2/L n-gram overlap metrics for quantitative quality measurement against human references; and (3) Claude API-based semantic evaluation that performs holistic natural-language judgment of summary quality, with graceful fallback to heuristics when the API is unavailable in network-isolated environments.

## LLM-based semantic scoring
The Claude integration uses structured prompting to elicit JSON-formatted failure mode identification, enabling semantic reasoning that catches subtle errors rule-based approaches miss — such as meaning-preserving paraphrases that nonetheless introduce false implications. The LLM layer is additive: it can surface additional failure modes not caught by rules, flagged with an "llm:" prefix to distinguish AI-detected from rule-detected failures.

## False-positive minimization through compound signals
Each rule requires strong compound evidence before flagging: truncation needs both short word-count ratio AND absent reference numbers; wrong_document requires named entity disagreement between both summaries; hallucination requires extra sentences AND vocabulary verified absent from the source document.

## ROUGE metrics for continuous quality
ROUGE-1, ROUGE-2, and ROUGE-L F1 scores provide continuous signals across precision/recall/overlap dimensions, enabling nuanced quality ranking and detecting subtle degradation not captured by binary flags.

## Robustness
All three layers are wrapped in per-item try/except blocks; ROUGE is installed via requirements.txt; LLM layer activates only when ANTHROPIC_API_KEY is set.
