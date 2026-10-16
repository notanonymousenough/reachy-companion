"""Read-only ALSA role observations; unknown children never prove absence.

Caller supplies the existing process identity reader, candidate list and bounded
cmdline reader. Only qualified playback may trigger a playback-phase action.
Before/after cue quiescence requires both no playback AND no unknown children.
No retry, sleep, process control or authority grant occurs here.
"""


def observe_roles(proc, candidates, read_cmdline, parent_identity):
    """Return qualified identities and aggregate ambiguity counts only.

    An Agent identity change is always fatal. Child exit/reuse is a sampled
    race, never playback. Permission/I/O errors other than disappearance still
    propagate. A later ordinary caller poll may observe a qualified child.
    """
    parent_pid = parent_identity['pid']
    counts = dict(raced=0, empty=0, unknown=0, capture=0)
    playbacks = []

    def check_parent():
        if proc(parent_pid) != parent_identity:
            raise ValueError('agent_identity_changed')

    check_parent()
    for item in candidates:
        try:
            before = proc(item['pid'])
            if (before != item or before['ppid'] != parent_pid or
                    before['cgroup'] != parent_identity['cgroup'] or
                    before['exe'] != '/usr/bin/aplay'):
                counts['raced'] += 1
                continue
            raw = read_cmdline(item['pid'])
            after = proc(item['pid'])
            if after != before:
                counts['raced'] += 1
                continue
        except (FileNotFoundError, ProcessLookupError):
            counts['raced'] += 1
            continue
        if raw == b'':
            counts['empty'] += 1
            continue
        if type(raw) is not bytes or len(raw) > 8192 or not raw.endswith(b'\0'):
            counts['unknown'] += 1
            continue
        argv = raw.split(b'\0')
        name = argv[0].rsplit(b'/', 1)[-1]
        if (name == b'arecord' or b'--capture' in argv or
                any(a.startswith(b'-') and not a.startswith(b'--') and b'C' in a
                    for a in argv[1:])):
            counts['capture'] += 1
        elif name == b'aplay':
            playbacks.append(item)
        else:
            counts['unknown'] += 1
    check_parent()
    return dict(playbacks=playbacks, counts=counts,
                absence_verified=not playbacks and not any(
                    counts[k] for k in ('raced', 'empty', 'unknown')))
