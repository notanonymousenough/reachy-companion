# Frozen regression sources

These files are source fixtures, never installed or launched on a device by the
unit suite. Keep them separate from the evolving production modules.

- `r15`: recovered exact Agent / ExpressionPlayer before-and-after sources. Agent
  is the R20 preimage; reverting its single maintenance keyword reproduces the
  documented R8 hash. Player sources are R29's preimage and U127's retained copy.
  All four hashes match the historical R15 report. The lost absolute operator
  path is no longer needed. This is regression recovery, not hardware evidence.
- `r20`: only candidate, preimages and source manifest used by acoustic FastView tests.
- `s4`: voice preimage, candidate and patch used by rejection taxonomy tests.
- `r52`: frozen worker and portable builder for conversation modes. The prompt
  fixture is synthetic and deliberately mojibake-encoded; no installed prompt
  or private conversation is shipped.

Historical provenance inside manifests identifies original sources; paths in
those records are not runtime dependencies. Do not update frozen source hashes
merely to accommodate production changes. Main-path tests cover current code.
