"""Build a messy sample Excel that mimics what a client file might look like:
   - Arabic sector names
   - some invalid emails
   - some duplicates
   - some unknown sectors
   Used to verify preview_import.py handles real-world chaos.
"""
import os
from openpyxl import Workbook

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "_messy_sample.xlsx")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

wb = Workbook()
ws = wb.active
ws.title = "Companies"
# Arabic header names — preview should auto-map them
ws.append(["اسم الشركة", "الإيميل", "اللغة", "القطاع", "المدينة"])

rows = [
    ["شركة الصحة المتقدمة", "hr@health-co-example.com", "ar", "صحة", "Riyadh"],
    ["TechCo", "jobs@techco-example.com", "en", "IT", "Riyadh"],
    ["مكتب القانون الأول", "info@law-example.com", "ar", "قانون", "Riyadh"],
    ["Marketing House", "careers@mkt-example.com", "en", "Marketing & Advertising", "Jeddah"],
    ["شركة الشحن السريع", "ops@shipping-example.com", "ar", "لوجستيك وشحن", "Dammam"],
    ["UnknownCo", "x@unk-example.com", "en", "Quantum Hyperloop", "Riyadh"],  # unknown sector
    ["BadEmail Inc", "not-an-email", "en", "Finance", "Riyadh"],              # invalid email
    ["Dup1", "dup@example.com", "en", "Finance", "Riyadh"],
    ["Dup2", "dup@example.com", "en", "Finance", "Jeddah"],                   # duplicate
    ["NoSector", "ns@example.com", "en", "", "Riyadh"],                       # missing sector
    ["HotelLux", "hr@hotel-example.com", "en", "Hospitality", "Mecca"],
    ["Aramex Branch", "jobs@aramex2-example.com", "en", "Logistics", "Riyadh"],
]
for r in rows:
    ws.append(r)
wb.save(OUT)
print(f"messy sample written: {OUT}")
