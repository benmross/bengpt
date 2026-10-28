#!/usr/bin/env bash
# Waits for the GGUF export on the pod (ssh alias `runpod`), copies the file to
# $LOCAL, asks the pod to stop, and reports once through $NOTIFY. Gives up
# after 90 minutes.
LOCAL=${LOCAL:-$HOME/bengpt}
say() { [ -n "${NOTIFY:-}" ] && $NOTIFY "BenGPT export" "$1" >/dev/null 2>&1; echo "$(date '+%H:%M') $1"; }
stop_pod() { ssh -n runpod 'export $(tr "\0" "\n" < /proc/1/environ | grep RUNPOD_POD_ID); runpodctl stop pod $RUNPOD_POD_ID' >/dev/null 2>&1 && echo "The pod has been told to stop; check that it shows as stopped." || echo "I could not stop the pod from here: stop it in the Runpod console, it is still billing."; }
for i in $(seq 1 90); do
  sleep 60
  s=$(ssh -n -o ConnectTimeout=20 runpod 'cd /workspace/bengpt; grep -a -c EXPORT_DONE export.log; pgrep -f "[e]xport_gguf.py" | wc -l' 2>/dev/null | tr '\n' ' ')
  set -- $s
  if [ "${1:-0}" -ge 1 ]; then
    mkdir -p $LOCAL/runs/gemma12b/gguf
    f=$(ssh -n runpod 'ls -S /workspace/bengpt/runs/gemma12b/gguf*/*.gguf /workspace/bengpt/runs/gemma12b/*.gguf 2>/dev/null | head -1')
    if [ -n "$f" ] && scp -q "runpod:$f" $LOCAL/runs/gemma12b/gguf/; then
      say "The 4-bit model file is on this machine ($(du -h $LOCAL/runs/gemma12b/gguf/*.gguf | cut -f1 | head -1)). $(stop_pod)"
    else
      say "The export finished on the pod but copying the file to this machine failed. The pod is left running so nothing is lost; it is still billing."
    fi
    exit 0
  fi
  if [ "${2:-1}" -eq 0 ] && [ -n "$s" ]; then
    say "The export to a 4-bit file failed on the pod. The trained adapter is already safe on this machine. $(stop_pod)"; exit 1
  fi
done
say "The export has not finished after 90 minutes. The pod is still running and billing."
