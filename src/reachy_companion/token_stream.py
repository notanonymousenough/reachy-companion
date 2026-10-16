"""Opt-in local completion SSE → bounded semantic segments.

Source candidate only; runtime schema/installed overlay must be verified before
activation. No new endpoint, model, background thread, audio or motor owner.
"""
import json
import re
import socket
import threading
import time
import uuid
from urllib.request import Request,build_opener,ProxyHandler


def need(value):
    if not value:raise ValueError('Invalid bounded completion stream')


def unique(pairs):
    result={}
    for key,value in pairs:
        need(key not in result);result[key]=value
    return result


def reject_constant(value):raise ValueError('Non-finite completion stream JSON')


def sse_tokens(response,model,*,deadline,terminal,set_timeout=None):
    """Legacy completions data-only SSE; terminal stop is distinct from DONE."""
    size=count=0;data=[];finished=False;finish=None;identity=None
    while True:
        remaining=(deadline() if callable(deadline) else deadline)-time.monotonic()
        need(remaining>0)
        if set_timeout is not None:set_timeout(remaining)
        line=response.readline(32769);size+=len(line)
        need(time.monotonic()<(deadline() if callable(deadline) else deadline))
        need(line and len(line)<=32768 and line.endswith(b'\n') and size<=1048576)
        line=line.rstrip(b'\r\n')
        if line.startswith(b':'):continue
        if line:
            need(line.startswith(b'data:'))
            data.append(line[5:].lstrip(b' '));need(sum(map(len,data))<=32768)
            continue
        if not data:continue
        raw=b'\n'.join(data);data=[];count+=1;need(count<=8192)
        if raw==b'[DONE]':
            need(finished);terminal();need(finish=='stop');return
        need(not finished)
        event=json.loads(raw,object_pairs_hook=unique,parse_constant=reject_constant)
        need(type(event) is dict and event.get('model')==model and event.get('object')=='text_completion'
             and not any(key in event for key in ('error','content','output','message','delta','reasoning',
                                                  'reasoning_content','tool_calls','function_call'))
             and type(event.get('id')) is str and 1<=len(event['id'])<=256
             and type(event.get('choices')) is list and len(event['choices'])==1)
        if identity is None:identity=event['id']
        need(event['id']==identity)
        choice=event['choices'][0]
        need(type(choice) is dict and type(choice.get('index')) is int and choice['index']==0
             and type(choice.get('text')) is str and 'finish_reason' in choice
             and choice['finish_reason'] in (None,'stop','length','content_filter')
             and not any(key in choice for key in ('delta','message','tool_calls','reasoning','reasoning_content')))
        reason=choice.get('finish_reason')
        if reason is not None:
            finished=True;finish=reason
            if reason!='stop':continue
        if choice['text']:yield choice['text']


