import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_order_pdf(order):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    title_style.alignment = 1 # Center
    
    normal_style = styles['Normal']
    
    elements = []
    
    # Title
    elements.append(Paragraph(f"Order #{order.id} Confirmation", title_style))
    elements.append(Spacer(1, 12))
    
    # Customer Info
    cust_info = f"<b>Customer:</b> {order.user.username if order.user else 'Guest'}<br/>"
    cust_info += f"<b>Email:</b> {order.email or (order.user.email if order.user else 'N/A')}<br/>"
    cust_info += f"<b>Date:</b> {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}<br/>"
    cust_info += f"<b>Status:</b> {order.status}"
    
    elements.append(Paragraph(cust_info, normal_style))
    elements.append(Spacer(1, 12))
    
    # Address Info
    if hasattr(order, 'orderaddress'):
        addr = order.orderaddress
        addr_info = f"<b>Shipping Address:</b><br/>"
        addr_info += f"Name: {addr.name}<br/>"
        addr_info += f"Phone: {addr.phone}<br/>"
        addr_info += f"Address: {addr.address}<br/>"
        addr_info += f"Type: {addr.type}"
        
        elements.append(Paragraph(addr_info, normal_style))
        elements.append(Spacer(1, 12))
    
    # Items Table
    data = [['Product', 'Quantity', 'Price']]
    for item in order.items.all():
        if getattr(item, 'is_free_item', False):
            name = f"Free T-shirt (Size: {getattr(item, 'free_item_size', 'N/A')})"
        elif item.product:
            name = item.product.name
            if getattr(item, 'ordered_size', None):
                name += f"\n(Size: {item.ordered_size})"
            if getattr(item, 'ordered_color_name', None):
                name += f"\n(Color: {item.ordered_color_name})"
        else:
            name = 'Item'
            
        reconstitute = "\n[Includes Reconstitute Pen]" if getattr(item, 'reconstitute_pen', False) else ""
        data.append([f"{name}{reconstitute}", str(item.quantity), f"${item.price:.2f}"])
    
    table = Table(data, colWidths=[300, 100, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 12))
    
    # Summary
    summary_info = f"<b>Subtotal:</b> ${order.total_price:.2f}<br/>"
    if hasattr(order, 'extra_charge') and order.extra_charge > 0:
        summary_info += f"<b>Reconstitute Pen Charge:</b> ${order.extra_charge:.2f}<br/>"
    summary_info += f"<b>Shipping Fee:</b> ${order.shipping_fee:.2f}<br/>"
    
    total = order.total_price + order.shipping_fee + getattr(order, 'extra_charge', 0)
    summary_info += f"<br/><b>Total Paid:</b> ${total:.2f}"
    
    summary_style = ParagraphStyle('Summary', parent=styles['Normal'], alignment=2) # Right align
    elements.append(Paragraph(summary_info, summary_style))
    
    doc.build(elements)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
