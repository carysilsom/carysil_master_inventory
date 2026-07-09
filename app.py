from flask import Flask, render_template, request, jsonify, session, redirect, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
import pytz
from io import BytesIO
import threading  # Sync control ke liye

# ReportLab Graphics Engine Imports
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.secret_key = "carysil_secret_key"

USERNAME = "carysilsom"
PASSWORD = "Puneet2026"
DATABASE_URL = "postgresql://neondb_owner:npg_kUGiCDj30LNW@ep-noisy-field-aozk7iqi.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

# --- GLOBAL MEMORY CACHE (SUPER FAST SEARCH ENGINE) ---
GLOBAL_STOCK_CACHE = []
cache_lock = threading.Lock()

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        return conn
    except Exception as e:
        print(f"DATABASE CONNECTION ERROR: {str(e)}")
        raise e

# Internet Database se stock utha kar RAM memory mein load karne ka function
def refresh_stock_cache():
    global GLOBAL_STOCK_CACHE
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        sql = """
            SELECT sr_no, UPPER(TRIM(product_name)) AS p_name, UPPER(TRIM(product_size)) AS p_size,
                   UPPER(TRIM(colour)) AS p_col, price, quantity
            FROM master_stock
            ORDER BY p_name, p_size, p_col
        """
        cursor.execute(sql)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        with cache_lock:
            GLOBAL_STOCK_CACHE = []
            for row in results:
                GLOBAL_STOCK_CACHE.append({
                    'sr_no': row['sr_no'],
                    'product_name': row['p_name'],
                    'product_size': row['p_size'],
                    'colour': row['p_col'],
                    'price': float(row['price']),
                    'quantity': int(row['quantity'])
                })
        print(f"--- MEMORY CACHE REFRESHED: {len(GLOBAL_STOCK_CACHE)} ITEMS LOADED FROM CLOUD ---")
    except Exception as e:
        print(f"CACHE REFRESH ERROR: {str(e)}")

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


# === BULLET FAST SEARCH ROUTE (AB ZERO INTERNET LAG!) ===
@app.route('/api/search', methods=['GET'])
def search_stock():
    query = request.args.get('q', '').strip().upper()
    if not query:
        return jsonify([])
    
    # Agar cache khali hai toh ek baar load kar lo
    if not GLOBAL_STOCK_CACHE:
        refresh_stock_cache()
        
    filtered_results = []
    with cache_lock:
        # Bina internet use kiye Memory/RAM ke andar fast filter lagana
        for item in GLOBAL_STOCK_CACHE:
            if query in item['product_name'] or query in item['product_size']:
                filtered_results.append(item)
                
    return jsonify(filtered_results)


