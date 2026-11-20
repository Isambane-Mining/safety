frappe.query_reports["Monthly SHE Performance"] = (() => {
    // MONTHLY SHE EXCEL FORMATTING V1
    // Presentation only. Incident calculations are unchanged.

    const wholeNumberRows = new Set([
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
        "Workforce"
    ]);

    const totalColours = {
        "Total Injuries": "#a7c8e8",
        "Cumm Total Injuries": "#d1d5db",
        "Total PDI": "#d1d5db"
    };

    return {
        formatter: function (
            value,
            row,
            column,
            data,
            default_formatter
        ) {
            const formatted = default_formatter(
                value, row, column, data
            );

            if (!data) {
                return formatted;
            }

            const category = String(data.category || "").trim();

            // Blank section rows should never show 0.00.
            if (!category) {
                return "";
            }

            const isMonthlyColumn =
                typeof column.fieldname === "string" &&
                /^m_\d{4}_\d{2}$/.test(column.fieldname);

            let display = formatted;

            if (isMonthlyColumn && wholeNumberRows.has(category)) {
                const number = Number(value);

                if (
                    value !== null &&
                    value !== undefined &&
                    value !== "" &&
                    Number.isFinite(number) &&
                    Number.isInteger(number)
                ) {
                    display = number.toLocaleString(undefined, {
                        minimumFractionDigits: 0,
                        maximumFractionDigits: 0
                    });
                }
            }

            // Bold total-row names without recolouring the label.
            if (column.fieldname === "category") {
                if (totalColours[category]) {
                    return `<strong>${display}</strong>`;
                }
                return display;
            }

            // Match the original Excel total-row cell shading.
            if (isMonthlyColumn && totalColours[category]) {
                return (
                    '<div style="' +
                    'display:block;' +
                    'margin:-6px -10px;' +
                    'padding:6px 10px;' +
                    'min-height:26px;' +
                    'box-sizing:border-box;' +
                    'font-weight:700;' +
                    'background-color:' +
                    totalColours[category] +
                    ';">' +
                    display +
                    '</div>'
                );
            }

            return display;
        }
    };
})();
