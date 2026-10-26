# Northstar Shop — AI-Powered Data Deletion Audit Agent

A Python-based audit pipeline built for the **HackerRank Orchestrate AI Hackathon**. The agent investigates data-deletion requests, correlates evidence across data sources, evaluates deletion status, and produces structured remediation and verification steps.

> **Focus:** evidence-driven auditing, identity resolution, audit cutoffs, policy-aware remediation, and validated output.

## Overview

Removing a record from one system does not necessarily mean personal data has been fully deleted. Related records may remain in logs, linked systems, backups, or downstream data flows. This project analyzes each deletion request against available evidence and produces a structured prediction.

The pipeline is designed to:
- Parse deletion requests and supporting evidence from multiple formats.
- Resolve current and historical identifiers when supported by evidence.
- Respect request-specific audit cutoffs.
- Classify requests as `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
- Generate ordered remediation and verification steps.
- Validate output structure and evidence references.

## Workflow

```text
Deletion Requests + Evidence Sources
                 |
                 v
          Request Ingestion
                 |
                 v
      Evidence Parsing & Normalization
                 |
                 v
       Identity / Identifier Resolution
                 |
                 v
        Audit-Cutoff-Aware Evaluation
                 |
                 v
         Status Classification
                 |
                 v
       Remediation & Verification Steps
                 |
                 v
         Output Validation & Tests
                 |
                 v
               output.csv
```

## Key Components

### Request ingestion
Loads deletion requests from CSV and prepares their fields for analysis.

### Evidence parsing
Extracts relevant observations from available evidence files, including structured records and supported document/log formats.

### Identity resolution
Correlates current and historical identifiers using evidence-backed matching, avoiding unsupported links and case-specific hardcoding.

### Temporal reasoning
Applies request-specific audit cutoffs so evidence captured after the applicable cutoff is not incorrectly used to establish the state at that time.

### Status classification
Assigns one of the challenge-defined outcomes:
- `COMPLETE`
- `INCOMPLETE`
- `NOT_APPLICABLE`

### Remediation and verification planning
Generates ordered steps to address remaining data, potential data-recreation paths, and verification needs while considering applicable policy requirements.

### Validation and tests
Checks output structure and allowed values, with automated tests for important parsing, matching, cutoff, and step-generation behavior.

## Output Format

The prediction file uses these columns:

| Column | Description |
|---|---|
| `case_id` | Deletion request identifier |
| `deletion_status` | `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE` |
| `steps_json` | JSON-encoded ordered remediation and verification steps |

The pipeline is designed to produce one output row per request and validate the generated structure, evidence references, and audit-cutoff handling.

## Tech Stack

- Python
- CSV and structured-data processing
- Evidence parsing and normalization
- Unit and regression testing
- Command-line execution and output validation

The prediction pipeline was implemented as a deterministic, evidence-first Python workflow and did not require external model/API calls during the reported run.

## Run Locally

Run commands from the repository root in a Python environment.

### Generate predictions

```bash
python code/main.py --input dataset/deletion_requests.csv --output output.csv --report code/evaluation/run_report.json
```

### Run tests

```bash
python -m unittest discover -s code/tests -v
```

### Run the public-sample evaluation

This command uses sample/baseline files available in the challenge repository:

```bash
python code/evaluation/main.py --output work/final_sample_prediction.csv --report code/evaluation/evaluation_report.md --baseline work/baseline_sample_prediction.csv
```

> Evaluation paths depend on the files present in your local challenge checkout. Do not publish restricted datasets, hidden test cases, or other confidential challenge materials.

## Testing and Evaluation

In the recorded development run:
- The full pipeline generated **518 prediction rows**.
- **17 unit tests passed**.
- On the available **32-case public sample**, status accuracy was **29/32 (90.6%)**.
- Exact row/step-sequence accuracy was **6/32 (18.8%)**.
- Aligned step accuracy was **102/195 (52.3%)**.
- Step-field accuracy was **859/1,365 (62.9%)**.

These results apply only to the available public-sample evaluation. They are not a claim about hidden-test performance or official hackathon ranking. The full 518-request dataset did not have a local canonical answer set available for an accuracy calculation. Some screenshot evidence could not be OCR-read in the recorded environment.

## Design Principles

- **Evidence first:** ground conclusions in available evidence.
- **Temporal correctness:** honor the audit cutoff for each request.
- **Conservative identity matching:** avoid linking identities without sufficient support.
- **Ordered remediation:** produce actionable steps in dependency-aware order.
- **Validation by default:** validate output and regression-test behavior.
- **General rules:** avoid hardcoded answers for individual requests.

## Limitations and Future Improvements

- Improve OCR coverage for screenshots and image-based evidence.
- Increase identity-linking recall while preserving precision.
- Improve remediation-step coverage, ordering, and exact field accuracy.
- Expand tests for additional evidence formats and edge cases.
- Improve per-request explanations and evidence provenance where the output contract permits.

## Repository Artifacts

Depending on what you choose to publish, the repository may contain:
- `code/` — implementation, tests, and evaluation utilities.
- `output.csv` — generated predictions, if permitted by the challenge rules.
- `code.zip` — packaged source artifact.
- `log.txt` — development/audit transcript, if appropriate to publish.
- `code/evaluation/` — evaluation and usage reports.

Do not commit private datasets, hidden test cases, credentials, local environment folders, or restricted challenge materials. Review the hackathon rules before publishing challenge-derived files.

## Acknowledgement

Built as a project for the **HackerRank Orchestrate AI Hackathon**.

---

*This repository documents a hackathon engineering project and its measured public-sample evaluation. It does not claim official endorsement by HackerRank or a winning result.*
