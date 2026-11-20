from collections import defaultdict
from datetime import date

import frappe
from frappe import _
from frappe.utils import getdate


# ---------------------------------------------------------
# REPORT CONFIGURATION
# ---------------------------------------------------------

CATEGORY_TYPES = {
    "LTI": {
        "Lost Time Injury (LTI)",
    },
    "First Aid Case": {
        "FA",
        "First Aid Case (FAC)",
    },
    "Medical Treatment": {
        "Medical Treatment Case (MTC)",
    },
    "TMM Incidents": {
        "Trackless Mobile Machinery (TMM)",
    },
    "Property Damage": {
        "Property Damage",
    },
    # MONTHLY SHE FOG CLASSIFICATION V1
    "FOG": {
        "Fall of Ground (FOG)",
    },
    # MONTHLY SHE SEPARATE INJURY CATEGORIES V1
    "Fatality": {
        "FATAL",
        "Fatality",
    },
    "NIHL": {
        "NIHL",
    },
    "Occupational Disease": {
        "Ocuupational Disease",
        "Occupational Disease",
    },
}

INJURY_TYPES = {
    "Lost Time Injury (LTI)",
    "FA",
    "First Aid Case (FAC)",
    "Medical Treatment Case (MTC)",
}

LTI_TYPES = {
    "Lost Time Injury (LTI)",
}

PDI_TYPES = {
    "Trackless Mobile Machinery (TMM)",
    "Property Damage",
}

STATUS_NAMES = {
    0: "Draft",
    1: "Submitted",
}


# ---------------------------------------------------------
# MONTH HELPERS
# ---------------------------------------------------------

def shift_month(year, month, offset):
    index = year * 12 + month - 1 + offset
    return index // 12, index % 12 + 1


def month_field(year, month):
    return f"m_{year}_{month:02d}"


def get_months(from_year, to_year):
    return [
        (year, month)
        for year in range(from_year, to_year + 1)
        for month in range(1, 13)
    ]


def get_rolling_months(year, month):
    return [
        shift_month(year, month, offset)
        for offset in range(-11, 1)
    ]


def complete_sum(values):
    if not values or any(value is None for value in values):
        return None

    return round(sum(values), 2)


def calculate_rate(count, hours):
    if hours is None or hours <= 0:
        return None

    return round((count * 1000000) / hours, 2)


# ---------------------------------------------------------
# SITE AUTHORIZATION
# ---------------------------------------------------------

def resolve_report_sites(filters):
    operation = (
        filters.get("operation")
        or "Mining and Workshop"
    )

    if operation not in (
        "Mining",
        "Workshop",
        "Mining and Workshop",
    ):
        frappe.throw(_("Invalid operation selected."))

    selected_site = filters.get("site")

    requested = (
        [selected_site]
        if selected_site
        else None
    )

    from safety.safety.report.site_safe_days.site_safe_days import (
        resolve_safety_dashboard_sites,
    )

    sites = resolve_safety_dashboard_sites(
        requested=requested,
        operation=operation,
    )

    if not sites:
        frappe.throw(
            _("No authorized sites are available for this report.")
        )

    if selected_site and selected_site not in sites:
        frappe.throw(
            _("You are not authorized to report on this site."),
            frappe.PermissionError,
        )

    return sorted(set(sites))


# ---------------------------------------------------------
# REPORT FILTER VALIDATION
# ---------------------------------------------------------

def normalize_filters(filters):
    filters = frappe._dict(filters or {})

    try:
        from_year = int(filters.get("from_year") or 2025)
        to_year = int(filters.get("to_year") or 2026)
    except (TypeError, ValueError):
        frappe.throw(_("Enter valid reporting years."))

    if from_year < 2000 or to_year > 2100:
        frappe.throw(_("Reporting years must be between 2000 and 2100."))

    if from_year > to_year:
        frappe.throw(_("From Year cannot be after To Year."))

    if to_year - from_year > 9:
        frappe.throw(_("Maximum reporting range is 10 years."))

    filters.from_year = from_year
    filters.to_year = to_year

    return filters


# ---------------------------------------------------------
# INCIDENT DATA
# ---------------------------------------------------------

