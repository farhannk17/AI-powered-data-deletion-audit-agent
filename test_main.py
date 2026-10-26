import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class IntentTests(unittest.TestCase):
    def test_deletion_requests_across_languages(self):
        self.assertTrue(main.is_deletion_request("Je demande la suppression définitive du compte."))
        self.assertTrue(main.is_deletion_request("このアカウントの完全な削除を依頼します。"))
        self.assertTrue(main.is_deletion_request("계정의 영구 삭제를 요청합니다."))

    def test_non_deletion_requests(self):
        self.assertFalse(main.is_deletion_request("My surname is misspelled. Can you correct it without removing any records?"))
        self.assertFalse(main.is_deletion_request("Please remove me from marketing lists only."))
        self.assertFalse(main.is_deletion_request("I need help resetting the login. Do not close the account."))


class IdentityAndTimeTests(unittest.TestCase):
    def test_historical_email_resolves_to_current_identity(self):
        identities = [{"user_id": "user_7", "email": "new@example.com", "phone": "+1 202 555 0100", "email_hash": "abc"}]
        audits = [{"user_id": "user_7", "field_name": "email", "old_value": "old@example.com", "new_value": "new@example.com"}]
        user_ids, emails, phones, hashes = main.resolve_identity("OLD@example.com", identities, audits)
        self.assertEqual(user_ids, {"user_7"})
        self.assertEqual(emails, {"old@example.com", "new@example.com"})
        self.assertIn("12025550100", phones)
        self.assertIn("abc", hashes)

    def test_future_identity_snapshot_is_not_added_after_cutoff(self):
        identities = [{"user_id": "user_7", "email": "new@example.com", "phone": "+1 202 555 0100",
                       "email_hash": "abc", "updated_at": "2026-09-03T00:00:00Z"}]
        audits = [{"user_id": "user_7", "field_name": "email", "old_value": "old@example.com",
                   "new_value": "new@example.com", "event_time": "2026-08-03T00:00:00Z"}]
        _, emails, phones, hashes = main.resolve_identity("old@example.com", identities, audits,
                                                           main.parse_time("2026-09-01T00:00:00Z"))
        self.assertEqual(emails, {"old@example.com", "new@example.com"})
        self.assertEqual(phones, set())
        self.assertEqual(hashes, set())

    def test_evidence_after_cutoff_is_ineligible(self):
        obs = main.Observation("evidence_1", datetime(2026, 9, 2, tzinfo=timezone.utc), "account_service", "account_7",
                               "USER_PROFILE", {"email": "a@example.com", "resource_id": "account_7"})
        cutoff = datetime(2026, 9, 1, tzinfo=timezone.utc)
        self.assertIsNone(main.classify_observation(obs, cutoff))

    def test_evidence_captured_after_cutoff_is_ineligible_even_if_record_is_old(self):
        obs = main.Observation("evidence_1", datetime(2026, 8, 1, tzinfo=timezone.utc), "account_service", "account_7",
                               "USER_PROFILE", {"email": "a@example.com"}, "file",
                               datetime(2026, 9, 2, tzinfo=timezone.utc))
        self.assertIsNone(main.classify_observation(obs, datetime(2026, 9, 1, tzinfo=timezone.utc)))

    def test_log_parser_unquotes_identifiers_and_reads_zero_row_lookup(self):
        dt, data = main.parse_log_record(
            '2026-09-01T12:00:00Z level=INFO service=account_service trace_id=t1 '
            'resource_id=account_7 event=profile_lookup_completed rows="0" http_status="404" '
            'correlation_key="a@example.com"')
        self.assertEqual(main.norm_email(data["correlation_key"]), "a@example.com")
        self.assertEqual(main.state_of(data, "USER_PROFILE"), "ABSENT")
        self.assertEqual(main.infer_category(data, {})[0], "account_service")

    def test_handover_pipe_parser_accepts_bullet_prefix(self):
        dt, data = main.parse_log_record(
            "- 2026-10-01T12:00:00Z | account_service | account_7 | USER_PROFILE | NOT_FOUND | a@example.com")
        self.assertEqual(dt, main.parse_time("2026-10-01T12:00:00Z"))
        self.assertEqual(data["resource_id"], "account_7")
        self.assertEqual(data["subject_reference"], "a@example.com")
        self.assertEqual(main.state_of(data, data["record_type"]), "ABSENT")

    def test_service_names_are_not_parsed_as_resource_ids(self):
        _, data = main.parse_log_record("2026-09-01T12:00:00Z service=account_service event=health_check")
        self.assertNotIn("resource_id", data)
        self.assertIsNone(main.RESOURCE_ID_RE.search("account_service"))

    def test_trace_identity_is_carried_only_within_same_trace(self):
        context = {}
        first = {"trace_id": "trace-a", "subject_key": "a@example.com"}
        main.inherit_trace_identity(first, context)
        sibling = {"trace_id": "trace-a", "resource_id": "data_flow_17"}
        main.inherit_trace_identity(sibling, context)
        unrelated = {"trace_id": "trace-b", "resource_id": "data_flow_18"}
        main.inherit_trace_identity(unrelated, context)
        self.assertEqual(sibling["subject_key"], "a@example.com")
        self.assertNotIn("subject_key", unrelated)

    def test_generic_replica_table_aliases(self):
        self.assertEqual(main.table_system_category("search_documents_primary"),
                         ("search_service", "SEARCH_INDEX_ENTRY"))
        self.assertEqual(main.table_system_category("customer_profiles_failover_replica"),
                         ("account_service", "USER_PROFILE"))
        self.assertIsNone(main.table_system_category("unrelated_table"))

    def test_pdf_context_links_identifier_on_neighboring_lines(self):
        records = main.pdf_evidence_records(
            "Support reference / support_17\nCustomer name\nA. Person\nEmail\na.person@example.com\nPhone\n+1 202 555 0100",
            "delivery_attachment")
        self.assertEqual(len(records), 1)
        system, category, data = records[0]
        self.assertEqual((system, category), ("support_platform", "SUPPORT_ATTACHMENT"))
        self.assertEqual(data["email"], "a.person@example.com")

    def test_unlinked_text_does_not_match_email_substrings(self):
        obs = main.Observation("e1", None, "support_platform", "support_1", "SUPPORT_MESSAGE",
                               {"text": "alex@example.com.au"})
        self.assertFalse(main.observation_matches(obs, set(), {"alex@example.com"}, set(), set(), set()))


