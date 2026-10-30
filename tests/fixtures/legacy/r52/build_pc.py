"""Adapt exact installed worker, retaining its non-mode behavior and old clients."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent / 'baseline/pc-voice.py'
EXPECTED = '224ff166401f7842deeec96c59f08585232bee971306c33e02c9fe45c1059b71'


def candidate():
    raw = BASE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED, 'Installed producer preimage changed'
    source = raw.decode()
    helpers = (ROOT/'src/reachy_companion/conversation_context.py').read_text()
    source = source.replace('class Pipeline:', helpers + '\n\nclass Pipeline:', 1)
    source = source.replace('*, reply_constraints=None, alice_short=False):',
                            '*, reply_constraints=None, alice_short=False, conversation_mode=None):', 1)
    source = source.replace("system_prompt = self.config['llm']['system_prompt']",
                            "system_prompt = mode_prompt(self.config['llm']['system_prompt'], conversation_mode)", 1)
    # Every ingress, including acknowledgement, captures the same enum.
    for signature in ('def prepare(self, payload, path, recognized_text=None, answer_result=None):',
                      'def turn(self, payload, path):', 'def stream(self, payload, path):'):
        assert source.count(signature) == 1
        source = source.replace(signature, signature + '\n        payload = mode_payload(payload)', 1)
    session_check = "            raise ValueError('Invalid session')"
    # prepare's validated session and stream acknowledgement's validated session.
    source = source.replace(session_check + '\n        self.check_robot()',
                            session_check + "\n        session = mode_session(session, payload.get('conversation_mode'))\n        self.check_robot()", 1)
    source = source.replace(session_check + "\n                    self.phase = 'thinking'",
                            session_check + "\n                    session = mode_session(session, payload.get('conversation_mode'))\n                    self.phase = 'thinking'", 1)
    source = source.replace("reply_constraints=reply_constraints,alice_short=True)",
                            "reply_constraints=reply_constraints,alice_short=True,**mode_options)", 1)
    source = source.replace("reply_constraints=reply_constraints)\n                                   if reply_constraints",
                            "reply_constraints=reply_constraints,**mode_options)\n                                   if reply_constraints", 1)
    source = source.replace("else self.answer(text,session,payload.get('previous_reply_interrupted',False))))",
                            "else self.answer(text,session,payload.get('previous_reply_interrupted',False),**mode_options)))", 1)
    source = source.replace("        pending = None\n        command = None",
                            "        mode_options = {} if payload.get('conversation_mode') is None else dict(conversation_mode=payload['conversation_mode'])\n        pending = None\n        command = None", 1)
    source = source.replace("future = executor.submit(self.answer, recognized, session, payload.get('previous_reply_interrupted', False))",
                            "future = executor.submit(self.answer, recognized, session, payload.get('previous_reply_interrupted', False), **({} if payload.get('conversation_mode') is None else dict(conversation_mode=payload['conversation_mode'])))", 1)
    ast.parse(source)
    return source


if __name__ == '__main__':
    target = Path(__file__).resolve().parent/'candidate/voice.py'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(candidate())
    print(json.dumps(dict(preimage_sha256=EXPECTED,candidate_sha256=hashlib.sha256(target.read_bytes()).hexdigest())))