def fetch_incidents(sites, start_date, end_date):
    start_datetime = f"{start_date} 00:00:00"
    end_datetime = f"{end_date} 23:59:59"

    incidents = frappe.get_all(
        "Incident Report",
        filters={
            "site": ["in", sites],
            "datetime_incident": [
                "between",
                [start_datetime, end_datetime],
            ],
            "docstatus": ["in", [0, 1]],
        },
        fields=[
            "name",
            "site",
            "datetime_incident",
            "docstatus",
        ],
        limit_page_length=0,
    )

    names = [row.name for row in incidents]

    types_by_parent = defaultdict(set)

    if names:
        children = frappe.get_all(
            "Classify Type of Incident",
            filters={
                "parent": ["in", names],
                "parenttype": "Incident Report",
                "parentfield": "select_type_of_incident",
            },
            fields=[
                "parent",
                "type_of_incident",
            ],
            limit_page_length=0,
        )

        for child in children:
            if child.type_of_incident:
                types_by_parent[child.parent].add(
                    child.type_of_incident.strip()
                )

    return incidents, types_by_parent


def aggregate_incidents(incidents, types_by_parent):
    category_sets = defaultdict(set)
    injury_sets = defaultdict(set)
    lti_sets = defaultdict(set)
    pdi_sets = defaultdict(set)
    status_incident_sets = defaultdict(set)

    for incident in incidents:
        incident_name = incident.name

        types = types_by_parent.get(
            incident_name,
            set(),
        )

        status = STATUS_NAMES.get(
            int(incident.docstatus),
        )

        if not status:
            continue

        incident_date = getdate(
            incident.datetime_incident
        )

        month_key = (
            incident_date.year,
            incident_date.month,
        )

        status_incident_sets[status].add(
            incident_name
        )

        for category, accepted_types in CATEGORY_TYPES.items():
            if types.intersection(accepted_types):
                category_sets[
                    (month_key, category, status)
                ].add(incident_name)

        if types.intersection(INJURY_TYPES):
            injury_sets[
                (month_key, status)
            ].add(incident_name)

        if types.intersection(LTI_TYPES):
            lti_sets[
                (month_key, status)
            ].add(incident_name)

        if types.intersection(PDI_TYPES):
            pdi_sets[
                (month_key, status)
            ].add(incident_name)

    return (
        category_sets,
        injury_sets,
        lti_sets,
        pdi_sets,
        status_incident_sets,
    )


# ---------------------------------------------------------
# VERIFIED MONTHLY SHE DATA
# ---------------------------------------------------------

def fetch_verified_monthly_data(
    sites,
    start_date,
    end_date,
):
    records = frappe.get_all(
        "Monthly SHE Data",
        filters={
            "site": ["in", sites],
            "reporting_month": [
                "between",
                [start_date, end_date],
            ],
            "verification_status": ["in", ["Draft", "Verified"]],
        },
        fields=[
            "site",
            "reporting_month",
            "hours_recorded",
            "hours_worked",
            "workforce_recorded",
            "workforce",
        ],
        limit_page_length=0,
    )

    by_site_month = {}

    for row in records:
        reporting_month = getdate(
            row.reporting_month
        )

        key = (
            row.site,
            reporting_month.year,
            reporting_month.month,
        )

        if key in by_site_month:
            frappe.throw(
                _("Duplicate verified Monthly SHE Data found.")
            )

        by_site_month[key] = row

    hours_by_month = {}
    workforce_by_month = {}
    # MONTHLY SHE PARTIAL AGGREGATION V1
    complete_hours_by_month = {}

    start_year = getdate(start_date).year
    start_month = getdate(start_date).month

    end_year = getdate(end_date).year
    end_month = getdate(end_date).month

    current = (start_year, start_month)
    final = (end_year, end_month)

    while current <= final:
        year, month = current

        site_rows = [
            by_site_month.get((site, year, month))
            for site in sites
        ]

        hours_complete = all(
            row is not None
            and row.hours_recorded
            and row.hours_worked is not None
            for row in site_rows
        )

        workforce_complete = all(
            row is not None
            and row.workforce_recorded
            and row.workforce is not None
            for row in site_rows
        )

        key = (year, month)

        # Sum only explicitly recorded monthly inputs.
        # Missing values are never treated as zero.
        recorded_hours_rows = [
            row for row in site_rows
            if row is not None
            and row.hours_recorded
            and row.hours_worked is not None
        ]

        recorded_workforce_rows = [
            row for row in site_rows
            if row is not None
            and row.workforce_recorded
            and row.workforce is not None
        ]

        hours_by_month[key] = (
            round(
                sum(
                    float(row.hours_worked)
                    for row in recorded_hours_rows
                ),
                2,
            )
            if recorded_hours_rows
            else None
        )

        workforce_by_month[key] = (
            sum(
                int(row.workforce)
                for row in recorded_workforce_rows
            )
            if recorded_workforce_rows
            else None
        )

        # Rate denominators require complete coverage.
        # Partial hours may be displayed but must not
        # produce misleading LTIFR or TIFR values.
        complete_hours_by_month[key] = (
            hours_by_month[key]
            if hours_complete
            else None
        )

        current = shift_month(year, month, 1)

    return (
        hours_by_month,
        workforce_by_month,
        complete_hours_by_month,
    )


