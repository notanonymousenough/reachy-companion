# Request-scoped spoken reply constraints

The legacy LM Studio raw `/v1/completions` request and ordinary stream acknowledgements remain the defaults. An authenticated `/text` or `/turn` request may explicitly supply:

```json
{"reply_constraints":{"schema_version":"reply-1","max_chars":60,"no_question":true,"no_wake":true}}
```

This path uses the configured model and messages through `/v1/chat/completions`, with a strict reply-only JSON schema. It never substitutes a preset, truncates text, strips reasoning/tags, retries as free text, or emits an acknowledgement. Empty input, pause/reset/stop and `/say` reject constrained requests before their control effects. Only complete `finish_reason=stop`, strict JSON with exactly one `reply` key, valid spoken text and unchanged expression processing can reach TTS. History receives plain spoken text after successful synthesis as before.

The schema bounds length and punctuation. Host validation independently checks length, forbidden markup, a word character, normalized question marks, and wake substrings. Normalization uses casefold/NFKD/removal of combining marks and the fixture's Latin-to-Cyrillic mapping for mixed wake names. This detects punctuation and selected wake spellings; it does not establish that a sentence cannot implicitly ask a question. The independent fixture's question/wake, source age, operator epoch, global deadline, PCM duration and actual consumed playback guards remain mandatory. A character bound does not guarantee a TTS duration or latency.

## Capability gate

[LM Studio documents JSON schema output on chat completions](https://lmstudio.ai/docs/developer/openai-compat/structured-output). This does not prove that the currently loaded model/runtime implements each schema keyword. Before enabling this path, the sole hardware runner must complete the bounded PC-only capability probe on the already loaded model, without model reload or production configuration changes. Record model/runtime identity, endpoint, exact schema hash, finish reason, validity and latency as aggregate evidence. An accepted HTTP request alone cannot demonstrate enforcement of `maxLength` and `pattern`; inspect the generated result and capability evidence, and keep host validation regardless.

Absent a verified operator profile, a constrained request fails before inference. An isolated trial configuration may set `llm.reply_schema` as follows, replacing placeholders with the exact audited current values:

```json
{"enabled":true,"verified":true,"model":"EXACT_CURRENT_MODEL","base_url":"EXACT_CONFIGURED_BASE_URL","api_path":"/chat/completions","max_length_verified":true,"pattern_verified":true}
```

`api_path` is appended to the configured base URL and must resolve to exactly `/v1/chat/completions`; a base URL ending in `/v1` uses `/chat/completions`. The profile must match the configured model and base URL. This profile records operator evidence; it is not cryptographic attestation. A changed loaded model/runtime invalidates the evidence and requires a new capability check. No production defaults or model settings are changed by this feature. Unsupported schemas, backend errors, malformed output and guard failures fail closed.

## Minimal legacy overlay

Run `python3 deploy/autonomous/prepare_spoken_reply.py NEW_PRIVATE_OUTPUT_DIRECTORY` from this exact source checkout. It creates only `brains.py`, `voice.py`, `spoken_reply.py` and a hash manifest. The voice file derives from the audited legacy `95be315…` source, with only this feature's edits. It excludes the later STT diagnostics. The generator never connects to or modifies a device/service.

Before staging, independently audit the generator and match every manifest preimage on the actual worker, require the new helper to be absent, and match the existing strict-decoder dependency hash and safe package import. A dependency mismatch is a stop condition; do not silently deploy full HEAD or replace a dependency. The manifest intentionally reports actual capability and hardware acceptance false. Fresh trial ownership must bind container ID/image, launch generation, configuration, module preimages, output hashes and rollback nonce. Restore only if the exact current trial still matches all those ownership fields; preserve foreign/newer state. Do not force overwrite, recover stale ownership, alter the microphone or run another device session from the writer.

Validation: `PYTHONPATH=src python3 -m unittest discover -s tests -p test_spoken_reply.py -v`. Tests cover unchanged legacy payloads, exact chat/schema selection, missing/changed capability gates, strict output rejection, request-local concurrent rules, control paths, history, unchanged TTS and suppressed canned acknowledgements. Local tests and generated hashes are source evidence, not actual model or playback acceptance.

On 2026-10-15 the runner's first PC-only same-model chat-schema probe returned HTTP 200 but its message content failed strict JSON parsing. The probe did not reach TTS. Finish reason and usage were not captured before that parse failed, so the result does not establish whether the schema was unsupported, ignored or generation was incomplete. Capability remains unverified and the gate must stay closed pending the separately instrumented diagnostic. Do not strip reasoning or repair JSON to turn this failure into acceptance.

If the actual worker has no `autonomous` directory at all (including no symlink), the runner may generate an explicit five-file closure with `--include-decoder`. This includes only the audited docstring-only `autonomous/__init__.py` and `autonomous/contracts.py` in addition to the three feature files. Its manifest requires the entire target `autonomous` path to be absent and records both new file hashes/preimages. Do not use this mode over an existing or partially populated package; match the default dependency hashes or prepare a separately audited closure. The decoder module imports only the standard library; its `jsonschema`/asset-dependent validator is lazy and is never invoked by this reply path. A clean-process closure test verifies strict duplicate-key rejection and that no model, hardware or `jsonschema` module is loaded. Rollback may remove this added directory only while its exact owned contents and trial identity still match.
