import importlib.util
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'deploy/autonomous'))
try:
    spec = importlib.util.spec_from_file_location('vision_fixture_probe', ROOT/'deploy/autonomous/vision_fixture_probe.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
finally: sys.path.pop(0)


class VisionFixtureTests(unittest.TestCase):
    def execute(self, low_headroom):
        cancelled = threading.Event()
        result = SimpleNamespace(parsed=dict(left_color='blue', left_shape='circle', right_color='red', right_shape='square'),
                                 stats=SimpleNamespace(stop_reason='eosFound', predicted_tokens_count=30, prompt_tokens_count=108))
        class Stream:
            def __iter__(self):
                if low_headroom: cancelled.wait(2)
                return iter(())
            def result(self): return result
            def cancel(self): cancelled.set()
        class Handle:
            def get_info(self): return SimpleNamespace(identifier='main', instance_reference='exact', vision=True)
            def respond_stream(self, chat, **kwargs):
                self_test.assertEqual(kwargs['config']['maxTokens'],96)
                self_test.assertEqual(kwargs['config']['contextOverflowPolicy'],'stopAtLimit')
                return Stream()
        handle = Handle()
        class Client:
            def __init__(self, *args):
                self.llm = SimpleNamespace(list_loaded=lambda:[handle])
                self.files = SimpleNamespace(prepare_image=self.prepare)
            def prepare(self, image):
                self_test.assertIsInstance(image,bytes)
                self_test.assertLess(len(image),2048)
                return 'synthetic-only'
            def __enter__(self): return self
            def __exit__(self,*args): pass
        class Chat:
            def add_user_message(self, prompt, **kwargs):
                self_test.assertEqual(kwargs['images'],['synthetic-only'])
        self_test = self
        identity = dict(instance_reference='exact')
        initial = dict(uuid='GPU-one', free_mib=1500)
        samples = [initial, dict(uuid='GPU-one',free_mib=400), initial] if low_headroom else [initial,initial]
        report = {}
        with patch.dict(sys.modules, lmstudio=SimpleNamespace(Client=Client,Chat=Chat)), \
             patch.object(probe,'load',return_value={'models':{'main':{'id':'main','base_url':'http://localhost:1234'}}}), \
             patch.object(probe,'main_identity',return_value=identity), patch.object(probe,'gpu_sample',side_effect=samples):
            probe.run_fixture(SimpleNamespace(config=Path('unused')), report)
        self.assertTrue(report['main_preserved'])
        self.assertTrue(report['prediction_drained'])
        self.assertFalse(report['production_camera_admitted'])
        self.assertFalse(report['effective_image_token_cap_verified'])
        self.assertEqual(cancelled.is_set(),low_headroom)
        self.assertEqual(report['accepted'],not low_headroom)
        self.assertEqual(report['image_requests'],1)
        self.assertEqual(report['model_load_calls'],0)
        if low_headroom: self.assertEqual(report['abort_reason'],'gpu_headroom')

    def test_exact_existing_handle_and_empirical_token_receipt(self): self.execute(False)
    def test_low_vram_cancels_only_owned_prediction_and_never_accepts_its_result(self): self.execute(True)


if __name__ == '__main__': unittest.main()
