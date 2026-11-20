frappe.ui.form.on("Monthly SHE Data", {
    // MONTHLY SHE AUTO RECORDED FLAGS V1
    hours_worked(frm) {
        monthly_she_mark_recorded(
            frm, "hours_worked", "hours_recorded"
        );
    },

    workforce(frm) {
        monthly_she_mark_recorded(
            frm, "workforce", "workforce_recorded"
        );
    },
    // END MONTHLY SHE AUTO RECORDED FLAGS V1

    refresh(frm) {
        // Keep verification fields controlled by the server workflow.
        frm.set_df_property("verification_status", "read_only", 1);
        frm.set_df_property("verified_by", "read_only", 1);
        frm.set_df_property("verified_on", "read_only", 1);

        // Default new records to Draft.
        if (frm.is_new() && !frm.doc.verification_status) {
            frm.set_value("verification_status", "Draft");
        }

        // Retrieve authorized sites from the server.
        frappe.call({
            method: "safety.safety.doctype.monthly_she_data.monthly_she_data.get_authorized_sites",

            callback(r) {
                if (!r.message) return;

                const allowedSites = r.message;

                frm.set_query("site", () => ({
                    filters: {
                        name: ["in", allowedSites]
                    }
                }));
            }
        });

        // Verified records are locked for ordinary users.
        if (
            frm.doc.verification_status === "Verified" &&
            frappe.session.user !== "Administrator"
        ) {
            frm.disable_form();
            return;
        }

        // Only another Safety Manager may verify a Draft.
        if (
            !frm.is_new() &&
            frm.doc.verification_status === "Draft" &&
            frappe.user.has_role("Safety Manager") &&
            frm.doc.owner !== frappe.session.user
        ) {
            frm.add_custom_button(
                __("Verify"),
                () => {
                    frappe.confirm(
                        __(
                            "Verify Monthly SHE data for {0} - {1}?",
                            [
                                frm.doc.site,
                                frm.doc.reporting_month
                            ]
                        ),
                        () => {
                            frm.set_value(
                                "verification_status",
                                "Verified"
                            ).then(() => {
                                frm.save();
                            });
                        }
                    );
                },
                __("Workflow")
            );
        }
    }
});


function monthly_she_mark_recorded(frm, valueField, flagField) {
    // Never modify an already verified document.
    if (frm.doc.verification_status === "Verified") {
        return;
    }

    const value = frm.doc[valueField];

    // Zero is a valid recorded value.
    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return;
    }

    if (!frm.doc[flagField]) {
        frm.set_value(flagField, 1);
    }
}
