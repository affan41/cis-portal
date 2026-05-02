import io, os
from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from xero_client import XeroClient
from pdf_gen import generate_cis_pdf

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())
xero = XeroClient()

# Hardcoded contractor details (these don't change)
CONTRACTOR = {
    "name": "Instruct Construction Group LTD",
    "address": "C/O Cutts And Company, Eden Point, Three Acres Lane, Cheadle Hulme, Cheshire, SK8 6RL",
    "paye_ref": "120/BF00913",
}

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _cis_period(month, year):
    """CIS period runs 6th of month to 5th of next month."""
    m = int(month)
    y = int(year)
    from_date = f"{y}-{m:02d}-06"
    if m == 12:
        to_date = f"{y + 1}-01-05"
        period_label = f"6 December to 5 January {y + 1}"
        tax_month_ended = f"5 Jan {y + 1}"
    else:
        to_date = f"{y}-{m + 1:02d}-05"
        period_label = f"6 {MONTH_NAMES[m]} to 5 {MONTH_NAMES[m + 1]} {y}"
        tax_month_ended = f"5 {MONTH_NAMES[m + 1][:3]} {y}"
    return from_date, to_date, period_label, tax_month_ended


@app.route("/")
def index():
    if not xero.is_authenticated():
        return render_template("connect.html")
    return render_template("index.html", org=xero.org_name())


@app.route("/connect")
def connect():
    url, state = xero.get_auth_url()
    session["oauth_state"] = state
    return redirect(url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Authorisation failed. Please try again.", 400
    try:
        xero.handle_callback(code)
    except Exception as e:
        return f"Error: {e}", 500
    return redirect("/")


@app.route("/disconnect")
def disconnect():
    token_path = os.path.join(os.path.dirname(__file__), ".tokens.json")
    if os.path.exists(token_path):
        os.remove(token_path)
    xero._tokens = {}
    return redirect("/")


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not xero.is_authenticated():
        return jsonify([])
    try:
        return jsonify(xero.search_contacts(q))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/all-periods")
def all_periods():
    contact_id = request.args.get("contact_id")
    if not contact_id:
        return jsonify({"error": "Missing contact_id"}), 400
    try:
        contact = xero.get_contact(contact_id)
        result = xero.get_all_cis_data(contact_id)
        if result.get("error"):
            return jsonify({"contact": {"name": contact.get("Name", "")}, "error": result["error"]})
        return jsonify({
            "contact": {"name": contact.get("Name", ""), "utr": contact.get("TaxNumber", "")},
            "periods": result["periods"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/statement")
def statement():
    contact_id = request.args.get("contact_id")
    month = request.args.get("month")
    year = request.args.get("year")
    if not all([contact_id, month, year]):
        return jsonify({"error": "Missing parameters"}), 400
    try:
        from_date, to_date, period_label, tax_month_ended = _cis_period(month, year)
        contact = xero.get_contact(contact_id)
        contact_name = contact.get("Name", "")
        utr = contact.get("TaxNumber", "")

        result = xero.get_cis_data(contact_id, from_date, to_date)
        if result.get("error"):
            return jsonify({"contact": {"name": contact_name}, "error": result["error"]})

        return jsonify({
            "contact": {"name": contact_name, "utr": utr},
            "invoices": result["invoices"],
            "totals": result["totals"],
            "period_label": period_label,
            "tax_month_ended": tax_month_ended,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download")
def download():
    contact_id = request.args.get("contact_id")
    month = request.args.get("month")
    year = request.args.get("year")

    from_date, to_date, period_label, tax_month_ended = _cis_period(month, year)
    contact = xero.get_contact(contact_id)
    contact_name = contact.get("Name", "Unknown")
    utr = contact.get("TaxNumber", "")
    # Try to get verification number from contact
    verification = ""

    result = xero.get_cis_data(contact_id, from_date, to_date)
    invoices = result.get("invoices", [])
    totals = result.get("totals", {
        "gross": 0, "materials": 0, "non_cis": 0,
        "liable": 0, "cis_deduction": 0, "paid": 0,
    })

    pdf = generate_cis_pdf(
        contractor_name=CONTRACTOR["name"],
        contractor_address=CONTRACTOR["address"],
        paye_ref=CONTRACTOR["paye_ref"],
        period_label=period_label,
        tax_month_ended=tax_month_ended,
        subcontractor_name=contact_name,
        utr=utr,
        verification_number=verification,
        invoices=invoices,
        totals=totals,
    )

    safe_name = contact_name.replace(" ", "_")
    month_name = MONTH_NAMES[int(month)][:3]
    return send_file(
        io.BytesIO(pdf),
        download_name=f"CIS_Statement_{contact_name}_{year}{month_name}.pdf",
        as_attachment=True,
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    print("\n  CIS Portal — Instruct Construction Group LTD")
    print("  Running at: http://localhost:8080")
    print("  Office network: http://192.168.10.31:8080\n")
    app.run(host="0.0.0.0", port=8080, debug=False)
