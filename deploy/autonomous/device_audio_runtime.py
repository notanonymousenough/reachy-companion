"""Finite owned realtime audio service. Device capture/PCM only; no inference."""
import argparse
import json
import signal
import threading
import time
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
from reachy_companion.config import Config
from reachy_companion.autonomous.alsa_capture import AlsaCapture
from reachy_companion.autonomous.alsa_pcm import AlsaPCM
from reachy_companion.autonomous.audio_peer import diagnostic_operator,AudioPeer,create_server
from reachy_companion.autonomous.playback import Playback
from reachy_companion.autonomous.response_endpoint import ResponseEndpoint
from reachy_companion.autonomous.contracts import uid
from reachy_companion.autonomous.lease_datagram import LeaseDatagramServer
from reachy_companion.autonomous.pcm_controls import StereoChannels,CaptureExclusion

HTTP=build_opener(ProxyHandler({}))

def agent(cfg,path,payload=None):
    request=Request(cfg['network']['agent_url']+path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+cfg.token,'Content-Type':'application/json'})
    with HTTP.open(request,timeout=.3 if payload is None else 1) as response:
        raw=response.read(65537)
    if len(raw)>65536:raise ValueError('Operator cap')
    return json.loads(raw)


def cleanup(cfg,owner_path):
    if not owner_path.exists():return
    owner=json.loads(owner_path.read_text());actual=agent(cfg,'/operator')
    if actual['agent_boot_id']!=owner['agent_boot_id']:return
    if (actual['microphone_epoch']==owner['owned_microphone_epoch']
            and actual.get('microphone_owner_id')==owner['owner_id']):
        agent(cfg,'/microphone',dict(enabled=False,expected_boot_id=owner['agent_boot_id'],
            expected_epoch=owner['owned_microphone_epoch'],expected_owner_id=owner['owner_id']))
    elif actual['microphone_epoch']==owner['initial_microphone_epoch']:
        agent(cfg,'/microphone',dict(enabled=False,expected_boot_id=owner['agent_boot_id'],
            expected_epoch=owner['initial_microphone_epoch']))


