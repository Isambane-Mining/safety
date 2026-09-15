import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url, now

from safety.controllers.recipients import get_notification_recipients


class FlashReports(Document):

    def validate(self):
        self.set_photo_timestamps()

    def set_photo_timestamps(self):
        for row in self.get("photos_and_attachments", []):
            if row.photos_and_attachments and not row.date_and_time_of_photo:
                row.date_and_time_of_photo = now()


# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
def _first_non_empty(row, fieldnames):
    if not row:
        return None

    for fieldname in fieldnames:
        value = row.get(fieldname)
        if value not in (None, "", []):
            return value

    return None


def _extract_table_multiselect_values(doc, table_fieldname):
    """
    Generic reader for Table MultiSelect / child table rows.
    Returns a list of readable values from each row.
    """
    rows = doc.get(table_fieldname) or []
    values = []

    system_fields = {
        "name", "owner", "creation", "modified", "modified_by",
        "parent", "parentfield", "parenttype", "idx", "docstatus"
    }

    for row in rows:
        row_dict = row.as_dict() if hasattr(row, "as_dict") else dict(row)

        picked = None

        preferred_fields = [
            "incident_type",
            "severity",
            "life_saving_rule",
            "body_part",
            "nature_of_injury",
            "type_of_damage",
            "task",
            "description",
            "title",
            "name1",
            "value",
            "item",
            "type"
        ]

        for field in preferred_fields:
            if row_dict.get(field) not in (None, "", []):
                picked = row_dict.get(field)
                break

        if picked is None:
            for key, val in row_dict.items():
                if key in system_fields:
                    continue
                if isinstance(val, (str, int, float)) and val not in ("", None):
                    picked = val
                    break

        if picked not in (None, ""):
            values.append(str(picked))

    seen = set()
    clean_values = []
    for value in values:
        if value not in seen:
            seen.add(value)
            clean_values.append(value)

    return clean_values


def _join_table_multiselect(doc, table_fieldname):
    return ", ".join(_extract_table_multiselect_values(doc, table_fieldname))


def _get_first_row_from_possible_tables(doc, table_fieldnames):
    """
    Returns the first row from the first non-empty child table found.
    Useful when fieldname may differ from the label.
    """
    for table_fieldname in table_fieldnames:
        rows = doc.get(table_fieldname) or []
        if rows:
            return rows[0]
    return None


# ------------------------------------------------------------------
# LINK FIELD QUERY — FILTER INCIDENT NUMBER
# ------------------------------------------------------------------
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def incident_link_query(doctype, txt, searchfield, start, page_len, filters):
    action_category = (filters or {}).get("action_category")

    conditions = ["docstatus < 2"]
    values = {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    }

    if action_category:
        conditions.append("event_category = %(action_category)s")
        values["action_category"] = action_category

    where_clause = " AND ".join(conditions)

    return frappe.db.sql(
        f"""
        SELECT
            name,
            COALESCE(incident_number, name) AS incident_number
        FROM `tabIncident Report`
        WHERE {where_clause}
          AND (
              name LIKE %(txt)s
              OR incident_number LIKE %(txt)s
          )
        ORDER BY creation DESC
        LIMIT %(start)s, %(page_len)s
        """,
        values
    )


