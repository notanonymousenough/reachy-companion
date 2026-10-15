"""Normal joined companion, inside one existing finite device-owner window.

No device startup, microphone acquisition, automatic reconnect or practice script.
The device's 180s lifetime and 32-stream budget remain real limits.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import threading
import time
from .audio_adapter import AudioAdapter,HttpSTT
from .audio_peer import AudioPolling,PeerClient,PeerLease,PeerStartup,RemotePCM
from .audio_session_control import create_server
from .config import load
from .lease_datagram import DatagramRenewal
from .motion_adapter import MotionAdapter
from .playback import Playback
from .runtime import Job,RemoteGateway,Scheduler
from .speech_adapter import SpeechAdapter,HttpTTS
from .voice_chain import check_context_task,check_context_view,context_binding


class ContextGateway(RemoteGateway):
    def __init__(self,config,binding):
        self.memory_binding=binding
        super().__init__(config)
    def fast(self,request_id,view):
        if self.memory_binding is not None:check_context_view(view,self.memory_binding)
        return super().fast(request_id,view)
    def main(self,task):
        if self.memory_binding is not None:check_context_task(task,self.memory_binding)
        return super().main(task)


def occupied(scheduler,poller,lease,peer_job=None,health_job=None,stop_job=None):
    jobs={name:getattr(scheduler,name+'_job') for name in
          ('fast','main','actor','motion','context','context_revoke','context_terminal')}
    jobs.update(peer_status=peer_job,health=health_job,peer_stop=stop_job)
    result={name:bool(job and not job.future.done()) for name,job in jobs.items()}
    result['context_terminal_revoke']=result.pop('context_terminal')
    result.update(audio=scheduler.audio_adapter.status()['execution_busy'],
        speech=scheduler.speech_adapter.status()['execution_busy'],
        peer_poll=poller.status()['execution_busy'],lease=lease.status()['execution_busy'])
    if scheduler.motion_adapter:result['motion']=result['motion'] or scheduler.motion_adapter.status()['execution_busy']
    return result


def run_session(scheduler,poller,lease,client,stop_client,source,stop,duration,publish):
    """Reducer-owned loop. Each remote operation keeps one real occupied slot."""
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 1<=duration<=180:
        raise ValueError('Normal session must fit the existing finite device window')
    startup=PeerStartup(source);peer_job=health_job=stop_job=None
    next_peer=next_health=0;started=time.monotonic();last_health=last_operator=started
    reason='duration';errors=[];ready_seen=False
    report=dict(mode='normal_joined_companion',continuous=False,accepted=False,
        device_lifetime_cap_s=180,device_stream_cap=32,raw_audio_retained=False,
        transcripts_retained=False,speaker_identity='unknown',automatic_microphone_activation=False,
        automatic_reconnect=False,source_boot=source,hub_boot_id=scheduler.state.authority.hub_boot_id,
        context_enabled=scheduler.config.get('context',{}).get('enabled',False))
    report['lease_transport']='udp' if lease.datagram is not None else 'tcp'
    motion_identity=None
    if scheduler.motion_adapter:
        current=scheduler.motion_adapter.cached
        if current:motion_identity={key:current['binding'][key] for key in ('agent_boot_id','actor_boot_id','session_id')}
    try:
        while not stop.is_set() and time.monotonic()-started<duration:
            now=time.monotonic()
            if peer_job and peer_job.future.done():
                try:startup.observe(peer_job.future.result(),lease.status()['calls']>lease.status()['errors'])
                except Exception as exc:startup.failure(type(exc).__name__)
                peer_job=None
            if startup.advance()=='WITHDRAWN':reason=startup.reason;break
            if not peer_job and now>=next_peer:
                peer_job=Job(client.call,'/status');next_peer=now+.1
            if health_job and health_job.future.done():
                health=health_job.future.result();health_job=None
                if health.get('compute_boot_id')!=scheduler.state.authority.compute_boot_id or health.get('quarantined'):
                    raise RuntimeError('Compute owner changed or completion unknown; no automatic reconnect')
                last_health=now
            if now-last_health>=.5:raise RuntimeError('Compute health expired; occupied calls retained')
            if not health_job and now>=next_health:
                health_job=Job(scheduler.gateway.call,'/health');next_health=now+.2
            scheduler.speech_adapter.advance(scheduler.state.authority)
            operator=scheduler.speech_adapter.operator_view()
            if operator is not None:
                last_operator=now
                if motion_identity is not None and operator['binding'][0]!=motion_identity['agent_boot_id']:
                    raise RuntimeError('Speaker and motor belong to different physical operator boots')
            if now-last_operator>=.5:raise RuntimeError('Local operator receipt expired; no automatic recovery')
            if startup.phase=='ACTIVE':
                # No synthetic question, echo-reference admission or speaker claim.
                scheduler.advance()
                poller.advance(scheduler.state.authority,scheduler.speech_adapter.operator_view())
                ready_seen=ready_seen or scheduler.audio_adapter.allowed
                if scheduler.motion_adapter:
                    current=scheduler.motion_adapter.cached
                    if current and motion_identity!={key:current['binding'][key] for key in motion_identity}:
                        raise RuntimeError('Motor owner changed; explicit new admission required')
                if (scheduler.speech_adapter.playback.backend.reservation_attempts>=31
                        and not scheduler.speech_adapter.status()['execution_busy']):
                    reason='finite_stream_budget';break
            if stop.is_set():reason='controller_stop';break
            lease.tick() # actual reducer progress; never a background perpetual grant
            publish(dict(stage=startup.phase,elapsed_s=now-started,counts=dict(scheduler.state.counts),
                listening_ready=startup.phase=='ACTIVE' and scheduler.audio_adapter.allowed
                    and scheduler.speech_adapter.operator_view() is not None,
                peer=startup.status(),execution_busy=occupied(scheduler,poller,lease,peer_job,health_job)))
            stop.wait(.005)
        if stop.is_set():reason='controller_stop'
    except BaseException as exc:
        reason='runtime_error';errors.append(type(exc).__name__)
    finally:
        stop.set();startup.close()
        # Attempt every owner withdrawal, retaining all actual job references.
        actions=[lease.close,poller.close,scheduler.close]
        if scheduler.motion_adapter:actions.append(scheduler.motion_adapter.close)
        for action in actions:
            try:action()
            except BaseException as exc:errors.append(type(exc).__name__)
        stop_job=Job(lambda:stop_client.call('/stop',source_boot=source))
        deadline=time.monotonic()+1
        while time.monotonic()<deadline and any(occupied(scheduler,poller,lease,peer_job,health_job,stop_job).values()):
            time.sleep(.005)
        peer_stop=None
        if stop_job.future.done():
            try:peer_stop=stop_job.future.result()
            except Exception as exc:errors.append(type(exc).__name__)
        report.update(reason=reason,errors=errors,elapsed_s=time.monotonic()-started,
            listening_ready_seen=ready_seen,
            counts=dict(scheduler.state.counts),peer_stop=peer_stop,
            peer_stop_execution_busy=not stop_job.future.done(),
            execution_busy=occupied(scheduler,poller,lease,peer_job,health_job,stop_job),
            speech_stop_known=scheduler.speech_adapter.status()['stop_known'])
        report.update(speech_after=scheduler.speech_adapter.status(),audio=scheduler.audio_adapter.status(),
            peer_poll=poller.status(),lease=lease.status(),
            reservation_attempts=scheduler.speech_adapter.playback.backend.reservation_attempts)
        if scheduler.motion_adapter:report['motion_receipts']=list(scheduler.motion_adapter.receipts)
        if scheduler.context_terminal_job and scheduler.context_terminal_job.future.done():
            try:report['context_terminal_revoke']=scheduler.context_terminal_job.future.result()
            except Exception:report['context_terminal_revoke_unknown']=True
        context_ok=not report['context_enabled'] or (
            report.get('context_terminal_revoke',{}).get('output',{}).get('terminal') is True
            and report.get('context_terminal_revoke',{}).get('output',{}).get('revoked') is True)
        motion_ok=not scheduler.motion_adapter or scheduler.motion_adapter.status()['stop_known'] is True
        report['cleanup_verified']=(not errors and not any(report['execution_busy'].values()) and context_ok and motion_ok
            and report['speech_stop_known'] is True and isinstance(peer_stop,dict)
            and peer_stop.get('stop_known') is True and peer_stop.get('execution_busy') is False)
        report['accepted']=ready_seen and report['cleanup_verified'] and reason in ('duration','controller_stop','finite_stream_budget')
        publish(dict(stage='STOPPED',reason=reason,execution_busy=report['execution_busy'],cleanup_verified=report['cleanup_verified']))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('normal',),required=True)
    for name in ('config','companion-config','token-file','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--peer-url',required=True);parser.add_argument('--peer-stop-port',type=int,required=True)
    parser.add_argument('--controller',required=True);parser.add_argument('--source-boot',required=True)
    parser.add_argument('--duration',type=float,default=60);parser.add_argument('--status-port',type=int,default=8791)
    parser.add_argument('--lease-datagram-port',type=int);parser.add_argument('--trusted-private-lan',action='store_true')
    parser.add_argument('--allow-capture-output',action='store_true');parser.add_argument('--allow-bounded-motion',action='store_true')
    parser.add_argument('--memory-readback',type=Path);parser.add_argument('--memory-readback-sha256')
    args=parser.parse_args()
    if not args.allow_capture_output or args.output.exists() or not math.isfinite(args.duration) or not 1<=args.duration<=180:
        raise ValueError('Fresh explicit finite normal companion opt-in required')
    if not 1<=len(args.source_boot)<=128 or any(port is not None and not 1<=port<=65535
            for port in (args.status_port,args.peer_stop_port,args.lease_datagram_port)):
        raise ValueError('Explicit source binding and valid transport ports required')
    cfg=load(args.config);binding=None
    if cfg.get('speech',{}).get('enabled'):
        raise ValueError('Normal distributed mode uses the explicit remote peer, not the local ALSA speech profile')
    context_enabled=cfg.get('context',{}).get('enabled',False)
    if context_enabled or args.memory_readback is not None or args.memory_readback_sha256 is not None:
        from .voice_memory_fixture import read_json
        if (not context_enabled or cfg['context'].get('mode')!='memory_only' or args.memory_readback is None
                or not args.memory_readback_sha256):raise ValueError('Reviewed isolated memory-only readback required')
        artifact,sha=read_json(args.memory_readback,65536)
        if sha!=args.memory_readback_sha256:raise ValueError('Readback changed')
        binding=context_binding(artifact)
    motion_enabled=cfg.get('motion',{}).get('enabled',False)
    if motion_enabled!=args.allow_bounded_motion:raise ValueError('Matching explicit bounded antenna17 opt-in required')
    if motion_enabled and (args.config.resolve().parent/cfg['motion']['hub_config_path']).resolve()!=args.companion_config.resolve():
        raise ValueError('Motor profile must bind the same explicitly selected companion configuration')
    from reachy_companion.config import Config
    from reachy_companion.hub import Hub
    companion=Config(args.companion_config);hub=Hub(companion)
    os.environ[cfg['gateway']['token_env']]=args.token_file.read_text().strip()
    gateway=ContextGateway(cfg,binding)
    client=PeerClient(args.peer_url,companion.token,args.controller,trusted_private_lan=args.trusted_private_lan)
    stop_client=client.at_port(args.peer_stop_port)
    initial=client.call('/status')
    if initial.get('source_boot')!=args.source_boot or initial.get('closed') is not False:
        raise ValueError('Exact existing device source owner required')
    motion=None;audio=speech=poller=lease=server=scheduler=datagram=None
    stop=threading.Event();latest={};lock=threading.Lock();report=None;server_thread=None
    def publish(value):
        with lock:latest.clear();latest.update(value)
    def status():
        with lock:return dict(latest)
    previous_signals={}
    try:
        server=create_server(companion.token,args.controller,args.source_boot,stop,status,port=args.status_port)
        server_thread=threading.Thread(target=server.serve_forever,daemon=True);server_thread.start()
        for signum in (signal.SIGTERM,signal.SIGINT):
            previous_signals[signum]=signal.signal(signum,lambda *_:stop.set())
        if motion_enabled:
            # Existing actor owns hardware; this path cannot construct/restart it.
            native=cfg['motion'];motor_hub=Hub(Config(args.companion_config))
            motor_hub.config.data['guarded_motion']['enabled']=True
            motor_hub.config.data['network']['agent_url']=native['agent_url']
            motion=MotionAdapter(motor_hub,cooldown_s=native['cooldown_s'],heartbeat_s=native['heartbeat_s'])
            current=motor_hub.agent('/status');actor=current['motion_actor']
            if (not isinstance(actor.get('hold'),dict) or actor['hold'].get('verified') is not True
                    or actor['hold'].get('trajectory_updates_after_hold')!=0):raise ValueError('Current physical hold proof required')
            if not motion.refresh()['motion_allowed']:raise ValueError('Current bounded motor owner not ready')
        audio=AudioAdapter(HttpSTT(companion['network']['compute_url'],companion.token))
        pcm=Playback(RemotePCM(client,stop_port=args.peer_stop_port,source_boot=args.source_boot,max_streams=32),chunk_frames=4096,motion=motion)
        speech=SpeechAdapter(pcm,HttpTTS(companion['network']['voice_url'],companion.token,
            gain=cfg.get('speech',{}).get('tts_gain',1)),lambda:hub.agent('/operator'))
        poller=AudioPolling(client,audio,args.source_boot)
        scheduler=Scheduler(cfg,gateway,motion,speech,audio)
        datagram=DatagramRenewal(client,args.source_boot,args.lease_datagram_port) if args.lease_datagram_port is not None else None
        lease=PeerLease(client,datagram=datagram)
        report=run_session(scheduler,poller,lease,client,stop_client,args.source_boot,stop,args.duration,publish)
    except BaseException as exc:
        report=dict(mode='normal_joined_companion',accepted=False,cleanup_verified=False,
            reason='startup_error',errors=[type(exc).__name__],source_boot=args.source_boot,
            raw_audio_retained=False,transcripts_retained=False,continuous=False)
    finally:
        if report is None or report.get('reason')=='startup_error':
            stop.set();cleanup_errors=[]
            for resource in (lease,datagram,poller,scheduler,audio,speech,motion):
                if resource is not None:
                    try:resource.close()
                    except BaseException as exc:cleanup_errors.append(type(exc).__name__)
            startup_stop=Job(lambda:stop_client.call('/stop',source_boot=args.source_boot))
            deadline=time.monotonic()+1
            def startup_busy():
                return dict(peer_stop=not startup_stop.future.done(),
                    audio=audio.status()['execution_busy'] if audio is not None else False,
                    speech=speech.status()['execution_busy'] if speech is not None else False,
                    peer_poll=poller.status()['execution_busy'] if poller is not None else False,
                    lease=lease.status()['execution_busy'] if lease is not None else False,
                    motion=motion.status()['execution_busy'] if motion is not None else False,
                    context_terminal_revoke=bool(scheduler and scheduler.context_terminal_job and not scheduler.context_terminal_job.future.done()))
            while time.monotonic()<deadline and any(startup_busy().values()):time.sleep(.005)
            report['startup_execution_busy']=startup_busy();report['cleanup_errors']=cleanup_errors
            if startup_stop.future.done():
                try:report['peer_stop']=startup_stop.future.result()
                except Exception as exc:cleanup_errors.append(type(exc).__name__)
        final_errors=[]
        if server:
            try:
                if server_thread is not None and server_thread.is_alive():server.shutdown();server_thread.join(1)
            except BaseException as exc:final_errors.append(type(exc).__name__)
            try:server.server_close()
            except BaseException as exc:final_errors.append(type(exc).__name__)
            deadline=time.monotonic()+.5
            while server.transport_status()['execution_busy'] and time.monotonic()<deadline:time.sleep(.005)
            report['control_transport']=server.transport_status()
            report['control_listener_execution_busy']=bool(server_thread and server_thread.is_alive())
            if report['control_transport']['execution_busy'] or report['control_listener_execution_busy']:
                report['accepted']=report['cleanup_verified']=False
        for signum,handler in previous_signals.items():
            try:signal.signal(signum,handler)
            except BaseException as exc:final_errors.append(type(exc).__name__)
        if final_errors:
            report['control_cleanup_errors']=final_errors;report['accepted']=report['cleanup_verified']=False
    report.update(server.session_binding if server is not None else dict(controller=args.controller))
    with args.output.open('x') as file:json.dump(report,file,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['accepted'] else 2


if __name__=='__main__':raise SystemExit(main())
