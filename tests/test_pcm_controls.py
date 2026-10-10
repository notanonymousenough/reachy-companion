"""Synthetic PCM, actual local stop worker and mocked ALSA position; no devices."""
import base64
import ctypes as C
import io
import json
import struct
import threading
import time
import unittest
from unittest.mock import patch
from reachy_companion.autonomous.pcm_controls import PcmGain,StereoChannels,CaptureExclusion
from reachy_companion.autonomous.speech_adapter import HttpTTS
from reachy_companion.autonomous.playback import Playback,ReplayPCM
from reachy_companion.autonomous.alsa_capture import AlsaCapture,Timespec
from reachy_companion.autonomous.response_endpoint import ResponseEndpoint


def safe(timeline=None):return dict(execution_busy=False,stop_known=True,closed=False,quarantined=False,timeline=timeline or [])
def pcm(values):return struct.pack('<'+'h'*len(values),*values)
def event(data,**fields):return dict(type='audio',sample_rate=16000,channels=1,format='S16_LE',pcm_base64=base64.b64encode(data).decode(),**fields)


class PcmControlsTests(unittest.TestCase):
    def test_channel_selection_and_scoped_aggregates_without_raw_retention(self):
        stereo=pcm([10,100,-20,-200,30,300]);left=StereoChannels(0);right=StereoChannels(1)
        self.assertEqual(left.select(stereo,'endpoint'),pcm([10,-20,30]))
        self.assertEqual(right.select(stereo,'echo_tail'),pcm([100,-200,300]))
        status=right.status();self.assertEqual(status['scopes']['echo_tail'][0]['peak'],30)
        self.assertEqual(status['scopes']['echo_tail'][1]['peak'],300)
        self.assertEqual(status['scopes']['endpoint'][1]['samples'],0);self.assertFalse(status['raw_audio_retained'])
        for channel in (True,-1,2):
            with self.assertRaises(ValueError):StereoChannels(channel)
        with self.assertRaises(ValueError):right.select(b'\0\0','endpoint')

    def test_default_gain_bit_exact_and_optin_soft_limit(self):
        data=pcm([-32768,-16000,-10,0,10,16000,32767]);default=PcmGain()
        self.assertEqual(default.process(data),data)
        gained=PcmGain(3);values=struct.unpack('<7h',gained.process(data))
        self.assertGreater(abs(values[2]),10);self.assertLessEqual(max(map(abs,values)),30000)
        self.assertEqual(gained.status()['output']['rail_samples'],0)
        self.assertEqual(default.status()['output']['rail_samples'],2)
        self.assertFalse(gained.status()['acoustic_audibility_verified'])
        for gain in (True,float('nan'),float('inf'),.9,4.1):
            with self.assertRaises(ValueError):PcmGain(gain)
        with self.assertRaises(ValueError):gained.process(b'\0')
        with self.assertRaises(ValueError):gained.process(b'\0'*8194)

    def test_capture_tail_uses_sample_start_not_read_time(self):
        exclusion=CaptureExclusion(.4)
        status=safe([dict(kind='speech_stopped',stream_id='short',stop_known=True,at=10)])
        # A completed short output happened between polls; delayed read includes
        # a capture prefix from before the tail even though readtime is later.
        self.assertEqual(exclusion.classify(None,status,10.35,10.6),'echo_tail')
        self.assertEqual(exclusion.classify(None,status,10.41,10.6),'endpoint')
        self.assertEqual(exclusion.last_stream,'short')
        for value in (.1,.6,True,float('nan')):
            with self.assertRaises(ValueError):CaptureExclusion(value)
        with self.assertRaises(ValueError):exclusion.classify(None,status,11,10.6)

    def test_actual_stop_worker_with_no_active_stream_still_excludes_capture(self):
        entered=threading.Event();release=threading.Event()
        class Blocked(ReplayPCM):
            def stop(self,stream):entered.set();release.wait(1);return super().stop(stream)
        playback=Playback(Blocked(),allow_simulated=True,stop_timeout=.5)
        self.addCleanup(playback.close);self.addCleanup(release.set)
        playback.operator('owner',microphone_enabled=True,valid_until=time.monotonic()+5)
        stream=playback.begin('owner','request',deadline=time.monotonic()+5)
        playback.push(stream,b'\0\0'*100)
        playback.interrupt(preserve=False,wait=False);self.assertTrue(entered.wait(1))
        self.assertIsNone(playback.active);self.assertTrue(playback.status()['execution_busy'])
        exclusion=CaptureExclusion(.4);now=time.monotonic()
        self.assertEqual(exclusion.classify(None,playback.status(),now-.02,now),'owned_or_unknown_stop')
        release.set();deadline=time.monotonic()+1
        while playback.status()['execution_busy'] and time.monotonic()<deadline:time.sleep(.002)
        status=playback.status();self.assertTrue(status['stop_known']);self.assertFalse(status['execution_busy'])
        now=time.monotonic();self.assertEqual(exclusion.classify(None,status,now,now),'echo_tail')
        self.assertEqual(exclusion.classify(None,status,now+.39,now+.6),'echo_tail')
        self.assertEqual(exclusion.classify(None,status,now+.41,now+.6),'endpoint')

    def test_http_tts_large_event_is_chunked_and_default_output_identical(self):
        data=pcm([100,-200]*10000);tts=HttpTTS('http://fixture','token',max_event=100000)
        body=(json.dumps(event(data))+'\n'+json.dumps(dict(type='done',ok=True))+'\n').encode()
        with patch.object(tts.opener,'open',return_value=io.BytesIO(body)):
            chunks=list(tts.stream('neutral',threading.Event()))
        self.assertEqual(b''.join(chunks),data);self.assertTrue(all(len(chunk)<=8192 for chunk in chunks))
        self.assertTrue(tts.status()[0]['complete']);self.assertEqual(tts.status()[0]['output']['samples'],20000)
        self.assertNotIn('neutral',json.dumps(tts.status()))

    def test_tts_cancellation_after_read_and_bad_pcm_never_yield(self):
        for kind in ('cancel','odd','bool_channels','float_rate'):
            with self.subTest(kind=kind):
                cancel=threading.Event();tts=HttpTTS('http://fixture','token',gain=3)
                payload=event(b'\0' if kind=='odd' else pcm([100]))
                if kind=='bool_channels':payload['channels']=True
                if kind=='float_rate':payload['sample_rate']=16000.0
                class Response(io.BytesIO):
                    def readline(self,*args):
                        line=super().readline(*args)
                        if kind=='cancel':cancel.set()
                        return line
                with patch.object(tts.opener,'open',return_value=Response((json.dumps(payload)+'\n').encode())):
                    with self.assertRaises((ValueError,RuntimeError)):next(tts.stream('neutral',cancel))
                self.assertFalse(tts.status()[0]['complete']);self.assertEqual(tts.status()[0]['output']['samples'],0)
        tts=HttpTTS('http://fixture','token');body=(json.dumps(event(pcm([100]*9000)))+'\n').encode();cancel=threading.Event()
        with patch.object(tts.opener,'open',return_value=io.BytesIO(body)):
            stream=tts.stream('neutral',cancel);self.assertEqual(len(next(stream)),8192);cancel.set()
            with self.assertRaises(RuntimeError):next(stream)
        self.assertEqual(tts.status()[0]['output']['samples'],4096)

    def test_alsa_capture_subtracts_available_backlog_and_rejects_stale_mapping(self):
        class Lib:
            def snd_pcm_avail_update(self,handle):return 320
            def snd_pcm_readi(self,handle,buffer,max_frames):return 320
            def snd_pcm_htimestamp(self,handle,available,stamp):
                C.cast(available,C.POINTER(C.c_ulong))[0]=self.backlog
                value=C.cast(stamp,C.POINTER(Timespec));value.contents.seconds=10;value.contents.nanoseconds=600000000
                return 0
        capture=AlsaCapture.__new__(AlsaCapture);capture.lib=Lib();capture.handle=None;capture.closed=False;capture.previous_end=None
        capture.lib.backlog=1600
        with patch('reachy_companion.autonomous.alsa_capture.time.monotonic',return_value=10.6):
            value=capture._read(1024)
        self.assertAlmostEqual(value['captured_end'],10.5);self.assertEqual(value['provenance'],'alsa_monotonic_available_position')
        capture.lib.backlog=8192 #512ms backlog cannot be relabelled as a fresh read
        with patch('reachy_companion.autonomous.alsa_capture.time.monotonic',return_value=10.6):
            with self.assertRaises(RuntimeError):capture._read(1024)

    def test_endpoint_bounds_reject_boolean_nan_and_fractional_silence(self):
        for fields in (dict(max_seconds=True),dict(max_seconds=float('nan')),dict(silence_frames=True),dict(silence_frames=30.5)):
            with self.assertRaises(ValueError):ResponseEndpoint(None,**fields)


if __name__=='__main__':unittest.main()
