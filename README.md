# BenGPT

A language model fine-tuned on five years of my own text messages, so that it
texts the way I do. In blind conversations a close friend could not reliably
tell it from me. It is also where my personal agent,
[Herald](https://github.com/benmross/herald), started.

There are two versions here: the original from 2024 to 2025, and a 2026
rebuild that fixed what went wrong with it. This repository has the code and
the method. It has no messages, contact names, datasets, trained weights or
generated samples. Weights trained on private conversations can repeat them,
so those stay off the internet.

## Version 1 (2024 to 2025)

```text
v1-2025/prep/   exports to CSV, then CSV to ShareGPT
v1-2025/train/  the Colab training script and the LLaMA-Factory settings
```

1. Export. Android SMS and MMS through the *SMS Backup & Restore* app (one
   XML file), an Instagram data download, and WhatsApp chat exports.
2. Clean. `sms_clean_backup.py` strips images and video from the backup and
   removes duplicate messages. `sms_extract_conversation.py` pulls out one
   person's thread. `sms_to_csv.py`, `instagram_to_csv.py` and
   `whatsapp_to_csv.py` write each conversation as `sender¦timestamp¦content`
   (sender 0 is you).
3. Format. `csv_to_sharegpt.py` turns those CSVs into ShareGPT
   conversations, splitting on long silences and merging bursts of messages
   into one turn. (The 2025 version of this step lived in a notebook that no
   longer exists; this is the same transformation written down.)
4. Train, on free and paid Google Colab GPUs:
   - April 2024: Llama 3 8B with Unsloth on public instruction data, to learn
     the stack.
   - September 2024 to April 2025: LLaMA-Factory. The main run (19 April 2025)
     was a LoRA (rank 8, alpha 16) on Llama 3.1 8B Instruct through LlamaBoard,
     comparing 4-bit against 8-bit quantization and 1,024 against 2,048-token
     context. Settings: `train/llamafactory/train_lora.yaml`.
   - April and May 2025: Unsloth LoRA (rank 16) on Phi-4 and Qwen3 14B, with
     a chat loop for testing (`train/finetune_lora_colab.py`), and Ollama
     export.

The model picked up my vocabulary and rhythm but lost the
thread of a conversation. It often replied to nothing in particular. The
likely cause was the data format: short, isolated turns gave it little reason
to condition on what the other person had just said.

## Version 2 (2026)

```text
v2-2026/prep/   archives to one cleaned database, then to training conversations
v2-2026/train/  QLoRA training, the reply sweep, GGUF export, run watchers
v2-2026/chat/   a terminal chat client against the exported model
```

1. One cleaned database (`prep/build_unified.py`). SMS, RCS and iMessage
   from my own message archive, the Instagram export, and Discord through
   DiscordChatExporter go into one SQLite table. Every excluded row keeps a
   reason: reactions and tapbacks, stickers, unsent messages, calls, bots,
   edit fallbacks, threads I never wrote in, and threads too short to learn
   from. Links become `<link>` and attachments `<media>`, so the model learns
   that something was sent without memorising it.
2. Who each thread is (`prep/people_candidates.py`). It suggests a person
   for every one-to-one thread with 100+ messages, grouping the same person
   across platforms by name. You correct it by hand and add a relationship.
3. Training conversations (`prep/export.py`). Each example is one
   conversation window with one person, ended by a three-hour silence. It
   opens with a system line naming the person, the relationship, the platform
   and the month, so you can steer it at inference. The other person is
   `user`, you are `assistant`, and consecutive messages are one turn joined
   by newlines, which teaches the burst pattern of real texting. Three percent
   of recent conversations are held out.
4. Training (`train/train.py`) on a rented GPU: a 4-bit QLoRA (rank 16) on
   Gemma 4 12B with Unsloth, loss on my turns only, one epoch, cosine learning
   rate from 2e-4, evaluated every 250 steps. On 22,238 training
   conversations the held-out loss finished at 2.92. `watch.sh` reports
   progress hourly, copies the adapter home and stops the pod when it ends.
5. Checking the voice (`train/gen.py`). For each held-out conversation it
   cuts before one of my real replies and generates that reply at several
   adapter strengths (1.0, 0.8, 0.6 and 0.0, the base model), saved beside
   what I actually sent.
6. Running it (`train/export_gguf.py`, `chat/bengpt`). The adapter is
   merged and exported as a Q4_K_M GGUF, which `llama-server` runs on a
   laptop. In the chat client you play the other person and the model answers.

The 2026 version was written with an AI coding agent working under my
direction. The design decisions above, and the evaluation, are mine.

## Recreating it

You need your own message exports, Python 3.11+, and a GPU with about 24 GB
for training (a rented RTX 4090 or A100 is enough; version 1 ran on Colab).

```bash
# 1. build the database from whichever exports you have
python v2-2026/prep/build_unified.py --instagram ~/ig/messages \
    --discord ~/discord-json --self-name "Your Name" --discord-self-id 1234567890
# 2. suggest who each thread is, then edit people.csv by hand
python v2-2026/prep/people_candidates.py
# 3. write dataset/train.jsonl and dataset/eval.jsonl
python v2-2026/prep/export.py
# 4. on the GPU machine, with the dataset copied to /workspace/bengpt
pip install unsloth trl datasets
python v2-2026/train/train.py --smoke          # 20 steps, checks the pipeline
python v2-2026/train/train.py --out /workspace/bengpt/runs/gemma12b
python v2-2026/train/gen.py /workspace/bengpt/runs/gemma12b
python v2-2026/train/export_gguf.py /workspace/bengpt/runs/gemma12b
# 5. locally, with llama.cpp installed and the GGUF at ~/bengpt/
v2-2026/chat/bengpt "Riley" --rel "friend from school"
```

The chat client reads `chat/people.json`, a map of names to relationships,
which you write yourself and which is git-ignored.

## Privacy

Every training example contains other people's words. The pipeline keeps all
of it on your own machine and a GPU you rent, and this repository's
`.gitignore` excludes exports, databases, datasets, weights and samples.
Do not publish a model trained this way, and keep the people you text in mind
before you train one.
