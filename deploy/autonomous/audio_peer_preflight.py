"""Finite actual device timestamp/lease preflight, no inference or PCM output."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from reachy_companion.config import Config
from reachy_companion.autonomous.audio_peer import PeerClient,PeerLease
from reachy_companion.autonomous.contracts import uid


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','output','owner-file','device-script'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();cfg=Config(a.config);controller=uid()
    client=PeerClient('http://127.0.0.1:8780',cfg.token,controller)
    child=subprocess.Popen([sys.executable,str(a.device_script),'--config',str(a.config),
        '--output',str(a.output),'--owner-file',str(a.owner_file),'--controller',controller,
        '--duration','10','--allow-capture-output','--capture-device','reachymini_audio_src'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    import threading
    samples=[];start=time.monotonic();last=None;job=None;lease=PeerLease(client);next_status=0
    try:
        while child.poll() is None and time.monotonic()-start<15:
            lease.tick()
            if time.monotonic()>=next_status and (not job or not job.is_alive()):
                next_status=time.monotonic()+.1
                def status():
                    nonlocal last
                    began=time.monotonic()
                    try:last=client.call('/status');samples.append((time.monotonic()-began)*1000)
                    except Exception:pass
                job=threading.Thread(target=status,daemon=True);job.start()
            time.sleep(.005)
        child.wait(timeout=1)
    finally:
        lease.close()
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=1)
    receipt=json.loads(a.output.read_text()) if a.output.exists() else {}
    accepted=(child.returncode==0 and receipt.get('accepted') is True and last
        and not any(event['kind']=='speech_progress' for event in receipt.get('playback',{}).get('timeline',[])))
    print(json.dumps(dict(mode='actual_capture_clock_no_output_preflight',accepted=bool(accepted),
        child_exit=child.returncode,lease=lease.status(),status_requests=len(samples),max_status_ms=max(samples,default=None),
        receipt=receipt)),flush=True)
    if not accepted:raise SystemExit(2)


if __name__=='__main__':main()
