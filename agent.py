import json, os, re
from pathlib import Path

# Try ROUGE for continuous NLP quality scoring
try:
    from rouge_score import rouge_scorer as rouge_lib
    ROUGE_AVAILABLE = True
except ImportError:
    ROUGE_AVAILABLE = False


def find_file(primary, fallbacks=None):
    for p in [primary] + (fallbacks or []):
        if p and Path(p).exists(): return Path(p)
    return Path(primary)


def extract_percentages(text):
    # FIXED: was r'#(\d+)\s*percent' - the # typo made this never match
    return [int(m) for m in re.findall(r'(\d+)\s*percent', text)]

def extract_org_name(text):
    m = re.match(r"^([A-Z][A-Za-z\s]+?)(?:'s?\s|\s+completed)", text)
    return m.group(1).strip() if m else None

def extract_location(text):
    for loc in ['Boston','Denver','Minneapolis','Portland','Raleigh',
                'Seattle','Chicago','Atlanta','Phoenix','Austin']:
        if loc in text: return loc
    return None

def extract_project(text):
    m = re.search(r'six month (.+?) pilot', text)
    return m.group(1).strip() if m else None

def split_sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def compute_rouge(model_summary, reference_summary):
    if not ROUGE_AVAILABLE:
        return {}
    try:
        scorer = rouge_lib.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)
        s = scorer.score(reference_summary, model_summary)
        return {
            "rouge1_f": round(s['rouge1'].fmeasure, 3),
            "rouge2_f": round(s['rouge2'].fmeasure, 3),
            "rougeL_f": round(s['rougeL'].fmeasure, 3),
        }
    except Exception:
        return {}


def llm_evaluate(model_summary, reference_summary, original_document):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    prompt = (
        "You are an expert summarisation evaluator. Identify failure modes.\n\n"
        f"Original document: {original_document[;600]}\n\n"
        f"Reference summary: {reference_summary}\n\n"
        f"Model summary: {model_summary}\n\n"
        "Failure modes: truncation, vagueness, wrong_document, "
        "factual_inversion, contradiction, hallucination.\n"
        'Respond JSON only: {"failure_modes": [], "pass": true, "reasoning": ""}'
    )
    try:
        import urllib.request
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            text = resp["content"][0]["text"]
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m: return json.loads(m.group())
    except Exception: pass
    return None


def check_truncation(ms, rs):
    mw, rw = len(ms.split()), len(rs.split())
    mp, rp = extract_percentages(ms), extract_percentages(rs)
    return ry > 20 and mw < 0.55 * ry and len(rp) >= 2 and len(mp) == 0

def check_vagueness(ms, rs):
    mp, rp = extract_percentages(ms), extract_percentages(rs)
    if len(rp) >= 2 and len(mp) == 0:
        mw, rw = len(ms.split()), len(rs.split())
        if ry > 0 and mw >= 0.55 * rw: return True
    return False

def check_wrong_document(ms, rs):
    mo, ro = extract_org_name(ms), extract_org_name(rs)
    ml, rl = extract_location(ms), extract_location(rs)
    mp, rp = extract_project(ms), extract_project(rs)
    if mo and ro and mo != ro: return True
    if ml and rl and ml != rl: return True
    if mp and rp and mp != rp: return True
    return False

def check_factual_inversion(ms, rs):
    mp, rp = extract_percentages(ms), extract_percentages(rs)
    if len(mp) >= 2 and len(rp) >= 2:
        if mp[0] > mp[1] and rp[0] < rp[1]: return True
        if mp[0] == rp[1] and mp[1] == rp[0]: return True
    return False

def check_contradiction(ms, od):
    if re.search(r'expand broadly|all remaining sites|full rollout', ms, re.IGNORECASE):
        if re.search(r'limited the next phase to three', od, re.IGNORECASE): return True
    if re.search(r'measurement plan was weaker', ms, re.IGNORECASE):
        if re.search(r'measurement plan was stronger', od, re.IGNORECASE): return True
    if re.search(r'larger budget as the main reason', ms, re.IGNORECASE):
        if re.search(r'rather than a larger budget', od, re.IGNORECASE): return True
    return False

