"""PC-only processing of a verified ephemeral camera sample; deletes raw input."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4
from reachy_companion.autonomous import perception


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('frame','metadata','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    try:
        metadata=json.loads(args.metadata.read_text())
        if not metadata['accepted'] or not metadata['child_reaped'] or metadata['audio_or_motor_commands']!=0:
            raise ValueError('Camera producer probe not accepted')
        if any(metadata['operator_after'].get(key) is not False for key in ('microphone_enabled','capture_active')):
            raise ValueError('Producer microphone mute not verified')
        if args.frame.stat().st_size>1048576:raise ValueError('Oversized raw frame')
        started=time.monotonic()
        metrics=perception.pixel_metrics(args.frame.read_bytes(),metadata['frame_sha256'])
        report=dict(mode='real_camera_pixel_metrics_cpu_pc',producer_boot_id=str(uuid4()),producer_seq=0,
                    received_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                    extractor_sha256=hashlib.sha256(Path(perception.__file__).read_bytes()).hexdigest(),
                    processing_s=time.monotonic()-started,lineage_id=metadata['lineage_id'],
                    frame_id=metadata['frame_id'],robot_boot_id=metadata['robot_boot_id'],
                    source_received_at=metadata['received_at'],source_capture_time_verified=False,
                    source_capture_age_ms=None,metrics=metrics,shadow_event=perception.shadow_event(metrics),
                    raw_retained=False,export_enabled=False)
        args.frame.unlink()
        with args.output.open('x',encoding='utf-8') as out:json.dump(report,out,indent=2)
        print(json.dumps(report))
    finally:args.frame.unlink(missing_ok=True)


if __name__=='__main__':main()
