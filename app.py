from flask import Flask, render_template, request, jsonify, session, redirect, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
from reportlab.lib.pagesizes import A4  
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime

app = Flask(__name__)
app.secret_key = "carysil_secret_key"

USERNAME = "carysilsom"
PASSWORD = "Puneet2026"
DATABASE_URL = "postgresql://neondb_owner:npg_kUGiCDj30LNW@ep-noisy-field-aozk7iqi.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def calculate_double_discount(gross_amount, discount_str):
    try:
        if not discount_str:
            return gross_amount
        clean_str = str(discount_str).replace('%', '').strip()
        if '-' in clean_str:
            discounts = [float(d.strip()) for d in clean_str.split('-') if d.strip()]
            current_amount = gross_amount
            for d in discounts:
                current_amount = current_amount * (1 - (d / 100.0))
            return current_amount
        else:
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
        SELECT sr_no, UPPER(TRIM(product_name)) AS p_name, UPPER(TRIM(product_size)) AS p_size,
               UPPER(TRIM(colour)) AS p_col, price, quantity
        FROM master_stock
        WHERE product_name ILIKE %s OR product_size ILIKE %s
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

# --- DAILY SALES SUMMARY ROUTE (Fix Date Filter) ---
@app.route('/api/today_billing_summary', methods=['GET'])
def today_billing_summary():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Date filter hata diya taaki jo entry abhi hui hai wo instantly bina timezone issue ke dikhe
    sql_history = """
        SELECT 
            to_char(bill_date, 'DD/MM/YYYY') as date, 
            bill_no, 
            UPPER(customer_name) as customer_name,
            string_agg(UPPER(product_name) || ' (' || UPPER(product_size) || '-' || UPPER(colour) || ')', ', ') as items_summary,
            SUM(qty) as total_qty,
            SUM(final_subtotal) as total_amount
        FROM bill_history
        GROUP BY bill_date, bill_no, customer_name
        ORDER BY bill_no DESC
    """
    cursor.execute(sql_history)
    history_rows = cursor.fetchall()
    
    sql_total = "SELECT SUM(final_subtotal) as total_sales FROM bill_history"
    cursor.execute(sql_total)
    total_result = cursor.fetchone()
    total_sales = float(total_result['total_sales']) if total_result['total_sales'] else 0.0
    
    cursor.close()
    conn.close()
    
    return jsonify({
        "total_selling_amount": total_sales,
        "history": history_rows
    })

# --- INWARD STOCK SUMMARY ROUTE (Fix Date Filter) ---
@app.route('/api/today_inward_summary', methods=['GET'])
def today_inward_summary():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    sql = """
        SELECT to_char(inward_date, 'DD/MM/YYYY') as date, sr_no, UPPER(product_name) as item_name, 
               UPPER(product_size) as size, UPPER(colour) as colour, price, qty_added as qty
        FROM inward_history
        ORDER BY id DESC
    """
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)

