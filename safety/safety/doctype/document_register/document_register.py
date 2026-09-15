# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, nowdate, get_url


REVISION_PATTERN = re.compile(r"^(?P<base>.+)-Rev\.(?P<revision>\d+)$")
FRAPPE_AMENDMENT_PATTERN = re.compile(r"^(?P<base>.+)-(?P<amendment>\d+)$")


class DocumentRegister(Document):
	def before_naming(self):
		self.set_document_number()

	def autoname(self):
		self.set_document_number()

	def before_insert(self):
		self.set_document_number()

	def validate(self):
		if self.name:
			self.document_no = self.name

	def before_submit(self):
		if not self.attach:
			frappe.throw(_("You cannot submit this document unless 'Attach Executed Document' is populated."))

	def set_document_number(self):
		if self.amended_from:
			self.set_revision_document_number()
		else:
			self.set_original_document_number()

	def set_original_document_number(self):
		company_abbrev = self.get_company_abbrev()
		department_abbrev = self.get_department_abbrev()
		subclass_abbrev = self.get_subclass_abbrev()

		prefix = f"{company_abbrev}-{department_abbrev}-{subclass_abbrev}"
		next_number = self.get_next_number(prefix)

		document_no = f"{prefix}-{next_number}"

		self.name = document_no
		self.document_no = document_no

	def set_revision_document_number(self):
		base_document_no = self.get_base_document_no(self.amended_from)
		next_revision = self.get_next_revision_number(base_document_no)

		document_no = f"{base_document_no}-Rev.{next_revision}"

		self.name = document_no
		self.document_no = document_no

	def get_base_document_no(self, document_no):
		if not document_no:
			frappe.throw(_("Amended From is required to create a revision."))

		revision_match = REVISION_PATTERN.match(document_no)
		if revision_match:
			return revision_match.group("base")

		frappe_amendment_match = FRAPPE_AMENDMENT_PATTERN.match(document_no)
		if frappe_amendment_match:
			possible_base = frappe_amendment_match.group("base")

			if frappe.db.exists("Document Register", possible_base):
				return possible_base

		return document_no

	def get_next_revision_number(self, base_document_no):
		"""
		The original submitted document is treated as Rev.1.

		Examples:
		    IS-HR-POL-001          = original / Rev.1
		    IS-HR-POL-001-Rev.2    = first amendment
		    IS-HR-POL-001-Rev.3    = second amendment

		Cancelled revisions are included because a cancelled Rev.2 must still
		cause the next amended document to become Rev.3.
		"""

		existing = frappe.db.sql(
			"""
			SELECT name
			FROM `tabDocument Register`
			WHERE name = %s
			   OR name LIKE %s
			   OR name LIKE %s
			""",
			(
				base_document_no,
				f"{base_document_no}-Rev.%",
				f"{base_document_no}-%",
			),
			as_dict=True,
		)

		max_revision = 1

		for row in existing:
			name = row.name or ""

			if name == base_document_no:
				max_revision = max(max_revision, 1)
				continue

			revision_match = REVISION_PATTERN.match(name)
			if revision_match and revision_match.group("base") == base_document_no:
				max_revision = max(max_revision, int(revision_match.group("revision")))
				continue

			# This handles documents already created as Frappe amendments,
			# e.g. IS-HR-POL-001-1. Treat the first Frappe amendment as Rev.2,
			# the second as Rev.3, etc.
			frappe_amendment_match = FRAPPE_AMENDMENT_PATTERN.match(name)
			if frappe_amendment_match and frappe_amendment_match.group("base") == base_document_no:
				amendment_number = int(frappe_amendment_match.group("amendment"))
				max_revision = max(max_revision, amendment_number + 1)

		return max_revision + 1

	def get_company_abbrev(self):
		if not self.company:
			frappe.throw(_("Company is required."))

		company_abbrev = frappe.db.get_value(
			"Company Abbreviation",
			self.company,
			"company_abbrev",
		)

		if not company_abbrev:
			frappe.throw(_("Company Abbreviation is missing for company {0}.").format(self.company))

		return company_abbrev.strip()

	def get_department_abbrev(self):
		if not self.department:
			frappe.throw(_("Department is required."))

		return self.department.strip()

	def get_subclass_abbrev(self):
		if not self.document_subclass:
			frappe.throw(_("Document Subclass is required."))

		subclass_abbrev = frappe.db.get_value(
			"Document Register Subclass",
			self.document_subclass,
			"subclass_abbrev",
		)

		if not subclass_abbrev:
			frappe.throw(_("Subclass Abbreviation is missing for subclass {0}.").format(self.document_subclass))

		return subclass_abbrev.strip()

	def get_next_number(self, prefix):
		like_pattern = f"{prefix}-%"

		existing = frappe.db.sql(
			"""
			SELECT name
			FROM `tabDocument Register`
			WHERE name LIKE %s
			ORDER BY creation DESC
			""",
			(like_pattern,),
			as_dict=True,
		)

		max_number = 0

		for row in existing:
			name = row.name or ""

			if REVISION_PATTERN.match(name):
				continue

			parts = name.split("-")

			if len(parts) < 4:
				continue

			last_part = parts[-1]

			if last_part.isdigit():
				max_number = max(max_number, int(last_part))

		return str(max_number + 1).zfill(3)


