from flask import Flask, render_template, request, jsonify, session, redirect, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
from reportlab.lib.pagesizes import A4  
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

app = Flask(__name__)
app.secret_key = "carysil_secret_key"

USERNAME = "carysilsom"
PASSWORD = "Puneet2026"
DATABASE_URL = "postgresql://neondb_owner:npg_kUGiCDj30LNW@ep-noisy-field-aozk7iqi.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

@app.route('/')
def home():
    if not session.get("logged_in"):
        return redirect("/login")
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == USERNAME and password == PASSWORD:
            session['logged_in'] = True
            return redirect('/')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/api/search', methods=['GET'])
def search_stock():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    sql = """
        SELECT
            sr_no,
            UPPER(TRIM(product_name)) AS p_name,
            UPPER(TRIM(product_size)) AS p_size,
            UPPER(TRIM(colour)) AS p_col,
            price,
            quantity
        FROM master_stock
        WHERE product_name ILIKE %s
           OR product_size ILIKE %s
        ORDER BY p_name, p_size, p_col
    """
    search_pattern = f"%{query}%"
    cursor.execute(sql, (search_pattern, search_pattern))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    stock_list = []
    for row in results:
        stock_list.append({
            'sr_no': row['sr_no'],
            'product_name': row['p_name'],
            'product_size': row['p_size'],
            'colour': row['p_col'],
            'price': float(row['price']),
            'quantity': int(row['quantity'])
        })
    return jsonify(stock_list)

def generate_pdf_invoice(bill_data):
    pdf_filename = f"Invoice_{bill_data.get('bill_no', '100')}.pdf"
    
    doc = SimpleDocTemplate(
        pdf_filename, 
        pagesize=A4,
        rightMargin=30, 
        leftMargin=30, 
        topMargin=30, 
        bottomMargin=30
    )
    
    story = []
    styles = getSampleStyleSheet()
    navy_blue = colors.HexColor("#1A365D")
    
    # VIP & Professional Typography Changes (Halka Tedha - Oblique)
    invoice_header_style = ParagraphStyle(
        'InvoiceHeader', parent=styles['Normal'], fontName='Helvetica-BoldOblique', fontSize=26, leading=30, textColor=navy_blue, alignment=1
    )
    brand_sub_style = ParagraphStyle(
        'BrandSubHeader', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=13, leading=16, textColor=colors.HexColor("#4A5568"), alignment=1
    )
    
    # FIXED: Increased leading (line space) to prevent overlapping of customer details
    meta_text_left = ParagraphStyle(
        'MetaLeft', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=11, leading=20, textColor=colors.black
    )
    meta_text_right = ParagraphStyle(
        'MetaRight', parent=styles['Normal'], fontName='Helvetica-BoldOblique', fontSize=11, leading=20, textColor=colors.black, alignment=2
    )
    
    th_style = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=11, leading=14, alignment=1, textColor=colors.white)
    td_style = ParagraphStyle('TD', fontName='Helvetica-Oblique', fontSize=10, leading=14, alignment=1)
    td_left = ParagraphStyle('TDLeft', fontName='Helvetica-Oblique', fontSize=10, leading=14, alignment=0)
    
    sum_lbl_style = ParagraphStyle('SumLbl', fontName='Helvetica-BoldOblique', fontSize=11, leading=16, alignment=2)
    sum_val_style = ParagraphStyle('SumVal', fontName='Helvetica-Bold', fontSize=11, leading=16, alignment=2)

    story.append(Paragraph("TAX INVOICE", invoice_header_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Carysil Som Associates Challan Bill", brand_sub_style))
    story.append(Spacer(1, 25))
    
    left_info = f"<b>Customer Name:</b> {bill_data.get('party_name', '')}<br/><b>Address:</b> {bill_data.get('party_address', bill_data.get('address', ''))}<br/><b>Mobile Number:</b> {bill_data.get('mobile_no', '')}"
    right_info = f"<b>Bill No:</b> {bill_data.get('bill_no', '')}<br/><b>Date:</b> {bill_data.get('bill_date', '')}"
    
    meta_table = Table([[Paragraph(left_info, meta_text_left), Paragraph(right_info, meta_text_right)]], colWidths=[335, 200])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0)
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 20))
    
    table_content = [[
        Paragraph("Sr.", th_style),
        Paragraph("Particulars Description", th_style), 
        Paragraph("Size", th_style), 
        Paragraph("Colour", th_style),
        Paragraph("Qty", th_style),
        Paragraph("Rate (Rs.)", th_style), 
        Paragraph("Disc", th_style), 
        Paragraph("Final SubTotal", th_style)
    ]]
    
    sub_total = 0
    for idx, item in enumerate(bill_data.get('items', []), start=1):
        qty = int(item.get('qty', 1))
        rate = float(item.get('rate', 0))
        discount = float(item.get('discount', 0))
        
        gross_amount = qty * rate
        discount_value = gross_amount * (discount / 100.0)
        net_amount = gross_amount - discount_value
        sub_total += net_amount
        
        disc_text = f"{discount}%" if discount > 0 else "-"
        
        table_content.append([
            Paragraph(str(idx), td_style),
            Paragraph(item.get('product_name', item.get('particulars', '')).upper(), td_left), 
            Paragraph(item.get('product_size', item.get('size', '')).upper(), td_style),
            Paragraph(item.get('colour', '').upper(), td_style), 
            Paragraph(str(qty), td_style),
            Paragraph(f"{rate:,.2f}", td_style), 
            Paragraph(disc_text, td_style), 
            Paragraph(f"{net_amount:,.2f}", td_style)
        ])
        
    advance_paid = float(bill_data.get('advance_paid', 0))
    balance_due = sub_total - advance_paid
    
    table_content.append([Paragraph("Gross Total:", sum_lbl_style), "", "", "", "", "", "", Paragraph(f"{sub_total:,.2f}", sum_val_style)])
    table_content.append([Paragraph("Net Payable:", sum_lbl_style), "", "", "", "", "", "", Paragraph(f"{sub_total:,.2f}", sum_val_style)])
    table_content.append([Paragraph("Advance Paid:", sum_lbl_style), "", "", "", "", "", "", Paragraph(f"{advance_paid:,.2f}", sum_val_style)])
    table_content.append([Paragraph("Balance Due:", sum_lbl_style), "", "", "", "", "", "", Paragraph(f"{balance_due:,.2f}", sum_val_style)])
    
    # FIXED: Re-adjusted column widths (Increased Colour and Disc widths to prevent small text clipping)
    item_table = Table(table_content, colWidths=[25, 175, 55, 75, 30, 65, 50, 60])
    
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), navy_blue),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-5), 0.5, colors.HexColor("#CBD5E0")),
        ('BOX', (0,0), (-1,-1), 1, navy_blue),
        
        ('SPAN', (0,-4), (6,-4)),
        ('SPAN', (0,-3), (6,-3)),
        ('SPAN', (0,-2), (6,-2)),
        ('SPAN', (0,-1), (6,-1)),
        
        ('LINEABOVE', (0,-4), (-1,-4), 1, colors.HexColor("#A0AEC0")),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    
    story.append(item_table)
    doc.build(story)
    return pdf_filename