def completion_tokens(config,messages):
    """Use the current local raw-prompt API and its existing model permit."""
    from . import brains
    need(config['brains']['provider']=='lm_studio' and config['llm']['api_path']=='/completions')
    settings=config['llm'];identity=brains.model_identity(config)
    payload=dict(model=settings['model'],prompt=brains.raw_prompt(config,messages),
        temperature=settings['temperature'],max_tokens=settings['max_tokens'],stream=True,stop=settings['stop'])
    request=Request(identity[0]+'/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    deadline=time.monotonic()+config['timeouts']['llm']
    with brains.MODEL_EXECUTION.reserve(identity) as execution:
        execution.submitted()
        with build_opener(ProxyHandler({})).open(request,timeout=config['timeouts']['llm']) as response:
            need(response.headers.get_content_type()=='text/event-stream')
            try:set_timeout=response.fp.raw._sock.settimeout
            except AttributeError:set_timeout=None
            read_deadline=[deadline]
            tokens=sse_tokens(response,identity[1],deadline=lambda:read_deadline[0],terminal=execution.terminal,set_timeout=set_timeout)
            try:
                for token in tokens:yield token
            except GeneratorExit:
                # No tokens leave this branch. A verified terminal releases the
                # shared permit; timeout/EOF retains UNKNOWN, never timer-cleared.
                timer=None
                try:
                    if set_timeout is None:raise AttributeError('No bounded socket drain')
                    read_deadline[0]=min(deadline,time.monotonic()+2)
                    sock=response.fp.raw._sock
                    def abort_drain():
                        try:sock.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
                    # Idle socket timeouts alone do not bound a trickled line.
                    timer=threading.Timer(max(0,read_deadline[0]-time.monotonic()),abort_drain)
                    timer.daemon=True;timer.start()
                    while True:next(tokens)
                except (StopIteration,ValueError,OSError,AttributeError):pass
                finally:
                    if timer is not None:timer.cancel();timer.join()
                raise
            finally:tokens.close()


class Segments:
    """Never release partial tags or think content, even at single-char splits."""
    def __init__(self,maximum=5000,segment_maximum=600):
        self.maximum=maximum;self.segment_maximum=segment_maximum
        self.raw_count=0;self.count=0;self.tag=None;self.thinking=False;self.text=''
        self.emotion='neutral';self.gesture='auto';self.style=None;self.segments=0

    def emit(self):
        text=self.text.strip();self.text='';style=self.style;self.style=None
        if not text:return None
        self.segments+=1;need(self.segments<=32)
        return dict(text=text,emotion=style[0],gesture=style[1])

    def feed(self,chunk):
        from .expressions import EMOTIONS
        from .speech_motion import GESTURES
        need(type(chunk) is str);self.raw_count+=len(chunk);need(self.raw_count<=131072)
        for char in chunk:
            if self.tag is not None:
                self.tag+=char;need(len(self.tag)<=128)
                if char!='>':continue
                tag=self.tag.lower();self.tag=None
                if tag=='<think>':need(not self.thinking);self.thinking=True;continue
                if tag=='</think>':need(self.thinking);self.thinking=False;continue
                if self.thinking:continue
                match=re.fullmatch(r'<(emotion|gesture)=([a-z_]+)>',tag)
                need(match is not None)
                if self.text.rstrip().endswith(('.','!','?','…')):
                    segment=self.emit()
                    if segment:yield segment
                name,value=match.groups()
                need(value in (EMOTIONS if name=='emotion' else GESTURES))
                setattr(self,name,value);continue
            if char=='<':self.tag='<';continue
            if self.thinking:continue
            # Alternative analysis/chat delimiters are not FINAL prose.
            need(char not in '[]|`')
            if char.isspace() and self.text.rstrip().endswith(('.','!','?','…')):
                segment=self.emit()
                if segment:yield segment
            if not self.text and char.isspace():continue
            if self.style is None:self.style=(self.emotion,self.gesture)
            self.text+=char;self.count+=1
            need(self.count<=self.maximum and len(self.text)<=self.segment_maximum)

    def finish(self):
        need(self.tag is None and not self.thinking)
        segment=self.emit()
        if segment:yield segment
        need(self.segments>0)


def semantic_segments(tokens,maximum):
    builder=Segments(maximum)
    try:
        for token in tokens:yield from builder.feed(token)
        yield from builder.finish()
    finally:
        close=getattr(tokens,'close',None)
        if close is not None:close()


def incremental_audio(pipeline,segments,prefix):
    """Reuse existing TTS, clock offsets and output bounds across all segments."""
    total=cue_count=characters=0;first=True
    maximum=pipeline.config['conversation']['expressions']['speech_sync']['max_cues']
    try:
        for segment in segments:
            text=segment['text'];actual_prefix=prefix if first else ''
            characters+=len(pipeline.address_speech(text,actual_prefix))+(0 if first else 1)
            need(characters<=pipeline.config['limits']['max_speech_chars'])
            yield dict(type='reply',reply=text,emotion=segment['emotion'],command=None,
                **pipeline.speech_address_metadata(text,actual_prefix))
            events=pipeline.audio_events([segment],total,speech_address_prefix=actual_prefix)
            try:
                for event in events:
                    if event['type']=='audio':
                        import base64
                        total+=len(base64.b64decode(event['pcm_base64'],validate=True))
                    elif event['type']=='motion':
                        cues=event['cues'][:max(0,maximum-cue_count)];cue_count+=len(cues)
                        if not cues:continue
                        event=dict(event,cues=cues)
                    yield event
            finally:
                close=getattr(events,'close',None)
                if close is not None:close()
            first=False
    finally:
        close=getattr(segments,'close',None)
        if close is not None:close()


def content_events(pipeline,payload,path):
    """Existing worker stream hook; caller owns the existing pipeline lock.

    Returns terminal data to the caller, which must release producers/lock
    before yielding done. No history commit on EOF, truncation or early close.
    """
    import base64
    from .expressions import spoken_segments
    need('reply_constraints' not in payload and type(payload.get('previous_reply_interrupted',False)) is bool)
    p=pipeline;cfg=p.config;started=time.monotonic();p.check_robot()
    text=p.transcribe(base64.b64decode(payload['pcm_base64'],validate=True)) if path=='/turn' else payload['text'].strip()
    need(type(text) is str and len(text)<=cfg['limits']['max_text_chars'])
    session=payload.get('session',cfg['conversation']['session'])
    need(type(session) is str and 1<=len(session)<=cfg['limits']['max_session_chars'])
    decision=p.classify(text);action=decision['action'];pending=None
    prefix=p.speech_address(payload.get('speech_address_prefix',p.speech_address()))
    if not text or action!='answer':
        command=None
        if not text:reply=''
        elif action=='stop':reply='';command='stop'
        elif action=='pause':reply=cfg['conversation']['pause_reply'];command='pause'
        elif action=='reset':p.reset(session);reply=cfg['conversation']['reset_reply']
        else:raise ValueError('Unknown streaming control decision')
        result=dict(transcript=text,reply=reply,emotion=decision.get('emotion','neutral'),command=command,
            decision=decision,segments=spoken_segments(reply),**p.speech_address_metadata(reply,prefix))
        yield dict(type='reply',**result)
        yield from p.audio_events(result['segments'],speech_address_prefix=prefix)
        return dict(type='done',ok=True,**p.completed(result,session,None,started))
    now=time.monotonic()
    p.sessions={k:v for k,v in p.sessions.items() if now-v['used']<cfg['llm']['history_ttl_seconds']}
    if session not in p.sessions and len(p.sessions)>=cfg['llm']['max_sessions']:
        del p.sessions[min(p.sessions,key=lambda k:p.sessions[k]['used'])]
    p.agent_sessions={k:v for k,v in p.agent_sessions.items() if k in p.sessions}
    entry=p.sessions.get(session,dict(used=now,messages=[]))
    messages=[dict(role='system',content=cfg['llm']['system_prompt'])]+entry['messages'][-cfg['llm']['history_messages']:]
    if payload.get('previous_reply_interrupted',False):
        messages.append(dict(role='system',content='Предыдущий ответ был прерван и не прозвучал полностью. Отвечай на новую реплику пользователя, не продолжай старый ответ без просьбы.'))
    messages.append(dict(role='user',content=text));p.agent_sessions.setdefault(session,uuid.uuid4().hex)
    collected=[]
    def collect():
        for segment in semantic_segments(completion_tokens(cfg,messages),cfg['limits']['max_speech_chars']):
            collected.append(segment)
            yield segment
    events=incremental_audio(p,collect(),prefix)
    try:
        p.phase='thinking'
        for event in events:
            if event['type']=='reply':
                event=dict(event,transcript=text)
            if event['type']=='audio':p.phase='speaking'
            yield event
    finally:events.close()
    reply=' '.join(s['text'] for s in collected);need(reply)
    result=dict(transcript=text,reply=reply,command=None,emotion=collected[0]['emotion'],decision=decision,
        segments=collected,**p.speech_address_metadata(reply,prefix))
    pending=dict(used=now,messages=(entry['messages']+[dict(role='user',content=text),dict(role='assistant',content=reply)])[-cfg['llm']['history_messages']:])
    return dict(type='done',ok=True,**p.completed(result,session,pending,started))
