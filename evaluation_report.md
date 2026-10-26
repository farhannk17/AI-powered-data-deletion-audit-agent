# Evaluation report

## Public sample comparison

The evaluator compares the 32 public requests with `dataset/sample_output.csv`. This is a development check only; it is not an estimate of hidden-set performance.

| Metric | Result |
|---|---:|
| Cases | 32 |
| Case-level deletion-status accuracy | 29/32 (90.6%) |
| Exact output-row accuracy (status and whole step sequence) | 6/32 (18.8%) |
| Exact step-sequence accuracy | 6/32 (18.8%) |
| Aligned step accuracy | 102/195 (52.3%) |
| Step-field accuracy | 859/1365 (62.9%) |

The final full-dataset pipeline run processed 518 requests and emitted 518 rows. It indexed 2545 observations from 94 manifest entries. The run reported 11 evidence warnings; those limitations are recorded in `run_report.json`.

## Baseline and case-by-case error inventory

The saved pre-change run scored 26/32 status cases (81.2%), 1/32 exact rows, 1/32 exact sequences, 19/196 aligned steps, and 332/1372 fields.

This inventory lists every public sample row that is not an exact match. Step tuples are `(phase, system_id, resource_id, operation, state, evidence_id)`. `missing` and `extra` are multiset differences against the public reference.

- `case_01` status: predicted `INCOMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_001', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_54')]; extra/different predicted steps: none.
- `case_02` status: predicted `INCOMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_002', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_54')]; extra/different predicted steps: none.
- `case_03` status: predicted `COMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'analytics_platform', 'analytics_9406', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_94')]; extra/different predicted steps: none.
- `case_04` status: predicted `INCOMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_004', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_54'), ('VERIFICATION', 'analytics_platform', 'analytics_901', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_56')]; extra/different predicted steps: none.
- `case_06` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_006', 'VERIFY_RECORD_ABSENT', 'ABSENT', '')]; extra/different predicted steps: none.
- `case_07` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_007', 'VERIFY_RECORD_ABSENT', 'ABSENT', '')]; extra/different predicted steps: none.
- `case_08` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_008', 'VERIFY_RECORD_ABSENT', 'ABSENT', '')]; extra/different predicted steps: none.
- `case_09` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_3960', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'security_service', 'audit_record_4902', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: none.
- `case_10` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_010', 'VERIFY_RECORD_ABSENT', 'ABSENT', '')]; extra/different predicted steps: [('FINDING', 'support_platform', 'support_002', 'REPORT_EXPOSED_PII', 'PRESENT', 'evidence_61'), ('REMEDIATION', 'support_platform', 'support_002', 'REDACT_RECORD', 'REDACTED', ''), ('VERIFICATION', 'support_platform', 'support_002', 'VERIFY_RECORD_REDACTED', 'REDACTED', '')].
- `case_12` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'security_service', 'audit_record_2945', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: none.
- `case_16` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('FINDING', 'account_service', 'account_994', 'REPORT_REMAINING_RECORD', 'PRESENT', 'evidence_05'), ('FINDING', 'search_service', 'search_1007', 'REPORT_REMAINING_RECORD', 'PRESENT', 'evidence_05'), ('REMEDIATION', 'account_service', 'account_994', 'DELETE_RECORD', 'ABSENT', ''), ('REMEDIATION', 'search_service', 'search_1007', 'DELETE_RECORD', 'ABSENT', ''), ('VERIFICATION', 'account_service', 'account_994', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'search_service', 'search_1007', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'security_service', 'audit_record_9528', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: none.
- `case_17` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'security_service', 'audit_record_1797', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: [('VERIFICATION', 'account_service', 'account_6523', 'VERIFY_RECORD_ABSENT', 'ABSENT', '')].
- `case_18` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_5521', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'security_service', 'audit_record_6645', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: none.
- `case_20` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_5037', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'security_service', 'audit_record_5569', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: none.
- `case_21` status: predicted `COMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_6440', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_92'), ('VERIFICATION', 'analytics_platform', 'analytics_5335', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')]; extra/different predicted steps: none.
- `case_22` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('FINDING', 'search_service', 'search_8911', 'REPORT_REMAINING_RECORD', 'PRESENT', 'evidence_05'), ('FINDING', 'analytics_platform', 'analytics_4440', 'REPORT_EXPOSED_PII', 'PRESENT', 'evidence_05'), ('REMEDIATION', 'search_service', 'search_8911', 'DELETE_RECORD', 'ABSENT', ''), ('REMEDIATION', 'analytics_platform', 'analytics_4440', 'ANONYMIZE_RECORD', 'ANONYMIZED', ''), ('VERIFICATION', 'account_service', 'account_4990', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'search_service', 'search_8911', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'security_service', 'audit_record_3482', 'VERIFY_RECORD_PRESENT', 'PRESENT', ''), ('VERIFICATION', 'analytics_platform', 'analytics_4440', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', '')]; extra/different predicted steps: none.
- `case_23` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_410', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'security_service', 'audit_record_4128', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: none.
- `case_24` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'security_service', 'audit_record_7095', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: none.
- `case_25` status: predicted `COMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_3136', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_92'), ('VERIFICATION', 'analytics_platform', 'analytics_1895', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')]; extra/different predicted steps: none.
- `case_26` status: predicted `COMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_5684', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_92'), ('VERIFICATION', 'analytics_platform', 'analytics_4566', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')]; extra/different predicted steps: none.
- `case_27` status: predicted `COMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_3866', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_92'), ('VERIFICATION', 'analytics_platform', 'analytics_4574', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')]; extra/different predicted steps: none.
- `case_28` status: predicted `COMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_5482', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_92'), ('VERIFICATION', 'analytics_platform', 'analytics_6077', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')]; extra/different predicted steps: none.
- `case_29` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_7012', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'security_service', 'audit_record_3954', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: none.
- `case_30` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_4163', 'VERIFY_RECORD_ABSENT', 'ABSENT', ''), ('VERIFICATION', 'security_service', 'audit_record_1707', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')]; extra/different predicted steps: none.
- `case_31` status: predicted `COMPLETE`, expected `COMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_4857', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_51')]; extra/different predicted steps: none.
- `case_32` status: predicted `INCOMPLETE`, expected `INCOMPLETE`; missing expected steps: [('VERIFICATION', 'account_service', 'account_8858', 'VERIFY_RECORD_ABSENT', 'ABSENT', '')]; extra/different predicted steps: none.

