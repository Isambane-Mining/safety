app_name = "safety"
app_title = "Safety"
app_publisher = "BuFf0k"
app_description = "Safety Incident Management System for Mining"
app_email = "buff0k@gmail.com"
app_license = "mit"
required_apps = [
    "frappe/hrms",
    "buff0k/is_attendance",
]
source_link = "http://github.com/buff0k/safety"
app_logo_url = "/assets/safety/images/is-logo.png"
app_home = "/desk/safety"
add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/safety/images/is-logo.png",
		"title": app_title,
		"route": app_home,
		"has_permission": "safety.safety.utils.check_app_permission",
	}
]
fixtures = [
	{"dt": "Role", "filters": [["name", "in", [
		"Safety Manager",
		"Safety User"
	]]]},
	{"dt": "Custom DocPerm", "filters": [["role", "in", [
		"Safety Manager",
		"Safety User"
	]]]},
	{"dt": "Safety Incident Classification", "filters": [["name", "in", [
		"Fatality",
		"Lost Time Injury",
		"Minor Injury",
		"Near Miss",
		"Unsafe Act"
	]]]},
    {"dt": "Document Register Subclass", "filters": [["name", "in", [
		"Policy",
		"Mandatory Code of Practice",
		"System Procedure",
        "Standard Operating Procedure",
        "Template",
        "Register"
	]]]},
    {"dt": "Document Register Class", "filters": [["name", "in", [
		"Policy",
		"Procedure"
	]]]},
	{"dt": "PEEPO Factor"},
	{"dt": "ICAM Category"}
]

doctype_js = {
    "Safety Performance Communication": "doctype/safety_performance_communication/safety_performance_communication.js",
    "Monthly SHE Data": "doctype/monthly_she_data/monthly_she_data.js"
}

scheduler_events = {
    "cron": {
        "0 4 * * 1": [
            "safety.safety.doctype.safety_performance_communication.safety_performance_communication.generate_weekly_safety_performance_communications"
        ]
    },
    "daily": [
		"safety.safety.doctype.document_register.document_register.send_author_revision_reminders",
	],
    "weekly": [
		"safety.controllers.notifications.send_weekly_ppe_expired_notifications",
		"safety.controllers.notifications.send_weekly_ppe_expiring_soon_notifications",
	]
}

after_install = "safety.setup.add_employee_doclinks.ensure_employee_links"
after_migrate = "safety.setup.add_employee_doclinks.ensure_employee_links"

# MONTHLY SHE DATA SECURITY HOOKS V1
permission_query_conditions = globals().get(
    "permission_query_conditions", {}
)
permission_query_conditions["Monthly SHE Data"] = (
    "safety.safety.doctype.monthly_she_data.monthly_she_data."
    "get_permission_query_conditions"
)

has_permission = globals().get("has_permission", {})
has_permission["Monthly SHE Data"] = (
    "safety.safety.doctype.monthly_she_data.monthly_she_data."
    "has_permission"
)
# END MONTHLY SHE DATA SECURITY HOOKS V1
