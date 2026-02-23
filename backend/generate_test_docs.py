import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def create_pdf(filename, title, doc_number, ref_num, date, vendor, lines, total, is_grn=False):
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    
    # Header
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, title)
    
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Document Number: {doc_number}")
    c.drawString(50, height - 100, f"Date: {date}")
    if ref_num:
        c.drawString(50, height - 120, f"Reference PO: {ref_num}")
    
    # Vendor
    c.setFont("Helvetica-Bold", 12)
    c.drawString(400, height - 80, "Vendor:")
    c.setFont("Helvetica", 12)
    c.drawString(400, height - 100, vendor)
    
    # Line Items Header
    y = height - 180
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Description")
    c.drawString(300, y, "Qty")
    if not is_grn:
        c.drawString(380, y, "Unit Price")
        c.drawString(480, y, "Total")
    
    # Line Items
    y -= 30
    c.setFont("Helvetica", 12)
    for line in lines:
        c.drawString(50, y, line["desc"])
        c.drawString(300, y, str(line["qty"]))
        if not is_grn:
            c.drawString(380, y, f"${line['price']:.2f}")
            c.drawString(480, y, f"${line['qty'] * line['price']:.2f}")
        y -= 25
        
    # Total
    if not is_grn:
        y -= 20
        c.setFont("Helvetica-Bold", 14)
        c.drawString(380, y, "Grand Total:")
        c.drawString(480, y, f"${total:.2f}")
        
    c.save()

os.makedirs("test_documents", exist_ok=True)

# Scenario 1: Perfect Match
lines = [
    {"desc": "Dell 27-inch 4K Monitor", "qty": 10, "price": 350.00},
    {"desc": "Logitech MX Master 3 Mouse", "qty": 15, "price": 99.00},
    {"desc": "Keychron K2 Mechanical Keyboard", "qty": 15, "price": 85.00},
]
total = sum(l["qty"] * l["price"] for l in lines)

create_pdf("test_documents/PO-1001.pdf", "PURCHASE ORDER", "PO-1001", None, "2026-02-01", "Tech Supplies Inc.", lines, total)
create_pdf("test_documents/GRN-1001.pdf", "GOODS RECEIPT NOTE", "GRN-1001", "PO-1001", "2026-02-05", "Tech Supplies Inc.", lines, total, is_grn=True)
create_pdf("test_documents/INV-1001.pdf", "INVOICE", "INV-1001", "PO-1001", "2026-02-10", "Tech Supplies Inc.", lines, total)

# Scenario 2: Price Mismatch (SAMR trigger)
lines_po = [
    {"desc": "Herman Miller Aeron Chair", "qty": 5, "price": 1200.00},
    {"desc": "Standing Desk Frame", "qty": 5, "price": 450.00},
]
total_po = sum(l["qty"] * l["price"] for l in lines_po)

lines_inv = [
    {"desc": "Herman Miller Aeron Chair", "qty": 5, "price": 1350.00}, # Price increased!
    {"desc": "Standing Desk Frame", "qty": 5, "price": 450.00},
]
total_inv = sum(l["qty"] * l["price"] for l in lines_inv)

create_pdf("test_documents/PO-2002.pdf", "PURCHASE ORDER", "PO-2002", None, "2026-02-15", "Office Depot", lines_po, total_po)
create_pdf("test_documents/GRN-2002.pdf", "GOODS RECEIPT NOTE", "GRN-2002", "PO-2002", "2026-02-18", "Office Depot", lines_po, total_po, is_grn=True)
create_pdf("test_documents/INV-2002.pdf", "INVOICE", "INV-2002", "PO-2002", "2026-02-20", "Office Depot", lines_inv, total_inv)

print("Generated 6 synthetic PDF documents in test_documents/ directory for testing workflows.")
