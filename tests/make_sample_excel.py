"""Generate a sample companies.xlsx for testing and as a client template."""
import os
from openpyxl import Workbook

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "companies_sample.xlsx")

wb = Workbook()
ws = wb.active
ws.title = "Companies"

# Header row (matches what excel_reader expects)
ws.append(["company_name", "email", "language"])

# Sample rows - some valid, some edge cases for validation testing
rows = [
    ["Acme Corp", "hr@acme-example.com", "en"],
    ["شركة النور", "jobs@alnoor-example.com", "ar"],
    ["Globex", "careers@globex-example.com", ""],          # empty language -> default
    ["Initech", "not-an-email", "en"],                      # invalid email -> error report
    ["", "ghost@example.com", "en"],                        # missing company name -> error
    ["Umbrella", "info@umbrella-example.com", "EN"],        # uppercase language
]
for r in rows:
    ws.append(r)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
wb.save(OUT)
print(f"Sample Excel written to: {os.path.abspath(OUT)}")