class PolicyTests(unittest.TestCase):
    def test_policy_action_comes_from_supplied_rules(self):
        rules = [{"data_category": "USER_PROFILE", "condition": "Always", "required_action": "REDACT"}]
        action = main.required_action("USER_PROFILE", {"email": "a@example.com"}, rules)
        self.assertEqual(action, "REDACT")

    def test_collection_aliases_and_null_values_are_classified(self):
        self.assertEqual(main.infer_category({"system": "analytics_platform"}, {"collection": "profiles"}),
                         ("analytics_platform", "ANALYTICS_PROFILE"))
        data = {"email": "null", "phone": "null", "email_hash": "null", "audience_cohort": "general_shopper"}
        obs = main.Observation("e1", None, "analytics_platform", "analytics_1", "ANALYTICS_PROFILE", data)
        self.assertEqual(main.classify_observation(obs, main.parse_time("2026-09-01T00:00:00Z"),
                                                   [{"data_category": "ANALYTICS_PROFILE", "condition": "Attributable", "required_action": "ANONYMIZE"}])[0],
                         "ANONYMIZED")

    def test_backup_candidate_fields_show_restore_risk(self):
        self.assertEqual(main.state_of({"eligible": "true", "deletion_block": "false"}, "BACKUP_ARCHIVE"), "ACTIVE")
        self.assertEqual(main.state_of({"eligible": "true", "deletion_block": "true"}, "BACKUP_ARCHIVE"), "BLOCKED")

    def test_dependency_order_places_copy_before_its_source(self):
        source = main.make_step("REMEDIATION", "account_service", "account_1", "DELETE_RECORD", "ABSENT", "")
        copy = main.make_step("REMEDIATION", "search_service", "search_1", "DELETE_RECORD", "ABSENT", "")
        ordered = main.dependency_order([source, copy], {"search_1": {"account_1"}})
        self.assertEqual([step["resource_id"] for step in ordered], ["search_1", "account_1"])


if __name__ == "__main__":
    unittest.main()
