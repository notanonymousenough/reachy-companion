"""Build an exact-source, ephemeral audio-only client; never installs it."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEFORE = 'adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f'


def candidate(raw):
    if hashlib.sha256(raw).hexdigest() != BEFORE:
        raise ValueError('Audio-only client preimage changed')
    text = raw.decode()
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Exact audio-only edit unavailable')
        text = text.replace(old, new)
    replace("    base = config['network']['hub_url']\n",
        "    if seconds != 180 or turns != 1 or prime_paused or vision_text is not None:\n"
        "        raise ValueError('Audio-only requires one turn, 180s hard budget, direct listening')\n"
        "    base = config['network']['hub_url']\n")
    replace("        claims['policy'] = policy['epoch'] + 1  # Also covers an applied POST with a lost response.",
            "        if policy['motor_enabled'] is not False or deadline - time.monotonic() < 100:\n"
            "            raise ValueError('Audio-only requires OFF policy and startup reserve')\n"
            "        claims['policy'] = policy['epoch'] + 1  # Disabled-policy ownership only.")
    replace("write('/control/motion-policy', dict(motor_enabled=True, quiet=False, privacy_all=False,",
            "write('/control/motion-policy', dict(motor_enabled=False, quiet=False, privacy_all=False,")
    replace("                or current['microphone_epoch'] != initial['microphone_epoch']):",
            "                or current['microphone_epoch'] != initial['microphone_epoch']\n"
            "                or current['motion_policy']['motor_enabled'] is not False):")
    replace("                        or current['motion_policy']['epoch'] != claims['policy']):",
            "                        or current['motion_policy']['epoch'] != claims['policy']\n"
            "                        or current['motion_policy']['motor_enabled'] is not False\n"
            "                        or current['motion_policy']['quiet']\n"
            "                        or current['motion_policy']['privacy_all']):")
    replace("                if current['capture_active'] and current['listening'] and not listening_reported:",
            "                if current['microphone_enabled'] and current['capture_active'] and current['listening'] and not listening_reported:")
    replace('                if completed >= turns:', '                if listening_reported and completed >= turns:')
    replace("                    print('Microphone capture active: speak related turns now.', flush=True)",
            "                    listening_at = time.monotonic()\n"
            "                    if deadline - listening_at < 90:\n"
            "                        raise TimeoutError('Insufficient bounded human listening window')\n"
            "                    deadline = listening_at + 90\n"
            "                    print('AUDIO_ONLY_LISTENING window_seconds=90 motor_policy=false', flush=True)")
    # Vision path is forbidden before I/O; leave its historical implementation
    # unreachable rather than changing other supported demo behavior.
    compile(text, '<audio-only-client>', 'exec')
    return text.encode()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    raw = candidate((ROOT / 'src/reachy_companion/client.py').read_bytes())
    with args.output.open('xb') as stream:
        stream.write(raw)
    print(hashlib.sha256(raw).hexdigest())
