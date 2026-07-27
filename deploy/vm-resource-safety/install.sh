#!/usr/bin/env bash
# install.sh — (re)apply the Fields VM resource-safety layer. Idempotent.
#
# Added 2026-07-27 after the VM OOM-wedged and needed an external reset.
# Applies: memory caps on session/ollama/runner slices, OOM protection for
# mongod/orchestrator, 4GB swap, and the fast resource-guard timer.
# Run on the VM as a user with sudo:  bash deploy/vm-resource-safety/install.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
RUNNER="actions.runner.Will954633-fields-automation.fields-vm-runner.service"

echo "1/4 systemd drop-ins (memory caps + OOM priority)..."
sudo mkdir -p /etc/systemd/system/code-server.service.d /etc/systemd/system/ollama.service.d \
              /etc/systemd/system/mongod.service.d /etc/systemd/system/fields-orchestrator.service.d \
              "/etc/systemd/system/${RUNNER}.d"
sudo cp "$DIR/dropins/code-server.zz-resource-caps.conf"        /etc/systemd/system/code-server.service.d/zz-resource-caps.conf
sudo cp "$DIR/dropins/ollama.zz-resource-caps.conf"             /etc/systemd/system/ollama.service.d/zz-resource-caps.conf
sudo cp "$DIR/dropins/mongod.zz-oom-protect.conf"              /etc/systemd/system/mongod.service.d/zz-oom-protect.conf
sudo cp "$DIR/dropins/fields-orchestrator.zz-oom-protect.conf" /etc/systemd/system/fields-orchestrator.service.d/zz-oom-protect.conf
sudo cp "$DIR/dropins/actions-runner.zz-resource-caps.conf"    "/etc/systemd/system/${RUNNER}.d/zz-resource-caps.conf"

echo "2/4 resource-guard service + timer..."
sudo cp "$DIR/fields-resource-guard.service" /etc/systemd/system/
sudo cp "$DIR/fields-resource-guard.timer"   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fields-resource-guard.timer

echo "3/4 swap (ensure 4GB total)..."
if ! swapon --show | grep -q /swapfile2; then
  sudo fallocate -l 2G /swapfile2 || sudo dd if=/dev/zero of=/swapfile2 bs=1M count=2048
  sudo chmod 600 /swapfile2 && sudo mkswap /swapfile2 && sudo swapon /swapfile2
  grep -q /swapfile2 /etc/fstab || echo '/swapfile2 none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "4/4 apply OOM protection to running mongod/orchestrator now..."
for pid in $(pgrep -x mongod); do echo -800 | sudo tee /proc/$pid/oom_score_adj >/dev/null; done
OPID=$(systemctl show fields-orchestrator -p MainPID --value); [ "${OPID:-0}" != "0" ] && echo -500 | sudo tee /proc/$OPID/oom_score_adj >/dev/null || true

echo "done. Verify: systemctl list-timers fields-resource-guard.timer ; free -h"
