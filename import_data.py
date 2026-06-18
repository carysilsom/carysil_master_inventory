import sqlite3
import psycopg2

sqlite_conn = sqlite3.connect("carysil_inventory.db")
sqlite_conn.row_factory = sqlite3.Row
sqlite_cur = sqlite_conn.cursor()

pg_conn = psycopg2.connect(
    "postgresql://neondb_owner:npg_kUGiCDj30LNW@ep-noisy-field-aozk7iqi.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
)

pg_cur = pg_conn.cursor()


# master_stock
sqlite_cur.execute("SELECT * FROM master_stock")
for row in sqlite_cur.fetchall():

    pg_cur.execute("""
    INSERT INTO master_stock
    (sr_no,product_name,product_size,colour,price,quantity)

    VALUES(%s,%s,%s,%s,%s,%s)

    """,

    (
    row["sr_no"],
    row["product_name"],
    row["product_size"],
    row["colour"],
    row["price"],
    row["quantity"]
    ))


# bills
sqlite_cur.execute("SELECT * FROM bills")
for row in sqlite_cur.fetchall():

    pg_cur.execute("""
    INSERT INTO bills

    VALUES(%s,%s,%s,%s,%s,%s)

    """,

    (

    row["bill_no"],
    row["party_name"],
    row["address"],
    row["mobile_no"],
    row["bill_date"],
    row["total_amount"]

    ))


# bill_items
sqlite_cur.execute("SELECT * FROM bill_items")
for row in sqlite_cur.fetchall():

    pg_cur.execute("""

    INSERT INTO bill_items

    (
    bill_no,
    particulars,
    size,
    colour,
    qty,
    rate,
    total_amt
    )

    VALUES(%s,%s,%s,%s,%s,%s,%s)

    """,

    (

    row["bill_no"],
    row["particulars"],
    row["size"],
    row["colour"],
    row["qty"],
    row["rate"],
    row["total_amt"]

    ))

pg_conn.commit()

print("SUCCESS")
print("master_stock copied")
print("bills copied")
print("bill_items copied")

sqlite_conn.close()
pg_conn.close()