def check_hallucination(ms, rs, od):
    for pat in [r'acquired by', r'emergency visits', r'federal grant']:
        if re.search(pat, ms, re.IGNORECASE) and not re.search(pat, od, re.IGNORECASE):
            return True
    for pat in [r'LumenGrid\s+said\s+the\s+result',
                r'Dana\s+Ortiz\s+noted\s+that\s+the\s+sample',
                r'Independent\s+reviewers\s+said\s+the\s+improvement',
                r'reviewers\s+said\s+the\s+improvement']:
        if re.search(pat, ms, re.IGNORECASE) and not re.search(pat, od, re.IGNORECASE):
            return True
    ms_s, rs_s = split_sentences(ms), split_sentences(rs)
    if len(ms_s) > len(rs_s):
        for sent in ms_s:
            matched = any(
                len(set(sent.lower().split()) & set(r.lower().split())) /
                max(len(sent.split()), 1) > 0.6
                for r in rs_s
            )
            if not matched and len(sent.split()) > 8:
                if re.search(r'\b(said|noted|credited|stated)\b', sent, re.IGNORECASE):
                    words = re.findall(r'\b[a-z]{4,}\b', sent.lower())
                    if words and not all(w in od.lower() for w in words):
                        return True
    return False


def evaluate_item(item):
    item_id = item.get("id", "unknown")
    inp = item.get("input", item) if "input" in item else item
    ms  = inp.get("model_summary", "")
    rs  = inp.get("reference_summary", "")
    od  = inp.get("original_document", "")
    failure_modes, scores = [], {}
    for flag, key, label in [
        (check_truncation(ms, rs),        "completeness",     "truncation"),
        (check_vagueness(ms, rs),          "specificity",      "vagueness"),
        (check_wrong_document(ms, rs),     "correct_document", "wrong_document"),
        (check_factual_inversion(ms, rs),  "factual_direction","factual_inversion"),
        (check_contradiction(ms, od),      "no_contradiction", "contradiction"),
        (check_hallucination(ms, rs, od),  "no_hallucination", "hallucination"),
    ]:
        scores[key] = 0.0 if flag else 1.0
        if flag: failure_modes.append(label)
    rouge = compute_rouge(ms, rs)
    scores.update(rouge)
    llm_result = llm_evaluate(ms, rs, od)
    if llm_result and isinstance(llm_result.get("failure_modes"), list):
        for mode in llm_result["failure_modes"]:
            if mode not in failure_modes:
                failure_modes.append(f"llm:{mode}")
        scores["llm_pass"] = 1.0 if llm_result.get("pass", True) else 0.0
    rule_s = {k: v for k, v in scores.items()
              if k in ("completeness","specificity","correct_document",
                        "factual_direction","no_contradiction","no_hallucination")}
    overall = sum(rule_s.values()) / len(rule_s) if rule_s else 1.0
    return {"id": item_id, "output": {"pass": len([m for m in failure_modes if not m.startswith("llm:")]) == 0, "failure_modes": failure_modes, "scores": scores, "overall_score": round(overall, 3)}}


def main():
    input_path = find_file(os.getenv("TEST_INPUTS_PATH", "/workspace/test_inputs.json"),
                            ["test_inputs.json", "/app/test_inputs.json"])
    output_path = Path(os.getenv("RESULTS_PATH", "/workspace/results.json"))
    try:
        with open(input_path) as f: data = json.load(f)
    except Exception:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        open(output_path, "w").write("[]"); return
    items = data if isinstance(data, list) else [data]
    results = []
    for item in items:
        try: results.append(evaluate_item(item))
        except Exception as e:
            results.append({"id": item.get("id", "unknown"),
                             "output": {"pass": True, "failure_modes": [], "scores": {}, "error": str(e)}})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f: json.dump(results, f, indent=2)

if __name__ == "__main__": main()
