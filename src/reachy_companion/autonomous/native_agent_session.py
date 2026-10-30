"""Native Agent observer: finite by default; explicit observation-only service."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import threading
import time

from .audio_session_control import create_server
from .companion_session import session_context
from .config import load
from .native_agent import GoalClockNativeAgent, NativeAgent, NativeClient, NativeScheduler
from .runtime import Job, RemoteGateway


class NativeGateway(RemoteGateway):
    def call(self, path, payload=None):
        if path == '/main': raise ValueError('Normal Agent exclusively owns main/reply')
        result = super().call(path, payload)
        if path == '/health' and result.get('conversation_owner') != 'native_agent':
            raise ValueError('Gateway must use the same native_agent profile')
        return result

    def main(self, task):
        raise ValueError('Normal Agent exclusively owns main/reply')


def occupied(scheduler, health_job=None):
    result = {name: bool(getattr(scheduler, name+'_job') and not getattr(scheduler, name+'_job').future.done())
        for name in ('fast', 'main', 'context', 'context_revoke', 'context_terminal')}
    result.update(scheduler.native.busy())
    result['health'] = bool(health_job and not health_job.future.done())
    return result


def validate_lifecycle(config, *, service=False, duration=60, allow_stock=False, allow_camera=False):
    goal_clock = config.get('native_agent', {}).get('stock_profile') == 'finite_goal_clock'
    if goal_clock and (service or not allow_stock or allow_camera or config.get('context', {}).get('enabled')):
        raise ValueError('Goal/clock stock requires explicit finite arm without context/camera/service')
    if service:
        if (duration is not None or allow_stock or allow_camera
                or config.get('context', {}).get('enabled')
                or config['models']['main'].get('base_url') is not None
                or any(config.get(role, {}).get('enabled') for role in ('speech', 'motion', 'workflows'))):
            raise ValueError('Service requires observation only, no duration/context/main/speech/motion/workflows/stock')
    elif type(duration) not in (int, float) or not math.isfinite(duration) or not 1 <= duration <= 180:
        raise ValueError('Finite native window 1..180 seconds')


class MetadataSnapshots:
    """Two bounded metadata snapshots, replaced atomically; never append content logs."""
    def __init__(self, path):
        self.path = path
        self.next_write = 0

    def write(self, value, *, force=False):
        now = time.monotonic()
        if not force and now < self.next_write: return
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        if len(raw) > 1024*1024: raise ValueError('Metadata snapshot cap')
        temporary = self.path.with_name(self.path.name+'.tmp')
        previous = self.path.with_name(self.path.name+'.previous')
        with temporary.open('wb') as handle:
            os.chmod(temporary, 0o600)
            handle.write(raw)
        if self.path.exists(): os.replace(self.path, previous)
        os.replace(temporary, self.path)
        self.next_write = now+5


def run_native_session(scheduler, stop, duration, publish, *, service=False):
    validate_lifecycle(scheduler.config, service=service, duration=duration,
                       allow_stock=scheduler.native.allow_stock)
    native = scheduler.native
    # /stop and signals close the send predicate immediately, before the loop
    # notices the Event. This is a terminal local arm disable, never durable OFF
    # attestation; server microphone/policy disable remains the durable fence.
    if isinstance(native, GoalClockNativeAgent): native.stop_requested = stop.is_set
    started = time.monotonic(); health_job = None; next_health = 0; last_health = started
    reason = 'duration'; errors = []; observed = False
    try:
        while not stop.is_set() and (service or time.monotonic()-started < duration):
            now = time.monotonic()
            if health_job and health_job.future.done():
                health = health_job.future.result(); health_job = None
                if (health.get('compute_boot_id') != scheduler.state.authority.compute_boot_id
                        or health.get('conversation_owner') != 'native_agent' or health.get('quarantined')):
                    raise ValueError('Compute authority changed/UNKNOWN; no reconnect')
                last_health = now
            if now-last_health >= .5: raise TimeoutError('Compute health expired')
            if not health_job and now >= next_health:
                health_job = Job(scheduler.gateway.call, '/health'); next_health = now+.2
            scheduler.advance(now)
            if native.withdrawn: reason = 'native_withdrawn'; break
            observed = observed or native.latest is not None
            publish(dict(stage='OBSERVATION_UNAVAILABLE' if native.unavailable else 'ACTIVE' if native.latest else 'OBSERVING',
                         observation=native.observation_report(now), elapsed_s=now-started,
                         lifecycle='service' if service else 'finite', accepted=False,
                         counts=dict(scheduler.state.counts), execution_busy=occupied(scheduler, health_job)))
            stop.wait(.005)
        if stop.is_set(): reason = 'controller_stop'
    except BaseException as exc:
        reason = 'runtime_error'; errors.append(type(exc).__name__)
    finally:
        stop.set()
        try: scheduler.close()
        except BaseException as exc: errors.append(type(exc).__name__)
        deadline = time.monotonic()+1.5
        while time.monotonic() < deadline and any(occupied(scheduler, health_job).values()):
            time.sleep(.005)
        compute_after = None
        # A finished local HTTP future alone cannot certify remote inference idle.
        # Never replace an occupied health slot or retry an unknown model call.
        if health_job is None or health_job.future.done():
            if health_job:
                try: health_job.future.result()
                except Exception as exc: errors.append(type(exc).__name__)
            health_job = Job(scheduler.gateway.call, '/health')
            deadline = time.monotonic()+.5
            while not health_job.future.done() and time.monotonic() < deadline: time.sleep(.005)
            if health_job.future.done():
                try: compute_after = health_job.future.result()
                except Exception as exc: errors.append(type(exc).__name__)
        # Collect a finished stock job even after local admission is closed.
        if native.stock_job and native.stock_job.future.done():
            try: native.stock_receipt = native.stock_job.future.result()
            except Exception as exc:
                native.stock_unknown = True
                native.stock_receipt = dict(completion='UNKNOWN', error_class=type(exc).__name__)
                native.revoke('stock_outcome_UNKNOWN')
        context_receipt = None
        if scheduler.context_terminal_job and scheduler.context_terminal_job.future.done():
            try: context_receipt = scheduler.context_terminal_job.future.result()
            except Exception as exc: errors.append(type(exc).__name__)
        context_ok = not scheduler.config.get('context', {}).get('enabled') or (
            context_receipt is not None and context_receipt.get('output', {}).get('terminal') is True
            and context_receipt.get('output', {}).get('revoked') is True)
        busy = occupied(scheduler, health_job)
        compute_ok = bool(compute_after and compute_after.get('compute_boot_id') == scheduler.state.authority.compute_boot_id
            and compute_after.get('conversation_owner') == 'native_agent' and compute_after.get('quarantined') == []
            and compute_after.get('busy') == dict(fast=False, main=False))
        cleanup = not errors and not any(busy.values()) and context_ok and compute_ok and not native.stock_unknown
        goal_clock = isinstance(native, GoalClockNativeAgent)
        minimum_decisions = 1 if goal_clock else 10
        decisions_ok = scheduler.state.counts['decision_accepted'] >= minimum_decisions
        stock_observed = bool(native.stock_receipt and native.stock_receipt.get('completion') == 'observed')
        report = dict(mode='native_agent', lifecycle='service' if service else 'finite',
            accepted=observed and cleanup and decisions_ok and not native.withdrawn and (goal_clock or native.gap_count == 0)
            and (not native.allow_stock or stock_observed) and reason in ('duration', 'controller_stop'),
            stock_profile='finite_goal_clock' if isinstance(native, GoalClockNativeAgent) else 'r5_pcm',
            minimum_accepted_decisions=minimum_decisions, stock_dispatch_observed=stock_observed,
            continuous_acceptance=False, live_acceptance=False, reason=reason, errors=errors,
            elapsed_s=time.monotonic()-started, cleanup_verified=cleanup, execution_busy=busy,
            compute_after=compute_after,
            native_withdrawn=native.withdrawn, native_polls=native.polls,
            observation=native.observation_report(time.monotonic()),
            context_closed_after_gap=scheduler.context_closed_after_gap,
            invalidated_decisions=scheduler.state.counts['native_decision_invalidated'],
            discarded_decisions=scheduler.state.counts['native_decision_discarded'],
            native_status=native.latest, stock=native.stock_receipt, stock_used=native.stock_used,
            stock_unknown=native.stock_unknown, context_terminal_revoke=context_receipt,
            counts=dict(scheduler.state.counts),
            decisions=[dict(request_id=row['request_id'], activity=row['activity'], at=row['at'])
                for row in scheduler.state.ledger if row['kind']=='decision_accepted'],
            capture_owner='existing_normal_agent', conversation_owner='existing_normal_agent',
            scheduler_speech_enabled=False, raw_audio_retained=False, transcripts_retained=False,
            normal_agent_stopped=False)
        report['decision_history_cap'] = scheduler.state.ledger.maxlen
        report['decisions_total'] = scheduler.state.counts['decision_accepted']
        report['decisions_omitted'] = report['decisions_total']-len(report['decisions'])
        publish(dict(stage='STOPPED', reason=reason, cleanup_verified=cleanup, execution_busy=busy))
    return report


def exit_code(report, *, service=False):
    # A deliberate withdrawal is a clean lifecycle exit, independent of quality
    # acceptance. Unit Restart=no also covers runtime/cleanup/startup failures.
    if service:
        return 0 if report['cleanup_verified'] and not report['errors'] and report['reason'] in (
            'controller_stop', 'native_withdrawn') else 1
    return 0 if report['accepted'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'companion-config', 'token-file', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('agent-url', 'hub-url', 'agent-boot', 'controller'):
        parser.add_argument('--'+name, required=True)
    for name in ('microphone-epoch', 'policy-epoch'):
        parser.add_argument('--'+name, type=int, required=True)
    lifetime = parser.add_mutually_exclusive_group()
    lifetime.add_argument('--duration', type=float)
    lifetime.add_argument('--service', action='store_true', help='One continuous observation-only session; no auto-rebind')
    parser.add_argument('--metadata', type=Path, help='Service-only rotating metadata snapshot path')
    parser.add_argument('--status-port', type=int, default=8791)
    parser.add_argument('--allow-native-observation', action='store_true')
    parser.add_argument('--allow-camera-context', action='store_true')
    stock_arm = parser.add_mutually_exclusive_group()
    stock_arm.add_argument('--allow-stock-settle', action='store_true')
    stock_arm.add_argument('--allow-goal-clock-stock-settle', action='store_true',
                           help='One finite initial settle from explicit operator goal/clock; requires matching profile')
    parser.add_argument('--allow-configured-agent-url', action='store_true',
                        help='Hub-local status: exact companion Agent URL and Linux immediate header ACK')
    args = parser.parse_args()
    if (not args.allow_native_observation or args.output.exists() or not 1 <= args.status_port <= 65535
            or args.service != bool(args.metadata) or args.metadata == args.output):
        raise ValueError('Fresh native observation opt-in and service metadata required')
    duration = None if args.service else 60 if args.duration is None else args.duration
    cfg = load(args.config)
    goal_clock = cfg.get('native_agent', {}).get('stock_profile') == 'finite_goal_clock'
    if goal_clock != args.allow_goal_clock_stock_settle or (goal_clock and args.allow_stock_settle):
        raise ValueError('Matching explicit goal/clock stock arm/profile required')
    allow_stock = args.allow_stock_settle or args.allow_goal_clock_stock_settle
    validate_lifecycle(cfg, service=args.service, duration=duration,
                       allow_stock=allow_stock, allow_camera=args.allow_camera_context)
    if cfg.get('native_agent', {}).get('enabled') is not True: raise ValueError('Native profile required')
    session_context(cfg, allow_camera=args.allow_camera_context)
    from ..config import Config
    companion = Config(args.companion_config)
    configured = companion['network']['agent_url'] if args.allow_configured_agent_url else None
    if args.allow_configured_agent_url and args.agent_url != configured:
        raise ValueError('Hub-local status must use the exact configured Agent URL')
    agent = NativeClient(args.agent_url, companion.token, configured_url=configured,
                         quick_ack=args.allow_configured_agent_url)
    hub = NativeClient(args.hub_url, companion.token, quick_ack=args.allow_configured_agent_url)
    operator = hub.get('/control/operator')
    if (operator.get('agent_boot_id'), operator.get('microphone_epoch'), operator.get('motion_policy', {}).get('epoch')) != (
            args.agent_boot, args.microphone_epoch, args.policy_epoch):
        raise ValueError('Fresh explicit native authority required')
    if allow_stock and operator['motion_policy']['motor_enabled'] is not True:
        raise ValueError('Existing motor permission required; this entrypoint never grants it')
    # Bootstrap identity only: this aggregate response never admits an effect.
    hardware = hub.get('/status', setup_hardware=True)
    extra = dict(goal=cfg['native_agent']['operator_goal'], goal_ttl_s=cfg['native_agent']['goal_ttl_s']) if goal_clock else {}
    native = (GoalClockNativeAgent if goal_clock else NativeAgent)(
        agent, hub, companion, operator, hardware.get('stock_motion', {}).get('hub_boot_id'),
        allow_stock=allow_stock, **extra)
    # Discard bootstrap age; require current native authority before scheduler setup.
    native.latest = native.read()
    if goal_clock:
        if native.clock() >= native.latest['received'] + .3: raise TimeoutError('Initial motor receipt expired')
        native.motor_unavailable = False
    token = args.token_file.read_text().strip()
    os.environ[cfg['gateway']['token_env']] = token
    scheduler = NativeScheduler(cfg, NativeGateway(cfg), native)
    stop = threading.Event(); current = dict(stage='STARTING'); lock = threading.Lock()
    metadata = MetadataSnapshots(args.metadata) if args.service else None
    def publish(value):
        with lock: current.clear(); current.update(value)
        if metadata: metadata.write(value)
    def read_status():
        with lock: return dict(current)
    previous = {}; server = thread = None; report = None
    try:
        server = create_server(token, args.controller, args.agent_boot, stop, read_status, port=args.status_port)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, lambda *_: stop.set())
        report = run_native_session(scheduler, stop, duration, publish, service=args.service)
    finally:
        scheduler.close()
        if server:
            if thread and thread.is_alive(): server.shutdown(); thread.join(1)
            server.server_close()
        for signum, handler in previous.items(): signal.signal(signum, handler)
    if report is not None:
        report['control_listener_execution_busy'] = bool(thread and thread.is_alive())
        report['control_transport'] = server.transport_status()
        if report['control_listener_execution_busy'] or report['control_transport']['execution_busy']:
            report['accepted'] = report['cleanup_verified'] = False
        with args.output.open('x') as handle:
            os.chmod(args.output, 0o600)
            json.dump(report, handle, ensure_ascii=False, indent=2)
        if metadata: metadata.write(report, force=True)
        return exit_code(report, service=args.service)
    return 1


if __name__ == '__main__': raise SystemExit(main())
