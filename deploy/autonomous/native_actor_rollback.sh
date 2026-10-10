#!/bin/bash
# Independent finite-test recovery. An unknown release leaves the factory
# fenced; it does not reopen another serial writer or invent a known stop.
set -eu
exec 9>/run/reachy-native-fence-recovery.lock
flock -w 5 9
if [ ! -f /run/reachy-native-finite-owner.flag ]; then exit 0; fi
if [ "$(cat /run/reachy-native-finite-owner.flag)" != "$3" ]; then exit 1; fi
systemctl stop reachy-native-finite-actor.service || true
systemctl stop reachy-mini-daemon.service
runuser -u pollen -- env PYTHONPATH=/home/pollen/reachy-shadow/src \
  /venvs/mini_daemon/bin/python "$1" --production-root "$2" \
  --output /home/pollen/reachy-shadow/unused-recovery-receipt.json --recover --intent "$4"
rm /run/reachy-native-finite-owner.flag
rm -f /run/systemd/system/reachy-mini-daemon.service.d/90-reachy-native-finite-fence.conf
systemctl daemon-reload
systemctl start reachy-mini-daemon.service
