"""Northstar Shop deletion audit pipeline.

The implementation is deterministic and evidence driven. It treats operational
events as claims, and uses dated read-backs/snapshots to establish resource state.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shlex
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REQUIRED_REQUEST_COLUMNS = {"case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"}
OUTPUT_COLUMNS = ["case_id", "deletion_status", "steps_json"]
FIELDS = ("email", "phone", "email_hash", "user_id", "customer_reference", "subject_reference",
          "customer_email", "owner_email", "requester_email", "customer_phone", "owner_phone",
          "requester_phone", "full_name", "requester_name", "display_name", "name")
SYSTEM_BY_TABLE = {
    "customer_profiles": ("account_service", "USER_PROFILE"),
    "customer_search_documents": ("search_service", "SEARCH_INDEX_ENTRY"),
    "customer_analytics_profiles": ("analytics_platform", "ANALYTICS_PROFILE"),
    "customer_analytics_reports": ("analytics_platform", "ANALYTICS_PROFILE"),
    "support_records": ("support_platform", "SUPPORT_MESSAGE"),
    "customer_exports": ("export_service", "USER_EXPORT"),
    "connector_subscriptions": ("integration_service", "DATA_FLOW"),
    "backup_restore_entries": ("backup_service", "BACKUP_ARCHIVE"),
    "security_audit_records": ("security_service", "SECURITY_AUDIT_LOG"),
}
FINDING_ORDER = {"REPORT_REMAINING_RECORD": 0, "REPORT_EXPOSED_PII": 1,
                 "REPORT_ACTIVE_DATA_FLOW": 2, "REPORT_RESTORE_RISK": 3}
REMEDY_ORDER = {"DISABLE_DATA_FLOW": 0, "BLOCK_RESTORE": 1, "DELETE_RECORD": 2,
                "REDACT_RECORD": 3, "ANONYMIZE_RECORD": 4}
VERIFY_ORDER = {"VERIFY_RECORD_ABSENT": 0, "VERIFY_RECORD_PRESENT": 1,
                "VERIFY_RECORD_REDACTED": 2, "VERIFY_RECORD_ANONYMIZED": 3,
                "VERIFY_DATA_FLOW_DISABLED": 4, "VERIFY_RESTORE_BLOCKED": 5}
STEP_STATE = {
    "REPORT_REMAINING_RECORD": ("FINDING", "PRESENT"), "REPORT_EXPOSED_PII": ("FINDING", "PRESENT"),
    "REPORT_ACTIVE_DATA_FLOW": ("FINDING", "ACTIVE"), "REPORT_RESTORE_RISK": ("FINDING", "ACTIVE"),
    "DISABLE_DATA_FLOW": ("REMEDIATION", "DISABLED"), "BLOCK_RESTORE": ("REMEDIATION", "BLOCKED"),
    "DELETE_RECORD": ("REMEDIATION", "ABSENT"), "REDACT_RECORD": ("REMEDIATION", "REDACTED"),
    "ANONYMIZE_RECORD": ("REMEDIATION", "ANONYMIZED"), "VERIFY_RECORD_ABSENT": ("VERIFICATION", "ABSENT"),
    "VERIFY_RECORD_PRESENT": ("VERIFICATION", "PRESENT"), "VERIFY_RECORD_REDACTED": ("VERIFICATION", "REDACTED"),
    "VERIFY_RECORD_ANONYMIZED": ("VERIFICATION", "ANONYMIZED"), "VERIFY_DATA_FLOW_DISABLED": ("VERIFICATION", "DISABLED"),
    "VERIFY_RESTORE_BLOCKED": ("VERIFICATION", "BLOCKED"),
}


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def norm_email(value: Any) -> str:
    return str(value or "").strip().casefold()


def norm_phone(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def read_csv(path: Path) -> list[dict[str, str]]:
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                return list(csv.DictReader(f, dialect=dialect))
        except (UnicodeDecodeError, OSError) as exc:
            last_error = exc
    raise OSError(f"Could not read CSV {path}: {last_error}")


def validate_columns(rows: list[dict[str, str]], required: set[str], path: Path) -> None:
    present = set(rows[0]) if rows else set()
    missing = required - present
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")


def is_deletion_request(text: str) -> bool:
    t = text.casefold()
    # Explicitly reject common non-deletion intents before checking broad verbs.
    non_delete = [r"\bdo not (?:delete|close|erase)\b", r"\bwithout (?:deleting|removing|closing)\b",
                  r"\b(?:correct|fix|update) (?:my|the) (?:name|surname|address|email|phone|details)\b",
                  r"\b(?:reset|recover) (?:my )?(?:password|login|access)\b",
                  r"\b(?:marketing|promotional) (?:emails|messages|lists) only\b",
                  r"\b(?:unsubscribe|opt.?out)\b", r"\baccess (?:my )?(?:data|account)\b",
                  r"\b(?:export|copy) of my data\b", r"\bno quiero (?:eliminar|borrar)\b",
                  r"\bje ne veux pas (?:supprimer|effacer)\b", r"削除しない|削除しません",
                  r"\b(?:replace|change|update) (?:the |my )?(?:mobile number|phone number|email address)\b",
                  r"\bdownload my (?:account|personal|profile) (?:information|data)\b",
                  r"\bcopy of .*invoices\b", r"\bleave my (?:profile|account) .*in place\b"]
    if any(re.search(p, t) for p in non_delete):
        return False
    positive = [r"\bdelet(?:e|ion|ed|ing)\b", r"\beras(?:e|ed|ure)\b", r"\bremov(?:e|al|ed|ing)\b",
                r"\bclos(?:e|ure|ing) (?:my |this |the )?(?:account|profile)\b",
                r"\baccount.{0,30}(?:deletion|deleted|erasure|erased)\b",
                r"\b(?:supprim|effac|élimin|elimin|borr|exclu|apag)\w*\b",
                r"\b(?:suppression|supprimer|effacer|élimination)\b", r"削除|消去|抹消",
                r"영구\s*삭제|계정의\s*삭제",
                r"\b(?:eliminação|exclusão)\b", r"\b(?:account|personal data).{0,40}(?:delete|erase|remove)\b"]
    if re.search(r"\b(?:profile|account).{0,60}(?:gone|removed|deleted)\b", t):
        return True
    return any(re.search(p, t) for p in positive)


def flatten_values(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(flatten_values(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(flatten_values(v))
    elif obj is not None:
        out.append(str(obj))
    return out


@dataclass
class Observation:
    evidence_id: str
    observed_at: datetime | None
    system_id: str
    resource_id: str
    category: str
    data: dict[str, Any]
    source_kind: str = "file"
    captured_at: datetime | None = None


def infer_category(data: dict[str, Any], context: dict[str, Any]) -> tuple[str, str]:
    table = str(context.get("table", ""))
    collection = str(context.get("collection", ""))
    kind = str(data.get("record_type") or data.get("data_category") or data.get("category") or "")
    known = SYSTEM_BY_TABLE.get(table) or SYSTEM_BY_TABLE.get(collection)
    if known:
        return known[0], kind or known[1]
    cat = (kind or table or collection).upper()
    mappings = (("PROFILE_LOOKUP", ("account_service", "USER_PROFILE")),
                ("ACCOUNT_ADMIN", ("account_service", "USER_PROFILE")),
                ("CONTACT_LOOKUP", ("analytics_platform", "SECONDARY_IDENTIFIER")),
                ("CONTACT_QUERY", ("support_platform", "SECONDARY_IDENTIFIER")),
                ("ANALYTICS", ("analytics_platform", "ANALYTICS_PROFILE")),
                ("SEARCH", ("search_service", "SEARCH_INDEX_ENTRY")),
                ("SUPPORT", ("support_platform", "SUPPORT_MESSAGE")),
                ("EXPORT", ("export_service", "USER_EXPORT")),
                ("BACKUP", ("backup_service", "BACKUP_ARCHIVE")),
                ("RESTORE", ("backup_service", "BACKUP_ARCHIVE")),
                ("CONNECTOR", ("integration_service", "DATA_FLOW")),
                ("DATA_FLOW", ("integration_service", "DATA_FLOW")),
                ("AUDIT", ("security_service", "SECURITY_AUDIT_LOG")),
                ("TOMBSTONE", ("identity_service", "ACCOUNT_TOMBSTONE")),
                ("MARKETING", ("marketing_platform", "MARKETING_PROFILE")),
                ("DELIVERY", ("notification_service", "EMAIL_DELIVERY_LOG")))
    mappings = (("OBJECT_STORAGE", ("object_storage", "SUPPORT_ATTACHMENT")),
                ("SUPPORT_ATTACHMENT", ("support_platform", "SUPPORT_ATTACHMENT")),
                ("DELETED_CUSTOMER", ("identity_service", "ACCOUNT_TOMBSTONE")),
                ("DELETED_ACCOUNT", ("identity_service", "ACCOUNT_TOMBSTONE")),
                ("SECURITY_AUDIT", ("security_service", "SECURITY_AUDIT_LOG"))) + mappings
    for marker, result in mappings:
        if marker in cat:
            return result[0], result[1]
    system = str(data.get("system") or data.get("data_store") or context.get("system") or context.get("data_store") or
                 data.get("target_system") or data.get("source_system") or "unknown_system")
    default_categories = {"account_service": "USER_PROFILE", "search_service": "SEARCH_INDEX_ENTRY",
                          "analytics_platform": "ANALYTICS_PROFILE", "support_platform": "SUPPORT_MESSAGE",
                          "export_service": "USER_EXPORT", "backup_service": "BACKUP_ARCHIVE",
                          "integration_service": "DATA_FLOW", "security_service": "SECURITY_AUDIT_LOG",
                          "identity_service": "ACCOUNT_TOMBSTONE", "marketing_platform": "MARKETING_PROFILE",
                          "notification_service": "EMAIL_DELIVERY_LOG", "object_storage": "SUPPORT_ATTACHMENT"}
    collection_categories = {
        "PROFILES": "ANALYTICS_PROFILE", "CUSTOMER_ANALYTICS_REPORTS": "ANALYTICS_PROFILE",
        "SECURITY_AUDIT_EVENTS": "SECURITY_AUDIT_LOG", "DELETED_CUSTOMER_REFERENCES": "ACCOUNT_TOMBSTONE",
        "CUSTOMER_PROFILES": "USER_PROFILE", "PROFILE_LOOKUPS": "USER_PROFILE",
        "CUSTOMER_SEARCH_DOCUMENTS": "SEARCH_INDEX_ENTRY", "CUSTOMER_EXPORT_JOBS": "USER_EXPORT",
        "EXPORTS": "USER_EXPORT", "CONNECTORS": "DATA_FLOW", "CONNECTOR_SUBSCRIPTIONS": "DATA_FLOW",
        "RESTORE_ENTRIES": "BACKUP_ARCHIVE", "SUPPORT_RECORDS": "SUPPORT_MESSAGE",
    }
    if cat in collection_categories:
        return system, collection_categories[cat]
    if cat in {"MESSAGE_PII_SCAN", "ATTACHMENT_PII_SCAN", "MESSAGE_SCAN_STARTED", "ATTACHMENT_SCAN_STARTED",
               "DELETION_MARKER_CHECK"}:
        return system, default_categories.get(system, kind or "UNKNOWN")
    if cat in {"", "UNKNOWN", "OPERATIONAL_EVENT"} or cat.endswith(("_COMPLETED", "_READ", "_STARTED")):
        return system, default_categories.get(system, kind or "UNKNOWN")
    return system, kind or (cat if cat else "UNKNOWN")


def state_of(data: dict[str, Any], category: str) -> str:
    vals = {str(k).casefold(): str(v).strip().strip("\"'").casefold() for k, v in data.items() if v is not None}
    for k in ("status_code", "http_status"):
        if vals.get(k) == "404":
            return "ABSENT"
    if vals.get("rows", "").strip() == "0":
        return "ABSENT"
    for k in ("result", "status", "lookup_result", "state", "record_status"):
        v = vals.get(k, "")
        if v in {"not_found", "not found", "absent", "missing", "404"}:
            return "ABSENT"
        if v in {"anonymized", "redacted", "blocked", "disabled", "active", "identifiable", "found", "present"}:
            return v.upper()
    if vals.get("enabled", "") in {"true", "1", "yes", "enabled"}:
        return "ACTIVE"
    if vals.get("enabled", "") in {"false", "0", "no", "disabled"}:
        return "DISABLED"
    if vals.get("restore_allowed", "") in {"true", "1", "yes"}:
        return "ACTIVE"
    if vals.get("restore_allowed", "") in {"false", "0", "no"}:
        return "BLOCKED"
    if category.upper() == "BACKUP_ARCHIVE":
        if vals.get("deletion_block", "") in {"true", "1", "yes"}:
            return "BLOCKED"
        if vals.get("eligible", "") in {"true", "1", "yes"}:
            return "ACTIVE"
    return "PRESENT"


RESOURCE_ID_RE = re.compile(r"\b(?:account|search|analytics|support|audit_record|export|backup|data_flow|tombstone|marketing|object)_\d+\b", re.I)
KV_RE = re.compile(r"([A-Za-z_][\w.-]*)=(\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^\s|]+)")
SQL_TABLE_ALIASES = {
    "search_documents": ("search_service", "SEARCH_INDEX_ENTRY"),
    "analytics_profiles": ("analytics_platform", "ANALYTICS_PROFILE"),
    "analytics_reports": ("analytics_platform", "ANALYTICS_PROFILE"),
    "support_messages": ("support_platform", "SUPPORT_MESSAGE"),
    "support_attachments": ("support_platform", "SUPPORT_ATTACHMENT"),
    "export_jobs": ("export_service", "USER_EXPORT"),
    "marketing_profiles": ("marketing_platform", "MARKETING_PROFILE"),
    "backup_archives": ("backup_service", "BACKUP_ARCHIVE"),
}
TRACE_IDENTITY_FIELDS = ("user_id", "subject_reference", "subject_ref", "subject_key", "lookup_key",
                         "correlation_key", "matched_value", "email", "phone", "email_hash")


def table_system_category(table: str) -> tuple[str, str] | None:
    base = next((key for key in SYSTEM_BY_TABLE if table == key or table.startswith(key + "_")), None)
    if base:
        return SYSTEM_BY_TABLE[base]
    return next((value for key, value in SQL_TABLE_ALIASES.items()
                 if table == key or table.startswith(key + "_")), None)


def inherit_trace_identity(tokens: dict[str, Any], trace_context: dict[str, dict[str, Any]]) -> None:
    trace = str(tokens.get("trace_id") or tokens.get("requestId") or tokens.get("request_id") or "")
    if not trace:
        return
    context = trace_context.setdefault(trace, {})
    for key in TRACE_IDENTITY_FIELDS:
        if tokens.get(key) in (None, "", "null") and context.get(key) not in (None, "", "null"):
            tokens[key] = context[key]
    context.update({key: tokens[key] for key in TRACE_IDENTITY_FIELDS
                    if tokens.get(key) not in (None, "", "null")})


def pdf_evidence_records(body: str, filename: str) -> list[tuple[str, str, dict[str, Any]]]:
    lines = body.splitlines()
    record_type = "SUPPORT_ATTACHMENT" if "attachment" in filename.casefold() else "SUPPORT_MESSAGE"
    records = []
    for i, line in enumerate(lines):
        for match in RESOURCE_ID_RE.finditer(line):
            snippet = " ".join(lines[max(0, i - 4):min(len(lines), i + 10)])
            data: dict[str, Any] = {"resource_id": match.group(0), "text": snippet}
            emails = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", snippet)
            phones = re.findall(r"\+?\d[\d().\-\s]{7,}\d", snippet)
            if emails:
                data["email"] = emails[0]
            if phones:
                data["phone"] = phones[0]
            system, category = infer_category({"record_type": record_type, "system": "support_platform"}, {})
            records.append((system, category, data))
    return records


def parse_log_record(line: str) -> tuple[datetime | None, dict[str, Any]]:
    """Parse common timestamped JSON, key/value, and handover-log records."""
    stamp = re.search(r"20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?", line)
    observed = parse_time(stamp.group(0)) if stamp else None
    pipe = [part.strip() for part in line.split("|")]
    if len(pipe) >= 5:
        # Handover records may have a list marker before the timestamp.
        if not observed:
            observed = parse_time(pipe[0].lstrip("- •* "))
        resource = RESOURCE_ID_RE.search(pipe[2])
        if resource:
            return observed, {"system": pipe[1].strip(), "resource_id": resource.group(0),
                              "record_type": pipe[3].strip(), "result": pipe[4].strip(),
                              "subject_reference": pipe[5].strip() if len(pipe) > 5 else ""}
    # A JSON object may follow a timestamp/prefix. Preserve JSON field values.
    brace = line.find("{")
    if brace >= 0:
        try:
            obj = json.loads(line[brace:])
            if isinstance(obj, dict):
                data: dict[str, Any] = dict(obj)
                data.setdefault("recorded_at", observed.isoformat() if observed else None)
                return observed, data
        except (json.JSONDecodeError, TypeError):
            pass
    tokens: dict[str, Any] = {}
    for key, raw in KV_RE.findall(line):
        value = raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'" else raw
        tokens[key] = value
    # Some runtime exports wrap the actual key/value payload in message="...".
    nested = tokens.get("message")
    if isinstance(nested, str):
        for key, raw in KV_RE.findall(nested):
            value = raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'" else raw
            tokens.setdefault(key, value)
    service = re.search(r"\b(?:account|search|analytics|support|security|export|backup|integration|identity|marketing|notification|object)_(?:service|platform|storage)\b", line, re.I)
    if service:
        tokens.setdefault("system", service.group(0))
    event = tokens.get("event") or tokens.get("event_type")
    if event:
        tokens.setdefault("record_type", event)
    return observed, tokens


def build_observations(dataset: Path, manifest: list[dict[str, str]]) -> tuple[list[Observation], list[str]]:
    observations: list[Observation] = []
    warnings: list[str] = []

    def walk(obj: Any, file_id: str, captured: datetime | None, context: dict[str, Any], source_kind: str) -> None:
        if isinstance(obj, list):
            for item in obj:
                walk(item, file_id, captured, context, source_kind)
            return
        if not isinstance(obj, dict):
            return
        ctx = dict(context)
        for key in ("data_store", "system", "table", "collection", "region"):
            if obj.get(key) is not None:
                ctx[key] = obj[key]
        if obj.get("resource_id"):
            merged = dict(ctx)
            merged.update(obj)
            system, category = infer_category(obj, ctx)
            observed = next((parse_time(obj.get(k)) for k in ("observed_at", "recorded_at", "updated_at", "captured_at", "event_time") if parse_time(obj.get(k))), None) or captured
            observations.append(Observation(file_id, observed, system, str(obj["resource_id"]), category, merged, source_kind, captured))
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                child_ctx = dict(ctx)
                label = str(key)
                if label in {"account_service", "analytics_platform", "backup_service", "export_service",
                             "integration_service", "search_service", "security_service", "support_platform",
                             "identity_service", "marketing_platform", "notification_service"}:
                    child_ctx["system"] = label
                elif label in {"profile_lookups", "profiles", "exports", "connectors", "restore_entries",
                               "customer_profiles", "customer_search_documents", "customer_analytics_profiles",
                               "customer_analytics_reports", "support_records", "customer_exports",
                               "connector_subscriptions", "backup_restore_entries", "security_audit_records"}:
                    child_ctx["collection"] = label
                walk(value, file_id, captured, child_ctx, source_kind)

    for row in manifest:
        file_id, rel = row.get("file_id", ""), row.get("file_path", "")
        path = (dataset / rel).resolve()
        try:
            path.relative_to(dataset.resolve())
        except ValueError:
            warnings.append(f"Rejected manifest path outside dataset: {file_id}")
            continue
        if not path.is_file():
            warnings.append(f"Missing evidence file {file_id}: {rel}")
            continue
        captured = parse_time(row.get("captured_at"))
        suffix = path.suffix.casefold()
        try:
            if suffix == ".json":
                walk(json.loads(path.read_text(encoding="utf-8-sig")), file_id, captured, {}, "file")
            elif suffix == ".sql":
                # SQL evidence is untrusted input: execute only CREATE TABLE and INSERT statements
                # in an isolated in-memory database; ignore pragmas and all other statements.
                db = sqlite3.connect(":memory:")
                sql = path.read_text(encoding="utf-8-sig", errors="replace")
                for statement in sql.split(";"):
                    statement = statement.strip()
                    if re.match(r"(?is)^CREATE\s+TABLE\b", statement) or re.match(r"(?is)^INSERT\s+INTO\b", statement):
                        db.execute(statement)
                table_names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                for table in table_names:
                    known = table_system_category(table)
                    if not known:
                        continue
                    system, category = known
                    try:
                        # Table names came from the in-memory database created above; quote defensively.
                        cur = db.execute('SELECT * FROM "' + table.replace('"', '""') + '"')
                    except sqlite3.Error:
                        continue
                    cols = [d[0] for d in cur.description or []]
                    for vals in cur.fetchall():
                        data = dict(zip(cols, vals))
                        rid = data.get("resource_id")
                        if rid:
                            obs_time = parse_time(data.get("updated_at")) or captured
                        observations.append(Observation(file_id, obs_time, system, str(rid), category, data, "sql", captured))
                db.close()
            elif suffix in {".log", ".txt"}:
                trace_context: dict[str, dict[str, Any]] = {}
                for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    dt, tokens = parse_log_record(line)
                    inherit_trace_identity(tokens, trace_context)
                    rid_value = str(tokens.get("resource_id") or "")
                    rid_match = RESOURCE_ID_RE.search(rid_value)
                    rid = rid_match.group(0) if rid_match else ""
                    if not rid:
                        continue
                    system = tokens.get("service") or tokens.get("logger") or tokens.get("system") or "unknown_system"
                    if str(system).startswith("profile_service"):
                        system = "account_service"
                    elif str(system).startswith("support_replica"):
                        system = "support_platform"
                    tokens["system"] = system
                    event = tokens.get("event", "")
                    tokens.setdefault("record_type", event or "OPERATIONAL_EVENT")
                    cat_system, cat = infer_category(tokens, {})
                    if str(system).endswith(("_service", "_platform", "_storage")):
                        cat_system = str(system)
                    observations.append(Observation(file_id, dt or captured, cat_system, rid, cat, tokens, "log", captured))
            elif suffix == ".pdf":
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(str(path))
                    body = "\n".join(page.extract_text() or "" for page in reader.pages)
                    for system, cat, data in pdf_evidence_records(body, path.stem):
                        observations.append(Observation(file_id, captured, system, str(data["resource_id"]), cat, data, "pdf", captured))
                except Exception as exc:
                    warnings.append(f"PDF extraction failed for {file_id}: {exc}")
            elif suffix in {".png", ".jpg", ".jpeg"}:
                try:
                    import pytesseract
                    from PIL import Image
                    from pytesseract import Output
                    words = pytesseract.image_to_data(Image.open(path), output_type=Output.DICT, config="--psm 6")
                    grouped: dict[tuple[int, int, int], list[tuple[int, str]]] = defaultdict(list)
                    for i, word in enumerate(words.get("text", [])):
                        if str(word).strip():
                            k = (words["block_num"][i], words["par_num"][i], words["line_num"][i])
                            grouped[k].append((words["left"][i], str(word)))
                    lines = [" ".join(w for _, w in sorted(parts)) for parts in grouped.values()]
                    stem = path.stem.upper()
                    for line in lines:
                        m = re.search(r"\b(?:account|search|analytics|support|audit_record|export|backup|data_flow|tombstone|marketing|object)_\w+\b", line, re.I)
                        if not m:
                            continue
                        emails = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", line)
                        users = re.findall(r"\buser_\d+\b", line, re.I)
                        data = {"resource_id": m.group(0), "text": line}
                        if emails:
                            data["email"] = emails[0]
                        if users:
                            data["user_id"] = users[0]
                        system, cat = infer_category({"record_type": stem}, {})
                        observations.append(Observation(file_id, captured, system, m.group(0), cat, data, "image_ocr", captured))
                except Exception as exc:
                    warnings.append(f"OCR unavailable or failed for image evidence {file_id}: {exc}")
        except Exception as exc:
            warnings.append(f"Evidence parse failed for {file_id} ({rel}): {exc}")
    return observations, warnings


def resolve_identity(email: str, identities: list[dict[str, str]], audits: list[dict[str, str]],
                     cutoff: datetime | None = None) -> tuple[set[str], set[str], set[str], set[str]]:
    target = norm_email(email)
    user_ids: set[str] = set()
    for row in identities:
        updated = parse_time(row.get("updated_at"))
        if norm_email(row.get("email")) == target and (cutoff is None or updated is None or updated <= cutoff):
            user_ids.add(row.get("user_id", ""))
    for row in audits:
        event_time = parse_time(row.get("event_time"))
        if (row.get("field_name", "").casefold() == "email" and target in {norm_email(row.get("old_value")), norm_email(row.get("new_value"))}
                and (cutoff is None or event_time is None or event_time <= cutoff)):
            user_ids.add(row.get("user_id", ""))
    user_ids.discard("")
    emails: set[str] = {target}
    phones: set[str] = set()
    hashes: set[str] = set()
    for row in identities:
        updated = parse_time(row.get("updated_at"))
        if row.get("user_id") in user_ids and (cutoff is None or updated is None or updated <= cutoff):
            if row.get("email"):
                emails.add(norm_email(row["email"]))
            if row.get("phone"):
                phones.add(norm_phone(row["phone"]))
            if row.get("email_hash"):
                hashes.add(row["email_hash"].casefold())
    for row in audits:
        event_time = parse_time(row.get("event_time"))
        if row.get("user_id") not in user_ids or (cutoff is not None and event_time is not None and event_time > cutoff):
            continue
        field = row.get("field_name", "").casefold()
        for value in (row.get("old_value", ""), row.get("new_value", "")):
            if field == "email" and value:
                emails.add(norm_email(value))
            elif field == "phone" and value:
                phones.add(norm_phone(value))
            elif field in {"email_hash", "email_sha256"} and value:
                hashes.add(value.casefold())
    return user_ids, emails, phones, hashes


def observation_matches(obs: Observation, user_ids: set[str], emails: set[str], phones: set[str], hashes: set[str], resource_ids: set[str]) -> bool:
    if obs.resource_id in resource_ids:
        return True
    data = obs.data
    for key in ("user_id", "customer_reference", "subject_reference", "subject_ref"):
        if str(data.get(key, "")) in user_ids:
            return True
    for key in ("email", "customer_email", "owner_email", "requester_email", "lookup_key", "correlation_key",
                "subject_key", "matched_value", "subject_reference", "contact_email"):
        if norm_email(data.get(key)) in emails:
            return True
    for key in ("phone", "customer_phone", "owner_phone", "requester_phone"):
        n = norm_phone(data.get(key))
        if n and n in phones:
            return True
    for key in ("email_hash",):
        if str(data.get(key, "")).casefold() in hashes:
            return True
    # Search textual evidence for exact identifier tokens, never names or substrings.
    values = " ".join(flatten_values(data)).casefold()
    found_emails = {norm_email(x) for x in re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", values)}
    if found_emails & emails:
        return True
    found_hashes = {x.casefold() for x in re.findall(r"\b[a-f0-9]{32,128}\b", values)}
    if found_hashes & hashes:
        return True
    found_phones = {norm_phone(x) for x in re.findall(r"\+?\d[\d().\-\s]{7,}\d", values)}
    return bool({p for p in found_phones if p} & phones)


def required_action(category: str, data: dict[str, Any], rules: list[dict[str, str]],
                    cutoff: datetime | None = None) -> str:
    """Apply the participant-supplied category rule and its conditional scope."""
    rule = next((r for r in rules if str(r.get("data_category", "")).upper() == category.upper()), None)
    if not rule:
        return ""
    condition = str(rule.get("condition", "")).casefold()
    if category.upper() == "SECURITY_AUDIT_LOG" and "retention period" in condition:
        retention_until = parse_time(data.get("retention_until"))
        if retention_until is not None and cutoff and retention_until < cutoff:
            return ""
    if category.upper() == "LEGAL_HOLD_RECORD" and "legal hold" in condition:
        active = str(data.get("legal_hold_active", data.get("hold_status", ""))).casefold()
        if active not in {"true", "1", "yes", "active"}:
            return ""
    if category.upper() == "BACKUP_ARCHIVE" and "restore access" in condition:
        allowed = str(data.get("restore_allowed", "")).casefold()
        if allowed not in {"true", "false", "1", "0", "yes", "no"}:
            return ""
    return str(rule.get("required_action", "")).upper()


def direct_identifiers_present(data: dict[str, Any]) -> bool:
    keys = {str(k).casefold() for k, v in data.items() if v not in (None, "") and str(v).strip().casefold() not in {"null", "none", "n/a", "unknown"}}
    direct = {"email", "customer_email", "owner_email", "requester_email", "phone", "customer_phone",
              "owner_phone", "requester_phone", "email_hash", "full_name", "requester_name", "display_name", "name"}
    if keys & direct:
        return True
    # Explicit identifiers in log text or subject references remain linkable.
    text = " ".join(str(data.get(k, "")) for k in ("text", "subject_reference", "subject_ref", "lookup_key", "correlation_key", "matched_value"))
    return bool(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\+?\d[\d().\-\s]{7,}\d|\b[a-f0-9]{64}\b", text, re.I))


def classify_observation(obs: Observation, audit_at: datetime,
                         rules: list[dict[str, str]] | None = None) -> tuple[str, str] | None:
    if obs.captured_at and obs.captured_at > audit_at:
        return None
    if obs.observed_at and obs.observed_at > audit_at:
        return None
    state = state_of(obs.data, obs.category)
    category = obs.category.upper()
    action = required_action(category, obs.data, rules or [], audit_at)
    if category == "DATA_FLOW":
        return ("ACTIVE_FLOW", state) if state == "ACTIVE" else ("COMPLIANT_FLOW", state)
    if category == "BACKUP_ARCHIVE":
        return ("RESTORE_RISK", state) if state == "ACTIVE" else ("COMPLIANT_BACKUP", state)
    if state == "ABSENT":
        return "ABSENT", state
    if action == "DELETE":
        return "VIOLATION", state
    if action == "REDACT":
        return ("EXPOSED", state) if direct_identifiers_present(obs.data) else ("REDACTED", state)
    if action == "ANONYMIZE":
        # Stable user references are linkable; null identifiers indicate a de-identified record.
        linked = any(obs.data.get(k) not in (None, "") and str(obs.data.get(k)).strip().casefold() not in {"null", "none", "n/a"}
                     for k in ("email", "phone", "email_hash", "user_id", "customer_reference", "subject_reference", "subject_ref"))
        return ("EXPOSED", state) if linked else ("ANONYMIZED", state)
    if action == "RETAIN":
        return "RETAINED", state
    return "OBSERVED", state


def make_step(phase: str, system: str, resource: str, operation: str, state: str, evidence: str) -> dict[str, Any]:
    return {"step_no": 0, "phase": phase, "system_id": system or "unknown_system", "resource_id": resource or "unknown_resource",
            "operation": operation, "state": state, "evidence_id": evidence or ""}


def dependency_order(steps: list[dict[str, Any]], downstream_to_source: dict[str, set[str]]) -> list[dict[str, Any]]:
    """Topologically order same-operation copies before explicit source resources."""
    by_resource = {step["resource_id"]: step for step in steps}
    pending = set(by_resource)
    ordered: list[dict[str, Any]] = []
    while pending:
        ready = [rid for rid in pending if not any(rid in downstream_to_source.get(child, set()) for child in pending)]
        if not ready:  # A malformed/cyclic reference cannot justify unstable ordering.
            ready = list(pending)
        for rid in sorted(ready, key=lambda x: (by_resource[x]["system_id"], x)):
            ordered.append(by_resource[rid])
            pending.remove(rid)
    return ordered


def process_case(req: dict[str, str], identities: list[dict[str, str]], audits: list[dict[str, str]],
                 activity: list[dict[str, str]], observations: list[Observation],
                 rules: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    if not is_deletion_request(req.get("request_text", "")):
        return "NOT_APPLICABLE", []
    cutoff = parse_time(req.get("audit_at")) or datetime.max.replace(tzinfo=timezone.utc)
    user_ids, emails, phones, hashes = resolve_identity(req.get("email", ""), identities, audits, cutoff)
    resource_ids: set[str] = set()
    # Global event rows can extend identity links; event result is not treated as state proof.
    matched_events = []
    for event in activity:
        if (parse_time(event.get("event_time")) or datetime.min.replace(tzinfo=timezone.utc)) > cutoff:
            continue
        blob = " ".join((event.get("details", ""), event.get("resource_id", ""))).casefold()
        blob_emails = {norm_email(v) for v in re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", blob)}
        blob_hashes = {v.casefold() for v in re.findall(r"\b[a-f0-9]{32,128}\b", blob)}
        blob_users = set(re.findall(r"\buser_\d+\b", blob))
        blob_phones = {norm_phone(v) for v in re.findall(r"\+?\d[\d().\-\s]{7,}\d", blob)}
        if event.get("resource_id") and ((blob_emails & emails) or (blob_hashes & hashes) or
                                          (blob_users & user_ids) or (blob_phones & phones)):
            resource_ids.add(event.get("resource_id", ""))
            matched_events.append(event)
    matched = [o for o in observations if observation_matches(o, user_ids, emails, phones, hashes, resource_ids)
               and (o.observed_at is None or o.observed_at <= cutoff)
               and (o.captured_at is None or o.captured_at <= cutoff)]
    # Deduplicate identical file/resource/observation combinations.
    unique: dict[tuple[str, str, str, str], Observation] = {}
    for obs in matched:
        key = (obs.evidence_id, obs.system_id, obs.resource_id, obs.category)
        unique[key] = obs
    matched = list(unique.values())

    # Resource states can be duplicated across evidence captures. Keep the latest
    # read-back per resource/category and avoid letting an older bad snapshot trump a later clean one.
    latest: dict[tuple[str, str, str], Observation] = {}
    for obs in matched:
        key = (obs.system_id, obs.resource_id, obs.category)
        old = latest.get(key)
        if old is None or (obs.observed_at or datetime.min.replace(tzinfo=timezone.utc)) >= (old.observed_at or datetime.min.replace(tzinfo=timezone.utc)):
            latest[key] = obs
    # Recompute violation/steps only from each resource's most recent evidence.
    findings, remedies, verifies = [], {}, {}
    downstream_to_source: dict[str, set[str]] = defaultdict(set)
    for obs in latest.values():
        for key in ("source_resource_id", "source_resource", "parent_resource_id", "upstream_resource_id"):
            source = str(obs.data.get(key) or "").strip()
            if source and source != obs.resource_id:
                downstream_to_source[obs.resource_id].add(source)
    violation = False
    for obs in latest.values():
        result = classify_observation(obs, cutoff, rules)
        if not result:
            continue
        kind, _ = result
        action = required_action(obs.category, obs.data, rules, cutoff)
        if kind == "ABSENT":
            verifies[(obs.system_id, obs.resource_id, "VERIFY_RECORD_ABSENT")] = make_step("VERIFICATION", obs.system_id, obs.resource_id, "VERIFY_RECORD_ABSENT", "ABSENT", obs.evidence_id)
        elif kind == "RETAINED":
            verifies[(obs.system_id, obs.resource_id, "VERIFY_RECORD_PRESENT")] = make_step("VERIFICATION", obs.system_id, obs.resource_id, "VERIFY_RECORD_PRESENT", "PRESENT", obs.evidence_id)
        elif kind == "REDACTED":
            verifies[(obs.system_id, obs.resource_id, "VERIFY_RECORD_REDACTED")] = make_step("VERIFICATION", obs.system_id, obs.resource_id, "VERIFY_RECORD_REDACTED", "REDACTED", obs.evidence_id)
        elif kind == "ANONYMIZED":
            verifies[(obs.system_id, obs.resource_id, "VERIFY_RECORD_ANONYMIZED")] = make_step("VERIFICATION", obs.system_id, obs.resource_id, "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED", obs.evidence_id)
        elif kind == "COMPLIANT_FLOW":
            verifies[(obs.system_id, obs.resource_id, "VERIFY_DATA_FLOW_DISABLED")] = make_step("VERIFICATION", obs.system_id, obs.resource_id, "VERIFY_DATA_FLOW_DISABLED", "DISABLED", obs.evidence_id)
        elif kind == "COMPLIANT_BACKUP":
            verifies[(obs.system_id, obs.resource_id, "VERIFY_RESTORE_BLOCKED")] = make_step("VERIFICATION", obs.system_id, obs.resource_id, "VERIFY_RESTORE_BLOCKED", "BLOCKED", obs.evidence_id)
        else:
            violation = True
            if kind == "VIOLATION":
                fop, rop, rs, vop, vs = "REPORT_REMAINING_RECORD", "DELETE_RECORD", "ABSENT", "VERIFY_RECORD_ABSENT", "ABSENT"
            elif kind == "EXPOSED":
                fop = "REPORT_EXPOSED_PII"
                rop, rs, vop, vs = (("ANONYMIZE_RECORD", "ANONYMIZED", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED") if action == "ANONYMIZE" else ("REDACT_RECORD", "REDACTED", "VERIFY_RECORD_REDACTED", "REDACTED"))
            elif kind == "ACTIVE_FLOW":
                fop, rop, rs, vop, vs = "REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "DISABLED", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"
            elif kind == "RESTORE_RISK":
                fop, rop, rs, vop, vs = "REPORT_RESTORE_RISK", "BLOCK_RESTORE", "BLOCKED", "VERIFY_RESTORE_BLOCKED", "BLOCKED"
            else:
                continue
            findings.append(make_step("FINDING", obs.system_id, obs.resource_id, fop,
                                      "ACTIVE" if fop in {"REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"} else "PRESENT", obs.evidence_id))
            remedies[(obs.system_id, obs.resource_id, rop)] = make_step("REMEDIATION", obs.system_id, obs.resource_id, rop, rs, "")
            verifies[(obs.system_id, obs.resource_id, vop)] = make_step("VERIFICATION", obs.system_id, obs.resource_id, vop, vs, "")

    if not violation:
        # A complete decision needs positive current-state evidence, not an empty search.
        # If the corpus has no direct read-backs for this subject, remain conservatively incomplete.
        if not verifies:
            return "INCOMPLETE", []
        result_steps = sorted(verifies.values(), key=lambda s: (VERIFY_ORDER[s["operation"]], s["system_id"], s["resource_id"]))
        for n, step in enumerate(result_steps, 1):
            step["step_no"] = n
        return "COMPLETE", result_steps

    # For an incomplete case, include all evidence-backed findings, then actions
    # ordered by dependency class and operation order, then future checks.
    find_steps = sorted({(s["system_id"], s["resource_id"], s["operation"]): s for s in findings}.values(),
                        key=lambda s: (FINDING_ORDER[s["operation"]], s["system_id"], s["resource_id"]))
    rem_steps = []
    for operation in sorted({s["operation"] for s in remedies.values()}, key=lambda op: REMEDY_ORDER[op]):
        group = [s for s in remedies.values() if s["operation"] == operation]
        rem_steps.extend(dependency_order(group, downstream_to_source))
    ver_steps = sorted(verifies.values(), key=lambda s: (VERIFY_ORDER[s["operation"]], s["system_id"], s["resource_id"]))
    for step in ver_steps:
        step["evidence_id"] = ""
    all_steps = find_steps + rem_steps + ver_steps
    for n, step in enumerate(all_steps, 1):
        step["step_no"] = n
    return "INCOMPLETE", all_steps


def run(input_path: Path, dataset: Path, output_path: Path, report_path: Path | None = None) -> dict[str, Any]:
    requests = read_csv(input_path)
    identities = read_csv(dataset / "user_identities.csv")
    audits = read_csv(dataset / "user_audit_log.csv")
    activity = read_csv(dataset / "system_activity.csv")
    rules = read_csv(dataset / "deletion_rules.csv")
    manifest = read_csv(dataset / "evidence_files.csv")
    validate_columns(requests, REQUIRED_REQUEST_COLUMNS, input_path)
    validate_columns(identities, {"user_id", "email", "phone", "email_hash", "updated_at"}, dataset / "user_identities.csv")
    validate_columns(audits, {"audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"}, dataset / "user_audit_log.csv")
    validate_columns(activity, {"activity_id", "event_time", "event_type", "source_system", "target_system", "resource_id", "reported_result", "details"}, dataset / "system_activity.csv")
    validate_columns(rules, {"rule_id", "data_category", "condition", "required_action"}, dataset / "deletion_rules.csv")
    validate_columns(manifest, {"file_id", "file_path", "origin", "captured_at"}, dataset / "evidence_files.csv")
    observations, warnings = build_observations(dataset, manifest)
    outputs = []
    seen = set()
    for i, req in enumerate(requests, 1):
        cid = req["case_id"]
        if cid in seen:
            raise ValueError(f"Duplicate request case_id: {cid}")
        seen.add(cid)
        status, steps = process_case(req, identities, audits, activity, observations, rules)
        outputs.append({"case_id": cid, "deletion_status": status, "steps_json": json.dumps(steps, ensure_ascii=False, separators=(",", ":"))})
        if i % 100 == 0 or i == len(requests):
            print(f"Processed {i}/{len(requests)} requests")
    outputs.sort(key=lambda r: r["case_id"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(outputs)
    report = {"request_count": len(requests), "output_count": len(outputs),
              "statuses": {s: sum(x["deletion_status"] == s for x in outputs) for s in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE")},
              "manifest_count": len(manifest), "parsed_observations": len(observations), "warnings": warnings}
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Read back and validate the serialized contract.
    roundtrip = read_csv(output_path)
    request_ids = sorted(r["case_id"] for r in requests)
    output_ids = [r["case_id"] for r in roundtrip]
    if len(roundtrip) != len(requests) or (roundtrip and list(roundtrip[0]) != OUTPUT_COLUMNS) or output_ids != request_ids:
        raise ValueError("Output schema or row count validation failed")
    evidence_times = {r["file_id"]: parse_time(r.get("captured_at")) for r in manifest}
    evidence_times.update({r["activity_id"]: parse_time(r.get("event_time")) for r in activity})
    evidence_times.update({r["audit_id"]: parse_time(r.get("event_time")) for r in audits})
    valid_evidence = set(evidence_times)
    request_by_id = {r["case_id"]: r for r in requests}
    for row in roundtrip:
        val = json.loads(row["steps_json"])
        if row["deletion_status"] not in {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"} or not isinstance(val, list):
            raise ValueError(f"steps_json is not an array for {row['case_id']}")
        if row["deletion_status"] == "NOT_APPLICABLE" and val:
            raise ValueError(f"NOT_APPLICABLE must have no steps for {row['case_id']}")
        phases = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
        previous_phase = -1
        previous_operation_rank = -1
        cutoff = parse_time(request_by_id[row["case_id"]].get("audit_at"))
        for i, step in enumerate(val, 1):
            if step.get("step_no") != i:
                raise ValueError(f"Nonconsecutive step numbers for {row['case_id']}")
            if set(step) != {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}:
                raise ValueError(f"Invalid step fields for {row['case_id']}")
            expected = STEP_STATE.get(step["operation"])
            if not expected or (step["phase"], step["state"]) != expected:
                raise ValueError(f"Invalid operation/phase/state for {row['case_id']}")
            if phases[step["phase"]] < previous_phase:
                raise ValueError(f"Invalid phase ordering for {row['case_id']}")
            ranks = {"FINDING": FINDING_ORDER, "REMEDIATION": REMEDY_ORDER, "VERIFICATION": VERIFY_ORDER}
            rank = ranks[step["phase"]][step["operation"]]
            if phases[step["phase"]] != previous_phase:
                previous_operation_rank = -1
            if rank < previous_operation_rank:
                raise ValueError(f"Invalid operation ordering for {row['case_id']}")
            previous_phase = phases[step["phase"]]
            previous_operation_rank = rank
            if step["evidence_id"] and step["evidence_id"] not in valid_evidence:
                raise ValueError(f"Unknown evidence reference for {row['case_id']}")
            evidence_time = evidence_times.get(step["evidence_id"]) if step["evidence_id"] else None
            if step["evidence_id"] and evidence_time is None:
                raise ValueError(f"Evidence timestamp is unavailable for {row['case_id']}")
            if evidence_time and cutoff and evidence_time > cutoff:
                raise ValueError(f"Evidence reference is after audit_at for {row['case_id']}")
            if row["deletion_status"] == "COMPLETE" and (step["phase"] != "VERIFICATION" or step["evidence_id"] not in valid_evidence):
                raise ValueError(f"Complete verification lacks evidence for {row['case_id']}")
            if row["deletion_status"] == "INCOMPLETE":
                if step["phase"] == "FINDING" and step["evidence_id"] not in valid_evidence:
                    raise ValueError(f"Finding lacks valid evidence for {row['case_id']}")
                if step["phase"] != "FINDING" and step["evidence_id"] != "":
                    raise ValueError(f"Future action must have empty evidence_id for {row['case_id']}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("dataset/deletion_requests.csv"))
    parser.add_argument("--dataset", type=Path, default=Path("dataset"))
    parser.add_argument("--output", type=Path, default=Path("output.csv"))
    parser.add_argument("--report", type=Path, default=Path("code/evaluation/run_report.json"))
    args = parser.parse_args(argv)
    if not args.input.is_file():
        parser.error(f"Input file does not exist: {args.input}")
    try:
        report = run(args.input, args.dataset, args.output, args.report)
        print(json.dumps({k: v for k, v in report.items() if k != "warnings"}, indent=2))
        if report["warnings"]:
            print(f"Warnings: {len(report['warnings'])}; see {args.report}", file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
