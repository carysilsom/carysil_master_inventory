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

def calculate_double_discount(gross_amount, discount_str):
    """
    35-3 या 25-2 जैसे सक्सेसिव डिस्काउंट को सही तरीके से कैलकुलेट करने का फार्मूला
    """
    try:
        if not discount_str:
            return gross_amount
        
        # स्ट्रिंग को साफ़ करें और प्रतिशत हटाएं
        clean_str = str(discount_str).replace('%', '').strip()
        
        if '-' in clean_str:
            # 35-3 को अलग-अलग हिस्सों में बांटें
            discounts = [float(d.strip()) for d in clean_str.split('-') if d.strip()]
            current_amount = gross_amount
            for d in discounts:
                current_amount = current_amount * (1 - (d / 100.0))
            return current_amount
        else:
            # सिंगल डिस्काउंट
            d_val = float(clean_str) if clean_str else 0.0
            return gross_amount * (1 - (d_val / 100.0))
    except Exception as e:
        print(f"Discount Calculation Error: {e}")
        return gross_amount

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
    
    # Page settings with A4 and clean margins
    doc = SimpleDocTemplate(
        pdf_filename, 
        pagesize=A4,
        rightMargin=30, 
        leftMargin=30, 
        topMargin=25, 
        bottomMargin=25
    )
    
    story = []
    styles = getSampleStyleSheet()
    navy_blue = colors.HexColor("#1A365D")
    
    # Custom Fonts & Styles Mapping
    top_left_style = ParagraphStyle(
        'TopLeftNum', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.black, alignment=0
    )
    top_right_style = ParagraphStyle(
        'TopRightNum', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.black, alignment=2
    )
    invoice_header_style = ParagraphStyle(
        'InvoiceHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=24, leading=26, textColor=navy_blue, alignment=1
    )
    
    block_text_style = ParagraphStyle(
        'BlockText', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=14, textColor=colors.black
    )
    
    th_style = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=9, leading=12, alignment=1, textColor=colors.white)
    td_style = ParagraphStyle('TD', fontName='Helvetica', fontSize=8, leading=11, alignment=1)
    td_left = ParagraphStyle('TDLeft', fontName='Helvetica', fontSize=8, leading=11, alignment=0)
    
    sum_lbl_style = ParagraphStyle('SumLbl', fontName='Helvetica-Bold', fontSize=9, leading=13, alignment=2)
    sum_val_style = ParagraphStyle('SumVal', fontName='Helvetica-Bold', fontSize=9, leading=13, alignment=2)
    
    footer_style = ParagraphStyle(
        'BilledByStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=navy_blue, alignment=2
    )

    # 1. Top Section: INVOICE in center, Dialer Logo (📞) on both sides
    header_table_data = [
        [
            Paragraph("📞 +91 89578 19961", top_left_style),
            Paragraph("INVOICE", invoice_header_style),
            Paragraph("📞 +91 82990 50044", top_right_style)
        ]
    ]
    header_table = Table(header_table_data, colWidths=[150, 235, 150])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 20))
    
    # 2. Block Layout Section (Left: Customer Details, Right: Invoice Meta Details with Time)
    customer_html = f"""
    <b>Customer Name:</b> {bill_data.get('party_name', '').upper()}<br/>
    <b>Address:</b> {bill_data.get('party_address', bill_data.get('address', '')).upper()}<br/>
    <b>Mobile Number:</b> {bill_data.get('mobile_no', '')}
    """
    
    meta_html = f"""
    <b>Bill No:</b> {bill_data.get('bill_no', '')}<br/>
    <b>Date:</b> {bill_data.get('bill_date', '')}<br/>
    <b>Time:</b> {bill_data.get('bill_time', '')}
    """
    
    left_block_table = Table([[Paragraph(customer_html, block_text_style)]], colWidths=[310])
    left_block_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#718096")),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
    ]))
    
    right_block_table = Table([[Paragraph(meta_html, block_text_style)]], colWidths=[205])
    right_block_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#718096")),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
    ]))
    
    blocks_container_table = Table([[left_block_table, "", right_block_table]], colWidths=[310, 20, 205])
    blocks_container_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(blocks_container_table)
    story.append(Spacer(1, 20))
    
    # 3. Items Description Table Setup
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
        discount_input = str(item.get('discount', '0')).replace('%', '').strip()
        
        gross_amount = qty * rate
        net_amount = calculate_double_discount(gross_amount, discount_input)
        sub_total += net_amount
        
        if discount_input and discount_input != '0' and discount_input != '0.0':
            disc_text = f"{discount_input}%"
        else:
            disc_text = "-"
        
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
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 35))
    
    # 4. Footer Section: Billed Desk User Handler Mapping
    handler_name = bill_data.get('billed_by', 'Authorized Signatory').upper()
    story.append(Paragraph(f"INVOICE GENERATED BY: {handler_name}", footer_style))
    
    doc.build(story)
    return pdf_filename

@app.route('/api/generate_bill', methods=['POST'])
def generate_bill():
    bill_data = request.json
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for item in bill_data.get('items', []):
            p_name = item.get('product_name', item.get('particulars', '')).strip()
            p_size = item.get('product_size', item.get('size', '')).strip()
            p_col = item.get('colour', '').strip()
            qty_to_minus = int(item.get('qty', 1))
            
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
            
            if row:
                current_qty = row[0]
                if current_qty < qty_to_minus:
                    return jsonify({"status": "error", "message": f"Out of Stock! '{p_name}' has only {current_qty} items left."}), 400

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