# IFs Model Vetting

Standalone IFs runfile comparison tool, also bundled by the separate
`ifs-companion` application. This repository owns comparison logic, trajectory
audits, the comparison UI, the .NET Parquet decoder, and their tests.

Use Python 3.14 with NumPy (`python -m pip install numpy==2.5.3`) and a .NET 10 SDK.
Run `./build.ps1` to publish the decoder, then `./start.ps1 -PythonPath <python.exe>`
and open http://127.0.0.1:8765. Select an IFs folder containing DATA and RUNFILES,
choose two runs, load shared variables, and compare. Run
`python -m unittest discover -s tests -v` for the tool tests.

Source runfiles are opened read-only. Stored coordinate tuples drive alignment;
incompatible dimensions are skipped, partial payloads are identified, and
nonfinite values are excluded from numeric metrics. Each variable retains its own
units. Audits provide descriptive evidence, not causal or pass/fail judgments.
Completed reports and arrays are saved under `%LOCALAPPDATA%/IFsModelVetting`;
`IFS_VETTING_DATA_DIR` overrides the location for testing.

## Companion integration

Keep `ifs-companion` beside this checkout. Its build reads this repository directly
and bundles the tool into its installer. No Companion shell, desktop host, or
installer source is maintained here. The existing local HTTP API supplies
installation selection, metadata, comparisons, job status, reports, and exports.
`/api/recent` lists comparison jobs; the UI exposes `openCompanionReport(id)` for
the host to reopen a report. The comparison tool can still run on its own.

Older generated desktop distributions remain in ignored `dist` and `release`
directories for reference. New Companion builds belong to `ifs-companion`.
This project is MIT licensed; dependency notices remain in THIRD_PARTY_NOTICES.txt.
