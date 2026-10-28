#!/usr/bin/env python3
"""Adapter-strength sweep. For each held-out conversation, cut it before one of
Ben's replies, let the model write that reply at several LoRA strengths, and
save the candidates beside what he actually sent."""
import json, random, sys, os, torch
os.environ.setdefault("HF_HOME", "/workspace/hf")
from unsloth import FastLanguageModel
RUN = sys.argv[1] if len(sys.argv) > 1 else "/workspace/bengpt/runs/gemma12b"
SCALES = [1.0, 0.8, 0.6, 0.0]
model, tok = FastLanguageModel.from_pretrained(f"{RUN}/adapter", max_seq_length=2048, load_in_4bit=True)
FastLanguageModel.for_inference(model)
lora = [m for m in model.modules() if hasattr(m, "lora_A") and hasattr(m, "scaling")]
base = [dict(m.scaling) for m in lora]
def set_scale(s):
    for m, b in zip(lora, base):
        for k in b: m.scaling[k] = b[k] * s
print("lora layers", len(lora), flush=True)

random.seed(7)
rows = [json.loads(l) for l in open("/workspace/bengpt/eval.jsonl")]
out = open(f"{RUN}/sweep.jsonl", "w")
for r in rows:
    msgs = r["messages"]
    idx = [i for i, m in enumerate(msgs) if m["role"] == "assistant" and i >= 2]
    if not idx: continue
    cut = random.choice(idx[-3:])               # a late reply, so there is context to track
    prompt = tok.apply_chat_template(msgs[:cut], tokenize=False, add_generation_prompt=True)
    enc = tok(text=prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
    rec = {"system": msgs[0]["content"], "context": msgs[max(1, cut - 6):cut], "real": msgs[cut]["content"], "gen": {}}
    for s in SCALES:
        set_scale(s)
        torch.manual_seed(1)
        with torch.no_grad():
            y = model.generate(**enc, max_new_tokens=80, do_sample=True, temperature=0.7, top_p=0.9)
        rec["gen"][str(s)] = tok.decode(y[0][enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
print("SWEEP_DONE", flush=True)
