"""Finite Hub runtime: actual capture/PC STT/models/TTS/device PCM, two Alice rounds.

Own status/stop API, occupied async slots and bounded wake/reply admission.
No speaker identity, automatic memory promotion or interrupted PCM resume.
"""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import time
from reachy_companion.config import Config
from reachy_companion.hub import Hub
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.audio_adapter import AudioAdapter,HttpSTT
from reachy_companion.autonomous.audio_peer import PeerClient,RemotePCM,AudioPolling,PeerLease
from reachy_companion.autonomous.lease_datagram import DatagramRenewal
from reachy_companion.autonomous.playback import Playback
from reachy_companion.autonomous.speech_adapter import SpeechAdapter,HttpTTS
from reachy_companion.autonomous.runtime import RemoteGateway,Scheduler,Job


def normalized(text):
    text=re.sub(r'\W+',' ',text.lower()).strip()
    return text.replace('2','два').replace('3','три')


class PracticeTTS:
    """Owner-selected finite public wake questions; other model speech cannot wake Alice."""
    questions=('Алиса, сколько будет два плюс два?','Алиса, сколько будет три плюс три?')
    def __init__(self,tts):
        self.tts=tts;self.lock=threading.Lock();self.expected=None;self.events=[];self.replies=0
    def question(self,index):
        with self.lock:self.expected=self.questions[index]
    def stream(self,text,cancel):
        with self.lock:
            if self.expected is not None:
                if normalized(text)!=normalized(self.expected):raise ValueError('Model wake question differs from public owner plan')
                self.expected=None;kind='question'
            else:
                if 'алис' in text.lower() or len(text)>160 or self.replies>=3:
                    raise ValueError('Finite local reply admission')
                self.replies+=1;kind='reply'
            event=dict(kind=kind,started_at=time.monotonic(),characters=len(text),complete=False)
            self.events.append(event)
        for pcm in self.tts.stream(text,cancel):
            with self.lock:
                if 'first_pcm_at' not in event:event['first_pcm_at']=time.monotonic()
            yield pcm
        with self.lock:event['complete']=True
    def cancel(self):self.tts.cancel()
    def status(self):
        with self.lock:return [dict(event) for event in self.events]


