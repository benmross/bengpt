#!/usr/bin/env bash
# Watches the training run on a Runpod pod (ssh alias `runpod`) and reports
# progress through $NOTIFY (any command that takes a title and a message;
# default: print only): once 15 minutes in, then hourly. When training ends it
# copies the adapter back to $LOCAL, asks the pod to stop itself, and exits.
# $RATE is the pod's price per hour, for the running cost estimate.
set -u
RUN=${1:-gemma12b}
LOCAL=${LOCAL:-$HOME/bengpt}
RATE=${RATE:-0.74}
START=${START_TS:-$(date +%s)}
say() { [ -n "${NOTIFY:-}" ] && $NOTIFY "BenGPT training" "$1" >/dev/null 2>&1; echo "$(date '+%H:%M') $1"; }

status() {
  ssh -o ConnectTimeout=20 runpod "python3 - $RUN" <<'PY' 2>/dev/null
import re, sys, subprocess
run = sys.argv[1]
log = open("/workspace/bengpt/full.log", errors="replace").read().replace("\r", "\n")
alive = subprocess.run(["pgrep", "-f", "train.py --out"], capture_output=True).stdout.strip() != b""
done = "\neval: {" in log
prog = re.findall(r"\s(\d+)/(\d+) \[([\d:]+)<([\d:]+)", log)
prog = [p for p in prog if int(p[1]) > 500]
# Loss lines reach the log late (stdout is block-buffered), so read them from
# the newest checkpoint's trainer_state.json, written every 250 steps.
import glob, json, os
ev, tr = [], []
states = sorted(glob.glob(f"/workspace/bengpt/runs/{run}/checkpoint-*/trainer_state.json"), key=os.path.getmtime)
if states:
    hist = json.load(open(states[-1]))["log_history"]
    ev = [f"{h['eval_loss']:.3f}" for h in hist if "eval_loss" in h]
    tr = [f"{h['loss']:.3f}" for h in hist if "loss" in h]
err = [l for l in log.split("\n") if "Error" in l or "Traceback" in l][-1:] 
step, total, el, left = prog[-1] if prog else ("0", "?", "0:00", "?")
# tqdm's own estimate swings with the last few steps; use the average pace so far.
if prog and int(step) > 0:
    parts = [int(x) for x in el.split(":")]
    secs = sum(v * 60 ** i for i, v in enumerate(reversed(parts)))
    rem = int(secs / int(step) * (int(total) - int(step)))
    left = f"{rem // 3600}h {rem % 3600 // 60:02d}m"
print("|".join([str(int(alive)), str(int(done)), step, total, el, left,
                ",".join(ev[-4:]), tr[-1] if tr else "", (err[0][:160] if err else "")]))
PY
}

finish() {
  mkdir -p $LOCAL/runs/$RUN
  scp -q -r runpod:/workspace/bengpt/runs/$RUN/adapter $LOCAL/runs/$RUN/ && copied="The adapter is copied to this machine." || copied="Copying the adapter back failed; it is still on the volume."
  scp -q runpod:/workspace/bengpt/full.log $LOCAL/runs/$RUN/ 2>/dev/null
  ssh -n runpod 'export $(tr "\0" "\n" < /proc/1/environ | grep RUNPOD_POD_ID); runpodctl stop pod $RUNPOD_POD_ID' >/dev/null 2>&1 \
    && stopped="The pod has been told to stop; check that it shows as stopped." || stopped="I could not stop the pod from here: stop it in the Runpod console, it is still billing."
  say "$1 $copied $stopped"
}

n=0
while true; do
  if [ $n -eq 0 ]; then sleep ${FIRST_SLEEP:-900}; else sleep 3600; fi
  n=$((n+1))
  s=$(status); IFS='|' read -r alive done step total el left evals trl err <<<"$s"
  spent=$(awk -v s=$START -v n=$(date +%s) -v r=$RATE 'BEGIN{printf "%.2f", (n-s)/3600*r}')
  if [ -z "$s" ]; then say "Could not reach the pod. If you stopped it, ignore this; otherwise it may still be billing."; [ $n -gt 12 ] && exit 1; continue; fi
  if [ "$done" = 1 ]; then finish "Finished all $total steps in $el. Held-out eval loss over the run: ${evals//,/, }. About \$$spent of pod time."; exit 0; fi
  if [ "$alive" = 0 ]; then finish "Training stopped early at step $step of $total. Last error line: ${err:-none found}. Checkpoints are on the volume."; exit 1; fi
  if [ -n "$evals" ]; then losses="Training loss $trl; held-out eval loss at each check so far: ${evals//,/, }."; else losses="No loss figures yet; the first check is at step 250."; fi
  say "Step $step of $total after $el, about $left left. $losses About \$$spent of pod time on this run."
done
