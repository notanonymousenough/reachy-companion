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
ERROR_PHASES=frozenset(('startup','snapshot_import','parent_lifetime','packet_read','packet_validation',
    'model_inventory','capture','image_admission','inference','final_parser','post_guards','complete',
    'operator_before_capture','operator_before_image','operator_after_inference','operator_other'))
ERROR_CLASSES=frozenset(('ValueError','RuntimeError','TypeError','KeyError','AttributeError','ImportError',
    'ModuleNotFoundError','FileNotFoundError','PermissionError','OSError','TimeoutError','ConnectionRefusedError',
    'ConnectionResetError','BrokenPipeError','JSONDecodeError','HTTPException','IncompleteRead',
    'RemoteDisconnected','SystemExit','KeyboardInterrupt','OtherError'))
PHASE='startup'
SNAPSHOT=None


def failure(error):
    phase=getattr(SNAPSHOT,'PHASE','startup') if PHASE=='snapshot' else PHASE
    name=type(error).__name__
    return dict(kind='companion-spoken-vision-error',phase=phase if type(phase) is str and phase in ERROR_PHASES else 'startup',
                error_class=name if name in ERROR_CLASSES else 'OtherError')


def child_result(output, returncode):
    """Parse bounded typed failure before rc; never reflect untrusted strings."""
    if len(output)>16000:raise RuntimeError('Spoken snapshot child output exceeded bound')
    rows=[line for line in output.splitlines() if line.startswith(b'{')]
    if len(rows)!=1:raise ValueError('One snapshot result required')
    result=json.loads(rows[0])
    if type(result) is not dict:raise ValueError('Typed snapshot result required')
    if result.get('kind')=='companion-spoken-vision-error':
        if (set(result)=={'kind','phase','error_class'} and type(result['phase']) is str
                and result['phase'] in ERROR_PHASES and type(result['error_class']) is str
                and result['error_class'] in ERROR_CLASSES):
            raise RuntimeError('Spoken snapshot child failed phase='+result['phase']+' error_class='+result['error_class'])
        raise RuntimeError('Spoken snapshot child failed invalid diagnostic')
    if returncode:raise RuntimeError('Spoken snapshot child failed without typed diagnostic')
    return result


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
    result=child_result(output,process.returncode)
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
    global PHASE
    PHASE='packet_validation'
    deadline=packet['deadline']
    if (type(deadline) not in (int,float) or not math.isfinite(deadline) or not 0<deadline-time.monotonic()<=50
            or type(packet['port']) is not int or not 1<=packet['port']<=65535
            or type(packet['token']) is not str or len(packet['token'])<32):
        raise ValueError('Bounded local snapshot packet required')
    def check():
        global PHASE
        PHASE={'model_inventory':'operator_before_capture','image_admission':'operator_before_image',
               'post_guards':'operator_after_inference'}.get(getattr(snapshot,'PHASE',None),'operator_other')
        began=time.monotonic()
        connection=http.client.HTTPConnection('127.0.0.1',packet['port'],timeout=2)
        try:
            connection.request('GET','/operator',headers={'Authorization':'Bearer '+packet['token']})
            response=connection.getresponse();data=response.read(16001)
            if response.status!=200 or len(data)>16000:raise RuntimeError('Operator unavailable')
            check_operator(json.loads(data),packet['expected'],deadline)
            if time.monotonic()-began>.3:raise RuntimeError('Operator read expired')
            PHASE='snapshot'
            return began
        finally:connection.close()
    PHASE='snapshot'
    return snapshot.caption_checked(packet['config'],deadline,packet['question'],check)


def main():
    global PHASE,SNAPSHOT
    PHASE='snapshot_import'
    path=Path(__file__).with_name('snapshot_vision.py')
    spec=importlib.util.spec_from_file_location('spoken_snapshot_child',path)
    snapshot=importlib.util.module_from_spec(spec);SNAPSHOT=snapshot;spec.loader.exec_module(snapshot)
    PHASE='parent_lifetime'
    snapshot.bind_parent_lifetime()
    PHASE='packet_read'
    packet=json.loads(sys.stdin.buffer.read(16001))
    print(json.dumps(child(packet,snapshot)),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        # Never log camera bytes, caption, transcript, token or upstream body.
        print(json.dumps(failure(error)),flush=True)
        raise SystemExit(1)