# ---------------------------------------------------------
# REPORT COLUMNS
# ---------------------------------------------------------

def get_columns(months):
    columns = [
        {
            "label": _("Category"),
            "fieldname": "category",
            "fieldtype": "Data",
            "width": 250,
            "pinned": 1,
        }
    ]

    for year, month in months:
        columns.append({
            "label": date(year, month, 1).strftime("%B %Y"),
            "fieldname": month_field(year, month),
            "fieldtype": "Float",
            "precision": 2,
            "width": 200,
        })

    return columns


# ---------------------------------------------------------
# REPORT ROW BUILDING
# ---------------------------------------------------------

def build_rows(
    months,
    category_sets,
    injury_sets,
    lti_sets,
    pdi_sets,
    hours_by_month,
    workforce_by_month,
    complete_hours_by_month,
):
    data = []

    def append_row(label, getter):
        row = {"category": label}

        for year, month in months:
            row[month_field(year, month)] = getter(
                year,
                month,
            )

        data.append(row)

    def category_count(category, year, month, status):
        return len(
            category_sets.get(
                ((year, month), category, status),
                set(),
            )
        )

    def injury_count(year, month, status):
        return len(
            injury_sets.get(
                ((year, month), status),
                set(),
            )
        )

    def lti_count(year, month, status):
        return len(
            lti_sets.get(
                ((year, month), status),
                set(),
            )
        )

    def pdi_count(year, month, status):
        return len(
            pdi_sets.get(
                ((year, month), status),
                set(),
            )
        )

    def combined_count(counter, year, month):
        return sum(
            len(counter.get(((year, month), status), set()))
            for status in ("Draft", "Submitted")
        )

    # 1. Incident categories with status separation.
    for category in CATEGORY_TYPES:
        for status in ("Draft", "Submitted"):
            append_row(
                f"{category} - {status}",
                lambda y, m, c=category, s=status:
                    category_count(c, y, m, s),
            )

        append_row(
            f"{category} - Total",
            lambda y, m, c=category:
                category_count(c, y, m, "Draft")
                + category_count(c, y, m, "Submitted"),
        )


    # 2. Total injuries.
    for status in ("Draft", "Submitted"):
        append_row(
            f"Total Injuries - {status}",
            lambda y, m, s=status:
                injury_count(y, m, s),
        )

    append_row(
        "Total Injuries",
        lambda y, m:
            combined_count(injury_sets, y, m),
    )

    # 3. Cumulative total injuries, reset each calendar year.
    for status in ("Draft", "Submitted", "Total"):
        def cumulative_injuries(y, m, selected_status=status):
            selected = (
                ("Draft", "Submitted")
                if selected_status == "Total"
                else (selected_status,)
            )

            return sum(
                injury_count(y, month, s)
                for month in range(1, m + 1)
                for s in selected
            )

        append_row(
            f"Cumm Total Injuries - {status}",
            cumulative_injuries,
        )

    # 4. Total PDI: distinct incidents across TMM and Property Damage.
    for status in ("Draft", "Submitted"):
        append_row(
            f"Total PDI - {status}",
            lambda y, m, s=status:
                pdi_count(y, m, s),
        )

    append_row(
        "Total PDI",
        lambda y, m:
            combined_count(pdi_sets, y, m),
    )

    data.append({"category": ""})

    # 5. Monthly hours and workforce.
    append_row(
        "Hours Worked",
        lambda y, m: hours_by_month.get((y, m)),
    )

    def ytd_hours(y, m):
        return complete_sum([
            hours_by_month.get((y, month))
            for month in range(1, m + 1)
        ])

    append_row(
        "Cumm Hours YTD",
        ytd_hours,
    )

    def rolling_hours(y, m):
        # MONTHLY SHE PARTIAL ROLLING HOURS DISPLAY V1
        # Display available hours in the preceding 12 months.
        # This is for display only, not LTIFR or TIFR.
        if hours_by_month.get((y, m)) is None:
            return None

        values = [
            hours_by_month.get(key)
            for key in get_rolling_months(y, m)
        ]

        return round(
            sum(
                float(value)
                for value in values
                if value is not None
            ),
            2,
        )

    append_row(
        "Cumm Hours Rolling",
        rolling_hours,
    )

    # 6. LTI monthly and cumulative counts.
    append_row(
        "LTI",
        lambda y, m:
            combined_count(lti_sets, y, m),
    )

    def ytd_lti(y, m):
        return sum(
            lti_count(y, month, status)
            for month in range(1, m + 1)
            for status in ("Draft", "Submitted")
        )

    append_row(
        "Cumm LTI YTD",
        ytd_lti,
    )

    def rolling_lti(y, m):
        return sum(
            lti_count(year, month, status)
            for year, month in get_rolling_months(y, m)
            for status in ("Draft", "Submitted")
        )

    append_row(
        "Cumm LTI 12 Mnt Rolling",
        rolling_lti,
    )

    # Use complete monthly hours for frequency rates.
    # Displayed cumulative hours remain separate.
    def complete_ytd_hours(y, m):
        return complete_sum([
            complete_hours_by_month.get((y, month))
            for month in range(1, m + 1)
        ])

    def complete_rolling_hours(y, m):
        return complete_sum([
            complete_hours_by_month.get(key)
            for key in get_rolling_months(y, m)
        ])

    # 7. Rolling LTIFR.
    def rolling_ltifr(y, m):
        hours = complete_rolling_hours(y, m)
        count = rolling_lti(y, m)
        return calculate_rate(count, hours)

    append_row(
        "12 Mnt Rolling LTIFR",
        rolling_ltifr,
    )

    # 8. Rolling TIFR.
    def rolling_tifr(y, m):
        hours = complete_rolling_hours(y, m)

        count = sum(
            injury_count(year, month, status)
            for year, month in get_rolling_months(y, m)
            for status in ("Draft", "Submitted")
        )

        return calculate_rate(count, hours)

    append_row(
        "TIFR - 12 Mnt Rolling",
        rolling_tifr,
    )

    # 9. YTD LTIFR.
    def ytd_ltifr(y, m):
        return calculate_rate(
            ytd_lti(y, m),
            complete_ytd_hours(y, m),
        )

    append_row(
        "YTD LTIFR",
        ytd_ltifr,
    )

    # 10. Workforce.
    append_row(
        "Workforce",
        lambda y, m: workforce_by_month.get((y, m)),
    )

    return data


