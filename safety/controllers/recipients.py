# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

"""Shared recipient resolution for every notification/email controller in this
app, backed by Safety Settings > Notification Recipients.

A recipient with no Branch on their row is "global" - they get every record
for that notification type. A recipient with a Branch only gets records for
that branch. A recipient can have more than one row (one per branch) to
cover several branches without going global.
"""

import frappe


def get_notification_recipients(notification_type):
	"""Return one entry per distinct recipient configured for notification_type:

	    {"email": str, "full_name": str, "branches": set(...) | None}

	branches is None for a global recipient (no branch filtering applied);
	otherwise it's the set of Branch names this recipient is restricted to.
	Recipients with no resolvable, enabled User/email are skipped.
	"""
	settings = frappe.get_single("Safety Settings")
	rows = [
		row for row in settings.notification_recipients
		if row.notification_type == notification_type and row.recipient
	]

	if not rows:
		return []

	user_names = {row.recipient for row in rows}
	users = frappe.get_all(
		"User",
		filters={"name": ["in", list(user_names)], "enabled": 1},
		fields=["name", "email", "full_name"],
	)
	user_by_name = {user.name: user for user in users}

	grouped = {}
	for row in rows:
		user = user_by_name.get(row.recipient)
		if not user or not user.email:
			continue

		entry = grouped.setdefault(row.recipient, {
			"email": user.email,
			"full_name": user.full_name or user.name,
			"branches": set(),
			"is_global": False,
		})

		if row.branch:
			entry["branches"].add(row.branch)
		else:
			entry["is_global"] = True

	recipients = []
	for entry in grouped.values():
		recipients.append({
			"email": entry["email"],
			"full_name": entry["full_name"],
			"branches": None if entry["is_global"] else entry["branches"],
		})

	return recipients


def filter_rows_for_recipient(rows, branch_field, recipient):
	"""Given the full list of record dicts for a notification run, return only
	the ones a given recipient (as returned by get_notification_recipients)
	should see. A global recipient (branches is None) sees every row."""
	if recipient["branches"] is None:
		return rows

	return [row for row in rows if row.get(branch_field) in recipient["branches"]]
