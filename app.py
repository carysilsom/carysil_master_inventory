from datetime import datetime
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

# --- IS CODE KO APNE APP.PY KE DEF GENERATE_PDF_INVOICE MEIN REPLACE KAREIN ---

from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

def generate_pdf_invoice(bill_data):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    PAGE_WIDTH, PAGE_HEIGHT = A4

    LEFT = 15 * mm
    RIGHT = PAGE_WIDTH - 15 * mm
    TOP = PAGE_HEIGHT - 15 * mm

    # Colors Architecture matching the user's PDF
    BLUE = HexColor("#0D47A1")   # Solid Royal Blue for table header
    DARK = HexColor("#222222")   # Clean Charcoal Black for text
    BORDER = HexColor("#A0AEC0") # Professional Grey for grid/boxes
    RED = HexColor("#D32F2F")    # Crimson Red for top horizontal bar
    YELLOW = HexColor("#FFF9C4") # Soft Accent Yellow for Balance Due

    # Outer Document Box Border
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.rect(10 * mm, 10 * mm, PAGE_WIDTH - 20 * mm, PAGE_HEIGHT - 20 * mm)

    y = TOP

    # Header Contact Details
    c.setFont(FONT_BOLD, 10)
    c.setFillColor(DARK)
    c.drawString(LEFT, y, "+91 89578 19961")
    c.drawRightString(RIGHT, y, "+91 82990 50044")

    # Main Invoice Center Title
    y -= 12
    c.setFillColor(black)
    c.setFont(FONT_BOLD, 22)
    c.drawCentredString(PAGE_WIDTH / 2, y, "INVOICE")

    # Red Divider Accent Line
    y -= 8
    c.setStrokeColor(RED)
    c.setLineWidth(2)
    c.line(LEFT, y, RIGHT, y)

    y -= 22

    # CUSTOMER & BILL BOX LAYOUT (BOX_HEIGHT: 33mm)
    LEFT_BOX_WIDTH = 118 * mm
    RIGHT_BOX_WIDTH = 55 * mm
    BOX_HEIGHT = 33 * mm

    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    
    # Left Box: Customer Info
    c.rect(LEFT, y - BOX_HEIGHT, LEFT_BOX_WIDTH, BOX_HEIGHT)
    c.setFont(FONT_BOLD, 10)
    c.drawString(LEFT + 4 * mm, y - 8 * mm, "Customer Name :")
    c.drawString(LEFT + 4 * mm, y - 18 * mm, "Customer Address :")
    c.drawString(LEFT + 4 * mm, y - 28 * mm, "Mobile No :")

    c.setFont(FONT, 10)
    c.drawString(LEFT + 40 * mm, y - 8 * mm, str(bill_data.get('customer_name', bill_data.get('party_name', ''))).upper())
    c.drawString(LEFT + 40 * mm, y - 18 * mm, str(bill_data.get('customer_address', bill_data.get('address', ''))).upper())
    c.drawString(LEFT + 40 * mm, y - 28 * mm, str(bill_data.get('mobile', bill_data.get('mobile_no', ''))))

    # Right Box: Bill Metatdata
    RIGHT_BOX_X = LEFT + LEFT_BOX_WIDTH + 5 * mm
    c.rect(RIGHT_BOX_X, y - BOX_HEIGHT, RIGHT_BOX_WIDTH, BOX_HEIGHT)
    c.setFont(FONT_BOLD, 10)
    c.drawString(RIGHT_BOX_X + 4 * mm, y - 8 * mm, "Bill No :")
    c.drawString(RIGHT_BOX_X + 4 * mm, y - 18 * mm, "DATE :")
    c.drawString(RIGHT_BOX_X + 4 * mm, y - 28 * mm, "TIME :")

    # Safe timestamp extraction
    from datetime import datetime
    current_time = datetime.now().strftime('%I:%M %p')
    c.setFont(FONT, 10)
    c.drawString(RIGHT_BOX_X + 24 * mm, y - 8 * mm, str(bill_data.get('bill_no', '')))
    c.drawString(RIGHT_BOX_X + 24 * mm, y - 18 * mm, str(bill_data.get('date', bill_data.get('bill_date', ''))))
    c.drawString(RIGHT_BOX_X + 24 * mm, y - 28 * mm, current_time)

    y -= (BOX_HEIGHT + 10 * mm)

    # PRODUCT TABLE HEADERS GENERATION
    HEADER_HEIGHT = 10 * mm
    COLS = [
        ("Sr.\nNo", 12 * mm),
        ("Particulars Description", 58 * mm),
        ("Size", 22 * mm),
        ("Colour", 28 * mm),
        ("Qty", 12 * mm),
        ("Rate (Rs.)", 22 * mm),
        ("Disc%", 16 * mm),
        ("Final Sub Total", 28 * mm)
    ]

    x = LEFT
    for title, width in COLS:
        c.setFillColor(BLUE)
        c.rect(x, y - HEADER_HEIGHT, width, HEADER_HEIGHT, stroke=1, fill=1)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 9)
        
        # Multiline logic for compact header titles
        if "\n" in title:
            t1, t2 = title.split("\n")
            c.drawCentredString(x + width / 2, y - 4 * mm, t1)
            c.drawCentredString(x + width / 2, y - 8 * mm, t2)
        else:
            c.drawCentredString(x + width / 2, y - 6 * mm, title)
        x += width

    y -= HEADER_HEIGHT

    # DATA ROWS RENDERING
    c.setFont(FONT, 9)
    grand_total = 0
    row_height = 9 * mm
    sr = 1

    # Fetching list securely whether it comes as 'items' or default structure
    items_list = bill_data.get('items', [])
    if not items_list and 'product_name' in bill_data:
        items_list = [bill_data]

    for item in items_list:
        qty = int(item.get('qty', item.get('qty_to_minus', 1)))
        rate = float(item.get('rate', item.get('price', 0)))
        disc_input = str(item.get('discount', '0')).replace('%', '').strip()

        # Handle global fallback discount if individual item is empty
        if not disc_input or disc_input == '0':
            disc_input = str(bill_data.get('global_discount', '0')).replace('%', '').strip()

        # Calculate standard double discount structure natively
        gross_amount = qty * rate
        if '-' in disc_input:
            parts = disc_input.split('-')
            d1 = float(parts[0]) if parts[0] else 0.0
            d2 = float(parts[1]) if parts[1] else 0.0
            amt_after_d1 = gross_amount - ((gross_amount * d1) / 100)
            final_amount = amt_after_d1 - ((amt_after_d1 * d2) / 100)
        else:
            d1 = float(disc_input) if disc_input else 0.0
            final_amount = gross_amount - ((gross_amount * d1) / 100)

        grand_total += final_amount

        values = [
            f"{sr:02d}",
            str(item.get('product_name', item.get('particulars', ''))).upper(),
            str(item.get('size', item.get('product_size', ''))).upper(),
            str(item.get('colour', '')).upper(),
            str(qty),
            f"{rate:,.2f}",
            f"{disc_input}%" if disc_input else "0%",
            f"{final_amount:,.2f}"
        ]

        widths = [12*mm, 58*mm, 22*mm, 28*mm, 12*mm, 22*mm, 16*mm, 28*mm]
        x = LEFT
        for value, width in zip(values, widths):
            c.setFillColor(white)
            c.rect(x, y - row_height, width, row_height, stroke=1, fill=1)
            c.setFillColor(DARK)
            
            # Left aligning description text, others centered perfectly
            if width == 58 * mm:
                c.drawString(x + 3 * mm, y - 6 * mm, str(value))
            else:
                c.drawCentredString(x + width / 2, y - 6 * mm, str(value))
            x += width

        y -= row_height
        sr += 1

    y -= 8 * mm

    # TOTAL SUMMARY METRICS SECTION
    SUMMARY_WIDTH = 62 * mm
    SUMMARY_HEIGHT = 26 * mm
    summary_x = RIGHT - SUMMARY_WIDTH

    advance = float(bill_data.get('advance_paid', bill_data.get('advance', 0)))
    balance = grand_total - advance

    c.setStrokeColor(BORDER)
    c.rect(summary_x, y - SUMMARY_HEIGHT, SUMMARY_WIDTH, SUMMARY_HEIGHT)

    # Gross Total Row
    c.setFont(FONT_BOLD, 10)
    c.drawString(summary_x + 4 * mm, y - 7 * mm, "Gross Total :")
    c.drawRightString(RIGHT - 4 * mm, y - 7 * mm, f"{grand_total:,.2f}")

    # Advance Paid Row
    c.drawString(summary_x + 4 * mm, y - 16 * mm, "Advance Paid :")
    c.drawRightString(RIGHT - 4 * mm, y - 16 * mm, f"{advance:,.2f}")

    # Yellow Full-Width Balance Due Highlight
    c.setFillColor(YELLOW)
    c.rect(summary_x, y - 26 * mm, SUMMARY_WIDTH, 8.5 * mm, fill=1, stroke=1)
    c.setFillColor(DARK)
    c.drawString(summary_x + 4 * mm, y - 22 * mm, "Balance Due :")
    c.drawRightString(RIGHT - 4 * mm, y - 22 * mm, f"{balance:,.2f}")

    y -= (SUMMARY_HEIGHT + 15 * mm)

    # FOOTER LOGO & USER STAMP
    c.setStrokeColor(BORDER)
    c.line(LEFT, y, RIGHT, y)

    y -= 8 * mm
    c.setFont(FONT_BOLD, 10)
    handler_name = str(bill_data.get('billed_by', 'puneet kumar singh yadav')).lower().strip()
    c.drawString(LEFT, y, f"bill generated by: {handler_name}")

    c.save()
    pdf_out = buffer.getvalue()
    buffer.close()
    return pdf_out

