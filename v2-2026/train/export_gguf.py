#!/usr/bin/env python3
"""Merge the adapter into the base model and write a 4-bit GGUF for llama.cpp / Ollama."""
import os, sys
os.environ.setdefault("HF_HOME", "/workspace/hf")
from unsloth import FastLanguageModel
RUN = sys.argv[1] if len(sys.argv) > 1 else "/workspace/bengpt/runs/gemma12b"
model, tok = FastLanguageModel.from_pretrained(f"{RUN}/adapter", max_seq_length=2048, load_in_4bit=True)
model.save_pretrained_gguf(f"{RUN}/gguf", tok, quantization_method="q4_k_m")
print("EXPORT_DONE", flush=True)
