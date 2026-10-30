import copy
import threading
import time
import unittest
from reachy_companion.autonomous.stock_motion_adapter import StockMotionAdapter


class Hub:
    boot_id = 'controller-session'
    stock_unknown = False
    def __init__(self):
        self.actual = dict(agent_boot_id='agent', microphone_epoch=3,
                           microphone_enabled=True, expression_version=5,
                           motion_policy=dict(epoch=2, motor_enabled=True, quiet=False, privacy_all=False))
        self.calls = []
    def stock_selected(self): return True
    def operator_proxy(self): return copy.deepcopy(self.actual), time.monotonic()
    def expression(self, payload):
        self.calls.append(payload)
        return dict(ok=True, steps_observed=2, pose_verified=False, hard_stop_certified=False)


class StockMotionTests(unittest.TestCase):
    def proposal(self, adapter):
        return dict(request_id='request', motion='attentive', deadline=time.monotonic()+.5,
                    actual_binding=adapter.refresh()['binding'])

    def test_stock_profile_and_bounded_recognition_deadline_load(self):
        import json
        import tempfile
        from pathlib import Path
        from reachy_companion.autonomous.config import load
        root=Path(__file__).resolve().parents[1]
        data=json.loads((root/'config.autonomous.normal.example.json').read_text())
        data['actuators']='bounded_stock';data['motion']['enabled']=True
        data['production']['stt_deadline_s']=8
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json'
            path.write_text(json.dumps(data));self.assertEqual(load(path)['production']['stt_deadline_s'],8)
            for invalid in (True,0,16,float('inf')):
                data['production']['stt_deadline_s']=invalid;path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):load(path)

    def test_real_completion_receipt_and_cooldown(self):
        hub=Hub();adapter=StockMotionAdapter(hub)
        result=adapter.execute(self.proposal(adapter))
        self.assertTrue(result['accepted'])
        self.assertFalse(result['hard_stop_certified'])
        self.assertFalse(adapter.refresh()['motion_allowed'])
        self.assertEqual(hub.calls[0]['operator_binding']['expression_version'],5)
        self.assertEqual(len(hub.calls[0]['steps']),2)
        self.assertTrue(adapter.close())

    def test_permission_change_prevents_dispatch(self):
        for field in ('quiet','privacy_all','motor_enabled'):
            hub=Hub();adapter=StockMotionAdapter(hub);proposal=self.proposal(adapter)
            hub.actual['motion_policy'][field] = field != 'motor_enabled'
            self.assertFalse(adapter.execute(proposal)['accepted'])
            self.assertEqual(hub.calls,[])

    def test_epoch_change_and_expired_proposal_prevent_dispatch(self):
        for expired in (True,False):
            hub=Hub();adapter=StockMotionAdapter(hub);proposal=self.proposal(adapter)
            if expired:proposal['deadline']=time.monotonic()-1
            else:hub.actual['microphone_epoch']+=1
            self.assertFalse(adapter.execute(proposal)['accepted'])
            self.assertEqual(hub.calls,[])

    def test_close_cancels_active_owned_lane_and_retains_unknown(self):
        hub=Hub();adapter=StockMotionAdapter(hub);proposal=self.proposal(adapter)
        entered=threading.Event()
        def expression(payload):
            entered.set();adapter.cancel.wait(1);hub.stock_unknown=True
            raise RuntimeError('Unknown stop')
        hub.expression=expression
        worker=threading.Thread(target=adapter.execute,args=(proposal,));worker.start()
        self.assertTrue(entered.wait(1));self.assertFalse(adapter.close());worker.join(1)
        self.assertFalse(adapter.status()['stop_known'])
        self.assertFalse(adapter.refresh()['motion_allowed'])