@app.route('/api/generate_bill', methods=['POST'])
def generate_bill():
    bill_data = request.json
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Uniform compilation of items array
        items_list = bill_data.get('items', [])
        if not items_list and 'product_name' in bill_data:
            items_list = [bill_data]

        # 1. ATOMIC VALIDATION: Check master stock quantity limits
        for item in items_list:
            p_name = item.get('product_name', item.get('particulars', '')).strip()
            p_size = item.get('size', item.get('product_size', '')).strip()
            p_col = item.get('colour', '').strip()
            qty_needed = int(item.get('qty', item.get('qty_to_minus', 1)))
            if not p_name: continue
                
            cursor.execute("""
                SELECT quantity FROM master_stock 
                WHERE UPPER(TRIM(product_name)) = UPPER(TRIM(%s)) 
                  AND UPPER(TRIM(product_size)) = UPPER(TRIM(%s)) 
                  AND UPPER(TRIM(colour)) = UPPER(TRIM(%s))
            """, (p_name, p_size, p_col))
            row = cursor.fetchone()
            if row and row[0] < qty_needed:
                return jsonify({"status": "error", "message": f"Stock Alert! Only {row[0]} left for '{p_name}'."}), 400

        # 2. TRANSACTION EXECUTION: Execute stock minus and history save updates
        customer_name = bill_data.get('customer_name', bill_data.get('party_name', ''))
        customer_address = bill_data.get('customer_address', bill_data.get('address', ''))
        mobile_no = bill_data.get('mobile', bill_data.get('mobile_no', ''))
        bill_no = bill_data.get('bill_no')
        billed_by = bill_data.get('generated_by', 'puneet kumar singh yadav')

        for item in items_list:
            p_name = item.get('product_name', item.get('particulars', '')).strip()
            p_size = item.get('size', item.get('product_size', '')).strip()
            p_col = item.get('colour', '').strip()
            qty_needed = int(item.get('qty', item.get('qty_to_minus', 1)))
            rate = float(item.get('rate', item.get('price', 0)))
            disc_input = str(item.get('discount', '0')).replace('%', '').strip()

            if not disc_input or disc_input == '0':
                disc_input = str(bill_data.get('global_discount', '0')).replace('%', '').strip()
            if not p_name: continue
            
            # Standard relational decrement query
            cursor.execute("""
                UPDATE master_stock SET quantity = quantity - %s 
                WHERE UPPER(TRIM(product_name)) = UPPER(TRIM(%s)) 
                  AND UPPER(TRIM(product_size)) = UPPER(TRIM(%s)) 
                  AND UPPER(TRIM(colour)) = UPPER(TRIM(%s))
            """, (qty_needed, p_name, p_size, p_col))
            
            # Pricing discount execution logic
            gross_amount = qty_needed * rate
            if '-' in disc_input:
                parts = disc_input.split('-')
                d1 = float(parts[0]) if parts[0] else 0.0
                d2 = float(parts[1]) if parts[1] else 0.0
                amt_after_d1 = gross_amount - ((gross_amount * d1) / 100)
                net_amount = amt_after_d1 - ((amt_after_d1 * d2) / 100)
            else:
                d1 = float(disc_input) if disc_input else 0.0
                net_amount = gross_amount - ((gross_amount * d1) / 100)
            
            # Safe persistent insertion to system's history log ledger
            cursor.execute("""
                INSERT INTO bill_history (bill_no, customer_name, product_name, product_size, colour, price, qty, final_subtotal, billed_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (bill_no, customer_name, p_name, p_size, p_col, rate, qty_needed, net_amount, billed_by))
            
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": f"Database Operation Error: {str(e)}"}), 500
    
    # 3. DELIVERY STREAM: Pipe compiled byte buffer down as downloadeable stream file
    try:
        pdf_file_data = generate_pdf_invoice(bill_data)
        return send_file(
            BytesIO(pdf_file_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"Invoice_{bill_no}.pdf"
        )
    except Exception as pdf_error:
        return jsonify({"status": "error", "message": f"PDF Compilation Error: {str(pdf_error)}"}), 500