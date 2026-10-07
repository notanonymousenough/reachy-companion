#!/bin/sh
set -eu
companion_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$companion_root"
case "${1:-}" in hub|robot|worker) companion_role=$1;; *) echo 'Usage: scripts/update.sh hub|robot|worker [--no-pull]' >&2; exit 2;; esac
if [ "${2:-}" != '--no-pull' ]; then
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        echo 'Tracked files have local changes; commit or stash before updating.' >&2
        exit 1
    fi
    companion_remote=$(./scripts/companion config value runtime.git.remote)
    companion_branch=$(./scripts/companion config value runtime.git.branch)
    git pull --ff-only "$companion_remote" "$companion_branch"
    exec "$companion_root/scripts/update.sh" "$companion_role" --no-pull
fi
./scripts/companion config validate
sudo ./scripts/companion update "$companion_role"
