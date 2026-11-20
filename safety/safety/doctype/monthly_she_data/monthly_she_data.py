import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime


def _user_roles(user=None):
    return set(frappe.get_roles(user or frappe.session.user))


def _authorized_sites(user=None):
    user = user or frappe.session.user

    if user == "Administrator":
        return None

    if not _user_roles(user).intersection(
        {"Safety Manager", "Safety User"}
    ):
        return set()

    from safety.safety.report.site_safe_days.site_safe_days import (
        resolve_safety_dashboard_sites,
    )

    try:
        return set(
            resolve_safety_dashboard_sites(
                operation="Mining and Workshop",
                user=user,
            )
        )
    except frappe.PermissionError:
        return set()


def get_permission_query_conditions(user=None):
    user = user or frappe.session.user

    if user == "Administrator":
        return ""

    sites = _authorized_sites(user)

    if not sites:
        return "1=0"

    values = ", ".join(
        frappe.db.escape(site)
        for site in sorted(sites)
    )

    return f"`tabMonthly SHE Data`.`site` IN ({values})"


def has_permission(doc, ptype=None, user=None, debug=False):
    """Enforce Monthly SHE site and verified-record restrictions."""
    user = user or frappe.session.user

    if user == "Administrator":
        return True

    if not _user_roles(user).intersection(
        {"Safety Manager", "Safety User"}
    ):
        return False

    if ptype == "create" and not doc.site:
        return True

    if not doc.site:
        return False

    if doc.site not in (_authorized_sites(user) or set()):
        return False

    if ptype == "delete":
        return False

    # Check the persisted status, not the proposed new status.
    # A Draft-to-Verified transition must reach validate(),
    # where Safety Manager and ownership rules are enforced.
    # An already Verified record remains locked.
    if ptype == "write" and doc.name and not doc.is_new():
        saved_status = frappe.db.get_value(
            "Monthly SHE Data",
            doc.name,
            "verification_status",
        )

        if saved_status == "Verified":
            return False

    return True


# MONTHLY SHE AUTHORIZED SITE LINK QUERY V1

@frappe.whitelist()
def get_authorized_sites():
    """Return only sites the current user may select."""
    sites = _authorized_sites()

    if sites is None:
        return frappe.get_all(
            "Branch",
            pluck="name",
            order_by="name asc",
        )

    return sorted(sites)

# END MONTHLY SHE AUTHORIZED SITE LINK QUERY V1


class MonthlySHEData(Document):

    # MONTHLY SHE SITE SECURITY V1

    def validate(self):
        user = frappe.session.user
        roles = _user_roles(user)
        administrator = user == "Administrator"

        if not administrator:
            if not roles.intersection(
                {"Safety Manager", "Safety User"}
            ):
                frappe.throw(
                    "Not authorized to manage Monthly SHE Data.",
                    frappe.PermissionError,
                )

            if not self.site:
                frappe.throw("Select a site.")

            if self.site not in (_authorized_sites(user) or set()):
                frappe.throw(
                    "You are not authorized for this site.",
                    frappe.PermissionError,
                )

        if not self.reporting_month:
            frappe.throw("Reporting Month is required.")

        month = getdate(self.reporting_month)

        if month.day != 1:
            frappe.throw(
                "Reporting Month must be the first day of the month."
            )

        # Duplicate site/month validation.
        duplicates = frappe.get_all(
            "Monthly SHE Data",
            filters={
                "site": self.site,
                "reporting_month": self.reporting_month,
                "name": ["!=", self.name or ""],
            },
            pluck="name",
            limit=1,
        )

        if duplicates:
            frappe.throw(
                "Monthly SHE Data already exists for this site and month."
            )

        if self.hours_recorded:
            if self.hours_worked is None or self.hours_worked < 0:
                frappe.throw(
                    "Enter valid non-negative Hours Worked."
                )

        if self.workforce_recorded:
            if self.workforce is None or self.workforce < 0:
                frappe.throw(
                    "Enter valid non-negative Workforce."
                )

        old_doc = self.get_doc_before_save()

        if old_doc and old_doc.verification_status == "Verified":
            if not administrator:
                frappe.throw(
                    "Verified records are locked. "
                    "Administrator intervention is required for correction.",
                    frappe.PermissionError,
                )

        if self.verification_status == "Verified":
            if not self.hours_recorded or not self.workforce_recorded:
                frappe.throw(
                    "Hours Worked and Workforce must both be recorded "
                    "before verification."
                )

            if old_doc is None and not administrator:
                frappe.throw(
                    "Create the record as Draft before verification.",
                    frappe.PermissionError,
                )

            if old_doc and old_doc.verification_status != "Verified":
                if not administrator:
                    if "Safety Manager" not in roles:
                        frappe.throw(
                            "Only a Safety Manager can verify monthly SHE data.",
                            frappe.PermissionError,
                        )

                    if old_doc.owner == user:
                        frappe.throw(
                            "You cannot verify your own submission.",
                            frappe.PermissionError,
                        )

                    protected_fields = (
                        "site",
                        "reporting_month",
                        "hours_recorded",
                        "hours_worked",
                        "workforce_recorded",
                        "workforce",
                        "remarks",
                    )

                    if any(
                        old_doc.get(field) != self.get(field)
                        for field in protected_fields
                    ):
                        frappe.throw(
                            "Save corrections as Draft before verification. "
                            "Verification must be a separate action."
                        )

                self.verified_by = user
                self.verified_on = now_datetime()

        else:
            self.verified_by = None
            self.verified_on = None
