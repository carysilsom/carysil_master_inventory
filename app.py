from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('carysil_inventory.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/search', methods=['GET'])
def search_stock():
    query = request.args.get('q', '').strip()
    conn = get_db_connection()
    if not query:
        return jsonify([])
    
    # Text grouping ko clean karne ke liye UPPER aur TRIM layout optimization
    sql = """
        SELECT sr_no, UPPER(TRIM(product_name)) as p_name, UPPER(TRIM(product_size)) as p_size, UPPER(TRIM(colour)) as p_col, price, quantity 
        FROM master_stock 
        WHERE product_name LIKE ? OR product_size LIKE ?
        ORDER BY p_name ASC, p_size ASC, p_col ASC
    """
    search_pattern = f"%{query}%"
    results = conn.execute(sql, (search_pattern, search_pattern)).fetchall()
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
@app.route('/api/generate_bill', methods=['POST'])
def generate_bill():
    data = request.json
    bill_no = data.get('bill_no')
    party_name = data.get('party_name')
    address = data.get('address', 'N/A')
    mobile_no = data.get('mobile_no')
    bill_date = data.get('bill_date')
    advance_paid = float(data.get('advance_paid', 0))
    items = data.get('items')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    total_gross_amt = 0
    total_net_amt = 0
    
    try:
        # Strict dynamic validation to prevent mismatch bugs
        for item in items:
            p_name = item['particulars'].strip()
            p_size = item['size'].strip()
            p_colour = item['colour'].strip()
            order_qty = int(item['qty'])
            
            stock_row = cursor.execute(
                "SELECT quantity FROM master_stock WHERE UPPER(TRIM(product_name))=UPPER(TRIM(?)) AND UPPER(TRIM(product_size))=UPPER(TRIM(?)) AND UPPER(TRIM(colour))=UPPER(TRIM(?))",
                (p_name, p_size, p_colour)
            ).fetchone()
            
            if not stock_row or stock_row['quantity'] < order_qty:
                return jsonify({'status': 'error', 'message': f'{p_name} ({p_colour}) me पर्याप्त stock nahi hai!'}), 400
                
        # Calculations block
        for item in items:
            qty = int(item['qty'])
            rate = float(item['rate'])
            disc_pct = float(item.get('discount', 0))
            
            gross = qty * rate
            net = gross * (1 - (disc_pct / 100))
            
            total_gross_amt += gross
            total_net_amt += net
            
        balance_due = total_net_amt - advance_paid
        
        # Save invoice to master logs database securely
        cursor.execute("INSERT OR REPLACE INTO bills VALUES (?, ?, ?, ?, ?, ?)", 
                       (bill_no, party_name, address, mobile_no, bill_date, total_net_amt))
        
        for item in items:
            p_name = item['particulars'].strip()
            p_size = item['size'].strip()
            p_colour = item['colour'].strip()
            qty = int(item['qty'])
            rate = float(item['rate'])
            disc_pct = float(item.get('discount', 0))
            net_item_amt = (qty * rate) * (1 - (disc_pct / 100))
            
            cursor.execute("INSERT INTO bill_items (bill_no, particulars, size, colour, qty, rate, total_amt) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                           (bill_no, p_name, p_size, p_colour, qty, rate, net_item_amt))
            
            cursor.execute("UPDATE master_stock SET quantity = quantity - ? WHERE UPPER(TRIM(product_name))=UPPER(TRIM(?)) AND UPPER(TRIM(product_size))=UPPER(TRIM(?)) AND UPPER(TRIM(colour))=UPPER(TRIM(?))", 
                           (qty, p_name, p_size, p_colour))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    conn.close()
    
    # STANDARD COMMERCIAL INVOICE PREPARATION (PURE WHITE & BLACK GRID)
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CompTitle', fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=colors.black, alignment=1)
    tag_style = ParagraphStyle('TaxTag', fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.black, alignment=1)
    sub_style = ParagraphStyle('CompSub', fontName='Helvetica', fontSize=9, leading=12, textColor=colors.darkgrey, alignment=1)
    label_style = ParagraphStyle('ClientLabel', fontName='Helvetica-Bold', fontSize=10, leading=15, textColor=colors.black)
    
    story = []
    story.append(Paragraph("TAX INVOICE", tag_style))
    story.append(Paragraph("CARYSIL - SOM ASSOCIATES STOCK MANAGEMENT INVENTORY", title_style))
    story.append(Paragraph("OFFICIAL INVENTORY SYSTEM DISTRIBUTOR LOG", sub_style))
    story.append(Spacer(1, 15))
    
    info_data = [
        [Paragraph(f"<b>Customer Name:</b> {party_name}", label_style), Paragraph(f"<b>Invoice No:</b> {bill_no}", label_style)],
        [Paragraph(f"<b>Mobile No:</b> {mobile_no}", label_style), Paragraph(f"<b>Date:</b> {bill_date}", label_style)]
    ]
    info_table = Table(info_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW', (0,1), (-1,1), 1, colors.black),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 15))
    
    table_data = [["Sr.", "Particulars Description", "Size", "Colour", "Qty", "Rate (Rs.)", "Disc %", "Final SubTotal"]]
    for idx, item in enumerate(items, 1):
        q = int(item['qty'])
        r = float(item['rate'])
        d_p = float(item.get('discount', 0))
        sub_row_amt = (q * r) * (1 - (d_p / 100))
        
        table_data.append([
            str(idx), item['particulars'], item['size'], item['colour'], str(q),
            f"{r:,.2f}", f"{d_p}%", f"{sub_row_amt:,.2f}"
        ])
    
    # Financial totals summary block formatting mapping
    table_data.append(["", "", "", "", "", "", "GROSS TOTAL:", f"{total_gross_amt:,.2f}"])
    table_data.append(["", "", "", "", "", "", "NET PAYABLE:", f"{total_net_amt:,.2f}"])
    table_data.append(["", "", "", "", "", "", "ADVANCE PAID:", f"{advance_paid:,.2f}"])
    table_data.append(["", "", "", "", "", "", "BALANCE DUE:", f"{balance_due:,.2f}"])
    
    prod_table = Table(table_data, colWidths=[25, 175, 55, 65, 30, 65, 60, 65])
    prod_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('ALIGN', (1,1), (1,-5), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('GRID', (0,0), (-1,-5), 0.5, colors.black),
        ('LINEBELOW', (-2,-4), (-1,-1), 0.5, colors.black),
        ('FONTNAME', (-2,-4), (-1,-1), 'Helvetica-Bold'),
    ]))
    story.append(prod_table)
    
    doc.build(story)
    pdf_buffer.seek(0)
    return send_file(pdf_buffer, as_attachment=True, download_name=f"Invoice_{bill_no}.pdf", mimetype='application/pdf')

