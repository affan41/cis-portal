import os, json, time, secrets, hashlib, base64
from datetime import datetime
from urllib.parse import urlencode
import requests
from dotenv import load_dotenv

load_dotenv()

AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
API_BASE = "https://api.xero.com/api.xro/2.0"
CONNECTIONS_URL = "https://api.xero.com/connections"
REDIRECT_URI = os.getenv("XERO_REDIRECT_URI", "http://localhost:8080/callback")
SCOPES = "openid profile email accounting.contacts.read accounting.invoices.read accounting.payments.read offline_access"

TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".tokens.json")
PKCE_FILE = os.path.join(os.path.dirname(__file__), ".pkce.json")


def _pkce_pair():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _parse_xero_date(d):
    """Parse Xero date formats into a datetime object."""
    if not d:
        return None
    if "T" in str(d):
        return datetime.fromisoformat(str(d).replace("Z", ""))
    if "/Date(" in str(d):
        import re
        ms = re.search(r"\d+", str(d))
        if ms:
            return datetime.utcfromtimestamp(int(ms.group()) / 1000)
    return None


class XeroClient:
    def __init__(self):
        self.client_id = os.getenv("XERO_CLIENT_ID")
        self.client_secret = os.getenv("XERO_CLIENT_SECRET")
        self._tokens = self._load_tokens()

    def _load_tokens(self):
        try:
            with open(TOKEN_FILE) as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_tokens(self, tokens):
        self._tokens = tokens
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f)

    def is_authenticated(self):
        return bool(self._tokens.get("access_token"))

    def get_auth_url(self):
        state = secrets.token_urlsafe(16)
        verifier, challenge = _pkce_pair()
        with open(PKCE_FILE, "w") as f:
            json.dump({"verifier": verifier, "state": state}, f)
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}", state

    def handle_callback(self, code):
        verifier = ""
        try:
            with open(PKCE_FILE) as f:
                verifier = json.load(f).get("verifier", "")
        except Exception:
            pass
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": self.client_id,
                "code_verifier": verifier,
            },
            auth=(self.client_id, self.client_secret),
        )
        tokens = resp.json()
        if "access_token" not in tokens:
            raise Exception(f"Token error: {tokens}")
        tokens["expires_at"] = time.time() + tokens.get("expires_in", 1800)
        conns = requests.get(
            CONNECTIONS_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        ).json()
        if conns:
            tokens["tenant_id"] = conns[0]["tenantId"]
            tokens["org_name"] = conns[0].get("tenantName", "")
        self._save_tokens(tokens)

    def _refresh_if_needed(self):
        if time.time() > self._tokens.get("expires_at", 0) - 60:
            resp = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._tokens["refresh_token"],
                },
                auth=(self.client_id, self.client_secret),
            )
            tokens = resp.json()
            tokens["expires_at"] = time.time() + tokens.get("expires_in", 1800)
            tokens["tenant_id"] = self._tokens["tenant_id"]
            tokens["org_name"] = self._tokens.get("org_name", "")
            self._save_tokens(tokens)

    def _headers(self):
        self._refresh_if_needed()
        return {
            "Authorization": f"Bearer {self._tokens['access_token']}",
            "Xero-tenant-id": self._tokens["tenant_id"],
            "Accept": "application/json",
        }

    def org_name(self):
        return self._tokens.get("org_name", "Instruct Construction Group LTD")

    def search_contacts(self, query):
        if len(query) < 2:
            return []
        r = requests.get(
            f"{API_BASE}/Contacts",
            headers=self._headers(),
            params={"searchTerm": query, "ContactStatus": "ACTIVE"},
        )
        return [
            {"id": c["ContactID"], "name": c["Name"]}
            for c in r.json().get("Contacts", [])
        ]

    def get_contact(self, contact_id):
        r = requests.get(f"{API_BASE}/Contacts/{contact_id}", headers=self._headers())
        contacts = r.json().get("Contacts", [])
        return contacts[0] if contacts else {}

    def get_all_cis_data(self, contact_id):
        """Get ALL CIS bills for a subcontractor, grouped by CIS period."""
        where = f'Contact.ContactID==guid("{contact_id}") AND Type=="ACCPAY" AND Status=="PAID"'
        r = requests.get(
            f"{API_BASE}/Invoices",
            headers=self._headers(),
            params={"where": where},
        )
        if r.status_code != 200:
            return {"error": f"Xero returned {r.status_code}", "periods": []}
        try:
            all_bills = r.json().get("Invoices", [])
        except Exception:
            return {"error": "Invalid response from Xero", "periods": []}

        # Group bills by CIS period based on payment date
        period_map = {}
        for bill in all_bills:
            for pmt in bill.get("Payments", []):
                pmt_date = _parse_xero_date(pmt.get("Date"))
                if not pmt_date:
                    continue
                # Determine CIS period: 6th of month to 5th of next month
                if pmt_date.day <= 5:
                    # Falls in previous month's period
                    if pmt_date.month == 1:
                        period_month = 12
                        period_year = pmt_date.year - 1
                    else:
                        period_month = pmt_date.month - 1
                        period_year = pmt_date.year
                else:
                    period_month = pmt_date.month
                    period_year = pmt_date.year

                key = f"{period_year}-{period_month:02d}"
                if key not in period_map:
                    period_map[key] = {
                        "month": period_month,
                        "year": period_year,
                        "invoices": [],
                        "total_gross": 0,
                        "total_cis": 0,
                        "total_paid": 0,
                    }
                gross = bill.get("SubTotal", 0) or 0
                cis = bill.get("CISDeduction", 0) or 0
                period_map[key]["invoices"].append({
                    "reference": bill.get("InvoiceNumber", "") or "None",
                    "payment_date": pmt_date.strftime("%d %B %Y"),
                    "gross": gross,
                    "cis_deduction": cis,
                    "paid": gross - cis,
                })
                period_map[key]["total_gross"] += gross
                period_map[key]["total_cis"] += cis
                period_map[key]["total_paid"] += gross - cis
                break  # Only count once per bill

        # Sort by date descending
        MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"]
        periods = []
        for key in sorted(period_map.keys(), reverse=True):
            p = period_map[key]
            m = p["month"]
            y = p["year"]
            if m == 12:
                label = f"6 December {y} to 5 January {y + 1}"
            else:
                label = f"6 {MONTH_NAMES[m]} to 5 {MONTH_NAMES[m + 1]} {y}"
            periods.append({
                "key": key,
                "month": m,
                "year": y,
                "period_label": label,
                "total_gross": p["total_gross"],
                "total_cis": p["total_cis"],
                "total_paid": p["total_paid"],
                "invoice_count": len(p["invoices"]),
            })

        return {"periods": periods}

    def get_cis_data(self, contact_id, period_start, period_end):
        """
        Get CIS statement data for a subcontractor in a specific CIS period.
        Filters bills by payment date falling within the period.
        """
        where = f'Contact.ContactID==guid("{contact_id}") AND Type=="ACCPAY" AND Status=="PAID"'
        r = requests.get(
            f"{API_BASE}/Invoices",
            headers=self._headers(),
            params={"where": where},
        )
        if r.status_code != 200:
            return {"error": f"Xero returned {r.status_code}", "invoices": []}
        try:
            all_bills = r.json().get("Invoices", [])
        except Exception:
            return {"error": "Invalid response from Xero", "invoices": []}

        start = datetime.strptime(period_start, "%Y-%m-%d")
        end = datetime.strptime(period_end, "%Y-%m-%d")

        matched = []
        for bill in all_bills:
            # Check payment dates
            for pmt in bill.get("Payments", []):
                pmt_date = _parse_xero_date(pmt.get("Date"))
                if pmt_date and start <= pmt_date <= end:
                    matched.append({
                        "reference": bill.get("InvoiceNumber", "") or "None",
                        "payment_date": pmt_date.strftime("%d %B %Y"),
                        "gross": bill.get("SubTotal", 0) or 0,
                        "materials": 0,  # TODO: extract from line items if tagged
                        "non_cis": 0,
                        "cis_deduction": bill.get("CISDeduction", 0) or 0,
                        "cis_rate": bill.get("CISRate", 0) or 0,
                    })
                    break  # Only count once per bill

        # Calculate totals
        total_gross = sum(m["gross"] for m in matched)
        total_materials = sum(m["materials"] for m in matched)
        total_non_cis = sum(m["non_cis"] for m in matched)
        total_cis = sum(m["cis_deduction"] for m in matched)
        liable = total_gross - total_materials - total_non_cis
        total_paid = total_gross - total_cis

        # Add labour (= gross - materials - non_cis) to each row
        for m in matched:
            m["labour"] = m["gross"] - m["materials"] - m["non_cis"]
            m["paid"] = m["gross"] - m["cis_deduction"]

        return {
            "invoices": matched,
            "totals": {
                "gross": total_gross,
                "materials": total_materials,
                "non_cis": total_non_cis,
                "liable": liable,
                "cis_deduction": total_cis,
                "paid": total_paid,
            },
        }