## Error categories and inspected root causes

- **Identity resolution:** exact linkage is unavailable when evidence contains an unlinked empty snapshot or an operational event that names only a resource. The pipeline does not infer identity from case numbering, names alone, or time proximity. This limits cases whose resource IDs are not joined to supplied identifiers.
- **Evidence extraction:** the earlier parser did not preserve links across trace-correlated log events, handle bullet-prefixed handover rows, normalize quoted values, distinguish service names from resource IDs, recognize generic SQL replica table names, or connect identifiers split across PDF lines. These formats are now parsed and covered by regressions.
- **Temporal reasoning:** the previous filter checked record timestamps but not evidence-file capture timestamps, and a future current-identity snapshot could be added after resolving a historical email. Both timestamps are now enforced independently.
- **Policy evaluation:** event category aliases, literal `null` values, support attachments versus shared support messages, backup restore flags, and retained audit records with incomplete expiry metadata were not normalized consistently. These now use explicit category and rule conditions.
- **Recreation risk:** connector and backup states could be missed when the identity appeared on a sibling event in the same trace. Trace-scoped context is now carried, and `enabled`, `eligible`, and deletion-block fields are evaluated deterministically.
- **Remediation ordering:** the prior logic sorted only by operation class and lexical resource ID. Explicit source/parent references now place downstream copies before their source within an operation class; flow disabling and restore blocking remain first.
- **Output validation:** the previous validator checked row count, JSON, phase order, and evidence membership but not evidence cutoff or operation-class ordering. Those checks are now included.

These diagnoses come from inspected public evidence and regression cases. The local dataset does not contain canonical labels for the 518 evaluation requests, so the sample metrics must not be treated as full-dataset accuracy.

## Additional regression cases authored for this implementation

The 17 unit tests in `code/tests/test_main.py` cover these synthetic patterns; none use public case IDs or expected output rows:

1. French, Japanese, and Korean deletion intent.
2. Explicit non-deletion requests, including correction, marketing opt-out, and login recovery.
3. Historical email resolution and cutoff-safe identity snapshot use.
4. Observation-time and evidence-capture-time cutoff enforcement.
5. Quoted key/value log parsing and zero-row/404 state extraction.
6. Bullet-prefixed handover rows.
7. Rejecting service names as resource IDs.
8. Trace-scoped identity propagation without cross-trace leakage.
9. Generic replica-table aliases and unknown-table rejection.
10. PDF identifier extraction when fields span adjacent lines.
11. Exact email matching that rejects longer-domain substring collisions.
12. Collection category aliases and null-like PII fields.
13. Backup restore candidacy and deletion-block handling.
14. Explicit downstream-copy-before-source ordering.
15. Policy action selection from supplied rules.

These are synthetic regression tests, not scored challenge cases.

## Failures found and improvements made

- Initial intent detection missed French, Japanese, and Korean request templates. The classifier was expanded and tested against those languages while preserving explicit non-deletion checks.
- Initial SQL parsing indexed only generic table names and missed replica-specific table suffixes. The loader now safely executes only `CREATE TABLE` and `INSERT INTO` statements in an isolated in-memory SQLite database and indexes matching replica tables.
- Status and sequence accuracy remains below a reliable submission threshold. The remaining errors are mainly incomplete resource-to-subject linkage and lack of OCR for screenshots. The pipeline deliberately does not use case IDs, expected labels, or reported workflow status as shortcuts.

Mismatching public sample cases: case_01, case_02, case_03, case_04, case_06, case_07, case_08, case_09, case_10, case_12, case_16, case_17, case_18, case_20, case_21, case_22, case_23, case_24, case_25, case_26, case_27, case_28, case_29, case_30, case_31, case_32.

## Pipeline run counts

`COMPLETE`: 111; `INCOMPLETE`: 400; `NOT_APPLICABLE`: 7.