@app.route('/api/add_stock', methods=['POST'])
def add_stock():
    data = request.json
    sr_no = data.get('sr_no', '').strip()
    product_name = data.get('product_name').strip()
    product_size = data.get('product_size').strip()
    colour = data.get('colour').strip()
    price = float(data.get('price', 0))
    qty_to_add = int(data.get('qty', 0))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Strong text sanitization wrap to prevent structural duplication errors
        existing_item = cursor.execute(
            "SELECT id, quantity FROM master_stock WHERE UPPER(TRIM(product_name))=UPPER(TRIM(?)) AND UPPER(TRIM(product_size))=UPPER(TRIM(?)) AND UPPER(TRIM(colour))=UPPER(TRIM(?))",
            (product_name, product_size, colour)
        ).fetchone()
        
        if existing_item:
            cursor.execute("UPDATE master_stock SET quantity = quantity + ?, price = ? WHERE id = ?", (qty_to_add, price, existing_item['id']))
            message = "✓ SUCCESS: Stock successfully added into current color line!"
        else:
            cursor.execute("INSERT INTO master_stock (sr_no, product_name, product_size, colour, price, quantity) VALUES (?, ?, ?, ?, ?, ?)", 
                           (sr_no, product_name, product_size, colour, price, qty_to_add))
            message = "✓ SUCCESS: New variant structure successfully created!"
        conn.commit()
        response = {'status': 'success', 'message': message}
    except Exception as e:
        conn.rollback()
        response = {'status': 'error', 'message': str(e)}
    finally:
        conn.close()
    return jsonify(response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
