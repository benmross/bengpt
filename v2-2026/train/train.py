#!/usr/bin/env python3
"""QLoRA fine-tune on the BenGPT conversations with Unsloth.

Loss is computed on Ben's turns only (train_on_responses_only), conversations
stay whole so the model has to condition on the other side, and one epoch with
a held-out eval guards against the over-fit that cost coherence last time.

  python train.py --model unsloth/gemma-4-12b-it --out /workspace/bengpt/runs/gemma12b
  python train.py --smoke        # 200 conversations, 20 steps: checks the pipeline
"""
import argparse, json, os
ap = argparse.ArgumentParser()
ap.add_argument("--model", default="unsloth/gemma-4-12b-it")
ap.add_argument("--data", default="/workspace/bengpt")
ap.add_argument("--out", default="/workspace/bengpt/runs/gemma12b")
ap.add_argument("--max-seq", type=int, default=2048)
ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--lr", type=float, default=2e-4)
ap.add_argument("--epochs", type=float, default=1.0)
ap.add_argument("--batch", type=int, default=4)
ap.add_argument("--accum", type=int, default=4)
ap.add_argument("--min-year", type=int, default=0, help="train only on conversations from this year on")
ap.add_argument("--smoke", action="store_true")
a = ap.parse_args()
os.environ.setdefault("HF_HOME", "/workspace/hf")

from unsloth import FastLanguageModel
from unsloth.chat_templates import train_on_responses_only
from datasets import Dataset
from trl import SFTTrainer, SFTConfig

model, tok = FastLanguageModel.from_pretrained(a.model, max_seq_length=a.max_seq, load_in_4bit=True)
model = FastLanguageModel.get_peft_model(
    model, r=a.rank, lora_alpha=a.rank, lora_dropout=0,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    use_gradient_checkpointing="unsloth", random_state=3407)

def load(name):
    rows = [json.loads(l) for l in open(f"{a.data}/{name}.jsonl")]
    rows = [r for r in rows if r["meta"]["year"] >= a.min_year]
    return rows[:200] if a.smoke else rows

def render(msgs):
    try:
        return tok.apply_chat_template(msgs, tokenize=False)
    except Exception:
        # Template without a system role: fold the system line into the first user turn.
        m = [dict(x) for x in msgs[1:]]
        m[0]["content"] = msgs[0]["content"] + "\n\n" + m[0]["content"]
        return tok.apply_chat_template(m, tokenize=False)

def to_ds(rows):
    return Dataset.from_list([{"text": render(r["messages"])} for r in rows])

train, evald = to_ds(load("train")), to_ds(load("eval"))
sample = train[0]["text"]
print("=== rendered sample ===\n" + sample[:900] + "\n=======================", flush=True)

trainer = SFTTrainer(
    model=model, tokenizer=tok, train_dataset=train, eval_dataset=evald,
    args=SFTConfig(
        dataset_text_field="text", max_length=a.max_seq,
        per_device_train_batch_size=a.batch, gradient_accumulation_steps=a.accum,
        per_device_eval_batch_size=max(1, a.batch // 2),
        num_train_epochs=a.epochs, max_steps=20 if a.smoke else -1,
        learning_rate=a.lr, lr_scheduler_type="cosine", warmup_ratio=0.03,
        optim="adamw_8bit", weight_decay=0.01, logging_steps=10 if a.smoke else 25,
        eval_strategy="steps", eval_steps=10 if a.smoke else 250,
        save_strategy="steps", save_steps=10 if a.smoke else 250, save_total_limit=4,
        group_by_length=True, output_dir=a.out, report_to="none", seed=3407))

# Mask everything except Ben's turns. The markers are read off the rendered
# sample so the same script works for Gemma and ChatML models.
if "<|turn>" in sample:      # Gemma 4
    inst, resp = "<|turn>user\n", "<|turn>model\n"
elif "<start_of_turn>" in sample:
    inst, resp = "<start_of_turn>user\n", "<start_of_turn>model\n"
elif "<|im_start|>" in sample:
    inst, resp = "<|im_start|>user\n", "<|im_start|>assistant\n"
else:
    raise SystemExit("unknown chat template; set the turn markers by hand:\n" + sample[:400])
trainer = train_on_responses_only(trainer, instruction_part=inst, response_part=resp)
ex = trainer.train_dataset[0]
kept = sum(1 for x in ex["labels"] if x != -100)
print(f"masking check: {kept} of {len(ex['labels'])} tokens carry loss", flush=True)

trainer.train()
model.save_pretrained(f"{a.out}/adapter"); tok.save_pretrained(f"{a.out}/adapter")
print("eval:", trainer.evaluate(), flush=True)
