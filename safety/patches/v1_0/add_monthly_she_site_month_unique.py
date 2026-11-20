"""Enforce one Monthly SHE Data record per site and month."""

import frappe


DOCTYPE = "Monthly SHE Data"
TABLE = "tabMonthly SHE Data"
INDEX = "uniq_monthly_she_site_month"
COLUMNS = ["site", "reporting_month"]


def execute():
    """Create the unique index after DocType synchronization."""

    existing = frappe.db.sql(
        """
        SELECT
            NON_UNIQUE AS non_unique,
            COLUMN_NAME AS column_name
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        ORDER BY SEQ_IN_INDEX
        """,
        (TABLE, INDEX),
        as_dict=True,
    )

    if existing:
        actual_columns = [
            row.column_name for row in existing
        ]

        if (
            actual_columns != COLUMNS
            or any(int(row.non_unique) != 0 for row in existing)
        ):
            frappe.throw(
                "Monthly SHE unique index exists with an "
                "unexpected definition. Manual review required."
            )

        return

    duplicates = frappe.db.sql(
        """
        SELECT site, reporting_month, COUNT(*) AS total
        FROM `tabMonthly SHE Data`
        GROUP BY site, reporting_month
        HAVING COUNT(*) > 1
        LIMIT 1
        """,
        as_dict=True,
    )

    if duplicates:
        frappe.throw(
            "Duplicate Monthly SHE site/month records exist. "
            "Resolve duplicates before migration."
        )

    frappe.db.add_unique(
        DOCTYPE,
        COLUMNS,
        constraint_name=INDEX,
    )
