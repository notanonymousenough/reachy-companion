"""Exact spoken snapshot intent and bounded adapter for the existing Agent.

No background listener. Called only with a fresh normal STT result while the
Agent holds its existing audio lock. The runner installs the reviewed
deploy/autonomous/demo_vision.py beside this module as snapshot_vision.py.
"""
import http.client
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata

BAD_FINAL=('<think','</think','<|analysis|>','<|im_start|>','<analysis','[analysis]')


def words(text):
    return ' '.join(re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',text).casefold().replace('ё','е')))


def matches(text, own_reply=''):
    if type(text) is not str or not 1<=len(text)<=160 or any(c in text for c in '\"\'«»“”„`'):return False
    phrase=words(text)
    phrase=re.sub(r'^(?:алиса|ричи|риччи|reachy) ', '', phrase)
    phrase=re.sub(r'^пожалуйста ', '', phrase)
    phrase=re.sub(r' пожалуйста$', '', phrase)
    return phrase in ('что перед тобой','что ты видишь') and phrase not in words(own_reply)


def binding(value):
    return dict(agent_boot_id=value['agent_boot_id'],microphone_epoch=value['microphone_epoch'],
                policy_epoch=value['motion_policy']['epoch'],owner_id=value['microphone_owner_id'])


def check_operator(value, expected, deadline):
    policy=value['motion_policy']
    if (binding(value)!=expected or type(expected['owner_id']) is not str or not 1<=len(expected['owner_id'])<=128
            or value['motion_policy_owner_id']!=expected['owner_id']
            or not value['microphone_enabled'] or not value['listening'] or value['capture_active']
            or value['microphone_state_error'] is not None or value['phase']!='processing'
            or not policy['motor_enabled'] or policy['quiet'] or policy['privacy_all']
            or time.monotonic()>=deadline):
        raise RuntimeError('Spoken snapshot authority changed')


def dispatch(agent, text, epoch, expected):
    """Return the existing voice result; never acquire another audio owner."""
    if not matches(text,getattr(agent,'current_reply_text','')):
        raise ValueError('Exact non-echo snapshot request required')
    deadline=time.monotonic()+50
    if expected['microphone_epoch']!=epoch or not agent.audio_lock.locked() or agent.stopping.is_set():
        raise RuntimeError('Spoken snapshot admission changed')
    def check():
        if agent.stopping.is_set():raise RuntimeError('Agent stopped')
        check_operator(agent.operator_status(),expected,deadline)
    check()
    agent.pending_pcm=None;agent.resume_audio=None
    packet=dict(config=dict(network=dict(llm_base_url=agent.config['network']['llm_base_url']),
                            llm=dict(model=agent.config['llm']['model'])),
                port=agent.config['servers']['agent']['port'],token=agent.config.token,
                expected=expected,deadline=deadline,question=text)
    # Existing SDK camera interpreter, no shell, credentials only over stdin.
    process=subprocess.Popen(['/venvs/mini_daemon/bin/python',str(Path(__file__).resolve()),'--snapshot-child'],
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        try:output,_=process.communicate(json.dumps(packet).encode(),timeout=50)
        except subprocess.TimeoutExpired:
            process.kill();process.communicate();raise TimeoutError('Spoken snapshot child timed out') from None
    finally:
        if process.poll() is None:process.kill();process.communicate()
    check()
    if process.returncode or len(output)>16000:raise RuntimeError('Spoken snapshot child failed')
    rows=[line for line in output.splitlines() if line.startswith(b'{')]
    if len(rows)!=1:raise ValueError('One snapshot result required')
    result=json.loads(rows[0])
    if type(result) is not dict:raise ValueError('Typed snapshot result required')
    answer=result.get('final_text');expires=result.get('expires_at_monotonic')
    if (result.get('kind')!='companion-vision-snapshot' or type(answer) is not str or not 1<=len(answer)<=1600
            or any(tag in answer.lower() for tag in BAD_FINAL)
            or type(expires) not in (int,float) or not math.isfinite(expires)
            or not 0<expires-time.monotonic()<=60):raise ValueError('Bounded snapshot FINAL required')
    check()
    response=agent.voice('/say',dict(text=answer,session=agent.config['conversation']['session']),
                         expected_epoch=epoch,expected_policy_epoch=expected['policy_epoch'],
                         valid_until=min(expires,deadline),allow_barge_in=True)
    response['transcript']=text
    return response


def child(packet, snapshot):
    deadline=packet['deadline']
    if (type(deadline) not in (int,float) or not math.isfinite(deadline) or not 0<deadline-time.monotonic()<=50
            or type(packet['port']) is not int or not 1<=packet['port']<=65535
            or type(packet['token']) is not str or len(packet['token'])<32):
        raise ValueError('Bounded local snapshot packet required')
    def check():
        began=time.monotonic()
        connection=http.client.HTTPConnection('127.0.0.1',packet['port'],timeout=2)
        try:
            connection.request('GET','/operator',headers={'Authorization':'Bearer '+packet['token']})
            response=connection.getresponse();data=response.read(16001)
            if response.status!=200 or len(data)>16000:raise RuntimeError('Operator unavailable')
            check_operator(json.loads(data),packet['expected'],deadline)
            if time.monotonic()-began>.3:raise RuntimeError('Operator read expired')
            return began
        finally:connection.close()
    return snapshot.caption_checked(packet['config'],deadline,packet['question'],check)


def main():
    path=Path(__file__).with_name('snapshot_vision.py')
    spec=importlib.util.spec_from_file_location('spoken_snapshot_child',path)
    snapshot=importlib.util.module_from_spec(spec);spec.loader.exec_module(snapshot)
    snapshot.bind_parent_lifetime()
    packet=json.loads(sys.stdin.buffer.read(16001))
    print(json.dumps(child(packet,snapshot)),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException:
        # Never log camera bytes, caption, transcript, token or upstream body.
        print('{"kind":"companion-spoken-vision-error"}',flush=True)
        raise SystemExit(1)