# ------------------------------------------------------------------
# FETCH INCIDENT DATA FROM INCIDENT REPORT
# ------------------------------------------------------------------
@frappe.whitelist()
def get_flash_report_data(incident_number):
    ir = frappe.get_doc("Incident Report", incident_number)

    # ---------------- INCIDENT CLASSIFICATION ----------------
    incident_classification = _join_table_multiselect(ir, "select_type_of_incident")

    # ---------------- POTENTIAL SEVERITY ----------------
    potential_severity = _join_table_multiselect(ir, "select_severity")

    # ---------------- REPEAT INCIDENT ----------------
    repeat_values = []
    if ir.get("has_happened"):
        repeat_values.append("Has Happened")
    if ir.get("first_known_case"):
        repeat_values.append("First Known Case")
    repeat_incident = ", ".join(repeat_values)

    # ---------------- LIFE SAVING RULES ----------------
    life_saving_rules = _join_table_multiselect(ir, "life_save_rule")

    # ---------------- RESPONSIBLE PERSON CHILD TABLE ----------------
    # Requested mappings:
    # name_of_person                <- injured_person_name
    # position                      <- position_of_injured
    # years_in_current_position     <- years_in_current_position
    #
    # We try a few possible table fieldnames to avoid breaking if the actual
    # fieldname differs from the visible label "Responsible Person".
    responsible_person_row = _get_first_row_from_possible_tables(
        ir,
        [
            "responsible_person",
            "responsible_person_detail",
            "responsible_person_details",
            "injured_detail"
        ]
    )

    injured_name = _first_non_empty(responsible_person_row, [
        "injured_person_name"
    ])
    injured_position = _first_non_empty(responsible_person_row, [
        "position_of_injured"
    ])
    injured_years = _first_non_empty(responsible_person_row, [
        "years_in_current_position"
    ])

    # ---------------- PERSON RESPONSIBLE FOR DAMAGES ----------------
    # Requested mappings:
    # responsible_person_name            <- damages_by_full_name (kept as primary name source)
    # position_of_person_responsible     <- damages_caused_by_position
    # years_in_position                  <- damages_caused_by_years_in_current_position
    damage_row = _get_first_row_from_possible_tables(
        ir,
        ["responsible_for_damages"]
    )

    damage_name = _first_non_empty(damage_row, [
        "damages_by_full_name",
        "responsible_person_name",
        "employee_name",
        "full_name",
        "person_name"
    ])
    damage_position = _first_non_empty(damage_row, [
        "damages_caused_by_position"
    ])
    damage_years = _first_non_empty(damage_row, [
        "damages_caused_by_years_in_current_position"
    ])

    # ---------------- EQUIPMENT ----------------
    equipment_id = serial_number = registration_number = make = None
    if ir.get("equipment_details"):
        row = ir.get("equipment_details")[0]
        equipment_id = _first_non_empty(row, [
            "equipment_id",
            "equipment",
            "equipment_number",
            "equipment_name"
        ])
        serial_number = _first_non_empty(row, [
            "serial_number",
            "serial_no"
        ])
        registration_number = _first_non_empty(row, [
            "registration_number_if_applicable",
            "registration_number",
            "registration_no"
        ])
        make = _first_non_empty(row, [
            "make",
            "manufacturer"
        ])

    # ---------------- NATURE ----------------
    nature_parts = []

    if ir.get("incident_type"):
        nature_parts.append(str(ir.get("incident_type")))

    injury_nature = _join_table_multiselect(ir, "nature_of_the_injury")
    if injury_nature:
        nature_parts.append(injury_nature)

    damage_type = _join_table_multiselect(ir, "type_of_damage")
    if damage_type:
        nature_parts.append(damage_type)

    nature = ", ".join([x for x in nature_parts if x])

    # ---------------- EMPLOYER DISPLAY ----------------
    employer_display = ir.get("company") or ir.get("employer")

    # ---------------- DESCRIPTION ----------------
    # Requested mapping:
    # description_of_incident_impact <- description_of_the_event
    description_of_incident_impact = ir.get("description_of_the_event")

    return {
        "incident_classification": incident_classification,
        "date_and_time_of_incident": ir.get("datetime_incident"),
        "nature": nature,
        "site": ir.get("site"),
        "occurence": ir.get("location_on_site"),
        "description_of_incident_impact": description_of_incident_impact,

        "name_of_person": injured_name,
        "position": injured_position,
        "years_in_current_position": injured_years,

        "responsible_person_name": damage_name,
        "position_of_person_responsible": damage_position,
        "years_in_position": damage_years,

        "name_of_employer": employer_display,
        "potential_severity_classification": potential_severity,
        "repeat_incident": repeat_incident,
        "applicable_life_saving_rule": life_saving_rules,

        "equipment_id": equipment_id,
        "serial_number": serial_number,
        "registration_number": registration_number,
        "make": make
    }


# ------------------------------------------------------------------
# BUILD FLASH REPORT HTML
# ------------------------------------------------------------------
@frappe.whitelist()
def build_flash_html(data):
    d = frappe.parse_json(data)
    logo_url = get_url("/files/isambane_logo.png")

    image_urls = []
    for row in d.get("photos_and_attachments", []):
        if row.get("photos_and_attachments"):
            image_urls.append(get_url(row.get("photos_and_attachments")))

    photo_html = ""
    if image_urls:
        imgs = "".join(
            f'<img src="{url}" style="max-width:90%;max-height:500px;border:1px solid #999;margin:10px;">'
            for url in image_urls
        )

        photo_html = f"""
            <hr>
            <h3 style="text-align:center;margin-top:20px;">
                Incident Photos / Attachments
            </h3>
            <div style="text-align:center;">{imgs}</div>
        """

    return f"""
    <div style="padding:10px;border:1px solid #ccc;">
        <img src="{logo_url}" style="max-height:60px;">
        {photo_html}
    </div>
    """


# ------------------------------------------------------------------
# SEND FLASH REPORT
# ------------------------------------------------------------------
@frappe.whitelist()
def send_flash_report(name):
    doc = frappe.get_doc("Flash Reports", name)
    frappe.has_permission("Flash Reports", "write", doc=doc, throw=True)

    if doc.flash_sent:
        frappe.throw(_("Flash Report has already been sent."))

    recipients = get_notification_recipients("Flash Report")
    recipients = [
        recipient for recipient in recipients
        if recipient["branches"] is None or doc.site in recipient["branches"]
    ]

    if not recipients:
        frappe.throw(
            _(
                "No Flash Report recipients are configured for this record's branch. "
                "Add them under Safety Settings > Notification Recipients."
            )
        )

    # Built server-side from the doc's own fields rather than a client-only
    # preview, so the email is correct even if the on-screen preview was
    # never (re)generated in this session.
    message = build_flash_html(doc.as_dict())

    frappe.sendmail(
        recipients=[recipient["email"] for recipient in recipients],
        subject=f"FLASH REPORT – Incident {doc.incident_number}",
        message=message,
        now=True
    )

    doc.flash_sent = 1
    doc.flash_sent_on = now()
    doc.save(ignore_permissions=True)

    return True