def create_lease(client,source,port=None):
    if port is not None and (type(port) is not int or not 1<=port<=65535):
        raise ValueError('Explicit valid datagram port required')
    datagram=DatagramRenewal(client,source,port) if port is not None else None
    return PeerLease(client,datagram=datagram)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','companion-config','token-file','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--peer-url',required=True);p.add_argument('--controller',required=True)
    p.add_argument('--duration',type=float,default=70);p.add_argument('--allow-capture-output',action='store_true')
    p.add_argument('--status-port',type=int,default=8790)
    p.add_argument('--lease-datagram-port',type=int)
    p.add_argument('--trusted-private-lan',action='store_true');a=p.parse_args()
    if not a.allow_capture_output or a.output.exists() or not 20<=a.duration<=120:raise ValueError('Fresh finite realtime opt-in required')
    if a.lease_datagram_port is not None and not 1<=a.lease_datagram_port<=65535:
        raise ValueError('Explicit valid datagram port required')
    config=load(a.config);companion=Config(a.companion_config);hub=Hub(companion)
    if config.get('motion',{}).get('enabled'):raise ValueError('This first audio session requires a separately accepted joint motion profile')
    os.environ[config['gateway']['token_env']]=a.token_file.read_text().strip()
    client=PeerClient(a.peer_url,companion.token,a.controller,trusted_private_lan=a.trusted_private_lan)
    source=client.call('/status')['source_boot']
    playback=Playback(RemotePCM(client),chunk_frames=4096)
    tts=PracticeTTS(HttpTTS(companion['network']['voice_url'],companion.token,timeout=5,
        max_event=companion['streaming']['max_event_bytes']))
    speech=SpeechAdapter(playback,tts,lambda:hub.agent('/operator'))
    audio=AudioAdapter(HttpSTT(companion['network']['compute_url'],companion.token))
    poller=AudioPolling(client,audio,source);stop=threading.Event();turns=[];main_calls=[];fast_calls=[]
    class AuditedGateway(RemoteGateway):
        def fast(self,request_id,view):
            started=time.monotonic();result=super().fast(request_id,view)
            fast_calls.append(dict(elapsed_s=time.monotonic()-started,activity=result['output']['a'],usage=result.get('usage'),
                microphone_enabled=view['op']['microphone_enabled'],candidates=len(view['candidates']),ready=len(view['ready'])))
            del fast_calls[:-256];return result
        def main(self,task):
            started=time.monotonic();result=super().main(task)
            main_calls.append(dict(elapsed_s=time.monotonic()-started,task_id=task.task_id,usage=result.get('usage')))
            return result
    class AudioScheduler(Scheduler):
        def ingest(self,event,now=None):
            if event.get('audio'):
                words=set(re.findall(r'\w+',event['text'].lower()))
                expected='4' if stage=='alice_round_1' else '6' if stage=='alice_round_2' else None
                expected_word='четыре' if expected=='4' else 'шесть'
                receipts=speech.status()['receipts']
                question_index=0 if expected=='4' else 2
                question_stream=receipts[question_index].get('stream_id') if len(receipts)>question_index else None
                reference=playback.backend.stream_map.get(question_stream)
                if normalized(event['text']) in ('замолчи','стоп','тихо','не говори'):
                    stop.set();return
                # Practice responses need an actual completed question, not
                # background sound captured while the main task is pending.
                if reference is None or event['audio']['echo_reference']!=reference:
                    self.state.record('practice_unreferenced_audio');return
                turns.append(dict(received_at=time.monotonic(),capture_age_ms=event['audio']['capture_age_ms'],
                    lineage_id=event['audio']['lineage_id'],speaker_identity='unknown',confirmed=False,
                    expected_answer=expected,expected_answer_matched=expected is not None
                        and bool(words & {expected,expected_word}) and not words & {'не','нет'},
                    echo_reference_matched=reference is not None and reference==event['audio']['echo_reference']))
            return super().ingest(event,now)
    scheduler=AudioScheduler(config,AuditedGateway(config),speech_adapter=speech,audio_adapter=audio)
    lease=create_lease(client,source,a.lease_datagram_port)
    stage='startup';started=time.monotonic();latencies=[];cancel_at=None;cancel_stop_s=None;no_response_since=None
    latest={};status_lock=threading.Lock();stopped_streams=set();progress_frames={};first_consumed={}
    class StatusHandler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def authorized(self):return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+companion.token)
        def do_GET(self):
            if not self.authorized():self.send_error(401);return
            if self.path!='/status':self.send_error(404);return
            with status_lock:payload=json.dumps(latest).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def do_POST(self):
            if not self.authorized():self.send_error(401);return
            if self.path!='/stop':self.send_error(404);return
            stop.set();self.send_response(202);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',a.status_port),StatusHandler);server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    report=dict(mode='actual_distributed_realtime_audio_session',accepted=False,source_boot=source,
        private_cloud_inputs=0,raw_audio_retained=False,resume_attempts=0,motor_commands=0,
        hub_inference=False,questions_limit=2,lease_transport='udp' if a.lease_datagram_port is not None else 'tcp')
    try:
        while not stop.is_set() and time.monotonic()-started<a.duration:
            lease.tick();now=time.monotonic();began=now
            poller.advance(scheduler.state.authority,speech.operator_view());scheduler.advance()
            latencies.append((time.monotonic()-began)*1000)
            events=tts.status();status=speech.status();timeline=status['timeline']
            operator=speech.operator_view()
            if stage!='startup' and operator and (not operator['microphone_enabled'] or operator['quiet'] or operator['privacy_all']):
                raise RuntimeError('Actual operator withdrew realtime session')
            for event in timeline:
                stream=event.get('stream_id')
                if event['kind']=='speech_stopped' and event['stop_known']:stopped_streams.add(stream)
                if event['kind']=='speech_progress':
                    progress_frames[stream]=max(progress_frames.get(stream,0),event['consumed_frames'])
                    if event['consumed_frames']>0:first_consumed.setdefault(stream,event['at'])
            completed=sum(receipt.get('tts_complete') is True and not receipt.get('cancelled')
                and receipt.get('tts_frames',0)>0 and receipt.get('stream_id') in stopped_streams
                and progress_frames.get(receipt.get('stream_id'),0)>=receipt['tts_frames'] for receipt in status['receipts'])
            if stage=='startup' and speech.operator_view() and not status['execution_busy']:
                tts.question(0)
                scheduler.ingest(dict(type='utterance',text='Произнеси дословно, без ответа на вопрос и без пояснений: '+tts.questions[0]))
                stage='alice_round_1'
            elif stage=='alice_round_1' and completed>=2 and len(turns)>=1:
                cooldown=now;stage='cooldown'
            elif stage=='cooldown' and now-cooldown>=3 and not status['execution_busy']:
                tts.question(1)
                scheduler.ingest(dict(type='utterance',text='Произнеси дословно, без ответа на вопрос и без пояснений: '+tts.questions[1]))
                stage='alice_round_2'
            elif stage=='alice_round_2' and completed>=4 and len(turns)>=2:
                no_response_since=now;no_response_turns=len(turns);stage='no_response'
            elif stage=='no_response' and now-no_response_since>=8:
                report['no_response']=dict(seconds=now-no_response_since,new_turns=len(turns)-no_response_turns,
                    no_response_stt=audio.status()['counts']['no_response'])
                scheduler.ingest(dict(type='utterance',text='Произнеси дословно: Это конечная проверка отмены. Сейчас я произнесу ещё несколько слов, чтобы проверить остановку звука.'))
                stage='cancel_wait'
            # Playback status deliberately has no active PCM. Detect the fifth
            # producer's stream through its scoped receipt/progress timeline.
            if stage=='cancel_wait' and len(events)>=5:
                receipts=status['receipts'];streams=[r.get('stream_id') for r in receipts]
                earlier=set(streams[:4])
                progress=[event for event in timeline if event['kind']=='speech_progress'
                    and event['consumed_frames']>=320 and event['stream_id'] not in earlier]
                if progress:
                    cancel_at=now;scheduler.ingest(dict(type='operator',muted=True));stage='cancel_pending'
            if stage=='cancel_pending' and status['stop_known'] and not status['execution_busy']:
                cancel_stop_s=now-cancel_at;stage='complete';break
            with status_lock:latest=dict(stage=stage,elapsed_s=now-started,source_boot=source,
                audio=audio.status(),peer_poll=poller.status(),lease=lease.status(),
                speech_busy=status['execution_busy'],speech_stop_known=status['stop_known'],turns=len(turns),
                main_execution_busy=bool(scheduler.main_job and not scheduler.main_job.future.done()))
            time.sleep(.005)
        report.update(stage=stage,counts=dict(scheduler.state.counts),turns=turns,
            tts_events=tts.status(),main_calls=main_calls,fast_calls=fast_calls,
            max_scheduler_advance_ms=max(latencies,default=None),cancel_to_verified_s=cancel_stop_s,
            audio=audio.status(),peer_poll=poller.status(),lease=lease.status())
        report['consumption']=[dict(stream_id=receipt.get('stream_id'),tts_frames=receipt.get('tts_frames'),
            max_measured_consumed=progress_frames.get(receipt.get('stream_id'),0),
            verified_stopped=receipt.get('stream_id') in stopped_streams) for receipt in speech.status()['receipts']]
        for index,turn in enumerate(turns[:2]):
            receipts=speech.status()['receipts'];reply_index=index*2+1
            if len(receipts)>reply_index:
                receipt=receipts[reply_index];endpoint=turn['received_at']-turn['capture_age_ms']/1000
                consumed=first_consumed.get(receipt.get('stream_id'))
                if consumed is not None:turn['endpoint_to_first_consumed_upper_bound_s']=consumed-endpoint
                if 'tts_first_pcm_s' in receipt:
                    turn['endpoint_to_first_tts_pcm_upper_bound_s']=receipt['producer_started_at']+receipt['tts_first_pcm_s']-endpoint
        report['accepted']=(stage=='complete' and len(turns)==2 and len(main_calls)>=5
            and [turn['expected_answer'] for turn in turns]==['4','6']
            and all(turn['expected_answer_matched'] and turn['echo_reference_matched'] for turn in turns)
            and cancel_stop_s is not None and cancel_stop_s<=.5
            and report.get('no_response',{}).get('new_turns')==0 and max(latencies)<100
            and sum(event['kind']=='question' for event in tts.status())==2 and not playback.status()['resumable'])
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)[:128]
    finally:
        stop.set();poller.close();audio.close();speech.close();lease.close();scheduler.close()
        report.update(stage=stage,counts=dict(scheduler.state.counts),turns=turns,main_calls=main_calls,
            fast_calls=fast_calls,audio=audio.status(),peer_poll=poller.status(),lease=lease.status(),
            max_scheduler_advance_ms=max(latencies,default=None))
        # Owned device stop uses a separate bounded job. An HTTP failure never
        # becomes a false physical stop-known acknowledgement.
        stop_job=Job(client.call,'/stop');deadline=time.monotonic()+1
        while time.monotonic()<deadline and (not stop_job.future.done() or speech.status()['execution_busy']):time.sleep(.005)
        report['speech_after']=speech.status();report['peer_stop_execution_busy']=not stop_job.future.done()
        if stop_job.future.done():
            try:report['peer_stop']=stop_job.future.result()
            except Exception:report['peer_stop_unknown']=True
        report['execution_busy']=dict(fast=bool(scheduler.fast_job and not scheduler.fast_job.future.done()),
            main=bool(scheduler.main_job and not scheduler.main_job.future.done()),
            audio=audio.status()['execution_busy'],speech=speech.status()['execution_busy'],
            peer_poll=poller.status()['execution_busy'],lease=lease.status()['execution_busy'])
        report['accepted']=report['accepted'] and not any(report['execution_busy'].values()) and report.get('peer_stop',{}).get('stop_known') is True
        server.shutdown();server.server_close()
        with a.output.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
