import io
import re

import frappe
from frappe import _
from frappe.desk.query_report import (
    _export_query,
    get_report_doc,
)
from frappe.desk.utils import provide_binary_file
from openpyxl import load_workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)

from .monthly_she_performance import normalize_filters


REPORT_NAME = "Monthly SHE Performance"

MONTHS = (
    "January February March April May June July "
    "August September October November December"
).split()


def build_year_header_xlsx(filters=None):
    """Generate an authorized report export with merged year headings."""

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)

    if filters is None:
        filters = {}

    if not isinstance(filters, dict):
        frappe.throw(_("Invalid SHE report filters."))

    # Use the same report permissions as the standard download.
    report = get_report_doc(REPORT_NAME)

    frappe.permissions.can_export(
        report.ref_doctype,
        raise_exception=True,
    )

    normalized = normalize_filters(filters)

    permitted_filters = {
        "from_year": normalized.from_year,
        "to_year": normalized.to_year,
        "operation": (
            normalized.get("operation")
            or "Mining and Workshop"
        ),
    }

    if normalized.get("site"):
        permitted_filters["site"] = normalized.site

    if normalized.get("category"):
        permitted_filters["category"] = normalized.category

    # The standard report execution enforces site restrictions.
    params = frappe._dict({
        "report_name": REPORT_NAME,
        "file_format_type": "Excel",
        "filters": frappe.as_json(permitted_filters),
        "custom_columns": "[]",
        "include_indentation": 0,
        "include_filters": 0,
        "include_hidden_columns": 0,
        "visible_idx": [],
        "ignore_visible_idx": 1,
        "applied_filters": None,
    })

    _, extension, content = _export_query(
        params,
        {},
        populate_response=False,
    )

    if extension != "xlsx":
        frappe.throw(_("Expected an XLSX report export."))

    wb = load_workbook(io.BytesIO(content))
    ws = wb.active

    if ws.cell(1, 1).value != "Category":
        frappe.throw(_("Unexpected Excel report header."))

    # Validate all month columns before modifying the workbook.
    year_columns = {}

    for col in range(2, ws.max_column + 1):
        label = str(ws.cell(1, col).value or "").strip()

        match = re.fullmatch(
            r"(" + "|".join(MONTHS) + r")\s+(\d{4})",
            label,
        )

        if not match:
            frappe.throw(
                _("Unexpected month heading: {0}").format(label)
            )

        month_name, year_text = match.groups()
        year = int(year_text)

        year_columns.setdefault(year, []).append(
            (col, MONTHS.index(month_name) + 1)
        )

    expected_years = list(range(
        normalized.from_year,
        normalized.to_year + 1,
    ))

    if list(year_columns) != expected_years:
        frappe.throw(_("Unexpected Excel reporting years."))

    for year, positions in year_columns.items():
        if [month for _, month in positions] != list(range(1, 13)):
            frappe.throw(
                _("Incomplete monthly columns for {0}").format(year)
            )

    # Insert a dedicated year heading above the existing months.
    ws.insert_rows(1)

    black = Side(style="medium", color="111111")

    ws["A1"] = "Year"
    ws["A1"].font = Font(bold=True)
    ws["A1"].alignment = Alignment(horizontal="left")
    ws["A1"].fill = PatternFill(
        "solid", fgColor="D9D9D9"
    )
    ws["A1"].border = Border(
        left=black,
        right=black,
        top=black,
        bottom=black,
    )

    for index, (year, positions) in enumerate(year_columns.items()):
        start_col = positions[0][0]
        end_col = positions[-1][0]

        colour = "D9D9D9" if index % 2 == 0 else "A7C8E8"
        fill = PatternFill("solid", fgColor=colour)

        for col in range(start_col, end_col + 1):
            cell = ws.cell(1, col)
            cell.fill = fill
            cell.border = Border(
                top=black,
                bottom=black,
                left=black if col == start_col else Side(),
                right=black if col == end_col else Side(),
            )

        ws.merge_cells(
            start_row=1,
            start_column=start_col,
            end_row=1,
            end_column=end_col,
        )

        anchor = ws.cell(1, start_col)
        anchor.value = year
        anchor.font = Font(bold=True, size=12, color="111111")
        anchor.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )
        anchor.fill = fill

    ws.row_dimensions[1].height = 26

    # MONTHLY SHE UNIFORM MONTH WIDTH V1
    # Keep all month columns equal, including January 2025.
    # Do not change the Category column or any cell values.
    for positions in year_columns.values():
        for col_index, _ in positions:
            column_letter = ws.cell(
                row=2,
                column=col_index,
            ).column_letter

            ws.column_dimensions[column_letter].width = 18

    # END MONTHLY SHE UNIFORM MONTH WIDTH V1

    # Preserve the existing report's numeric values and styles.
    ws.freeze_panes = "B3"
    ws.print_title_rows = "1:2"
    ws.sheet_view.showGridLines = False

    output = io.BytesIO()
    wb.save(output)
    wb.close()

    return output.getvalue()


@frappe.whitelist()
def download_excel(filters=None):
    """Download the report without bypassing report/site permissions."""

    content = build_year_header_xlsx(filters)

    provide_binary_file(
        "Monthly SHE Performance - Year Headers",
        "xlsx",
        content,
    )
