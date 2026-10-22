# Lean extraction and integration fixtures

`Extract.lean` reads elaborated constant types and values, including computational definition bodies. The graph consumer retains type edges and definition-value edges while excluding theorem-proof-only edges from semantic review. Full proof dependencies remain a separate view.

The adapter uses the Lean 4.28 environment APIs inspected in upstream `Lean.Util.FoldConsts`, `Lean.Declaration`, and `Lean.Environment`. Lean Atlas itself pins 4.28.0. This does not establish compatibility with every audited project's version. Use the project's own toolchain and record it; do not upgrade the mathematics to fit this adapter.

Example, after installing/building the target project and configuring its execution policy:

```powershell
.\.venv\Scripts\python.exe -m apology.dependencies data/graph.json --extract --repo C:/path/to/analysis-checkout --module Project.Main --prefix Project --repository https://github.com/owner/project --commit FULL_COMMIT_SHA
```

The export stores types and values as structural expression representations and records module provenance. Missing source spans, opaque bodies, and untrusted external declarations become review blockers. Supply `--source-map data/source-map.json` with independently verified source spans to connect fully qualified names to immutable source snapshots. Never mark all imported constants trusted to remove blockers.

`Fixtures.lean` covers nested definitions, a proof-only helper, an abbreviation, an instance, data constructed with tactics, a proof appearing in a type, and a project axiom. Compile it using the pinned toolchain, then import its built module when testing the extractor. Python's synthetic graph fixtures test cycles without requiring recursive Lean definitions.

Execution is disabled by default. The Docker policy mounts the project and generated source read-only, disables network access, forwards no provider credentials, limits CPU/memory/processes, and requires a preinstalled digest-pinned image containing the matching toolchain and dependencies. The filesystem mount should be a disposable analysis checkout containing no secrets. Host-local mode is an explicit option for trusted fixtures and is not isolation.

Native extraction and the fixtures could not be compiled in the implementation environment because Lean was absent and Docker's daemon was unavailable. They are integration work to validate on an equipped machine. A successful graph export is not a certificate of proof validity or natural-language correspondence.