# ---------------------------------------------------------
# SCRIPT REPORT ENTRY POINT
# ---------------------------------------------------------

def execute(filters=None):
    filters = normalize_filters(filters)

    sites = resolve_report_sites(filters)

    from_year = filters.from_year
    to_year = filters.to_year

    # Include the previous 11 months for rolling calculations.
    rolling_start_year, rolling_start_month = shift_month(
        from_year,
        1,
        -11,
    )

    rolling_start = date(
        rolling_start_year,
        rolling_start_month,
        1,
    )

    end_date = date(to_year, 12, 31)

    output_months = get_months(
        from_year,
        to_year,
    )

    incidents, types_by_parent = fetch_incidents(
        sites,
        rolling_start,
        end_date,
    )

    (
        category_sets,
        injury_sets,
        lti_sets,
        pdi_sets,
        status_incident_sets,
    ) = aggregate_incidents(
        incidents,
        types_by_parent,
    )

    hours_by_month, workforce_by_month, complete_hours_by_month = (
        fetch_verified_monthly_data(
            sites,
            rolling_start,
            end_date,
        )
    )

    columns = get_columns(output_months)

    data = build_rows(
        output_months,
        category_sets,
        injury_sets,
        lti_sets,
        pdi_sets,
        hours_by_month,
        workforce_by_month,
        complete_hours_by_month,
    )

    # MONTHLY SHE SUMMARY SELECTED PERIOD V1
    # Exclude historical rolling lookback records from
    # the headline incident summary.
    report_start = date(from_year, 1, 1)
    report_end = date(to_year, 12, 31)

    reporting_incidents = [
        incident
        for incident in incidents
        if report_start <= getdate(incident.datetime_incident)
        <= report_end
    ]

    draft_count = sum(
        1 for incident in reporting_incidents
        if int(incident.docstatus) == 0
    )

    submitted_count = sum(
        1 for incident in reporting_incidents
        if int(incident.docstatus) == 1
    )
    # END MONTHLY SHE SUMMARY SELECTED PERIOD V1

    message = None

    report_summary = [
        {
            "label": _("Draft Incident Reports"),
            "value": draft_count,
            "datatype": "Int",
            "indicator": "Orange",
        },
        {
            "label": _("Submitted Incident Reports"),
            "value": submitted_count,
            "datatype": "Int",
            "indicator": "Green",
        },
        {
            "label": _("Total Incident Reports"),
            "value": draft_count + submitted_count,
            "datatype": "Int",
            "indicator": "Blue",
        },
    ]

    # MONTHLY SHE COMBINED INCIDENT DISPLAY V1
    # Preserve existing calculations: Draft + Submitted = Total.
    # Remove the individual status rows from the presentation only.

    existing_labels = {
        row.get("category")
        for row in data
        if isinstance(row.get("category"), str)
    }

    for incident_category in CATEGORY_TYPES:
        expected = f"{incident_category} - Total"
        if expected not in existing_labels:
            frappe.throw(
                _("Missing combined incident row: {0}").format(
                    expected
                )
            )

    combined_rows = []

    for row in data:
        label = row.get("category")

        if isinstance(label, str):
            if label.endswith((" - Draft", " - Submitted")):
                continue

            if label.endswith(" - Total"):
                combined_label = label[:-len(" - Total")]

                if combined_label == "LTI":
                    combined_label = "LTI's"

                if combined_label in existing_labels:
                    # An existing row may already contain the
                    # combined Draft + Submitted incident count.
                    originals = [
                        existing for existing in data
                        if existing.get("category") == combined_label
                    ]

                    if len(originals) != 1:
                        frappe.throw(
                            _("Duplicate original rows: {0}").format(
                                combined_label
                            )
                        )

                    monthly_fields = [
                        column.get("fieldname")
                        for column in columns
                        if column.get("fieldname") != "category"
                    ]

                    if any(
                        originals[0].get(field) != row.get(field)
                        for field in monthly_fields
                    ):
                        frappe.throw(
                            _(
                                "Conflicting monthly totals for {0}. "
                                "The rows cannot safely be combined."
                            ).format(combined_label)
                        )

                    # The existing row has identical totals.
                    # Keep it and do not add a duplicate.
                    continue

                row = dict(row)
                row["category"] = combined_label

        combined_rows.append(row)

    data = combined_rows

    # Keep only the combined incident count in the report summary.
    combined_summary = []

    for item in report_summary:
        label = item.get("label")

        if label in (
            _("Draft Incident Reports"),
            _("Submitted Incident Reports"),
        ):
            continue

        if label == _("Total Incident Reports"):
            item = dict(item)
            item["label"] = _("Incident Reports")

        combined_summary.append(item)

    report_summary = combined_summary
    # END MONTHLY SHE COMBINED INCIDENT DISPLAY V1

    # MONTHLY SHE EXCEL ROW ORDER V1
    # Match the original SHE spreadsheet without changing
    # monthly totals or rate calculations.

    incident_rows = [
        "LTI's",
        "First Aid Case",
        "Medical Treatment",
        "FOG",
        "TMM Incidents",
        "Property Damage",
        "Total Injuries",
        "Cumm Total Injuries",
        "Total PDI",
        "Fatality",
        "NIHL",
        "Occupational Disease",
    ]

    hours_rows = [
        "12 Mnt Rolling LTIFR",
        "Hours Worked",
        "Cumm Hours YTD",
        "Cumm Hours Rolling",
        "LTI",
        "Cumm LTI YTD",
        "Cumm LTI 12 Mnt Rolling",
    ]

    closing_rows = [
        "TIFR - 12 Mnt Rolling",
        "YTD LTIFR",
        "Workforce",
    ]

    expected_labels = (
        incident_rows + hours_rows + closing_rows
    )

    rows_by_label = {}

    for report_row in data:
        label = report_row.get("category")

        if not label:
            continue

        if label in rows_by_label:
            frappe.throw(
                _("Duplicate SHE row: {0}").format(label)
            )

        rows_by_label[label] = report_row

    missing = [
        label for label in expected_labels
        if label not in rows_by_label
    ]

    unexpected = [
        label for label in rows_by_label
        if label not in expected_labels
    ]

    if missing or unexpected:
        frappe.throw(
            _(
                "SHE layout mismatch. Missing: {0}. "
                "Unexpected: {1}."
            ).format(
                ", ".join(missing) or "None",
                ", ".join(unexpected) or "None",
            )
        )

    # Both LTI rows represent the same monthly incident
    # count but appear in different spreadsheet sections.
    # Use report columns because months is not in execute() scope.
    month_fields = [
        column["fieldname"]
        for column in columns
        if column.get("fieldname", "").startswith("m_")
    ]

    if not month_fields:
        frappe.throw(_("No monthly report columns found."))

    for field in month_fields:

        if (
            rows_by_label["LTI's"].get(field)
            != rows_by_label["LTI"].get(field)
        ):
            frappe.throw(
                _("LTI count mismatch for {0}").format(field)
            )

    data = (
        [rows_by_label[label] for label in incident_rows]
        + [{"category": ""}]
        + [rows_by_label[label] for label in hours_rows]
        + [{"category": ""}]
        + [rows_by_label[label] for label in closing_rows]
    )

    # END MONTHLY SHE EXCEL ROW ORDER V1

    # MONTHLY SHE CATEGORY FILTER V1
    selected_category = filters.get("category") or "All Categories"

    if not isinstance(selected_category, str):
        frappe.throw(_("Invalid category filter."))

    if selected_category != "All Categories":
        if selected_category not in expected_labels:
            frappe.throw(_("Invalid category filter."))

        data = [
            row for row in data
            if row.get("category") == selected_category
        ]
    # END MONTHLY SHE CATEGORY FILTER V1

    return columns, data, message, None, report_summary


