import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

OUTPUT_DIR = "/Users/macuser/Ventro/mas-vgfr/backend/test_documents/"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def create_po(filepath):
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    normal_style = styles['Normal']

    elements.append(Paragraph("PURCHASE ORDER: PO-2026-991", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Vendor: TechSupplies Inc.", normal_style))
    elements.append(Paragraph("Date: 2026-10-15", normal_style))
    elements.append(Spacer(1, 24))

    data = [
        ['Item', 'Description', 'Qty', 'Unit Price', 'Total'],
        ['001', 'Industrial Server Rack Type A', '5', '$1,200.00', '$6,000.00'],
        ['002', 'Cisco Catalyst Switch 9200', '10', '$850.00', '$8,500.00'],
        ['003', 'Cat6 Ethernet Cable (1000ft spool)', '20', '$150.00', '$3,000.00'],
    ]
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Subtotal: $17,500.00", styles['Heading3']))
    elements.append(Paragraph("Tax (10%): $1,750.00", styles['Heading3']))
    elements.append(Paragraph("Total Amount: $19,250.00", styles['Heading2']))
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Approved by: Corporate Procurement Dept.", normal_style))
    
    doc.build(elements)

def create_grn(filepath):
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    normal_style = styles['Normal']

    elements.append(Paragraph("RECEIVING REPORT (GRN)", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Doc Num: GRN-2026-8802", styles['Heading3']))
    elements.append(Paragraph("Ref PO: PO-2026-991", styles['Heading3']))
    elements.append(Paragraph("Date Received: 2026-10-18", styles['Heading3']))
    elements.append(Spacer(1, 24))

    data = [
        ['Part #', 'Details', 'Ordered', 'Received', 'Condition'],
        ['001', 'Industrial Server Rack Type A', '5', '5', 'Good'],
        ['002', 'Cisco Switch (9200 series)', '10', '8', '2 Missing'],
        ['003', 'Cat6 Cables (Spools)', '20', '20', 'Good'],
    ]
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Courier-Bold'),
        ('FONTNAME', (0,1), (-1,-1), 'Courier'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Received by: Warehouse Loading Dock B (J. Smith)", normal_style))
    
    doc.build(elements)

def create_inv(filepath):
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], textColor=colors.darkblue)
    normal_style = styles['Normal']

    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Invoice #: INV-449102", styles['Heading3']))
    elements.append(Paragraph("Date: 2026-10-20", styles['Heading3']))
    elements.append(Paragraph("Ref PO: PO-2026-991", styles['Heading3']))
    elements.append(Spacer(1, 24))

    data = [
        ['Description', 'Qty Shipped', 'Unit Price', 'Line Total'],
        ['Type A Server Rack', '5', '$1,200.00', '$6,000.00'],
        ['Cisco 9200 Switches', '8', '$850.00', '$6,800.00'],
        ['Cat6 Full Spool (1000\')', '20', '$150.00', '$3,000.00'],
        ['Freight & Handling', '1', '$450.00', '$450.00'],
    ]
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.navy),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Times-Bold'),
        ('FONTNAME', (0,1), (-1,-1), 'Times-Roman'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Subtotal: $16,250.00", normal_style))
    elements.append(Paragraph("Tax (10%): $1,625.00", normal_style))
    elements.append(Paragraph("Balance Due: $17,875.00", styles['Heading2']))
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("<i>Please remit payment within 30 days to TechSupplies Inc.</i>", normal_style))
    
    doc.build(elements)

create_po(os.path.join(OUTPUT_DIR, "1_PO_Complex.pdf"))
create_grn(os.path.join(OUTPUT_DIR, "2_GRN_Complex.pdf"))
create_inv(os.path.join(OUTPUT_DIR, "3_INV_Complex.pdf"))
print("All realistic test documents generated instantly via ReportLab!")