@app.route('/api/generate_bill', methods=['POST'])
def generate_bill():
    bill_data = request.json
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Validation Loop: ONLY check and validate items that are from master stock (have valid product details)
        for item in bill_data.get('items', []):
            p_name = item.get('product_name', item.get('particulars', '')).strip()
            p_size = item.get('product_size', item.get('size', '')).strip()
            p_col = item.get('colour', '').strip()
            qty_to_minus = int(item.get('qty', 1))
            
            # Skip validation if it's a completely manual ad-hoc item row with missing core data
            if not p_name:
                continue
                
            check_sql = """
                SELECT quantity FROM master_stock
                WHERE UPPER(TRIM(product_name)) = UPPER(TRIM(%s))
                  AND UPPER(TRIM(product_size)) = UPPER(TRIM(%s))
                  AND UPPER(TRIM(colour)) = UPPER(TRIM(%s))
            """
            cursor.execute(check_sql, (p_name, p_size, p_col))
            row = cursor.fetchone()
            
            # FIXED: Manual rows won't be blocked anymore. If item is in DB, validate stock.
            if row:
                current_qty = row[0]
                if current_qty < qty_to_minus:
                    return jsonify({"status": "error", "message": f"Out of Stock! '{p_name}' has only {current_qty} items left."}), 400

        # Update Loop: Deduct stock for DB items only
        for item in bill_data.get('items', []):
            p_name = item.get('product_name', item.get('particulars', '')).strip()
            p_size = item.get('product_size', item.get('size', '')).strip()
            p_col = item.get('colour', '').strip()
            qty_to_minus = int(item.get('qty', 1))
            
            if not p_name:
                continue
                
            update_sql = """
                UPDATE master_stock
                SET quantity = quantity - %s
                WHERE UPPER(TRIM(product_name)) = UPPER(TRIM(%s))
                  AND UPPER(TRIM(product_size)) = UPPER(TRIM(%s))
                  AND UPPER(TRIM(colour)) = UPPER(TRIM(%s))
            """
            cursor.execute(update_sql, (qty_to_minus, p_name, p_size, p_col))
            
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("Error updating stock quantity:", str(e))
        if conn:
            conn.rollback()
            conn.close()
        return jsonify({"status": "error", "message": "Database transaction failure while building bill"}), 500
    
    pdf_file = generate_pdf_invoice(bill_data)
    return send_file(pdf_file, as_attachment=True)

@app.route('/api/add_stock', methods=['POST'])
def add_stock():
    try:
        data = request.json
        sr_no = data.get('sr_no', '').strip()
        p_name = data.get('product_name', '').strip()
        p_size = data.get('product_size', '').strip()
        p_col = data.get('colour', '').strip()
        price = float(data.get('price', 0))
        qty_to_add = int(data.get('qty', 1))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        check_sql = "SELECT quantity FROM master_stock WHERE TRIM(sr_no) = TRIM(%s)"
        cursor.execute(check_sql, (sr_no,))
        row = cursor.fetchone()
        
        if row:
            update_sql = """
                UPDATE master_stock 
                SET quantity = quantity + %s, price = %s
                WHERE TRIM(sr_no) = TRIM(%s)
            """
            cursor.execute(update_sql, (qty_to_add, price, sr_no))
            message = "Stock Quantity Updated Successfully!"
        else:
            insert_sql = """
                INSERT INTO master_stock (sr_no, product_name, product_size, colour, price, quantity)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (sr_no, p_name, p_size, p_col, price, qty_to_add))
            message = "New Product Added to Stock Successfully!"
            
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message": message})
        
    except Exception as e:
        print("Inward Stock Entry Error:", str(e))
        return jsonify({"status": "error", "message": f"Server processing error: {str(e)}"}), 500

@app.route('/bill_summary')
def bill_summary():
    if not session.get("logged_in"):
        return redirect("/login")
    return render_template('index.html')

@app.route('/inward_summary')
def inward_summary():
    if not session.get("logged_in"):
        return redirect("/login")
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)