# ---------------------------------------------------------
# MONTHLY SHE XLSX BORDER LAYOUT V2
# Applies to the standard Frappe Excel export only.
# Does not change incident counts or report calculations.
# ---------------------------------------------------------

def get_xlsx_styles(metadata):
    # MONTHLY SHE XLSX BORDER LAYOUT V2
    # Standard XLSX export only; no data/calculation changes.
    from frappe.utils.xlsxutils import XLSXStyleBuilder

    builder = XLSXStyleBuilder(metadata, default_styling=False)

    category_col = builder.field_index_map.get("category")
    if category_col is None:
        raise ValueError("Monthly SHE category column missing.")

    columns = sorted(metadata.column_map)

    # MONTHLY SHE BOUNDED EXPORT STYLES V3
    # Style only actual report columns, never entire Excel rows.
    def style_report_row(row_index, style_id):
        for column_index in columns:
            builder.style_cell(
                row_index,
                column_index,
                style_id,
            )


    month_columns = [
        idx for idx in columns
        if str(
            metadata.column_map[idx].get("fieldname", "")
        ).startswith("m_")
    ]

    if not month_columns:
        raise ValueError("Monthly SHE month columns missing.")

    last_col = max(columns)

    integer_rows = {
        "LTI's",
        "First Aid Case",
        "Medical Treatment",
        "FOG",
        "TMM Incidents",
        "Property Damage",
        "Total Injuries",
        "Cumm Total Injuries",
        "Total PDI",
        "Fatality",
        "NIHL",
        "Occupational Disease",
        "LTI",
        "Cumm LTI YTD",
        "Cumm LTI 12 Mnt Rolling",
        "Workforce",
    }

    row_colours = {
        "Total Injuries": "#A7C8E8",
        "Cumm Total Injuries": "#D1D5DB",
        "Total PDI": "#D1D5DB",
    }

    # Normal light borders, as in the SHE spreadsheet.
    thin_grid = builder.register_style({
        "border": 1,
        "border_color": "#444444",
    })

    # Strong black boundary for Category and year sections.
    category_edge = builder.register_style({
        "left": 2,
        "right": 2,
        "left_color": "#111111",
        "right_color": "#111111",
    })

    year_edge = builder.register_style({
        "left": 2,
        "left_color": "#111111",
    })

    right_edge = builder.register_style({
        "right": 2,
        "right_color": "#111111",
    })

    header_band = builder.register_style({
        "bold": True,
        "bg_color": "#ECEFF2",
        "top": 2,
        "bottom": 2,
        "top_color": "#111111",
        "bottom_color": "#111111",
    })

    heavy_top = builder.register_style({
        "top": 2,
        "top_color": "#111111",
    })

    heavy_bottom = builder.register_style({
        "bottom": 2,
        "bottom_color": "#111111",
    })

    blank_separator = builder.register_style({
        "bg_color": "#FFFFFF",
        "top": 2,
        "bottom": 2,
        "top_color": "#111111",
        "bottom_color": "#111111",
    })

    decimal_format = builder.register_style({
        "num_format": "#,##0.00",
        "align": "right",
    })

    integer_format = builder.register_style({
        "num_format": "#,##0",
        "align": "right",
    })

    bold_style = builder.register_style({
        "bold": True,
    })

    background_styles = {
        label: builder.register_style({
            "bg_color": colour,
            "bold": True,
        })
        for label, colour in row_colours.items()
    }

    major_top_rows = {
        "Total Injuries",
        "12 Mnt Rolling LTIFR",
        "TIFR - 12 Mnt Rolling",
        "Workforce",
    }

    major_bottom_rows = {
        "Occupational Disease",
        "Cumm LTI 12 Mnt Rolling",
        "YTD LTIFR",
        "Workforce",
    }

    # Determine first monthly column for each calendar year.
    year_start_columns = []
    previous_year = None

    for col_idx in month_columns:
        fieldname = metadata.column_map[col_idx]["fieldname"]
        year = fieldname.split("_")[1]

        if year != previous_year:
            year_start_columns.append(col_idx)
            previous_year = year

    # Header and every report row receive the light grid.
    header_idx = metadata.get_header_index()

    for row_idx in [header_idx, *metadata.row_map.keys()]:
        style_report_row(row_idx, thin_grid)

        builder.style_cell(
            row_idx,
            category_col,
            category_edge,
        )

        for col_idx in year_start_columns:
            builder.style_cell(
                row_idx,
                col_idx,
                year_edge,
            )

        builder.style_cell(
            row_idx,
            last_col,
            right_edge,
        )

    style_report_row(header_idx, header_band)

    # Apply category-specific borders and colours.
    for row_idx, row in metadata.row_map.items():

        if isinstance(row, dict):
            category = row.get("category")

        elif isinstance(row, (list, tuple)):
            category = (
                row[category_col]
                if category_col < len(row)
                else None
            )

        else:
            continue

        category = str(category or "").strip()

        if not category:
            style_report_row(
                row_idx,
                blank_separator,
            )
            continue

        if category in background_styles:
            style_report_row(
                row_idx,
                background_styles[category],
            )

        if category in major_top_rows:
            style_report_row(
                row_idx,
                heavy_top,
            )

        if category in major_bottom_rows:
            style_report_row(
                row_idx,
                heavy_bottom,
            )

        if category in (
            "Total Injuries",
            "Cumm Total Injuries",
            "Total PDI",
        ):
            builder.style_cell(
                row_idx,
                category_col,
                bold_style,
            )

        for col_idx in month_columns:
            builder.style_cell(
                row_idx,
                col_idx,
                integer_format
                if category in integer_rows
                else decimal_format,
            )

    return builder.result

# END MONTHLY SHE XLSX BORDER LAYOUT V2
