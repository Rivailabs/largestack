import csv
import io
import re

def capture_lead(name: str, email: str, *, consent: bool = False, company: str = "") -> dict:
    if not consent:
        raise ValueError("Consent is required")
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        raise ValueError("Invalid email")
    return {
        "name": name,
        "email": email,
        "consent": consent,
        "company": company
    }

def qualify_lead(lead: dict) -> dict:
    qualified = bool(lead.get("email")) and lead.get("consent") is True
    return {"qualified": qualified, "lead": lead}

def export_csv(leads: list) -> str:
    if not leads:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["name", "email", "consent", "company"])
    writer.writeheader()
    for lead in leads:
        writer.writerow(lead)
    return output.getvalue()
