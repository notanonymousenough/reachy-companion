"""Finite design-only checks. No network, models, services, device I/O or writes.
Dependency: jsonschema. Run from any directory with the review temp Python venv.
This is a contract verifier, not the robot's future semantic guard.
"""
import copy
import json
import re
from datetime import datetime
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
checker = FormatChecker()

@checker.checks("date-time")
def utc_time(value):
    if not isinstance(value, str):
        return True  # type validated by schema
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False

def load(path):
    def reject_nonfinite(value):
        raise ValueError("Non-finite JSON: " + value)
    return json.loads(path.read_text(), parse_constant=reject_nonfinite)

def semantic_shape(value):
    if isinstance(value, dict):
        if "start_at" in value and "end_at" in value:
            assert value["start_at"] <= value["end_at"], "reversed sample interval"
        if "deadline_at" in value and "created_at" in value:
            begin = datetime.fromisoformat(value["created_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(value["deadline_at"].replace("Z", "+00:00"))
            assert end > begin, "deadline before creation"
            assert value["soft_timeout_ms"] <= (end - begin).total_seconds() * 1000
        if "stable_prefix" in value:
            assert value["text"].startswith(value["stable_prefix"])
        if "first" in value and "last" in value:
            assert value["first"] <= value["last"]
        if "activity" in value and "causality" in value:
            assert value["interaction_epoch"] == value["causality"]["interaction_epoch"]
        for child in value.values():
            semantic_shape(child)
    elif isinstance(value, list):
        for child in value:
            semantic_shape(child)

def same_action_authority(causality, current):
    fields = ("hub_boot_id", "compute_boot_id", "robot_boot_id", "operator_epoch",
              "microphone_epoch", "interaction_epoch", "speech_epoch")
    return all(causality[k] == current[k] for k in fields)

def silence_update(since, now, healthy=True, external_speech=False):
    # Conceptual hub-monotonic trace; unknown coverage invalidates the timer.
    if not healthy or external_speech:
        return None
    return now if since is None else since

def resume_allowed(state, now, timeout):
    return (state["healthy"] and state["since"] is not None
            and now - state["since"] >= timeout
            and state["stt"] in ("empty", "self_echo")
            and not state["muted"] and not state["confirmed_turn"]
            and state["authority_current"] and state["cursor_verified"]
            and state["plan_live"])

def main_budget_valid(profile, actual):
    parts = ("text_input_cap_tokens", "vision_input_cap_tokens", "template_cap_tokens")
    reserves = profile["output_reserved_tokens"] + profile["safety_reserved_tokens"]
    return (all(isinstance(actual[k], int) and 0 <= actual[k] <= profile[k] for k in parts)
            and sum(actual[k] for k in parts) + reserves <= profile["runtime_context_tokens"])

def validated_late_final(state, confirmed_external_turn):
    if confirmed_external_turn:
        return {**state, "confirmed_turn": True, "authority_current": False, "plan_live": False}
    return state

def main():
    schema = load(ROOT / "schemas/contracts.schema.json")
    caps = load(ROOT / "schemas/capabilities.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(caps)
    validator = Draft202012Validator(schema, format_checker=checker)
    fixtures = sorted((ROOT / "examples").glob("*.json"))
    for path in fixtures:
        value = load(path)
        validator.validate(value)
        expected = path.stem.split("--")[0]
        assert expected in schema["$defs"], path
        direct = {**schema, "oneOf": [{"$ref": "#/$defs/" + expected}]}
        Draft202012Validator(direct, format_checker=checker).validate(value)
        semantic_shape(value)
    negative = 0
    def reject(value):
        nonlocal negative
        assert not validator.is_valid(value), value
        negative += 1
    d = load(ROOT / "examples/Decision.json")
    for key, value in [("activity", "fake_charge"), ("expires_at", "2026-10-32T12:00:00Z"),
                       ("functions", [{"capability_id": "x", "arguments": {}, "intent_id": "x", "grant": "root"}])]:
        bad = copy.deepcopy(d); bad[key] = value; reject(bad)
    bad = load(ROOT / "examples/SensorEvent.json"); bad["availability"] = "disabled"; reject(bad)
    reject({"a": "wait", "why": "ok", "epoch": 999})
    reject({"a": "converse", "why": "ok", "commit": "p1", "say": "double speech"})
    bad = load(ROOT / "examples/AnalysisProposal.json"); bad["patches"][0]["document_type"] = "policy"; reject(bad)
    bad = load(ROOT / "examples/AnalysisProposal.json"); bad["patches"][0].update(document_type="personality", item=None, trait_deltas={"curiosity": 0.5}); reject(bad)
    capability_validator = Draft202012Validator(caps)
    for value in [
        {"capability_id":"shell.sandbox","arguments":{"template_id":"sh -c","arguments":{"relative_path":None}}},
        {"capability_id":"shell.sandbox","arguments":{"template_id":"sandbox.read_text","arguments":{"relative_path":"../secrets"}}},
        {"capability_id":"web.search","arguments":{"query":"test","max_results":999}}]:
        assert not capability_validator.is_valid(value); negative += 1
    # Cross-document ready->choice->binding->canonical commit path.
    ready = load(ROOT / "examples/DecisionInput--ready.json")
    fast_view = load(ROOT / "examples/FastView--ready.json")
    choice = load(ROOT / "examples/FastChoice--commit.json")
    binding = load(ROOT / "examples/RequestBinding.json")
    decision = load(ROOT / "examples/Decision--commit.json")
    proposal = load(ROOT / "examples/MainProposal.json")
    segment = load(ROOT / "examples/MainSegment.json")
    aliases = {a["alias"]: a for a in binding["aliases"]}
    target = aliases[choice["commit"]]["target_id"]
    assert target == proposal["proposal_id"] == ready["ready_proposals"][0]["proposal_id"]
    assert fast_view["ready"][0]["alias"] == choice["commit"]
    assert decision["request_id"] == binding["request_id"] == ready["request_id"]
    assert decision["binding_id"] == binding["binding_id"]
    assert decision["based_on_revision"] == binding["snapshot_revision"] == ready["state_revision"]
    assert decision["functions"][0]["arguments"]["proposal_id"] == target
    assert proposal["task_id"] == segment["task_id"] == load(ROOT / "examples/Task--main.json")["id"]
    assert decision["evidence_ids"] == proposal["supporting_ids"]
    assert proposal["speech_segments"][0] == segment["speech"]
    assert ready["snapshot_at"] < binding["result_deadline_at"] <= proposal["expires_at"]
    assert same_action_authority(proposal["causality"], binding["causality"])
    causality = proposal["causality"]
    traces = 1
    for field in ("hub_boot_id", "compute_boot_id", "robot_boot_id", "operator_epoch", "microphone_epoch", "interaction_epoch", "speech_epoch"):
        current = copy.deepcopy(causality)
        current[field] = current[field] + 1 if isinstance(current[field], int) else current[field] + "-new"
        assert not same_action_authority(causality, current), field
        traces += 1
    task = load(ROOT / "examples/Task.json"); result = load(ROOT / "examples/TaskResult.json")
    assert result["attempt_id"] == task["current_attempt_id"]
    assert "old-attempt" != task["current_attempt_id"]; traces += 1
    # Suspected pause without confirmed turn may resume; confirmed/mute cannot.
    current = copy.deepcopy(causality)
    assert same_action_authority(causality, current); traces += 1
    for field in ("interaction_epoch", "microphone_epoch"):
        current = copy.deepcopy(causality); current[field] += 1
        assert not same_action_authority(causality, current); traces += 1
    links = 0
    for path in ROOT.glob("*.md"):
        text = path.read_text()
        assert text.count("```") % 2 == 0, path
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if not target.startswith(("http:", "https:", "#")):
                assert (path.parent / target.split("#")[0]).exists(), (path, target)
                links += 1
    config = load(ROOT / "design-config.example.json")
    assert config["cycle"]["fast_output_cap_tokens"] == 192
    timeout = config["behavior"]["interruption_silence_timeout_ms"]
    assert timeout == 3000
    state = dict(healthy=True, since=1000, stt="empty", muted=False,
                 confirmed_turn=False, authority_current=True, cursor_verified=True, plan_live=True)
    interruption_traces = 0
    def check_resume(candidate, now, expected):
        nonlocal interruption_traces
        assert resume_allowed(candidate, now, timeout) == expected
        interruption_traces += 1
    check_resume(state, 3999, False)
    check_resume(state, 4000, True)
    check_resume({**state, "stt": "self_echo"}, 4000, True)
    for stt in ("pending", "queued", "running", "error", "no_data", "offline"):
        check_resume({**state, "stt": stt}, 6000, False)
    check_resume(state, 6000, True)  # STT settled empty after >3s, healthy coverage retained
    for key in ("muted", "confirmed_turn"):
        check_resume({**state, key: True}, 4000, False)
    for key in ("healthy", "authority_current", "cursor_verified", "plan_live"):
        check_resume({**state, key: False}, 4000, False)
    since = silence_update(state["since"], 3500, external_speech=True)
    since = silence_update(since, 3600)  # speech ended, including unintelligible speech
    check_resume({**state, "since": since}, 6599, False)
    check_resume({**state, "since": since}, 6600, True)
    since = silence_update(state["since"], 3500, healthy=False)
    check_resume({**state, "since": since, "healthy": False}, 7000, False)
    since = silence_update(since, 8000)  # restored hearing starts fresh coverage
    check_resume({**state, "since": since}, 10999, False)
    check_resume({**state, "since": since}, 11000, True)
    check_resume(validated_late_final(state, True), 6000, False)
    # Last case: validated late final revokes playback authority even after eligible resume.
    budget_checks = 0
    profiles = config["models"]["main_context_profiles"]
    assert config["models"]["main_context_tokens"] == profiles[config["models"]["main_context_profile"]]["runtime_context_tokens"]
    for name, context in (("baseline_4k", 4096), ("option_8k", 8192), ("measurement_32k", 32768)):
        profile = profiles[name]
        assert profile["runtime_context_tokens"] == context
        assert profile["output_reserved_tokens"] == 512 and profile["safety_reserved_tokens"] == 256
        assert profile["measurement_required"] == (name != "baseline_4k")
        actual = {k: profile[k] for k in ("text_input_cap_tokens", "vision_input_cap_tokens", "template_cap_tokens")}
        assert main_budget_valid(profile, actual); budget_checks += 1
        for key in actual:
            assert not main_budget_valid(profile, {**actual, key: actual[key] + 1})
            budget_checks += 1
        assert not main_budget_valid({**profile, "runtime_context_tokens": context - 1}, actual)
        budget_checks += 1
        assert not main_budget_valid(profile, {**actual, "vision_input_cap_tokens": None})
        budget_checks += 1
    print(f"PASS: 2 schemas, {len(fixtures)} fixtures, {negative} negative cases, {traces} finite authority traces, {interruption_traces} interruption traces, {budget_checks} context budget checks, {links} local links")
    print("No hardware/model execution. Cryptographic signatures, JCS and timing were not tested.")

if __name__ == "__main__":
    main()