# ------------------------------------------------------------------
# AUTHOR REVISION REMINDERS
# ------------------------------------------------------------------
def send_author_revision_reminders():
	"""Scheduler entry point (daily). Emails every employee listed as an
	"Author" on a submitted Document Register's Owners table, once, when the
	document's Next Revision Date falls within the configured lead window
	(Safety Settings > Document Register Reminder, default 30 days).

	Each document is only marked as reminded once an email has actually gone
	out, so a document with no resolvable Author email is retried on later
	daily runs until it either gets one or its revision date passes.
	"""
	days_before = frappe.db.get_single_value(
		"Safety Settings", "document_register_reminder_days_before"
	) or 30

	today = nowdate()
	window_end = add_days(today, days_before)

	names = frappe.get_all(
		"Document Register",
		filters={
			"docstatus": 1,
			"author_reminder_sent": 0,
			"revision_date": ["between", [today, window_end]],
		},
		pluck="name",
	)

	for name in names:
		_send_author_reminder_for_document(name)


def _send_author_reminder_for_document(name):
	doc = frappe.get_doc("Document Register", name)

	authors = [row for row in doc.owners if row.document_role == "Author" and row.employee]
	if not authors:
		return

	register_url = get_url(f"/app/document-register/{doc.name}")
	sent_any = False

	for row in authors:
		email = _get_employee_email(row.employee)
		if not email:
			continue

		message = "<br>".join([
			f"Dear {frappe.utils.escape_html(row.employee_name or '')},",
			"",
			(
				f"The document \"{frappe.utils.escape_html(doc.document_name or '')}\" "
				f"({frappe.utils.escape_html(doc.document_no or doc.name)}) is due for revision on "
				f"{frappe.utils.escape_html(str(doc.revision_date or ''))}."
			),
			"",
			f'<a href="{register_url}">View Document Register</a>',
		])

		frappe.sendmail(
			recipients=[email],
			subject=f"Document Revision Due: {doc.document_no or doc.name}",
			message=message,
		)
		sent_any = True

	if sent_any:
		frappe.db.set_value("Document Register", doc.name, "author_reminder_sent", 1)


def _get_employee_email(employee):
	emp = frappe.db.get_value(
		"Employee",
		employee,
		["user_id", "prefered_email", "company_email", "personal_email"],
		as_dict=True,
	)
	if not emp:
		return None

	if emp.user_id:
		user_email = frappe.db.get_value("User", emp.user_id, "email")
		if user_email:
			return user_email

	return emp.prefered_email or emp.company_email or emp.personal_email