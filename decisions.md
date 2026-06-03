# Summarisation Eval Suite — Key Decisions

## Multi-dimensional failure detection
Six independent eval functions each target a distinct failure mode: truncation (ratio + missing numbers), vagueness (no specifics despite adequate length), wrong_document (entity/location/project mismatch), factual_inversion (reversed before/after percentages), contradiction (direct semantic negation of source), and hallucination (extra sentences introducing fabricated facts or wrong attributions).

## Signal-based, not LLM-based
All evals use regex and lightweight text analysis — no external dependencies or network calls —!making results deterministic and reproducible in the network-isolated sandbox.

## Low false-positive design
Each check requires a strong positive signal before flagging: truncation needs both short length AND missing numbers; wrong_document requires both summaries to have named entities that disagree; hallucination requires extra sentences AND at least one word absent from the source.

## Attribution error patterns
Wrong-attribution hallucinations (e.g., "LumenGrid said the result" vs "Dana Ortiz said") are caught via explicit regex patterns that check whether a specific subject+verb+object appears in the model but not the original.

## Handles both input formats
Supports flat {id, field} and wrapped {id, input:{...}} formats; all errors are caught per-item so one bad document never fails the entire batch.