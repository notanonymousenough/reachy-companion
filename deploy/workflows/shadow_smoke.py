"""Explicit hybrid test: fixture L0 + live optional VPS workflow + simulated actors."""
import argparse
import json
import os
from pathlib import Path
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.runtime import ReplayGateway,Scheduler
from reachy_companion.autonomous.workflows import WorkflowClient


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--token-file')
    args=parser.parse_args();config=load(args.config)
    if args.token_file:
        path=Path(args.token_file)
        if path.stat().st_mode & 0o077:raise ValueError('Private token file must have0600 permissions')
        values=dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line)
        os.environ[config['workflows']['token_env']]=values[config['workflows']['token_env']]
    client=WorkflowClient(config['workflows'])
    class Hybrid(ReplayGateway):
        def main(self,task):
            if task.kind!='research':raise ValueError('Only synthetic workflow admitted')
            return dict(output=client.run(task),compute_boot_id=self.boot_id,request_id=task.attempt_id)
    scheduler=Scheduler(config,Hybrid())
    report=scheduler.run(4,[dict(at_s=0,type='workflow',value='synthetic-no-controls')])
    assert report['counts'].get('task_started')==1 and report['counts'].get('simulated_speech')==1,report['counts']
    print(json.dumps(dict(mode='fixture_fast_live_vps_workflow',actuators='simulated',counts=report['counts'],
                         actual_model_inference=False,export=False,paid_api=False)))


if __name__=='__main__':main()
