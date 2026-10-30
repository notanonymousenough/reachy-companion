"""S4 exact deployed S2 candidate: offline only, including actual POST handlers."""
import ast
import base64
import hashlib
import io
import itertools
import json
import logging
from pathlib import Path
import random
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

import test_alice_format as s2
from test_stream_cleanup_overlay import load

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'tests/fixtures/legacy/s4'
PREIMAGE = 'cfd55a2e930869a6d82b77325fab913d18dae2f42a888ca1e670775edf532681'
CANDIDATE = '4ec7cfe56f7ee5a4b37ac9906a2c467b70983a6437a7840c25416695a5dfd4fd'
REAL_RUN = subprocess.run


def sources():
    old = (EVIDENCE / 'preimage/voice.py').read_bytes()
    new = (EVIDENCE / 'candidate/voice.py').read_bytes()
    assert hashlib.sha256(old).hexdigest() == PREIMAGE
    assert hashlib.sha256(new).hexdigest() == CANDIDATE
    return old, new


class CandidateBehaviorTests(s2.AliceFormatTests):
    """Run every S2 behavioral test against S4, with the same model/TTS fixtures."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        old, new = sources()
        if old != cls.output['voice.py']:
            raise AssertionError('Frozen S2 builder and deployed D4 preimage differ')
        cls.output = {'voice.py': new}
        cls.module = load(new)

    def test_exact_portable_builder_tamper_guards_and_ast_scope(self):
        old, new = sources()
        # Every Pipeline method except the typed raise in prepare is identical.
        # Every HTTP handler except do_POST/stream_reply is identical.
        def outside(source):
            tree = ast.parse(source)
            tree.body = [n for n in tree.body if getattr(n, 'name', '') not in (
                'AliceRejectionReason', 'AlicePhraseRejected', 'validate_alice_phrase')
                and not (isinstance(n, ast.ImportFrom) and n.module == 'enum')]
            class Scope(ast.NodeTransformer):
                def visit_FunctionDef(self, node):
                    if node.name in ('do_POST', 'stream_reply'):
                        return None
                    return self.generic_visit(node)

                def visit_Raise(self, node):
                    if (isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name)
                            and node.exc.func.id == 'AlicePhraseRejected'):
                        node.exc.args = [ast.Constant(value='typed-style-rejection')]
                    return node
            return ast.dump(Scope().visit(tree), include_attributes=False)
        self.assertEqual(outside(old), outside(new))
        # Existing generic error blocks and all normal try paths remain exact.
        def handlers(source):
            tree = ast.parse(source)
            result = []
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef) or fn.name not in ('do_POST', 'stream_reply'):
                    continue
                for tr in ast.walk(fn):
                    if not isinstance(tr, ast.Try):
                        continue
                    tr.handlers = [h for h in tr.handlers if not (
                        isinstance(h.type, ast.Name) and h.type.id == 'AlicePhraseRejected')]
                result.append(ast.dump(fn, include_attributes=False))
            return result
        self.assertEqual(handlers(old), handlers(new))
        with tempfile.TemporaryDirectory() as directory, patch.object(subprocess, 'run', wraps=REAL_RUN):
            work = Path(directory)
            (work / 'voice.py').write_bytes(old)
            for options, expected in (([], new), (['-R'], old)):
                REAL_RUN(['patch', '--batch', '--fuzz=0', '-p1', *options, '-i',
                          str(EVIDENCE / 'patches/voice.py.patch')], cwd=work,
                         check=True, capture_output=True)
                self.assertEqual((work / 'voice.py').read_bytes(), expected)


class TaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        old, new = sources()
        cls.old = load(old)
        cls.module = load(new)

    setUp = s2.AliceFormatTests.setUp

    def test_validator_equivalence_boundary_combinations_and_deterministic_corpus(self):
        cases = [None, 0, True, [], {}, b'Yes.', '', '.', '!!!', '_!', '123!',
                 'Да.\n', 'Да\nверно.', 'Да\tверно.', 'Да\x00верно.',
                 'Алиса,\nДа.', 'Алиса,\tДа.', 'Алиса,\u00a0Да.',
                 'Алиса,  Да.', 'Алиса, Да. ', 'Алиса,', 'Алиса,Да.',
                 'а' * 112 + '.', 'а' * 113 + '.', 'а' * 114 + '.',
                 ' '.join(['да'] * 9) + '.', ' '.join(['да'] * 10) + '.',
                 ' '.join(['да'] * 11) + '.', 'Да, Аlиса.', 'Да, aLiSa.',
                 'Да, АЛИ́СА.', 'Да, Ａｌｉｃｅ.', 'Да, алｉса.',
                 'Алиса, Алиса, да.', 'Вероятность 3.14 процента.']
        for prefix, body, ending, whitespace in itertools.product(
                ('', 'Алиса, ', 'АЛИСА, ', ' Алиса, '),
                ('Да', 'Почему небо синее', 'Да. Ещё', 'Алиса', 'Alisa', 'Да*',
                 'да ' * 10 + 'да', 'а' * 114, '_', '123', 'да\nда'),
                ('', '.', '?', '!', '…', '?!', '。', '..'), ('', ' ', '\n')):
            cases.append(prefix + body + ending + whitespace)
        rng = random.Random(503)
        alphabet = 'ДаАлисаaLiSe, .!?…？؟！。．<>*#`[]{}|_\x00\t\n\u00a0é́'
        cases.extend(''.join(rng.choices(alphabet, k=rng.randrange(0, 140)))
                     for _ in range(3000))
        accepted = rejected = 0
        for text in cases:
            def outcome(module):
                try:
                    return True, module.validate_alice_phrase(text)
                except module.AlicePhraseRejected:
                    return False, None
            before, after = outcome(self.old), outcome(self.module)
            self.assertEqual(before, after)
            accepted += after[0]
            rejected += not after[0]
        self.assertGreaterEqual(accepted, 30)
        self.assertGreater(rejected, 1000)
        type(self).equivalence_counts = dict(total=len(cases), accepted=accepted, rejected=rejected)

    def test_stable_typed_first_failure_reasons_no_phrase_or_lengths(self):
        reason = self.module.AliceRejectionReason
        examples = (
            (None, reason.TEXT_TYPE), (' Да.', reason.EDGE_WHITESPACE),
            ('а' * 113 + '.', reason.CHARACTER_LIMIT),
            ('Да<верно.', reason.FORBIDDEN_SYMBOL), ('Да. Ещё.', reason.SENTENCE_SHAPE),
            ('_!', reason.WORD_COUNT), (' '.join(['да'] * 11) + '.', reason.WORD_COUNT),
            ('Да, Аlиса.', reason.WAKE_NAME),
            (' ' + 'а' * 121 + '<', reason.EDGE_WHITESPACE),
            ('а' * 121 + '<', reason.CHARACTER_LIMIT),
            ('Да<', reason.FORBIDDEN_SYMBOL),
            ('Алиса, Алиса. Ещё.', reason.SENTENCE_SHAPE))
        for text, expected in examples:
            with self.assertRaises(self.module.AlicePhraseRejected) as ctx:
                self.module.validate_alice_phrase(text)
            self.assertIs(ctx.exception.reason, expected)
            self.assertEqual(str(ctx.exception), 'alice_phrase_rejected:' + expected.value)
            self.assertEqual(ctx.exception.args, (str(ctx.exception),))
            self.assertEqual(vars(ctx.exception), {'reason': expected})
        self.assertEqual(self.module.validate_alice_phrase('а' * 112 + '.'), 'а' * 112 + '.')
        for untyped in ('word_count', 'PRIVATE_REPLY', None, 3, {'reason': 'word_count'}):
            with self.assertRaisesRegex(TypeError, '^Typed Alice rejection reason required$'):
                self.module.AlicePhraseRejected(untyped)
        # The pre-existing in-word style guard is typed, too.
        with patch('reachy_companion.brains.answer', return_value='По<emotion=joy>чему так?') as model:
            with self.assertRaises(self.module.AlicePhraseRejected) as ctx:
                list(self.p.stream({'text': 'Question'}, '/text'))
        self.assertIs(ctx.exception.reason, reason.STYLE_WORD_BOUNDARY)
        model.assert_called_once()
        self.assertEqual(self.spoken, [])

    def handler(self, path, payload):
        # Capture the real nested Handler without constructing a socket/server.
        captured = []
        def server(address, handler):
            captured.append(handler)
            return types.SimpleNamespace(server_address=address, serve_forever=lambda: None)
        with patch.object(self.module, 'Pipeline', return_value=self.p), \
                patch.object(self.module, 'ThreadingHTTPServer', side_effect=server), \
                patch('reachy_companion.logging_utils.configure'):
            self.module.main(self.config, worker=True)
        h = captured[0].__new__(captured[0])
        h.path = path
        raw = json.dumps(payload).encode()
        h.headers = {'Content-Length': str(len(raw)), 'Authorization': 'Bearer ' + self.config.token}
        h.rfile = io.BytesIO(raw)
        h.wfile = io.BytesIO()
        h.statuses, h.output_headers = [], []
        h.send_response = h.statuses.append
        h.send_header = lambda *value: h.output_headers.append(value)
        h.end_headers = lambda: None
        return h

    def rejection(self, h, reason, *, sent=False):
        with self.assertLogs(self.module.LOG, level=logging.WARNING) as records:
            h.do_POST()
        self.assertEqual(h.statuses, [200] if sent else [422])
        raw = h.wfile.getvalue()
        row = json.loads(raw.splitlines()[-1]) if sent else json.loads(raw)
        self.assertEqual(row, dict(ok=False, error='alice_phrase_rejected', reason=reason,
                                   **({'type': 'error'} if sent else {})))
        self.assertLessEqual(len(json.dumps(row).encode()), 128)
        self.assertEqual(len(records.records), 1)
        record = records.records[0]
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.stack_info)
        self.assertEqual(record.getMessage(),
                         'alice_phrase_rejected reason=%s headers_sent=%s' % (reason, sent))
        self.assertLessEqual(len(record.getMessage()), 96)
        return raw, records.output

    def test_actual_post_rejection_422_before_headers_tts_events_history_for_all_routes(self):
        for prefix in ('', '/stream'):
            for route in ('/text', '/turn', '/say'):
                self.p.sessions, self.p.agent_sessions = {}, {}
                self.p.last_turn = None
                self.spoken.clear()
                payload = dict(text='PRIVATE_REQUEST', session='PRIVATE_SESSION',
                               pcm_base64=base64.b64encode(b'PRIVATE_PCM').decode())
                if route == '/say':
                    payload['text'] = 'PRIVATE_REPLY without terminal'
                h = self.handler(prefix + route, payload)
                with patch('reachy_companion.brains.answer',
                           return_value='PRIVATE_REPLY without terminal') as model:
                    raw, logs = self.rejection(h, 'sentence_shape')
                self.assertEqual(model.call_count, 0 if route == '/say' else 1)
                self.assertEqual(self.spoken, [])
                self.assertEqual(self.p.sessions, {})
                self.assertIsNone(self.p.last_turn)
                self.assertEqual(self.p.phase, 'idle')
                self.assertFalse(self.p.lock.locked())
                self.assertNotIn(b'PRIVATE_', raw)
                self.assertNotIn('PRIVATE_', ''.join(logs))
                self.assertIn(('Content-Type', 'application/json; charset=utf-8'), h.output_headers)
                self.assertIn(('Content-Length', str(len(raw))), h.output_headers)

    def test_each_enum_has_bounded_http_and_log_metadata_even_with_secret_exception_context(self):
        for reason in self.module.AliceRejectionReason:
            for route, method in (('/text', 'turn'), ('/stream/text', 'stream')):
                def rejected(*args):
                    try:
                        raise RuntimeError('PRIVATE_EXCEPTION_CONTEXT')
                    except RuntimeError:
                        raise self.module.AlicePhraseRejected(reason)
                    yield  # stream fixture remains lazy, like real Pipeline.stream
                if method == 'turn':
                    def rejected(*args):
                        try:
                            raise RuntimeError('PRIVATE_EXCEPTION_CONTEXT')
                        except RuntimeError:
                            raise self.module.AlicePhraseRejected(reason)
                h = self.handler(route, {'text': 'PRIVATE_REQUEST'})
                with patch.object(self.p, method, side_effect=rejected):
                    raw, logs = self.rejection(h, reason.value)
                self.assertNotIn(b'PRIVATE_', raw)
                self.assertNotIn('PRIVATE_', ''.join(logs))

    def test_late_typed_rejection_is_error_event_never_second_http_status_and_closes_iterator(self):
        closed = []
        def stream(*args):
            try:
                yield {'type': 'reply', 'reply': 'Accepted fixture.'}
                raise self.module.AlicePhraseRejected(self.module.AliceRejectionReason.WORD_COUNT)
            finally:
                closed.append(True)
        h = self.handler('/stream/text', {'text': 'Question'})
        with patch.object(self.p, 'stream', side_effect=stream):
            self.rejection(h, 'word_count', sent=True)
        self.assertEqual(closed, [True])
        self.assertEqual(self.spoken, [])

    def test_unexpected_backend_stream_503_unchanged_and_worker_only_scope(self):
        old_pipeline_class = self.p.__class__
        outcomes = []
        for module in (self.old, self.module):
            self.p.__class__ = module.Pipeline
            candidate_module = self.module
            try:
                self.module = module
                for path in ('/text', '/stream/text'):
                    h = self.handler(path, {'text': 'Question'})
                    with patch('reachy_companion.brains.answer', side_effect=RuntimeError('Backend unavailable')), \
                            self.assertLogs(module.LOG, level=logging.ERROR) as records:
                        h.do_POST()
                    self.assertEqual(h.statuses, [503])
                    if path.startswith('/stream'):
                        self.assertEqual(json.loads(h.wfile.getvalue()), {'error': 'Worker stream failed'})
                    outcomes.append((path, h.statuses, h.wfile.getvalue(),
                                     [r.getMessage() for r in records.records]))
                    self.assertEqual(self.spoken, [])
                    self.assertFalse(self.p.lock.locked())
            finally:
                self.module = candidate_module
        self.p.__class__ = old_pipeline_class
        self.assertEqual(outcomes[:2], outcomes[2:])


if __name__ == '__main__':
    unittest.main()
