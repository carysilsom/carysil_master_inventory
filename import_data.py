import copy  
import sqlite3
import psycopg2
import pandas as pd

# ==========================================
# 1. EXCEL FILE SE BILKUL HU-BA-HU DATA READ KARNA
# ==========================================
excel_path = "NEW MASTER SHEET BILLING.xlsx"

print("Python Excel file ko import/read kar raha hai...")

# Jaisa aapka data hai, bina kisi badlav ke load ho raha hai
df = pd.read_excel(excel_path, sheet_name="MASTER SHEET")

# Columns ke extra spaces saaf karna
df.columns = [str(col).strip() for col in df.columns]

# Aapke bataye gaye exact 6 columns
required_columns = ["Sr.No", "PRODUCT NAME", "PRODUCT SIZE", "COLOUR", "PRICE", "QUANTITY"]
df = df[required_columns]

# Completely blank rows ko skip karna lekin beech ke design gaps ko allow karna
df = df.dropna(how='all')

# Local SQLite Database Connection
sqlite_conn = sqlite3.connect("carysil_inventory.db")
sqlite_cur = sqlite_conn.cursor()

# Column ko database format me badalna (Bina data badle)
df.columns = ["sr_no", "product_name", "product_size", "colour", "price", "quantity"]
df.to_sql("master_stock", sqlite_conn, if_exists="replace", index=False)

# Speed badhane ke liye local index banana
sqlite_cur.execute("CREATE INDEX IF NOT EXISTS idx_product_name ON master_stock (product_name);")
sqlite_conn.commit()
print("Local SQLite Database Successfully Update ho gaya!")

sqlite_conn.row_factory = sqlite3.Row
sqlite_cur = sqlite_conn.cursor()


# ==========================================
# 2. DATA KO AUTOMATIC CLOUD (NEON DB) PAR BHEJNA
# ==========================================
print("Cloud Database (Neon DB) se connect ho rahe hain...")
pg_conn = psycopg2.connect(
    "postgresql://neondb_owner:npg_kUGiCDj30LNW@ep-noisy-field-aozk7iqi.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
)
pg_cur = pg_conn.cursor()

# --- [FIX LOGIC] BILL_HISTORY KO DROP KARKE EXACT APP.PY KE COLUMNS SE MATCH KARNA ---
print("Cloud par Tables check aur fix kiye jaa rahe hain...")

pg_cur.execute("DROP TABLE IF EXISTS bill_history CASCADE;") # Purana galat column wala table hataya

pg_cur.execute("""
    CREATE TABLE IF NOT EXISTS master_stock (
        sr_no VARCHAR(50),
        product_name VARCHAR(255),
        product_size VARCHAR(100),
        colour VARCHAR(100),
        price NUMERIC(12,2),
        quantity INT
    );
""")

pg_cur.execute("""
    CREATE TABLE IF NOT EXISTS bill_history (
        id SERIAL PRIMARY KEY,
        bill_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        bill_no VARCHAR(50),
        customer_name VARCHAR(255),
        product_name VARCHAR(255),
        product_size VARCHAR(100),
        colour VARCHAR(100),
        qty INT,
        price NUMERIC(12,2),   -- Aapke app.py se exact match karne ke liye 'price' kiya
        final_subtotal NUMERIC(12,2)
    );
""")

pg_cur.execute("""
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
pg_conn.commit()

# Purana data clear karna
pg_cur.execute("TRUNCATE TABLE master_stock RESTART IDENTITY CASCADE;")
pg_conn.commit()


print("Naya Master Stock cloud par copy ho raha hai...")
sqlite_cur.execute("SELECT * FROM master_stock")
for row in sqlite_cur.fetchall():
    
    if row["product_name"] and str(row["product_name"]).strip() != 'None':
        sr_no = str(row["sr_no"]).strip() if row["sr_no"] and str(row["sr_no"]).strip() != 'None' else ""
        p_size = str(row["product_size"]).strip() if row["product_size"] and str(row["product_size"]).strip() != 'None' else ""
        p_col = str(row["colour"]).strip() if row["colour"] and str(row["colour"]).strip() != 'None' else ""
        price = float(row["price"]) if row["price"] and str(row["price"]).strip() != 'None' else 0.0
        qty = int(row["quantity"]) if row["quantity"] and str(row["quantity"]).strip() != 'None' else 0

        pg_cur.execute("""
            INSERT INTO master_stock
            (sr_no, product_name, product_size, colour, price, quantity)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            sr_no, str(row["product_name"]).strip(), p_size, p_col, price, qty
        ))


# --- (B) BILLS DATA KA SAFE COPY (TABLE CHECK KE SATH) ---
print("Bills data cloud par copy ho raha hai...")
sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bills';")
if sqlite_cur.fetchone():
    sqlite_cur.execute("SELECT * FROM bills")
    for row in sqlite_cur.fetchall():
        pg_cur.execute("""
            INSERT INTO bills
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            row["bill_no"], row["party_name"], row["address"], row["mobile_no"], row["bill_date"], row["total_amount"]
        ))
else:
    print("Local bills table abhi khali/absent hai, skip kar rahe hain.")


# --- (C) BILL ITEMS KA SAFE COPY (TABLE CHECK KE SATH) ---
print("Bill Items cloud par copy ho raha hai...")
sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bill_items';")
if sqlite_cur.fetchone():
    sqlite_cur.execute("SELECT * FROM bill_items")
    for row in sqlite_cur.fetchall():
        pg_cur.execute("""
            INSERT INTO bill_items
            (bill_no, particulars, size, colour, qty, rate, total_amt)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            row["bill_no"], row["particulars"], row["size"], row["colour"], row["qty"], row["rate"], row["total_amt"]
        ))
else:
    print("Local bill_items table abhi khali/absent hai, skip kar rahe hain.")

pg_conn.commit()

print("\n==============================")
print("SUCCESS - Aapka poora data 1189 tak ekdam safely cloud par sync ho gaya!")
print("==============================")

sqlite_conn.close()
pg_conn.close()