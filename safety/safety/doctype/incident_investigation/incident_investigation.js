// Copyright (c) 2026, BuFf0k and contributors
// For license information, please see license.txt

frappe.ui.form.on("Incident Investigation", {
    refresh(frm) {
        add_create_buttons(frm);
        render_linked_records(frm);
        setup_peepo_icam_queries(frm);
    },

    safety_incident(frm) {
        if (!frm.doc.safety_incident) {
            return;
        }

        frappe.db.get_value(
            "Incident Report",
            frm.doc.safety_incident,
            [
                "incident_number",
                "datetime_incident",
                "site",
                "location_on_site",
                "investigation_type",
                "description_of_the_event",
            ]
        ).then((r) => {
            const source = r.message || {};
            frm.set_value("incident_number", source.incident_number);
            frm.set_value("incident_datetime", source.datetime_incident);
            frm.set_value("site", source.site);
            frm.set_value("location_on_site", source.location_on_site);

            if (!frm.doc.investigation_type) {
                frm.set_value("investigation_type", source.investigation_type);
            }
            if (!frm.doc.incident_summary) {
                frm.set_value("incident_summary", source.description_of_the_event);
            }
        });
    },
});

function setup_peepo_icam_queries(frm) {
    // PEEPO Factor and ICAM Category are both taxonomies split by a sibling
    // field on the same row (peepo_category / icam_level) - restrict each
    // Link's options to the matching branch of the taxonomy.
    frm.set_query("factor", "peepo_items", (doc, cdt, cdn) => {
        const row = locals[cdt][cdn];
        return { filters: { peepo_category: row.peepo_category } };
    });

    frm.set_query("category", "icam_findings", (doc, cdt, cdn) => {
        const row = locals[cdt][cdn];
        return { filters: { icam_level: row.icam_level } };
    });
}

frappe.ui.form.on("Incident Investigation PEEPO Item", {
    peepo_category(frm, cdt, cdn) {
        // The previously picked Factor may no longer belong to the new category.
        frappe.model.set_value(cdt, cdn, "factor", null);
    },
});

frappe.ui.form.on("Incident Investigation ICAM Finding", {
    icam_level(frm, cdt, cdn) {
        // The previously picked Category may no longer belong to the new level.
        frappe.model.set_value(cdt, cdn, "category", null);
    },
});

function add_create_buttons(frm) {
    if (frm.is_new()) {
        return;
    }

    frm.add_custom_button(
        __("Interview"),
        () => make_linked_document(frm, "make_interview", "Incident Investigation Interview"),
        __("Create")
    );

    frm.add_custom_button(
        __("Lessons Learnt"),
        () => make_linked_document(frm, "make_lessons_learnt", "Safety Lessons Learnt"),
        __("Create")
    );

    if (["Approved", "Actions Generated"].includes(frm.doc.workflow_state)) {
        frm.add_custom_button(
            __("Corrective Actions"),
            () => generate_corrective_actions(frm),
            __("Create")
        );
    }
}

function make_linked_document(frm, method_name, target_doctype) {
    frappe.call({
        method: `safety.safety.doctype.incident_investigation.incident_investigation.${method_name}`,
        args: { investigation: frm.doc.name },
        freeze: true,
        callback(r) {
            if (!r.message) {
                return;
            }

            const doc = frappe.model.sync(r.message)[0];
            frappe.set_route("Form", target_doctype, doc.name);
        },
    });
}

function generate_corrective_actions(frm) {
    frappe.call({
        method: "safety.safety.doctype.incident_investigation.incident_investigation.generate_corrective_actions",
        args: { investigation: frm.doc.name },
        freeze: true,
        freeze_message: __("Generating corrective actions..."),
        callback(r) {
            const result = r.message || {};
            const count = (result.created || []).length;
            frappe.show_alert({
                message: __("{0} corrective action(s) created.", [count]),
                indicator: count ? "green" : "blue",
            });
            frm.reload_doc();
        },
    });
}

function render_linked_records(frm) {
    const field = frm.get_field("linked_records_html");
    if (!field || frm.is_new()) {
        return;
    }

    field.$wrapper.html(`<div class="text-muted">${__("Loading linked records...")}</div>`);

    frappe.call({
        method: "safety.safety.doctype.incident_investigation.incident_investigation.get_linked_records",
        args: { investigation: frm.doc.name },
        callback(r) {
            const data = r.message || {};
            field.$wrapper.html(
                linked_table(
                    __("Interviews"),
                    "Incident Investigation Interview",
                    data.interviews || [],
                    (row) => [
                        row.interviewee_employee || row.external_interviewee_name,
                        row.workflow_state || __("Draft"),
                    ].filter(Boolean).join(" · ")
                ) +
                linked_table(
                    __("Corrective Actions"),
                    "Safety Corrective Action",
                    data.actions || [],
                    (row) => [
                        row.priority,
                        row.responsible_employee,
                        row.workflow_state || __("Open"),
                    ].filter(Boolean).join(" · ")
                ) +
                linked_table(
                    __("Lessons Learnt"),
                    "Safety Lessons Learnt",
                    data.lessons || [],
                    (row) => [row.title, row.workflow_state || __("Draft")]
                        .filter(Boolean)
                        .join(" · ")
                )
            );
        },
    });
}

function linked_table(title, doctype, rows, detail_callback) {
    const body = rows.length
        ? rows.map((row) => {
            const href = frappe.utils.get_form_link(doctype, row.name);
            return `
                <tr>
                    <td><a href="${href}">${frappe.utils.escape_html(row.name)}</a></td>
                    <td>${frappe.utils.escape_html(detail_callback(row) || "")}</td>
                </tr>
            `;
        }).join("")
        : `<tr><td colspan="2" class="text-muted">${__("No records")}</td></tr>`;

    return `
        <div class="mb-4">
            <h5>${frappe.utils.escape_html(title)}
                <span class="badge badge-light">${rows.length}</span>
            </h5>
            <table class="table table-bordered table-sm"><tbody>${body}</tbody></table>
        </div>
    `;
}
