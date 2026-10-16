# Scoped Docker candidate comparison after a real failed rollout

The real finite content-stream rollout failed during lifecycle validation before
streaming voice acceptance. On the verified Docker Engine 29.7.2 / API 1.55,
its own candidate's created inspection had OomKillDisable false; running inspect
had null. Config and every other HostConfig/mount/network field matched. The
same raw HostConfig comparison also blocked ordinary failure recovery. Separate
recovery has now restored and verified the original worker/config: running/idle,
original brains/voice loaded, content_tokens false, inventory preserved, no OOM,
candidate parked and pending slot empty. Robot remained OFF/unowned/100% and
factory free. This is recovered baseline, **not streaming voice acceptance**.

Use `candidate_config_matches` from the existing public
`deploy/autonomous/docker_config_identity.py` seam, reviewed SHA256
`b31165ceeeb90b46cd224ab60971a300b26fab6e823298c6510dcd341e1f61f2`.
Do not use the older
`container_config_identity`/fingerprint for this runtime check: that older API
has an unscoped false/null equivalence and mount ordering policy. It is retained
unchanged for existing callers. The new comparator keeps Config/HostConfig
strict and type sensitive, including false versus integer zero. It mutates no
input, reads no device, emits no operational values and performs no operation.

The only exception is expected **literal false** to actual **null** at the one
HostConfig.OomKillDisable field. It requires the exact known Engine/API version
and a retained own-start witness. True, zero, missing fields, other null changes,
reverse null-to-false, other versions and unknown start identity do not qualify.
A never-started candidate still requires exact raw false. Complete Config and
HostConfig are compared; the exception does not waive any other nested value,
key presence, type, environment/argument order, security flag or HostConfig
mount/network option. Top-level mounts/network/image/owner/source fences remain
separate exact existing checks, in **both** validation and recovery.

## Exact executor integration contract

The runner integrates this function into its existing private finite executor;
no new lifecycle framework or HEAD worker deployment is needed. Pin the helper
bytes in the existing protected source set and load it using the existing
source-loading mechanism. One adapter serves both affected methods:

```python
def candidate_configuration_matches(self, value):
    return candidate_config_matches(
        dict(Id=self.candidate, Config=self.payload_config, HostConfig=self.payload_host),
        value, engine_version=VERSION, api_version=API,
        owned_start=getattr(self, 'candidate_start_witness', None))
```

`VERSION` and `API` refer to the executor's existing pins, after its daemon check
has matched the actual Engine identity/version/API. Keep that check; matching a
version string alone does not establish the right daemon. Preserve all fresh
source fences, manual STOP, authority, slot namespace and lifetime checks.

In `check_candidate`, replace only the raw Config/HostConfig equality with
`need(self.candidate_configuration_matches(v))`. **Remove** creation of
`candidate_instance` from an arbitrary running inspect. A running candidate
requires the retained trusted start witness, same StartedAt and positive exact
integer Pid; a parked candidate after that start requires Pid zero and the same
StartedAt. Keep immutable image, same owned candidate ID, Running identity,
RestartCount exact integer zero, mounts and network checks. The new helper
checks the latter PID/start/restart types when applying its exception; the
caller retains its independent state checks even on the raw-equality path.

In `restore_known_failure`, replace the raw Config/HostConfig equality with the
**same adapter and same retained witness**, not a recovery-specific weaker rule.
Keep exact mount inventory and add the already existing
`self.core.network_contract(v)==self.network` check here too. Keep owned ID,
immutable image, state/start/restart checks before any compensation. A parked
post-start candidate may have actual Pid zero; do not overwrite its retained
positive start Pid. A never-started candidate has no witness and raw false.

## Issuing the witness: existing start callback only

The pure helper validates witness shape and binding; it **cannot attest** that
its caller actually observed its own successful start. The issuer contract is
required for either call site to use the exception:

1. Existing `once(..., 'start-owned-candidate', invoke, started)` first durably
   records the same run/candidate/start phase with mutation_pending true. Retain
   the stopped candidate's prior StartedAt and Pid zero before invocation.
2. Only its callback may issue a witness, after its own POST start returns
   **exact integer 204**. Verify the same slot namespace/run/candidate/start
   phase and mutation_pending true; re-check the pinned daemon and source fences.
3. Inspect the same owned ID. Require Running literal true, Pid positive integer,
   RestartCount integer zero and a valid new StartedAt different from that prior
   stopped observation. Before Config/HostConfig comparison can fail, persist a
   private exclusive receipt under the existing run directory containing that
   actual 204, candidate ID, observed Pid/StartedAt, daemon identity/version/API,
   run and digest of the pending start intent. Use existing guarded persistence;
   no public operational pins/config/token/body export. Verify its identity.
4. Only from that verified receipt construct and retain exactly
   `candidate_start_witness = dict(Id=..., Pid=..., StartedAt=...)`. The public
   helper validates these keys, positive integer Pid, valid nonzero StartedAt,
   same candidate ID and running/parked current state. It is not a receipt store.
5. Then call `check_candidate(True)`. Only after all existing observe checks
   succeed may `once` mark mutation_pending false. Any other failure leaves the
   pending intent unknown; the comparator never clears it or authorizes a retry.

The old candidate_instance minted at check_candidate's first running inspect
was **not** a trusted receipt. Do not promote it, a current recovery inspect, a
successful readiness check or a general container match into own-start evidence.
No receipt means no normalization. If recovery reloads a durable receipt, verify
its exact private identity, run/candidate/pending binding and issuer evidence
before constructing the same witness; do not manufacture a replacement receipt.

The sole runner prepares its exact private source integration for coordinator
review and source checks before any device operation. This public fix itself
starts no worker, changes no config and grants no product retry. Baseline remains
restored. The next accepted rollout still needs fresh preflight and an actual
long substantive answer → further timely token READ → STOP → same-response
terminal/quiescence → fresh next-turn check on the same PC process. Continuous
capture/partial STT follows after this unresolved streaming acceptance.

Focused tests cover own running and parked shapes, never-started raw false,
missing/foreign/forged-shaped witnesses, PID/start/restart drift, unknown runtime,
literal type boundaries, every other Config/HostConfig leaf/key, ordered arrays,
mount/security/network changes, malformed JSON and no input mutation. They do
not prove receipt issuance, installation, recovery operations or audible speech.
