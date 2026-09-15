# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import nowdate
from frappe.utils.xlsxutils import make_xlsx

from safety.safety.report.site_safe_days.site_safe_days import get_today_snapshot


@frappe.whitelist()
def download_snapshot_xlsx():
    """Export the current Safety Dashboard snapshot (same data and site
    grouping shown on screen) as an .xlsx workbook."""
    snapshot = get_today_snapshot()
    rows = snapshot.get("rows") or {}
    complex_by_site = snapshot.get("complex_by_site") or {}

    headers = [
        "Complex", "Site", "LTIFR Target", "LTIFR Actual", "Scratch Free Days",
        "LTI Free Days", "MTC Free Days", "FA Free Days", "Property Damage - TMM Free Days",
    ]

    def row_values(complex_label, site, row):
        row = row or {}
        return [
            complex_label,
            site,
            row.get("ltifr_target"),
            row.get("ltifr"),
            row.get("tif_days"),
            row.get("lti_free_days"),
            row.get("mtc_days"),
            row.get("fac_days"),
            row.get("pdi_days"),
        ]

    data = [headers]

    if "Company" in rows:
        data.append(row_values("Company", "Isambane Mining", rows["Company"]))

    sites = [site for site in rows if site != "Company"]
    sites.sort(key=lambda site: ((complex_by_site.get(site) or "Other"), site))

    for site in sites:
        data.append(row_values(complex_by_site.get(site) or "Other", site, rows[site]))

    xlsx = make_xlsx(data, "Safety Dashboard")
    frappe.response["filename"] = f"Safety-Dashboard-{nowdate()}.xlsx"
    frappe.response["filecontent"] = xlsx.getvalue()
    frappe.response["type"] = "binary"