def mute_owned_agent(cfg,owner):
    receipt=agent(cfg,'/microphone',dict(enabled=False,listen=False,expected_boot_id=owner['agent_boot_id'],
        expected_epoch=owner['owned_microphone_epoch'],expected_owner_id=owner['owner_id']))
    return diagnostic_operator(receipt)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','output','owner-file'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--controller',required=True);p.add_argument('--duration',type=float,default=90)
    p.add_argument('--allow-capture-output',action='store_true');p.add_argument('--allow-agent-mute',action='store_true');p.add_argument('--cleanup-only',action='store_true')
    p.add_argument('--port',type=int,default=8780)
    p.add_argument('--capture-device',choices=('reachymini_audio_src','plug:reachymini_audio_src'))
    p.add_argument('--capture-channel',type=int,choices=(0,1),default=0)
    p.add_argument('--echo-tail-seconds',type=float,default=.2)
    p.add_argument('--endpoint-max-seconds',type=int,choices=range(1,9),default=8)
    p.add_argument('--endpoint-silence-frames',type=int,default=30)
    p.add_argument('--listen',default='127.0.0.1')
    p.add_argument('--lease-datagram-port',type=int)
    a=p.parse_args();cfg=Config(a.config)
    if a.cleanup_only:cleanup(cfg,a.owner_file);return
    channels=StereoChannels(a.capture_channel);exclusion=CaptureExclusion(a.echo_tail_seconds)
    endpoint_settings=dict(max_seconds=a.endpoint_max_seconds,silence_frames=a.endpoint_silence_frames)
    ResponseEndpoint(None,**endpoint_settings) # validate before activating an owner/microphone
    if not 1<=a.port<=65535 or a.lease_datagram_port is not None and not 1<=a.lease_datagram_port<=65535:
        raise ValueError('Explicit valid local transport ports required')
    if a.listen!='127.0.0.1':
        import ipaddress
        address=ipaddress.ip_address(a.listen)
        if not any(address in ipaddress.ip_network(network) for network in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
            raise ValueError('Explicit local private IPv4 interface required')
    if (not a.allow_capture_output or not 1<=a.duration<=180 or a.output.exists() or a.owner_file.exists()
            or not 1<=len(a.controller)<=128):raise ValueError('Explicit fresh finite audio owner required')
    before=agent(cfg,'/operator');policy=before['motion_policy']
    if (before['microphone_enabled'] or before['capture_active'] or before['phase']!='paused'
            or policy['quiet'] or policy['privacy_all']):raise RuntimeError('Idle operator baseline required')
    owner=dict(agent_boot_id=before['agent_boot_id'],initial_microphone_epoch=before['microphone_epoch'],
        owned_microphone_epoch=before['microphone_epoch']+1,owner_id=uid(),policy_epoch=policy['epoch'])
    with a.owner_file.open('x') as f:json.dump(owner,f);f.flush();__import__('os').fsync(f.fileno())
    report=dict(mode='finite_realtime_device_audio_owner',accepted=False,controller=a.controller,inference_on_robot=False,
        raw_audio_retained=False,physical_motor_commands=0,operator_before=diagnostic_operator(before),capture_frames=0,
        capture_timestamp_samples=0,utterances=0,no_response_windows=0,owned_output_frames_excluded=0)
    peer=capture=server=endpoint=datagram=None;stop=threading.Event()
    for signum in (signal.SIGTERM,signal.SIGINT):signal.signal(signum,lambda *_:stop.set())
    try:
        actual=agent(cfg,'/microphone',dict(enabled=True,listen=False,
            expected_boot_id=owner['agent_boot_id'],expected_epoch=owner['initial_microphone_epoch'],owner_id=owner['owner_id']))
        if actual.get('microphone_owner_id')!=owner['owner_id'] or actual['microphone_epoch']!=owner['owned_microphone_epoch']:
            raise RuntimeError('Mic activation owner mismatch')
        playback=Playback(AlsaPCM(cfg['audio']['playback_device']),chunk_frames=4096)
        peer=AudioPeer(playback,lambda:agent(cfg,'/operator'),owner,controller=a.controller,
            mute_owner=(lambda:mute_owned_agent(cfg,owner)) if a.allow_agent_mute else None)
        if a.lease_datagram_port is not None:
            datagram=LeaseDatagramServer(peer,cfg.token,a.listen,a.lease_datagram_port)
        server=create_server(peer,cfg.token,bind=a.listen,port=a.port)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        import webrtcvad
        capture_device=a.capture_device or cfg['audio']['capture_device']
        report['capture_device']=capture_device
        endpoint=ResponseEndpoint(webrtcvad.Vad(2),**endpoint_settings)
        start=time.monotonic()
        while not stop.is_set() and not peer.closed and time.monotonic()-start<a.duration:
            if not peer.permitted():
                endpoint.clear();time.sleep(.003);continue
            if capture is None:capture=AlsaCapture(capture_device)
            value=capture.read()
            if not value:time.sleep(.003);continue
            report['capture_frames']+=value['frames'];report['capture_timestamp_samples']+=1
            with playback.lock:
                active_stream=playback.active['stream_id'] if playback.active else None;output=playback.status()
            if type(value['frames']) is not int or value['frames']*4!=len(value['pcm']):raise ValueError('Complete stereo capture frames required')
            scope=exclusion.classify(active_stream,output,value['captured_end']-value['frames']/16000,time.monotonic())
            mono=channels.select(value['pcm'],scope)
            if scope!='endpoint':
                report['owned_output_frames_excluded']+=value['frames'];endpoint.clear()
                endpoint=ResponseEndpoint(webrtcvad.Vad(2),**endpoint_settings);continue
            available_bytes=len(endpoint.pcm)+len(endpoint.pending)+len(mono)
            endpoint.feed(mono);del mono
            if endpoint.reason:
                if endpoint.reason=='speech_then_silence':
                    # VAD can end inside this read. Do not date the retained
                    # utterance at the later samples that were discarded.
                    unused_frames=(available_bytes-len(endpoint.pcm))//2
                    captured_end=value['captured_end']-unused_frames/16000
                    if peer.publish(bytes(endpoint.pcm),captured_end,exclusion.last_stream):report['utterances']+=1
                else:report['no_response_windows']+=1
                endpoint.clear();endpoint=ResponseEndpoint(webrtcvad.Vad(2),**endpoint_settings)
        report.update(elapsed_s=time.monotonic()-start,source_boot=peer.boot_id,controller_lease_started=peer.started_lease,
            capture_timestamp_provenance='alsa_monotonic_available_position',peer_close_reason=peer.close_reason,
            max_operator_ms=peer.max_operator_ms,operator_requests=peer.operator_requests)
        report['accepted']=(peer.started_lease and report['capture_timestamp_samples']>0
            and (stop.is_set() or time.monotonic()-start>=a.duration or peer.close_reason=='controller_stop'))
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)[:128]
    finally:
        report.update(channel_levels=channels.status(),echo_tail_seconds=exclusion.tail_seconds,endpoint_settings=endpoint_settings)
        if endpoint:endpoint.clear()
        if peer:
            report['lease_requests']=peer.lease_requests;report['max_lease_gap_ms']=peer.max_lease_gap_ms
            peer.close();deadline=time.monotonic()+.5
            while (peer.playback.status()['execution_busy'] or peer.operator_control_busy) and time.monotonic()<deadline:time.sleep(.005)
            peer.watch.join(timeout=.1)
            report['playback']=peer.playback.status()
            report['peer_status']=peer.dispatch('/status',dict(controller=a.controller))
        if capture:
            report['capture_read_calls']=capture.calls
            report['capture_call_seconds']=capture.call_seconds
            report['max_capture_call_ms']=capture.max_call_seconds*1000
            report['capture_closed']=capture.close()
        if server:server.shutdown();server.server_close()
        if datagram:
            datagram.close();report['lease_datagram']=datagram.status()
            report['lease_datagram_execution_busy']=datagram.worker.is_alive()
        try:
            cleanup(cfg,a.owner_file);after=agent(cfg,'/operator')
            report['operator_after']=diagnostic_operator(after)
            report['microphone_restored']=after['microphone_enabled'] is False
        except Exception as exc:report['cleanup_error']=type(exc).__name__
        cancel=report.get('peer_status',{}).get('agent_mute_receipt')
        if cancel is not None:
            after=report.get('operator_after',{})
            final_policy=after.get('motion_policy',{})
            report['accepted']=('error' not in report and report.get('controller_lease_started') is True
                and report['capture_timestamp_samples']>0 and after.get('agent_boot_id')==cancel['agent_boot_id']
                and type(after.get('microphone_epoch')) is int and after['microphone_epoch']==cancel['microphone_epoch']
                and after.get('microphone_owner_present') is False and after.get('microphone_state_error') is None
                and after.get('capture_active') is False and after.get('listening') is False and after.get('phase')=='paused'
                and type(final_policy.get('epoch')) is int and final_policy['epoch']==owner['policy_epoch'] and final_policy.get('quiet') is False
                and final_policy.get('privacy_all') is False)
        report['accepted']=(report['accepted'] and report.get('capture_closed') is True
            and report.get('microphone_restored') is True and report.get('playback',{}).get('stop_known') is True
            and report.get('playback',{}).get('execution_busy') is False
            and report.get('peer_status',{}).get('watch_execution_busy') is False
            and report.get('peer_status',{}).get('operator_execution_busy') is False
            and report.get('peer_status',{}).get('operator_control_execution_busy') is False)
        with a.output.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