# --- AAPKA PURANA PDF FORMAT (100% ORIGINAL DESIGN AS REQUESTED) ---
def generate_pdf_invoice(bill_data):
    pdf_filename = f"Invoice_{bill_data.get('bill_no', '100')}.pdf"
    
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
    
    invoice_header_style = ParagraphStyle(
        'InvoiceHeaderTop', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=26, leading=28, textColor=navy_blue, alignment=1
    )
    phone_left_style = ParagraphStyle(
        'PhoneLeft', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=colors.black, alignment=0
    )
    phone_right_style = ParagraphStyle(
        'PhoneRight', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=colors.black, alignment=2
    )
    
    lbl_customer_style = ParagraphStyle(
        'LblCustomer', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=18, textColor=colors.black
    )
    lbl_meta_style = ParagraphStyle(
        'LblMeta', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=18, textColor=colors.black, alignment=0
    )
    
    th_style = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=9, leading=12, alignment=1, textColor=colors.white)
    td_style = ParagraphStyle('TD', fontName='Helvetica', fontSize=8, leading=11, alignment=1)
    td_left = ParagraphStyle('TDLeft', fontName='Helvetica', fontSize=8, leading=11, alignment=0)
    
    sum_lbl_style = ParagraphStyle('SumLbl', fontName='Helvetica-Bold', fontSize=9, leading=13, alignment=2)
    sum_val_style = ParagraphStyle('SumVal', fontName='Helvetica-Bold', fontSize=9, leading=13, alignment=2)
    footer_style = ParagraphStyle(
        'BilledByStyleMini', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=colors.black, alignment=0
    )

    story.append(Paragraph("INVOICE", invoice_header_style))
    story.append(Spacer(1, 10))
    
    phone_table_data = [
        [Paragraph("+91 89578 19961", phone_left_style), "", Paragraph("+91 82990 50044", phone_right_style)]
    ]
    phone_table = Table(phone_table_data, colWidths=[180, 175, 180])
    phone_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(phone_table)
    story.append(Spacer(1, 15))
    
    c_name = str(bill_data.get('party_name', '')).upper()
    c_addr = str(bill_data.get('party_address', bill_data.get('address', ''))).upper()
    c_mob = str(bill_data.get('mobile_no', ''))
    
    current_time = datetime.now().strftime('%I:%M %p').lower()
    
    customer_html = f"Customer Name: {c_name}<br/>Customer Address: {c_addr}<br/><br/>Mobile No: {c_mob}"
    meta_html = f"Bill No: {bill_data.get('bill_no', '')}<br/>DATE: {bill_data.get('bill_date', '')}<br/>TIME: {current_time}"
    
    left_block_table = Table([[Paragraph(customer_html, lbl_customer_style)]], colWidths=[310])
    left_block_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
    ]))
    
    right_block_table = Table([[Paragraph(meta_html, lbl_meta_style)]], colWidths=[205])
    right_block_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
    ]))
    
    blocks_container_table = Table([[left_block_table, "", right_block_table]], colWidths=[310, 20, 205])
    blocks_container_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(blocks_container_table)
    story.append(Spacer(1, 20))
    
    table_content = [[
        Paragraph("Sr.No", th_style), Paragraph("Particulars Description", th_style), 
        Paragraph("Size", th_style), Paragraph("Colour", th_style),
        Paragraph("Qty", th_style), Paragraph("Rate (Rs.)", th_style), 
        Paragraph("Disc%", th_style), Paragraph("Final Sub Total", th_style)
    ]]
    
    sub_total = 0
    for idx, item in enumerate(bill_data.get('items', []), start=1):
        qty = int(item.get('qty', 1))
        rate = float(item.get('rate', 0))
        discount_input = str(item.get('discount', '0')).replace('%', '').strip()
        
        gross_amount = qty * rate
        net_amount = calculate_double_discount(gross_amount, discount_input)
        sub_total += net_amount
        
        disc_text = f"{discount_input}%" if discount_input and discount_input not in ['0', '0.0'] else "-"
        
        table_content.append([
            Paragraph(f"{idx:02d}", td_style), Paragraph(item.get('product_name', item.get('particulars', '')).upper(), td_left), 
            Paragraph(item.get('product_size', item.get('size', '')).upper(), td_style), Paragraph(item.get('colour', '').upper(), td_style), 
            Paragraph(str(qty), td_style), Paragraph(f"{rate:,.2f}", td_style), 
            Paragraph(disc_text, td_style), Paragraph(f"{net_amount:,.2f}", td_style)
        ])
        
    advance_paid = float(bill_data.get('advance_paid', 0))
    balance_due = sub_total - advance_paid
    
    table_content.append([Paragraph("Gross Total:", sum_lbl_style), "", "", "", "", "", "", Paragraph(f"{sub_total:,.2f}", sum_val_style)])
    table_content.append([Paragraph("Advance Paid:", sum_lbl_style), "", "", "", "", "", "", Paragraph(f"{advance_paid:,.2f}", sum_val_style)])
    table_content.append([Paragraph("Balance Due:", sum_lbl_style), "", "", "", "", "", "", Paragraph(f"{balance_due:,.2f}", sum_val_style)])
    
    item_table = Table(table_content, colWidths=[35, 165, 55, 75, 30, 65, 50, 65])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), navy_blue),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-4), 0.5, colors.HexColor("#CBD5E0")),
        ('BOX', (0,0), (-1,-1), 1, navy_blue),
        ('SPAN', (0,-3), (6,-3)), ('SPAN', (0,-2), (6,-2)), ('SPAN', (0,-1), (6,-1)),
        ('LINEABOVE', (0,-3), (-1,-3), 1, colors.HexColor("#A0AEC0")),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6), ('TOPPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 40))
    
    handler_name = bill_data.get('billed_by', bill_data.get('billed_by', 'Puneet Yadav')).lower()
    story.append(Paragraph(f"Bill Generated By: {handler_name}", footer_style))
    
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
            if not p_name: continue
                
            cursor.execute("SELECT quantity FROM master_stock WHERE UPPER(TRIM(product_name)) = UPPER(TRIM(%s)) AND UPPER(TRIM(product_size)) = UPPER(TRIM(%s)) AND UPPER(TRIM(colour)) = UPPER(TRIM(%s))", (p_name, p_size, p_col))
            row = cursor.fetchone()
            if row and row[0] < qty_to_minus:
                return jsonify({"status": "error", "message": f"Out of Stock! '{p_name}' has only {row[0]} items."}), 400

        for item in bill_data.get('items', []):
            p_name = item.get('product_name', item.get('particulars', '')).strip()
            p_size = item.get('product_size', item.get('size', '')).strip()
            p_col = item.get('colour', '').strip()
            qty_to_minus = int(item.get('qty', 1))
            rate = float(item.get('rate', 0))
            discount_input = str(item.get('discount', '0')).replace('%', '').strip()
            if not p_name: continue
            
            cursor.execute("UPDATE master_stock SET quantity = quantity - %s WHERE UPPER(TRIM(product_name)) = UPPER(TRIM(%s)) AND UPPER(TRIM(product_size)) = UPPER(TRIM(%s)) AND UPPER(TRIM(colour)) = UPPER(TRIM(%s))", (qty_to_minus, p_name, p_size, p_col))
            net_amount = calculate_double_discount(qty_to_minus * rate, discount_input)
            
            cursor.execute("""
                INSERT INTO bill_history (bill_no, customer_name, product_name, product_size, colour, price, qty, final_subtotal, billed_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (bill_data.get('bill_no'), bill_data.get('party_name'), p_name, p_size, p_col, rate, qty_to_minus, net_amount, bill_data.get('billed_by', 'Puneet Yadav')))
            
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": f"Transaction failure: {str(e)}"}), 500
    
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
        cursor.execute("SELECT quantity FROM master_stock WHERE TRIM(sr_no) = TRIM(%s)", (sr_no,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("UPDATE master_stock SET quantity = quantity + %s, price = %s WHERE TRIM(sr_no) = TRIM(%s)", (qty_to_add, price, sr_no))
        else:
            cursor.execute("INSERT INTO master_stock (sr_no, product_name, product_size, colour, price, quantity) VALUES (%s, %s, %s, %s, %s, %s)", (sr_no, p_name, p_size, p_col, price, qty_to_add))
            
        cursor.execute("INSERT INTO inward_history (sr_no, product_name, product_size, colour, price, qty_added) VALUES (%s, %s, %s, %s, %s, %s)", (sr_no, p_name, p_size, p_col, price, qty_to_add))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message": "Stock Added Successfully!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/bill_summary')
def bill_summary():
    if not session.get("logged_in"): return redirect("/login")
    return render_template('index.html')

@app.route('/inward_summary')
def inward_summary():
    if not session.get("logged_in"): return redirect("/login")
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)