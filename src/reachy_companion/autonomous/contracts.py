"""Typed authority and bounded projection; wire validation uses the design schema."""
from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path
from uuid import uuid4
from jsonschema import Draft202012Validator, FormatChecker


def uid():
    return str(uuid4())


@lru_cache(maxsize=None)
def validator(name):
    schema = json.loads((Path(__file__).parents[1] / 'assets/autonomous-contracts.json').read_text())
    return Draft202012Validator({**schema, 'oneOf': [{'$ref': '#/$defs/' + name}]},
                               format_checker=FormatChecker())


def validate(name, value):
    validator(name).validate(value)
    return value


def decode(data):
    def reject(value):
        raise ValueError('non-finite JSON')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data, parse_constant=reject, object_pairs_hook=unique)


@dataclass(frozen=True)
class Authority:
    hub_boot_id: str
    compute_boot_id: str
    robot_boot_id: str = 'simulated-robot'
    operator_epoch: int = 0
    microphone_epoch: int = 0
    interaction_epoch: int = 0
    speech_epoch: int = 0

    def wire(self):
        return asdict(self)


@dataclass(frozen=True)
class Binding:
    request_id: str
    authority: Authority
    revision: int
    deadline: float  # hub monotonic seconds, valid only in hub_boot_id
    candidates: tuple[str, ...]
    ready: tuple[str, ...]
    evidence: tuple[str, ...]
    dependencies: tuple[tuple[str, str], ...]


@dataclass
class Sensor:
    sensor_id: str
    summary: str
    captured: float | None
    ttl: float
    availability: str = 'available'

    def view(self, now, muted):
        if muted and self.sensor_id.startswith('audio'):
            return dict(id=self.sensor_id, state='disabled', age_ms=None, summary='')
        age = None if self.captured is None else max(0, int((now - self.captured) * 1000))
        state = self.availability
        if state == 'available':
            state = 'no_data' if age is None else ('ready' if now - self.captured <= self.ttl else 'stale')
        return dict(id=self.sensor_id, state=state, age_ms=age,
                    summary=self.summary if state in ('ready', 'stale') else '')


@dataclass
class Task:
    task_id: str
    attempt_id: str
    input_ref: str
    prompt: str
    authority: Authority
    created: float
    deadline: float
    status: str = 'running'
    result: str | None = None
    expires: float = 0
    kind: str = "main"
