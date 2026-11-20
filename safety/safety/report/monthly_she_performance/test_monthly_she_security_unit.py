"""Isolated Monthly SHE security tests. No site or database required."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from safety.safety.doctype.monthly_she_data import (
    monthly_she_data as she,
)
from safety.safety.report.monthly_she_performance import (
    monthly_she_performance as report,
)
from safety.safety.report.monthly_she_performance import (
    monthly_she_excel as excel_export,
)


class TestMonthlySHEPermissions(unittest.TestCase):

    def test_no_safety_role_has_no_sites(self):
        with patch.object(she, "_user_roles", return_value=set()):
            result = she._authorized_sites("test@example.invalid")

        self.assertEqual(result, set())

    def test_administrator_site_resolution(self):
        self.assertIsNone(she._authorized_sites("Administrator"))

    def test_unassigned_user_query_denied(self):
        with patch.object(she, "_authorized_sites", return_value=set()):
            result = she.get_permission_query_conditions(
                "test@example.invalid"
            )

        self.assertEqual(result, "1=0")

    def test_administrator_query_unrestricted(self):
        self.assertEqual(
            she.get_permission_query_conditions("Administrator"),
            "",
        )

    def test_authorized_query_contains_only_assigned_site(self):
        fake_db = MagicMock()
        fake_db.escape.side_effect = lambda value: f"'{value}'"

        with (
            patch.object(she, "_authorized_sites", return_value={"Gwab"}),
            patch.object(she.frappe, "db", fake_db, create=True),
        ):
            result = she.get_permission_query_conditions(
                "test@example.invalid"
            )

        self.assertIn("'Gwab'", result)
        self.assertNotIn("Klipfontein", result)

    def test_document_access_restricted_by_site(self):
        doc = SimpleNamespace(site="Klipfontein", name="TEST")

        with (
            patch.object(
                she, "_user_roles", return_value={"Safety User"}
            ),
            patch.object(
                she, "_authorized_sites", return_value={"Gwab"}
            ),
        ):
            self.assertFalse(
                she.has_permission(
                    doc, "read", user="test@example.invalid"
                )
            )

    def test_document_access_allowed_for_assigned_site(self):
        doc = SimpleNamespace(site="Gwab", name="TEST")

        with (
            patch.object(
                she, "_user_roles", return_value={"Safety User"}
            ),
            patch.object(
                she, "_authorized_sites", return_value={"Gwab"}
            ),
        ):
            self.assertTrue(
                she.has_permission(
                    doc, "read", user="test@example.invalid"
                )
            )

    def test_document_delete_denied(self):
        doc = SimpleNamespace(site="Gwab", name="TEST")

        with (
            patch.object(
                she, "_user_roles", return_value={"Safety User"}
            ),
            patch.object(
                she, "_authorized_sites", return_value={"Gwab"}
            ),
        ):
            self.assertFalse(
                she.has_permission(
                    doc, "delete", user="test@example.invalid"
                )
            )

    def test_verified_document_write_denied(self):
        doc = SimpleNamespace(
            site="Gwab",
            name="TEST",
            is_new=lambda: False,
        )

        fake_db = MagicMock()
        fake_db.get_value.return_value = "Verified"

        with (
            patch.object(
                she, "_user_roles", return_value={"Safety User"}
            ),
            patch.object(
                she, "_authorized_sites", return_value={"Gwab"}
            ),
            patch.object(she.frappe, "db", fake_db, create=True),
        ):
            allowed = she.has_permission(
                doc, "write", user="test@example.invalid"
            )

        self.assertFalse(allowed)

    def test_draft_to_verified_permission_is_not_preemptively_blocked(self):
        doc = SimpleNamespace(
            site="Gwab",
            name="TEST",
            is_new=lambda: False,
        )

        fake_db = MagicMock()
        fake_db.get_value.return_value = "Draft"

        with (
            patch.object(
                she, "_user_roles", return_value={"Safety Manager"}
            ),
            patch.object(
                she, "_authorized_sites", return_value={"Gwab"}
            ),
            patch.object(she.frappe, "db", fake_db, create=True),
        ):
            allowed = she.has_permission(
                doc, "write", user="manager@example.invalid"
            )

        self.assertTrue(allowed)


class TestMonthlySHEReportSecurity(unittest.TestCase):

    def test_unauthorized_report_site_rejected(self):
        with (
            patch(
                "safety.safety.report.site_safe_days.site_safe_days."
                "resolve_safety_dashboard_sites",
                return_value=["Gwab"],
            ),
            patch.object(
                report.frappe,
                "throw",
                side_effect=frappe.PermissionError(
                    "Unauthorized site"
                ),
            ) as deny,
        ):
            with self.assertRaises(frappe.PermissionError):
                report.resolve_report_sites({
                    "site": "Klipfontein",
                    "operation": "Mining and Workshop",
                })

            deny.assert_called_once()
            assert deny.call_args.args[1] is frappe.PermissionError

    def test_report_uses_authorized_site_resolver(self):
        with patch(
            "safety.safety.report.site_safe_days.site_safe_days."
            "resolve_safety_dashboard_sites",
            return_value=["Gwab"],
        ) as resolver:
            result = report.resolve_report_sites({
                "site": "Gwab",
                "operation": "Mining and Workshop",
            })

        self.assertEqual(result, ["Gwab"])
        resolver.assert_called_once_with(
            requested=["Gwab"],
            operation="Mining and Workshop",
        )


class TestMonthlySHEExcelSecurity(unittest.TestCase):

    def test_export_denied_without_report_permission(self):
        with (
            patch.object(
                excel_export,
                "get_report_doc",
                side_effect=frappe.PermissionError(
                    "Report access denied"
                ),
            ),
            patch.object(excel_export, "_export_query") as exporter,
        ):
            with self.assertRaises(frappe.PermissionError):
                excel_export.build_year_header_xlsx({})

            exporter.assert_not_called()

    def test_export_denied_without_export_permission(self):
        fake_report = SimpleNamespace(
            ref_doctype="Incident Report"
        )

        with (
            patch.object(
                excel_export,
                "get_report_doc",
                return_value=fake_report,
            ),
            patch.object(
                excel_export.frappe.permissions,
                "can_export",
                side_effect=frappe.PermissionError(
                    "Export access denied"
                ),
            ) as permission_check,
            patch.object(excel_export, "_export_query") as exporter,
        ):
            with self.assertRaises(frappe.PermissionError):
                excel_export.build_year_header_xlsx({})

            permission_check.assert_called_once_with(
                "Incident Report",
                raise_exception=True,
            )
            exporter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
