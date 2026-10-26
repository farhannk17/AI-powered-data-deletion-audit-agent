# Model usage and cost report

## Final full-dataset prediction run

- Run command: `python code/main.py --input dataset/deletion_requests.csv --output output.csv --report code/evaluation/run_report.json`
- Runtime used for the recorded run: Python 3.12.14 (bundled environment runtime; machine-specific executable path omitted)
- Requests processed: 518
- Prediction rows written: 518
- Run result: 111 `COMPLETE`, 400 `INCOMPLETE`, 7 `NOT_APPLICABLE`
- Evidence files in manifest: 94
- Structured observations indexed: 2,545
- Model providers used by the prediction pipeline: none
- Model names used by the prediction pipeline: none
- Model calls: 0
- Input tokens: 0
- Output tokens: 0
- Total tokens: 0
- Average tokens per request: 0
- Estimated total model cost: $0.00
- Estimated model cost per request: $0.00

The predictions use local deterministic Python logic. The generation run made no model/API calls, so token and model-cost totals are zero. These figures do not include the AI coding assistant used to develop the program; no assistant token telemetry was exposed as part of the pipeline run.

The run completed output schema, row-count, sorted-ID, JSON-array, consecutive-step-number, allowed-operation/state, and evidence-reference validation. Eleven screenshots could not be OCR-read; the runtime reported that the `pytesseract` Python package was unavailable. The Tesseract executable's availability was not established. See `run_report.json` and the evaluation report.
