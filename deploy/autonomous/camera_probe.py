"""Opt-in one-frame video-only IPC probe; never initialises SDK audio or motors."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path
import signal
import sys
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4


def capture(frame_path, results):
    camera = None
    stage = 'sdk_import'
    deadline = time.monotonic()+6
    try:
        from importlib.metadata import version
        from reachy_mini.media.camera_gstreamer import GStreamerCamera
        from reachy_mini.media.camera_constants import get_camera_specs_by_name
        stage = 'camera_construct'
        camera = GStreamerCamera(camera_specs=get_camera_specs_by_name('wireless'))
        stage = 'camera_open'
        camera.open()
        stage = 'camera_read'
        frame = camera.read()
        while frame is None and time.monotonic()<deadline:
            time.sleep(.05)
            frame = camera.read()
        received = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        if frame is None:
            pad=camera._appsink_video.get_static_pad('sink')
            caps=pad.get_current_caps()
            results.put({'capture_error':'no_frame','capture_stage':stage,
                         'pipeline_state':camera.pipeline.get_state(0).state.value_nick,
                         'negotiated_caps':caps.to_string() if caps else None})
            return
        stage = 'camera_dimensions'
        if frame.shape != (720, 1280, 3):
            results.put({'capture_error':'unexpected_shape','source_shape':list(frame.shape)})
            return
        stage = 'audio_import_check'
        if 'reachy_mini.media.audio_gstreamer' in sys.modules:
            raise RuntimeError('Audio module unexpectedly imported')
        # Bounded transport sample; plain RGB, no ML or image-content inference.
        sample = frame[::4, ::4, ::-1].copy()
        height, width, _ = sample.shape
        payload = f'P6\n{width} {height}\n255\n'.encode()+sample.tobytes()
        with Path(frame_path).open('xb') as out: out.write(payload)
        Path(frame_path).chmod(0o600)
        results.put(dict(frame_id=str(uuid4()), lineage_id=str(uuid4()), received_at=received,
                         source_capture_age_ms=None, source_capture_time_verified=False,
                         source_shape=list(frame.shape), transport_shape=list(sample.shape),
                         sample_step=4, channel_conversion='BGR to RGB',
                         source_frame_sha256=hashlib.sha256(frame.tobytes()).hexdigest(),
                         frame_sha256=hashlib.sha256(payload).hexdigest(), sdk_version=version('reachy-mini'),
                         reader='camera_only_GStreamerCamera_IPC', audio_initialised=False))
    except Exception as exc:
        results.put({'capture_error':type(exc).__name__,'capture_stage':stage})
    finally:
        if camera is not None: camera.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('production-root','frame','output'): parser.add_argument('--'+key,type=Path,required=True)
    args = parser.parse_args()
    process = None
    def shutdown(signum, frame):
        if process is not None and process.is_alive():
            process.terminate(); process.join(timeout=2)
            if process.is_alive(): process.kill(); process.join(timeout=2)
        args.frame.unlink(missing_ok=True)
        raise SystemExit(128+signum)
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT): signal.signal(signum, shutdown)
    config = json.loads((args.production_root/'config.local.json').read_text())
    token_path = Path(config['paths']['token_file'])
    if not token_path.is_absolute(): token_path = args.production_root/token_path
    token = token_path.read_text().strip()
    port = urlsplit(config['network']['agent_url']).port
    opener = build_opener(ProxyHandler({}))
    def operator():
        with opener.open(Request('http://127.0.0.1:'+str(port)+'/status',
                         headers={'Authorization':'Bearer '+token}), timeout=3) as response:
            value=json.load(response)
        return {key:value.get(key) for key in ('microphone_enabled','capture_active','phase')}
    before=operator()
    if before['microphone_enabled'] is not False or before['capture_active'] is not False:
        raise RuntimeError('Probe requires existing microphone mute; never changes it')
    context=multiprocessing.get_context('spawn')
    results=context.Queue(maxsize=1)
    process=context.Process(target=capture,args=(str(args.frame),results))
    started=time.monotonic();process.start()
    try:
        result=results.get(timeout=8)
    except Exception:
        result={'capture_error':'deadline_or_child_exit'}
    finally:
        process.join(timeout=2)
        if process.is_alive(): process.terminate();process.join(timeout=2)
        if process.is_alive(): process.kill();process.join(timeout=2)
        results.close();results.join_thread()
    after=operator()
    report=dict(mode='real_camera_video_only_probe', **result,
                robot_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                elapsed_s=time.monotonic()-started, child_reaped=not process.is_alive(),
                operator_before=before,operator_after=after,
                audio_or_motor_commands=0, raw_retention='temporary processing artifact; automatic deletion within25s after capture')
    report['accepted']=('capture_error' not in result and process.exitcode==0 and before==after)
    if not report['accepted']:args.frame.unlink(missing_ok=True)
    with args.output.open('x',encoding='utf-8') as out:json.dump(report,out,indent=2)
    print(json.dumps({key:report[key] for key in ('accepted','elapsed_s','child_reaped','operator_after','audio_or_motor_commands')}
                     | {key:report[key] for key in ('transport_shape','capture_error','capture_stage','source_shape') if key in report}), flush=True)
    # Keep this finite supervisor alive for bounded pickup. SSH signals also
    # remove the raw artifact; there is no unbounded detached GC process.
    end=time.monotonic()+25
    try:
        while args.frame.exists() and time.monotonic()<end:time.sleep(.1)
    finally:args.frame.unlink(missing_ok=True)
    if not report['accepted']:raise SystemExit(2)


if __name__ == '__main__': main()
