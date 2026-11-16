# Development and verification

Use Python 3.10+ and `requirements.txt`. See [RUNNING.md](docs/RUNNING.md) for data and AWS configuration. Keep the interface, reports and repository documentation in English.

## Evidence discipline

- Models understand, plan, request catalog tools, synthesize and review. Financial arithmetic belongs in Python.
- Keep unprovided customer facts unknown. Names, personas, ages and qualitative risk labels must not create thresholds or determine conclusions.
- Bind substantive claims to customer statements or checked evidence. Retain counterevidence, unsupported scope and unresolved tasks.
- Separate observation, publication and retrieval dates. Delayed quotes are not real-time execution prices; current retrospective snapshots are not historical vintages.
- Keep original review separate from explicitly authorized alternative search. This simulation places no orders.

## Check a change

Run relevant tests during development and the full suite for shared-contract changes or release readiness:

```bash
python -m unittest discover -s tests -q
git diff --check
```

Set both starter-path variables for official-data coverage. CI has no AWS credentials or organizer archive; skips remain visible. Live evaluation is separate from deterministic regression and must record revision, configuration, frozen inputs, failures and scope. Inspected evaluation questions become development cases; use untouched questions for later generalization claims.

Use fictional inputs and sanitized traces. Keep credentials, local configuration, archives, raw downloaded prices and generated `outputs/` out of commits. The MIT code license does not replace source-data terms.

Update the README and technical guide when behavior changes. Date validation records instead of overwriting failures. Rebuild and inspect submission PDFs after source changes. The [submission index](submission/README.md) distinguishes current and historical material.
