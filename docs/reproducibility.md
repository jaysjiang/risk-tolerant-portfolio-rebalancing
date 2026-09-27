# Reproducibility

The repository contains the research code, aggregate results and figures. Tests and a synthetic example run without market data. Reproducing the financial results requires the [reviewed input snapshots](data_availability.md).

## Commands

Install the dependencies and package as described in the [README](../README.md). The original environment used Python 3.12.14; numerical package versions are pinned in [requirements.txt](../requirements.txt).

| Command | Scope |
|---|---|
| `python scripts/reproduce.py check` | Regression tests, release checksums, local links, selection chronology and result-grid consistency |
| `python scripts/reproduce.py demo --workers 2` | Five policies over 36 synthetic sessions, including cash distributions, an in-kind distribution and a split |
| `python scripts/reproduce.py smoke --data-dir PATH` | Input and source verification, followed by the first 15 final-evaluation sessions for the primary pair |
| `python scripts/reproduce.py full --data-dir PATH --workers 8` | All 189 runs, aggregate metric comparisons and 11 bootstrap comparisons |

`verify` and `tests` are aliases for `check`. Each command creates a new output folder under `work/`; use `--output-root PATH` to change the destination. Financial replay uses the fixed scenarios and selected parameters.

The full command compares every aggregate metric, bootstrap interval endpoints, classifications and resampling-index checksums. Individual historical ledgers and bootstrap draws are held in the research archive and are not distributed here. The smoke command checks execution over a short interval; it does not reproduce full-period performance.

## Verification

The [verification record](../reports/release_validation.json) documents a fresh Windows installation, 99 passing tests, the synthetic example and a 15-session replay matching all 38 daily ledger fields for each primary policy. The complete 189-run evaluation was not repeated for this release. GitHub-hosted CI has not yet run.

Tests cover risk constraints, no-trade decisions, self-financing trades, corporate actions, information timing, parallel execution, comparator selection and paired inference. Private data-adapter integration tests require the undistributed snapshots. The [historical verification record](../reports/results/historical_verification.json) describes the original financial evaluation.

Install the pinned requirements before the editable package. `--no-build-isolation` uses the installed setuptools version. The `.gitattributes` file preserves line endings across operating systems so release hashes remain stable.

## Research note

The [Markdown source](../reports/research_note.md) and [PDF](../PDF/research_note.pdf) contain the same note. To rebuild the PDF and its two figures from the Markdown, aggregate results and saved illustration geometry:

```shell
python -m pip install -r requirements-note.txt
python scripts/build_note.py
```

The output replaces `PDF/research_note.pdf` and refreshes the two PNG figures used by the Markdown. Graphs, display equations and inline mathematics are embedded as vectors; mathematical notation uses Computer Modern fonts. Intermediate PDFs stay under `work/note/PDF/`. The allocation-plane illustration uses the derived coefficients in `reports/results/note_figure_inputs.json`; no provider observations or financial replay are required. This is a presentation rebuild of the saved results.

## Version records

The specifications retain the original research dates and methodological choices. [Provenance](../reports/results/provenance.json) records the archived source hashes and changes to the public edition. Those changes concern documentation and presentation; the empirical results and executable research logic are unchanged.

[release_manifest.json](../release_manifest.json) records file hashes for this release. An intentional edit or PDF rebuild requires an updated manifest before `check` will pass. These hashes establish file consistency; they are not an independent timestamp or signature.

No software license has been selected. Provider-data redistribution rights are separate from access to the code.
