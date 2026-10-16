"""One explicit maintenance transition; never part of ordinary CREATE admission.

No CLI, lock creation, discovery, Docker, task or filesystem implementation.
The separately reviewed canonical provider MUST hold the existing mutex for
this entire call, fence the enrolled namespace, read the native marker exactly,
validate the approved namespace/plan/UNKNOWN operation, and persist immutable
records durably before returning. Effects own only the approved maintenance.
This source is unusable for execution without that reviewed composition.
"""
import base64
import hashlib
import json
import re


class MaintenanceDenied(RuntimeError):
    pass


HOLD = ('heartbeat_paused', 'task_disabled', 'task_preimage_saved',
        'managed_callers_held', 'old_submitters_absent')
BOUNDARY = ('desktop_stopped', 'target_terminated', 'old_processes_absent',
            'api_unavailable', 'no_auto_resume')
RECONCILE = ('fresh_incarnation', 'inventory_exact', 'baseline_exact',
             'sources_exact', 'profile_exact', 'ports_exact', 'operator_safe',
             'stopped_workloads_preserved', 'model_ready')
RESTORE = ('operator_safe', 'task_restored', 'heartbeat_restored')


def _need(value):
    if value is not True:
        raise MaintenanceDenied('Required maintenance witness unavailable')


def _witness(value, keys):
    if type(value) is not dict or set(value) != set(keys) | {'evidence_sha256'}:
        raise MaintenanceDenied('Exact typed maintenance witnesses required')
    for key in keys:
        _need(value[key])
    if (type(value['evidence_sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', value['evidence_sha256']) is None):
        raise MaintenanceDenied('Durable concrete witness bundle hash required')
    return dict(value)


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _marker(slot):
    slot.verify_namespace()
    raw = slot.read_marker()
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise MaintenanceDenied('Bounded native marker bytes required')
    slot.verify_namespace()
    return raw


def _persist(slot, kind, raw):
    # Provider must use no-overwrite durable storage in its enrolled namespace.
    # Existing records deny a new attempt; there is no idempotent retry here.
    slot.durable_record(kind, raw)
    slot.verify_namespace()
    if slot.read_record(kind) != raw:
        raise MaintenanceDenied('Durable maintenance record verification failed')


def supersede(provider, effects, *, approval):
    """Run once under approved provider; any exception escapes without retry.

    Records are PRIVATE: journal contains exact original bytes and approval.
    Each effect must durably retain its concrete witness bundle before returning
    evidence_sha256; these PRIVATE bundles bind the actual task preimage,
    terminated domain and fresh incarnation/reconcile, not just boolean claims.
    validate_approval must bind the full approval, raw UNKNOWN marker and
    canonical namespace/plan under this same mutex. Boolean effect witnesses
    require independent concrete evidence in the reviewed adapter, not assertions.
    A failed/unknown final save may already have replaced the native marker:
    keep HOLD, preserve journal/receipt and require RO manual reconciliation.
    No automatic rollback, pending rewrite or restore is attempted on failure.
    """
    # Freeze the approved JSON object; reject non-JSON/nonfinite content.
    if type(approval) is not dict:
        raise MaintenanceDenied('Explicit maintenance approval required')
    approved = _encode(approval)
    with provider as slot:
        original = _marker(slot)
        _need(slot.validate_approval(json.loads(approved), original))
        _need(slot.is_unknown(original))
        journal = _encode(dict(schema=1, kind='explicit-maintenance-intent',
            historical_outcome='UNKNOWN', approval=json.loads(approved),
            original_marker_base64=base64.b64encode(original).decode('ascii'),
            original_marker_sha256=_sha(original)))
        _persist(slot, 'intent', journal)  # Before HOLD or any disruption.
        held = _witness(effects.hold(), HOLD)
        if _marker(slot) != original:
            raise MaintenanceDenied('Original UNKNOWN marker changed')
        _need(slot.validate_approval(json.loads(approved), original))
        boundary = _witness(effects.terminate(), BOUNDARY)
        if _marker(slot) != original:
            raise MaintenanceDenied('Original UNKNOWN marker changed')
        _need(slot.validate_approval(json.loads(approved), original))
        # terminate MUST prove the old execution domain gone before reconcile
        # starts its fresh domain. Both occur under the same held mutex.
        reconciled = _witness(effects.reconcile(), RECONCILE)
        if _marker(slot) != original:
            raise MaintenanceDenied('Original UNKNOWN marker changed')
        _need(slot.validate_approval(json.loads(approved), original))
        receipt = _encode(dict(schema=1,
            kind='superseded-by-explicit-maintenance',
            historical_outcome='UNKNOWN', intent_sha256=_sha(journal),
            original_marker_sha256=_sha(original), hold=held,
            boundary=boundary, reconcile=reconciled))
        _persist(slot, 'supersession', receipt)
        # Reread BOTH records and exact pending preimage immediately before
        # the sole existing save(None); never turn UNKNOWN into known-false.
        if (slot.read_record('intent') != journal
                or slot.read_record('supersession') != receipt
                or _marker(slot) != original):
            raise MaintenanceDenied('Maintenance precommit evidence changed')
        _need(slot.validate_approval(json.loads(approved), original))
        slot.save(None)
        _need(slot.is_known_idle(_marker(slot)))
        restored = _witness(effects.restore(), RESTORE)
        return dict(historical_outcome='UNKNOWN',
                    disposition='superseded-by-explicit-maintenance',
                    receipt_sha256=_sha(receipt), restored=restored)