# --- REAL STOCK INWARD ENGINE ROUTE ---
@app.route('/api/inward', methods=['POST'])
def stock_inward():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json
        sr_no = str(data.get('sr_no', '')).strip()
        p_name = data.get('product_name', '').strip().upper()
        p_size = data.get('product_size', '').strip().upper()
        p_col = data.get('colour', '').strip().upper()
        price = float(data.get('price', 0))
        qty = int(data.get('qty', 0))

        if not p_name or qty <= 0:
            return jsonify({"status": "error", "message": "Product Name and Valid Quantity required!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inward_history (
                id SERIAL PRIMARY KEY,
                inward_date DATE DEFAULT CURRENT_DATE,
                sr_no VARCHAR(50),
                product_name VARCHAR(255),
                product_size VARCHAR(100),
                colour VARCHAR(100),
                price NUMERIC(12,2),
                qty_added INT
            );
        """)

# === [EKDAM PERFECT MATCH LOGIC: SARE 5 COLUMNS MATCH HONGE] ===
        # Ab ye check karega ki exact wahi Sr.No, Name, Size, Colour aur Price wala maal pehle se hai ya nahi
        cursor.execute("""
            SELECT sr_no FROM master_stock 
            WHERE sr_no = %s 
              AND UPPER(TRIM(product_name)) = %s 
              AND UPPER(TRIM(product_size)) = %s 
              AND UPPER(TRIM(colour)) = %s 
              AND price = %s
        """, (sr_no, p_name, p_size, p_col, price))
        
        row = cursor.fetchone()
        
        assigned_sr = ""
        if row:
            # EKDAM SAFE UPDATE: Sirf aur sirf usi ek bande ka stock badhega jiska SAAB KUCH match karega
            cursor.execute("""
                UPDATE master_stock 
                SET quantity = quantity + %s 
                WHERE sr_no = %s 
                  AND UPPER(TRIM(product_name)) = %s 
                  AND UPPER(TRIM(product_size)) = %s 
                  AND UPPER(TRIM(colour)) = %s 
                  AND price = %s
            """, (qty, sr_no, p_name, p_size, p_col, price))
            assigned_sr = str(row[0])
        else:
            # INSERT QUERY FIX: Agar naya item hai toh usme Sr.No bhi sahi se jayega
            cursor.execute("""
                INSERT INTO master_stock (sr_no, product_name, product_size, colour, price, quantity) 
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING sr_no
            """, (sr_no, p_name, p_size, p_col, price, qty))
            assigned_sr = str(cursor.fetchone()[0])

        # History table me entry ekdam sahi record hogi
        cursor.execute("""
            INSERT INTO inward_history (inward_date, sr_no, product_name, product_size, colour, price, qty_added)
            VALUES (CURRENT_DATE, %s, %s, %s, %s, %s, %s)
        """, (assigned_sr, p_name, p_size, p_col, price, qty))
            
        conn.commit()
        cursor.close()
        conn.close()
        
        # Inward hote hi live background cache refresh taaki sabhi logon ko naya stock turant dikhe
        threading.Thread(target=refresh_stock_cache).start()
        
        return jsonify({"status": "success", "message": "Stock Inward updated successfully in Database!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- LIVE BUSINESS DAY-WISE SUMMARY ROUTE ---
@app.route('/api/today_billing_summary', methods=['GET'])
def today_billing_summary():
    target_date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        sql_history = """
            SELECT 
                to_char(bill_date, 'DD/MM/YYYY') as date, 
                bill_no, 
                UPPER(customer_name) as customer_name,
                string_agg(UPPER(product_name) || ' (' || UPPER(product_size) || '-' || UPPER(colour) || ')', ', ') as items_summary,
                SUM(qty) as total_qty,
                SUM(final_subtotal) as total_amount
            FROM bill_history
            WHERE DATE(bill_date) = DATE(%s)
            GROUP BY bill_date, bill_no, customer_name
            ORDER BY bill_no DESC
        """
        cursor.execute(sql_history, (target_date,))
        history_rows = cursor.fetchall()
        
        sql_total = "SELECT SUM(final_subtotal) as total_sales FROM bill_history WHERE DATE(bill_date) = DATE(%s)"
        cursor.execute(sql_total, (target_date,))
        total_result = cursor.fetchone()
        total_sales = float(total_result['total_sales']) if total_result['total_sales'] else 0.0
        
        cursor.close()
        conn.close()
        return jsonify({
            "total_selling_amount": total_sales,
            "history": history_rows
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/today_inward_summary', methods=['GET'])
def today_inward_summary():
    target_date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        sql = """
            SELECT to_char(inward_date, 'DD/MM/YYYY') as date, sr_no, UPPER(product_name) as item_name, 
                   UPPER(product_size) as size, UPPER(colour) as colour, price, qty_added as qty
            FROM inward_history
            WHERE DATE(inward_date) = DATE(%s)
            ORDER BY id DESC
        """
        cursor.execute(sql, (target_date,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- EXACT CORRECTION ENGINE MATRICES ---
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

def generate_pdf_invoice(bill_data):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    PAGE_WIDTH, PAGE_HEIGHT = A4

    LEFT = 10 * mm
    RIGHT = PAGE_WIDTH - 10 * mm
    TOP = PAGE_HEIGHT - 16 * mm 

    BLUE = HexColor("#0044cc")   
    DARK = HexColor("#000000")   
    BORDER = HexColor("#000000") 
    RED = HexColor("#ff0000")    
    YELLOW = HexColor("#ffffb3") 

    y = TOP
    c.setFont(FONT_BOLD, 24)
    c.setFillColor(DARK)
    c.drawCentredString(PAGE_WIDTH / 2, y, "INVOICE")

    try:
        c.setFont("Helvetica-BoldOblique", 10)
    except:
        c.setFont("Helvetica-BoldOblique", 10)
        
    c.drawString(LEFT, y, "+91 89578 19961")
    c.drawRightString(RIGHT, y, "+91 82990 50044")

    y -= 5 * mm
    c.setStrokeColor(RED)
    c.setLineWidth(2.5)
    c.line(LEFT, y, RIGHT, y)

    y_text = y - 10 * mm
    try:
        c.setFont("Helvetica-BoldOblique", 16)
    except:
        c.setFont("Helvetica-BoldOblique", 16)
    c.setFillColor(DARK) 
    c.drawCentredString(PAGE_WIDTH / 2, y_text, "SOM ASSOCIATES") 

    y -= 25.4 * mm
    box_height = 32 * mm
    
    left_width = 140 * mm
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.rect(LEFT, y - box_height, left_width, box_height, fill=0, stroke=1)
    
    try:
        c.setFont("Helvetica-BoldOblique", 10)
    except:
        c.setFont("Helvetica-BoldOblique", 10)
        
    c.drawString(LEFT + 4 * mm, y - 7 * mm, "Customer Name :")
    c.drawString(LEFT + 4 * mm, y - 14 * mm, "Mobile No :")
    c.drawString(LEFT + 4 * mm, y - 21 * mm, "Customer Address :")
    
    try:
        c.setFont("Helvetica-BoldOblique", 8.5)
    except:
        c.setFont("Helvetica-BoldOblique", 8.5)
        
    c.drawString(LEFT + 38 * mm, y - 7 * mm, str(bill_data.get('customer_name', bill_data.get('party_name', ''))).upper())
    c.drawString(LEFT + 38 * mm, y - 14 * mm, str(bill_data.get('mobile', bill_data.get('mobile_no', ''))))
    
    # === 🛡️ HIGH-PREMIUM UNLIMITED ADDRESS WRAPPING ENGINE 🛡️ ===
    address_str = str(bill_data.get('customer_address', bill_data.get('address', ''))).upper().strip()
    words = address_str.split(" ")
    lines = []
    current_line = ""
    
    for word in words:
        if len(current_line + " " + word) <= 42:
            current_line = (current_line + " " + word).strip()
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
        
    addr_y = y - 21 * mm
    for idx, line_text in enumerate(lines):
        if idx > 0:
            addr_y -= 4.2 * mm  # Do lines ke beech ka uniform spacing gap
        if addr_y > (y - box_height + 2 * mm):
            c.drawString(LEFT + 38 * mm, addr_y, line_text)

    right_x = LEFT + left_width
    right_width = RIGHT - right_x
    c.rect(right_x, y - box_height, right_width, stroke=1, fill=0)
    
    try:
        c.setFont("Helvetica-BoldOblique", 10)
    except:
        c.setFont("Helvetica-BoldOblique", 10)
        
    c.drawString(right_x + 4 * mm, y - 7 * mm, "Bill No :")
    c.drawString(right_x + 4 * mm, y - 14 * mm, "DATE :")
    c.drawString(right_x + 4 * mm, y - 21 * mm, "TIME :")
    
    # === ⏰ INDIAN STANDARD TIME (IST) CORE IMPLEMENTATION ⏰ ===
    IST = pytz.timezone('Asia/Kolkata')
    india_time = datetime.now(IST)
    
    raw_date = str(bill_data.get('date', bill_data.get('bill_date', '')))
    formatted_date = raw_date
    if len(raw_date) == 10 and raw_date[4] == '-' and raw_date[7] == '-':
        try:
            parts = raw_date.split('-')
            formatted_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        except:
            formatted_date = raw_date
    if not raw_date:
        formatted_date = india_time.strftime("%d-%m-%Y")

    current_time = bill_data.get('bill_time', india_time.strftime('%I:%M %p'))
    
    try:
        c.setFont("Helvetica-BoldOblique", 8.5)
    except:
        c.setFont("Helvetica-BoldOblique", 8.5)
        
    c.drawString(right_x + 22 * mm, y - 7 * mm, str(bill_data.get('bill_no', '')))
    c.drawString(right_x + 22 * mm, y - 14 * mm, formatted_date)
    c.drawString(right_x + 22 * mm, y - 21 * mm, current_time)

    y -= (box_height + 12.7 * mm)
    header_height = 10 * mm
    
    widths = [10*mm, 56*mm, 26*mm, 32*mm, 12*mm, 20*mm, 12*mm, 22*mm] 

    COLS = [
        ("Sr.\nNo", widths[0]), ("Particulars Description", widths[1]),
        ("Size", widths[2]), ("Colour", widths[3]),
        ("Qty", widths[4]), ("Rate (Rs.)", widths[5]),
        ("Disc%", widths[6]), ("Sub Total", widths[7])
    ]

    x_start = LEFT
    for idx, (title, w) in enumerate(COLS):
        c.setFillColor(BLUE)
        c.rect(x_start, y - header_height, w, header_height, stroke=1, fill=1)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 9)
        if idx == 7:
            c.drawCentredString(x_start + w / 2, y - 6 * mm, "Sub Total")
        elif "\n" in title:
            t1, t2 = title.split("\n")
            c.drawCentredString(x_start + w / 2, y - 4 * mm, t1)
            c.drawCentredString(x_start + w / 2, y - 8 * mm, t2)
        else:
            c.drawCentredString(x_start + w / 2, y - 6 * mm, title)
        x_start += w

    y -= header_height

    c.setFont(FONT, 9.5)
    grand_total = 0
    row_height = 12 * mm 
    sr = 1

    items_list = bill_data.get('items', [])
    if not items_list and 'product_name' in bill_data:
        items_list = [bill_data]

    for item in items_list:
        qty = int(item.get('qty', item.get('qty_to_minus', 1)))
        rate = float(item.get('rate', item.get('price', 0)))
        
        disc_input = str(item.get('discount', '')).replace('%', '').strip()
        if not disc_input or disc_input == '0':
            disc_input = str(bill_data.get('global_discount', '0')).replace('%', '').strip()

        gross_amount = qty * rate
        net_amount = calculate_double_discount(gross_amount, disc_input)
        grand_total += net_amount
        disc_str = f"{disc_input}%" if disc_input and disc_input != '0' else "0%"

        p_name = str(item.get('product_name', item.get('particulars', ''))).upper()
        p_size = str(item.get('size', item.get('product_size', ''))).upper()
        p_colour = str(item.get('colour', '')).upper()

        values = [
            f"{sr:02d}", p_name, p_size, p_colour, str(qty), f"{rate:,.2f}", disc_str, f"{net_amount:,.2f}"
        ]

        x_start = LEFT
        for idx, (val, w) in enumerate(zip(values, widths)):
            c.setFillColor(white)
            c.rect(x_start, y - row_height, w, row_height, stroke=1, fill=1)
            c.setFillColor(DARK)
            
            if idx == 1: 
                if len(val) > 25:
                    space_idx = val.rfind(" ", 0, 26)
                    split_pt = space_idx if space_idx > 10 else 25
                    c.drawString(x_start + 2 * mm, y - 4.5 * mm, val[:split_pt].strip())
                    c.drawString(x_start + 2 * mm, y - 9.0 * mm, val[split_pt:].strip())
                else:
                    c.drawString(x_start + 2 * mm, y - 7.0 * mm, val)
                    
            elif idx == 2: 
                if len(val) > 13:
                    space_idx = val.rfind(" ", 0, 14)
                    split_pt = space_idx if space_idx > 4 else 12
                    c.drawCentredString(x_start + w / 2, y - 4.5 * mm, val[:split_pt].strip())
                    c.drawCentredString(x_start + w / 2, y - 9.0 * mm, val[split_pt:].strip())
                else:
                    c.drawCentredString(x_start + w / 2, y - 7.0 * mm, val)
                    
            elif idx == 3: 
                if len(val) > 14:
                    split_pt = val.find(" (")
                    if split_pt == -1 or split_pt > 14 or split_pt < 5:
                        space_idx = val.rfind(" ", 0, 15)
                        split_pt = space_idx if space_idx > 5 else 14
                    c.drawCentredString(x_start + w / 2, y - 4.5 * mm, val[:split_pt].strip())
                    c.drawCentredString(x_start + w / 2, y - 9.0 * mm, val[split_pt:].strip())
                else:
                    c.drawCentredString(x_start + w / 2, y - 7.0 * mm, val)
            else:
                c.drawCentredString(x_start + w / 2, y - 7.0 * mm, val)
            x_start += w

        y -= row_height
        sr += 1

    y -= 4 * mm

    summary_width = 65 * mm
    summary_row_height = 8 * mm
    summary_x = RIGHT - summary_width

    advance = float(bill_data.get('advance_paid', bill_data.get('advance', 0)))
    balance = grand_total - advance

    c.setFillColor(white)
    c.rect(summary_x, y - summary_row_height, summary_width, summary_row_height, stroke=1, fill=1)
    c.setFillColor(DARK)
    c.setFont(FONT_BOLD, 10)
    c.drawString(summary_x + 4 * mm, y - 5.5 * mm, "Gross Total :")
    c.drawRightString(RIGHT - 4 * mm, y - 5.5 * mm, f"{grand_total:,.2f}")
    y -= summary_row_height

    c.setFillColor(white)
    c.rect(summary_x, y - summary_row_height, summary_width, summary_row_height, stroke=1, fill=1)
    c.setFillColor(DARK)
    c.drawString(summary_x + 4 * mm, y - 5.5 * mm, "Advance Paid :")
    c.drawRightString(RIGHT - 4 * mm, y - 5.5 * mm, f"{advance:,.2f}")
    y -= summary_row_height

    c.setFillColor(YELLOW)
    c.rect(summary_x, y - summary_row_height, summary_width, summary_row_height, stroke=1, fill=1)
    c.setFillColor(DARK)
    c.drawString(summary_x + 4 * mm, y - 5.5 * mm, "Balance Due :")
    c.drawRightString(RIGHT - 4 * mm, y - 5.5 * mm, f"{balance:,.2f}")
    y -= summary_row_height

    y -= 38.1 * mm 
    try:
        c.setFont("Helvetica-BoldOblique", 10)
    except:
        c.setFont("Helvetica-BoldOblique", 10)
        
    handler_name = str(bill_data.get('billed_by', bill_data.get('generated_by', 'PUNEET YADAV'))).upper().strip()
    c.drawString(LEFT, y, f"BILL GENERATED BY : {handler_name}")

    y -= 4 * mm
    c.setStrokeColor(DARK)
    c.setLineWidth(1)
    c.line(LEFT, y, RIGHT, y)

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
        
        try:
            cursor.execute("ALTER TABLE bill_history ADD COLUMN IF NOT EXISTS price NUMERIC(12,2);")
            cursor.execute("ALTER TABLE bill_history ADD COLUMN IF NOT EXISTS billed_by VARCHAR(100);")
            conn.commit()
        except Exception as table_fix_err:
            print(f"Table patch skip or auto-applied: {table_fix_err}")
            conn.rollback()
        
        items_list = bill_data.get('items', [])
        if not items_list and 'product_name' in bill_data:
            items_list = [bill_data]

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

        customer_name = bill_data.get('customer_name', bill_data.get('party_name', ''))
        customer_address = bill_data.get('customer_address', bill_data.get('address', ''))
        mobile_no = bill_data.get('mobile', bill_data.get('mobile_no', ''))
        bill_no = bill_data.get('bill_no')
        billed_by = bill_data.get('billed_by', bill_data.get('generated_by', 'PUNEET YADAV'))
        
        # === DATABASE SIDE TIMEZONE CORRECTION ===
        IST = pytz.timezone('Asia/Kolkata')
        india_time = datetime.now(IST)
        
        bill_date_str = bill_data.get('date', bill_data.get('bill_date', ''))
        if not bill_date_str:
            bill_date_str = india_time.strftime("%Y-%m-%d")

        for item in items_list:
            p_name = item.get('product_name', item.get('particulars', '')).strip()
            p_size = item.get('size', item.get('product_size', '')).strip()
            p_col = item.get('colour', '').strip()
            qty_needed = int(item.get('qty', item.get('qty_to_minus', 1)))
            rate = float(item.get('rate', item.get('price', 0)))
            
            disc_input = str(item.get('discount', '')).replace('%', '').strip()
            if not disc_input or disc_input == '0':
                disc_input = str(bill_data.get('global_discount', '0')).replace('%', '').strip()
                
            if not p_name: continue
            
            cursor.execute("""
                UPDATE master_stock SET quantity = quantity - %s 
                WHERE UPPER(TRIM(product_name)) = UPPER(TRIM(%s)) 
                  AND UPPER(TRIM(product_size)) = UPPER(TRIM(%s)) 
                  AND UPPER(TRIM(colour)) = UPPER(TRIM(%s))
            """, (qty_needed, p_name, p_size, p_col))
            
            gross_amount = qty_needed * rate
            net_amount = calculate_double_discount(gross_amount, disc_input)
            
            cursor.execute("""
                INSERT INTO bill_history (bill_no, bill_date, customer_name, product_name, product_size, colour, price, qty, final_subtotal, billed_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (bill_no, bill_date_str, customer_name, p_name, p_size, p_col, rate, qty_needed, net_amount, billed_by))
            
        conn.commit()
        
        # Pura structured data pass karenge invoice engine ko
        bill_data['bill_time'] = india_time.strftime('%I:%M %p')
        pdf_data = generate_pdf_invoice(bill_data)
        
        cursor.close()
        conn.close()
        
        # Bill kat-te hi safe thread mein background mein RAM memory cache ko refresh karna
        threading.Thread(target=refresh_stock_cache).start()
        
        # Returning the calculated stream file object safely
        return send_file(BytesIO(pdf_data), mimetype='application/pdf', as_attachment=True, download_name=f"Invoice_{bill_no}.pdf")
        
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": f"Database Operation Error: {str(e)}"}), 500

# App start hote hi pehli baar automatic cloud se sara data RAM memory cache mein kheench lega
with app.app_context():
    refresh_stock_cache()

if __name__ == '__main__':
    app.run(debug=True, port=5000)