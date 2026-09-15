# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, get_url, nowdate

from safety.controllers.recipients import filter_rows_for_recipient, get_notification_recipients


def send_weekly_ppe_expired_notifications():
	"""Send weekly notifications for PPE items that have already expired."""
	today = nowdate()

	rows = frappe.db.sql(
		"""
		SELECT
			parent.name AS register_name,
			parent.employee,
			parent.employee_name,
			parent.designation,
			parent.branch,
			parent.issue_date,
			child.item,
			child.qty,
			child.re_issue_date,
			child.idx
		FROM `tabPPE Issue Register Table` child
		INNER JOIN `tabPPE Issue Register` parent
			ON child.parent = parent.name
		WHERE
			parent.docstatus < 2
			AND child.re_issue_date IS NOT NULL
			AND child.re_issue_date < %s
		ORDER BY child.re_issue_date ASC, parent.employee ASC
		""",
		(today,),
		as_dict=True,
	)

	if not rows:
		return

	subject = "Weekly PPE expiry notification: Expired PPE items"
	intro = "The following PPE items have already expired."
	_send_ppe_notification(rows, subject, intro, notification_type="PPE Expired")


def send_weekly_ppe_expiring_soon_notifications():
	"""Send weekly notifications for PPE items expiring within the next 30 days."""
	today = nowdate()
	thirty_days_from_now = add_days(today, 30)

	rows = frappe.db.sql(
		"""
		SELECT
			parent.name AS register_name,
			parent.employee,
			parent.employee_name,
			parent.designation,
			parent.branch,
			parent.issue_date,
			child.item,
			child.qty,
			child.re_issue_date,
			child.idx
		FROM `tabPPE Issue Register Table` child
		INNER JOIN `tabPPE Issue Register` parent
			ON child.parent = parent.name
		WHERE
			parent.docstatus < 2
			AND child.re_issue_date IS NOT NULL
			AND child.re_issue_date >= %s
			AND child.re_issue_date <= %s
		ORDER BY child.re_issue_date ASC, parent.employee ASC
		""",
		(today, thirty_days_from_now),
		as_dict=True,
	)

	if not rows:
		return

	subject = "Weekly PPE expiry notification: PPE items expiring in the next 30 days"
	intro = "The following PPE items will expire within the next 30 days."
	_send_ppe_notification(rows, subject, intro, notification_type="PPE Expiring Soon")


def _send_ppe_notification(rows, subject, intro, notification_type):
	recipients = get_notification_recipients(notification_type)
	if not recipients:
		return

	register_links = {}
	for row in rows:
		if row["register_name"] not in register_links:
			register_links[row["register_name"]] = get_url(
				f"/app/ppe-issue-register/{row['register_name']}"
			)

	for recipient in recipients:
		recipient_rows = filter_rows_for_recipient(rows, "branch", recipient)
		if not recipient_rows:
			continue

		table_html = _build_ppe_table(recipient_rows, register_links)

		message = "<br>".join([
			f"Dear {frappe.utils.escape_html(recipient['full_name'])},",
			"",
			intro,
			"",
			table_html,
		])

		frappe.sendmail(
			recipients=[recipient["email"]],
			subject=subject,
			message=message,
		)


def _build_ppe_table(rows, register_links):
	table_rows = []
	for row in rows:
		register_url = register_links[row["register_name"]]

		table_rows.append(
			f"""
			<tr>
				<td>{frappe.utils.escape_html(row.get("employee") or "")}</td>
				<td>{frappe.utils.escape_html(row.get("employee_name") or "")}</td>
				<td>{frappe.utils.escape_html(row.get("designation") or "")}</td>
				<td>{frappe.utils.escape_html(row.get("branch") or "")}</td>
				<td>{frappe.utils.escape_html(row.get("item") or "")}</td>
				<td style="text-align:right;">{row.get("qty") or 0}</td>
				<td>{frappe.utils.escape_html(str(row.get("re_issue_date") or ""))}</td>
				<td><a href="{register_url}">{frappe.utils.escape_html(row.get("register_name") or "")}</a></td>
			</tr>
			"""
		)

	return f"""
		<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%;">
			<thead>
				<tr>
					<th>Employee</th>
					<th>Employee Name</th>
					<th>Designation</th>
					<th>Branch</th>
					<th>PPE Item</th>
					<th>Qty</th>
					<th>Re-Issue Date</th>
					<th>PPE Register</th>
				</tr>
			</thead>
			<tbody>
				{''.join(table_rows)}
			</tbody>
		</table>
	"""
