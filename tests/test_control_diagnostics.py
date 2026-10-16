"""Diagnostic sinks cannot alter or retry the client's protected RPCs."""
import json
import unittest
from urllib.error import HTTPError
from reachy_companion.control_diagnostics import trace_guarded_control,trace_operator_reads


class ControlDiagnosticsTests(unittest.TestCase):
    def test_argument_and_result_identity_forwarded_once_without_private_fields(self):
        config=object();expected=object();payload=dict(enabled=False,listen=False,expected_epoch=11,
            owner_id='PRIVATEOWNER',text='PRIVATEBODY');result=object();calls=[];rows=[]
        def rpc(*args,**kwargs):calls.append((args,kwargs));return result
        observed=trace_guarded_control(rpc,rows.append,clock=iter((10,10.25)).__next__)
        self.assertIs(observed(config,'http://PRIVATEHOST','/control/microphone',payload,expected,deadline=99),result)
        self.assertEqual(len(calls),1);self.assertIs(calls[0][0][0],config)
        self.assertIs(calls[0][0][3],payload);self.assertIs(calls[0][0][4],expected)
        self.assertEqual(calls[0][1],dict(deadline=99));self.assertNotIn('PRIVATE',json.dumps(rows))
        self.assertEqual(rows[0]['desired_state'],dict(enabled=False,listen=False))
        self.assertEqual(rows[0]['expected_epoch'],11);self.assertEqual(rows[0]['elapsed_seconds'],.25)

    def test_same_error_rethrown_and_never_retried_or_reflected(self):
        error=RuntimeError('PRIVATE upstream body');calls=[];rows=[]
        def rpc(*args,**kwargs):calls.append(True);raise error
        with self.assertRaises(RuntimeError) as caught:
            trace_guarded_control(rpc,rows.append)(None,None,'/control/motion-policy',{})
        self.assertIs(caught.exception,error);self.assertEqual(len(calls),1)
        self.assertNotIn('PRIVATE',json.dumps(rows));self.assertEqual(rows[0]['exception_class'],'RuntimeError')
        self.assertIsNone(rows[0]['http_status'])

    def test_only_failed_operator_gets_report_typed_http_status(self):
        rows=[];calls=[];error=HTTPError('http://PRIVATE/?token=PRIVATE',503,'PRIVATE',{},None)
        def rpc(*args,**kwargs):calls.append(True);raise error
        traced=trace_operator_reads(rpc,rows.append)
        with self.assertRaises(HTTPError):traced(None,'http://PRIVATE/control/operator?token=PRIVATE')
        with self.assertRaises(HTTPError):traced(None,'http://PRIVATE/other')
        self.assertEqual(len(calls),2);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['http_status'],503)
        self.assertNotIn('PRIVATE',json.dumps(rows))

    def test_sink_failure_preserves_success_and_original_exception(self):
        def sink(row):raise ValueError('sink broke')
        result=object()
        self.assertIs(trace_guarded_control(lambda *a,**k:result,sink)(None,None,'/other',{}),result)
        error=TimeoutError('original')
        def rpc(*args,**kwargs):raise error
        with self.assertRaises(TimeoutError) as caught:trace_guarded_control(rpc,sink)(None,None,'/other',{})
        self.assertIs(caught.exception,error)

    def test_bad_clock_never_blocks_rpc_and_unknown_class_or_payload_stays_private(self):
        class PRIVATECLASS(Exception):pass
        error=PRIVATECLASS('PRIVATE');rows=[];calls=[]
        def rpc(*args,**kwargs):calls.append(True);raise error
        def clock():raise RuntimeError('clock broke')
        with self.assertRaises(PRIVATECLASS):
            trace_guarded_control(rpc,rows.append,clock=clock)(None,None,'/control/microphone',
                dict(enabled='PRIVATE',expected_epoch=True))
        self.assertEqual(calls,[True]);self.assertEqual(rows[0]['exception_class'],'OtherError')
        self.assertIsNone(rows[0]['elapsed_seconds']);self.assertIsNone(rows[0]['expected_epoch'])
        self.assertEqual(rows[0]['desired_state'],{});self.assertNotIn('PRIVATE',json.dumps(rows))

    def test_successful_gets_are_not_logged_and_keyboard_interrupt_propagates(self):
        rows=[];result=object()
        self.assertIs(trace_operator_reads(lambda *a,**k:result,rows.append)(None,'http://example/control/operator'),result)
        self.assertEqual(rows,[])
        def rpc(*args,**kwargs):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):trace_guarded_control(rpc,rows.append)(None,None,'/control/microphone',{})
        self.assertEqual(rows[0]['exception_class'],'KeyboardInterrupt')

    def test_oversize_integer_clock_does_not_replace_rpc(self):
        for readings in ((10**1000,1),(1,10**1000)):
            result=object();rows=[];calls=[]
            def rpc(*a,**k):calls.append(True);return result
            self.assertIs(trace_guarded_control(rpc,rows.append,
                clock=iter(readings).__next__)(None,None,'/control/microphone',{}),result)
            self.assertEqual(calls,[True]);self.assertIsNone(rows[0]['elapsed_seconds'])
            error=TimeoutError('original');calls=[]
            def failed(*a,**k):calls.append(True);raise error
            with self.assertRaises(TimeoutError) as caught:
                trace_guarded_control(failed,rows.append,
                    clock=iter(readings).__next__)(None,None,'/control/microphone',{})
            self.assertIs(caught.exception,error);self.assertEqual(calls,[True])
            self.assertIsNone(rows[-1]['elapsed_seconds'])


if __name__=='__main__':unittest.main()
