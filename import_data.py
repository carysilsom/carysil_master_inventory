import pandas as pd
import sqlite3

# 1. Excel file ko read karna (Sirf MASTER SHEET se data uthega)
excel_file = "stock.xlsx"
sheet_name = "MASTER SHEET"

print("Excel se data read ho raha hai, kripya rukein...")
df = pd.read_excel(excel_file, sheet_name=sheet_name)

# 2. Database se connect karna
conn = sqlite3.connect('carysil_inventory.db')
cursor = conn.cursor()

# Purana khali data saaf karna taaki double entry na ho
cursor.execute("DELETE FROM master_stock")

# 3. Merged cells ke data ko sahi karne ka automatic logic
current_sr = ""
current_product = ""
current_size = ""

for index, row in df.iterrows():
    # Agar columns khali nahi hain toh naya data uthao, nahi toh purana hi chalne do
    if pd.notna(row.iloc[0]): current_sr = str(row.iloc[0]).strip()
    if pd.notna(row.iloc[1]): current_product = str(row.iloc[1]).strip()
    if pd.notna(row.iloc[2]): current_size = str(row.iloc[2]).strip()
    
    colour = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""
    
    # PRICE Handle: Agar koi text ya error ho toh 0.0 maan le
    try:
        price = float(row.iloc[4]) if pd.notna(row.iloc[4]) else 0.0
    except:
        price = 0.0
        
    # QUANTITY Handle: Agar text ho (jaise TOTAL PCS) toh automatic 0 maan le, error na de
    try:
        qty_val = str(row.iloc[5]).strip() if pd.notna(row.iloc[5]) else "0"
        qty_clean = ''.join(filter(str.isdigit, qty_val))
        quantity = int(qty_clean) if qty_clean else 0
    except:
        quantity = 0
    
    # Faltu "TOTAL" waali rows ko chhodkar sirf sahi items ko database mein daalna
    if current_product and "TOTAL" not in current_product.upper() and colour:
        cursor.execute("""
            INSERT INTO master_stock (sr_no, product_name, product_size, colour, price, quantity)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (current_sr, current_product, current_size, colour, price, quantity))

conn.commit()
conn.close()
print("✓ Kamaal ho gaya bhai! Saara Excel stock data automatic software me load ho gaya hai!")
