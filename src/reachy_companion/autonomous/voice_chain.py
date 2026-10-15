"""Hash-only causal receipt checks; trusted runner files are not attestations."""
import hashlib
import json
import math
import re


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def _id(value):
    if type(value) is not str or not 1<=len(value)<=256:raise ValueError('Bounded receipt identity required')
def _sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('Receipt digest required')
def _time(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('Original finite monotonic time required')
    return value


def model_final(data,output,backend,model):
    return dict(kind='model-final-1',role='main',backend=backend,model_id_sha256=digest(model),
        request_sha256=digest(data),output_sha256=digest(output),
        utterance_sha256=digest(data['utterance'] if type(data) is dict else data),
        memory_projection_sha256=digest(data['memory'] if type(data) is dict else []))


def checked_final(task,output,proof):
    if (type(proof) is not dict or set(proof)!=set(model_final(task.prompt,output,'',''))
            or proof.get('kind')!='model-final-1' or proof.get('role')!='main'
            or proof.get('backend') not in ('lmstudio_sdk','llama_native','completion_http')):
        raise ValueError('Actual model FINAL provenance required')
    _sha(proof['model_id_sha256'])
    if proof['model_id_sha256'] in (digest(None),digest('')):raise ValueError('Configured model identity required')
    expected=model_final(task.prompt,output,proof['backend'],'')
    expected['model_id_sha256']=proof['model_id_sha256']
    if proof!=expected:raise ValueError('FINAL request/output/context binding mismatch')
    return dict(proof)


def speech_main(task,committed_at):
    if task.completion_provenance is None:return None # legacy/replay may speak, never live evidence
    return dict(task_id=task.task_id,attempt_id=task.attempt_id,input_ref=task.input_ref,
        authority=task.authority.wire(),created_at=task.created,deadline=task.deadline,
        completed_at=task.completed_at,committed_at=committed_at,proposal_expires=task.expires,
        memory_store_id=task.memory_store_id,memory_revision=task.memory_revision,
        final=dict(task.completion_provenance))


def retain_main_audit(records,receipt):
    records.append(receipt);overflow=len(records)>8
    if overflow:del records[:-8]
    return overflow


def context_binding(report):
    versions=report.get('versions')
    if (report.get('action')!='readback' or report.get('accepted') is not True
            or report.get('live_source_chain_validated') is not True or report.get('model_inference') is not False
            or report.get('state_projection_verified') is not True or report.get('content_whitelist_verified') is not True
            or type(versions) is not list or len(versions)!=1 or type(versions[0]) is not int or versions[0] not in (1,2)
            or type(report.get('revision')) is not int or report['revision']<0):raise ValueError('Confirmed live-source whitelist readback required')
    _id(report['store_id']);_sha(report['memory_projection_sha256']);_sha(report['memory_descriptor_sha256'])
    return dict(store_id=report['store_id'],revision=report['revision'],version=versions[0],
        memory_projection_sha256=report['memory_projection_sha256'],memory_descriptor_sha256=report['memory_descriptor_sha256'])


def check_context_view(view,binding):
    if digest(view.get('memory'))!=binding['memory_descriptor_sha256']:
        raise ValueError('Fast request refused before inference: memory whitelist changed/not ready')


def check_context_task(task,binding):
    data=task.prompt
    if (task.kind!='main' or task.memory_store_id!=binding['store_id'] or type(task.memory_revision) is not int or task.memory_revision!=binding['revision']
            or type(data) is not dict or data.get('schema_version')!='context-1' or data.get('observations')!=[]
            or type(data.get('memory')) is not list or len(data['memory'])!=1
            or digest(data['memory'])!=binding['memory_projection_sha256']):
        raise ValueError('Main request refused before inference: whitelist/store/revision changed')


def validate_turn(turn):
    if turn.get('stt_provenance')!='pc_http_stt' or type(turn.get('ttl_ms')) is not int or turn['ttl_ms']!=2000:raise ValueError('Actual HTTP STT admission required')
    _sha(turn['stt_text_sha256'])
    if type(turn['capture_age_ms']) is not int or not 0<=turn['capture_age_ms']<2000:raise ValueError('Capture TTL exceeded')
    main=turn['main_final'];play=turn['reply_playback']
    if type(main) is not dict or type(play) is not dict:raise ValueError('Typed chain receipts required')
    final=main['final']
    if type(final) is not dict or set(final)!=set(model_final('','','','')):raise ValueError('Closed FINAL receipt required')
    for name in ('task_id','attempt_id','input_ref'):_id(main[name])
    if main['input_ref']!=turn['working_input_ref'] or digest(main['authority'])!=digest(turn['working_authority']):
        raise ValueError('Turn/task authority mismatch')
    if (final.get('kind')!='model-final-1' or final.get('role')!='main'
            or final.get('backend') not in ('lmstudio_sdk','llama_native','completion_http')):raise ValueError('No model FINAL')
    _sha(final['model_id_sha256'])
    if final['model_id_sha256'] in (digest(None),digest('')):raise ValueError('Configured model identity required')
    for name in ('request_sha256','output_sha256','memory_projection_sha256','utterance_sha256'):_sha(final[name])
    if final['utterance_sha256']!=turn['stt_text_sha256']:raise ValueError('STT text did not bind the main request')
    times=[_time(v) for v in (turn['received_at'],main['created_at'],main['completed_at'],main['committed_at'],play['producer_started_at'])]
    if times!=sorted(times) or not times[1]<=times[2]<=_time(main['deadline']) or not times[3]<=_time(main['proposal_expires']):
        raise ValueError('Original task/proposal deadline exceeded')
    if (digest(play['authority'])!=digest(main['authority']) or digest(play['operator_binding'])!=digest(turn['working_operator_binding'])
            or play['output_sha256']!=final['output_sha256'] or play['tts_complete'] is not True
            or play['cancelled'] is not False or play['verified_stopped'] is not True
            or play['provenance']!='device_consumed_pcm' or type(play['tts_frames']) is not int or play['tts_frames']<=0
            or type(play['max_measured_consumed']) is not int or play['max_measured_consumed']!=play['tts_frames']
            or not times[-1]<_time(play['deadline'])<=main['proposal_expires']
            or not times[-1]<=_time(play['first_consumed_at'])<=play['deadline']):raise ValueError('Owned actual consumed reply required')
    _id(play['stream_id'])
    return main


def attach_turns(turns,calls,receipts,consumption):
    """Correlate real canonical task receipts, never positional speech indexes."""
    for turn in turns:
        matches=[r for r in receipts if r.get('main_receipt') and r['main_receipt']['input_ref']==turn['working_input_ref']]
        if len(matches)!=1:raise ValueError('Unique turn reply required')
        receipt=matches[0];main=receipt['main_receipt']
        audited=[c for c in calls if c.get('task_id')==main['task_id'] and c.get('attempt_id')==main['attempt_id']
            and c.get('input_ref')==main['input_ref'] and c.get('final')==main['final']]
        consumed=[c for c in consumption if c['stream_id']==receipt.get('stream_id')]
        if len(audited)!=1 or len(consumed)!=1:raise ValueError('Unique actual FINAL/playback audit required')
        turn['main_final']=main
        turn['reply_playback']={**consumed[0],**{key:receipt[key] for key in ('authority','operator_binding','output_sha256',
            'tts_complete','cancelled','producer_started_at','deadline')}}
        validate_turn(turn)
    if len({t['main_final']['attempt_id'] for t in turns})!=len(turns) or len({t['reply_playback']['stream_id'] for t in turns})!=len(turns):
        raise ValueError('Reused attempt or stream')
