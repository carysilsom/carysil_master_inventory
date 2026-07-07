import psycopg2

DATABASE_URL = "postgresql://neondb_owner:npg_kUGiCDj30LNW@ep-noisy-field-aozk7iqi.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

try:
    print("🔄 Online Cloud Database se connect ho raha hai...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # 1. Sales Summary (Bill History) saaf karne ke liye
    print("🧹 Daily Sales Summary saaf ho rahi hai...")
    cursor.execute("DROP TABLE IF EXISTS bill_history CASCADE;")
    
    # 2. Inward Stock Summary saaf karne ke liye
    print("🧹 Inward Stock Summary saaf ho rahi hai...")
    cursor.execute("DROP TABLE IF EXISTS inward_history CASCADE;")
    
    # 3. Agar master stock table ko bhi poora khali karna hai taaki fresh excel load ho ske
    print("🧹 Master Stock Table saaf ho rahi hai...")
    cursor.execute("DROP TABLE IF EXISTS master_stock CASCADE;")
    
    conn.commit()
    cursor.close()
    conn.close()
    print("🎉 SUCCESS: Cloud Database se saari purani history aur summaries 100% saaf ho chuki hain!")

except Exception as e:
    print(f"❌ ERROR: {str(e)}")