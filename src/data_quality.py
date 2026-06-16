"""
data_quality.py
---------------------------------
ฟังก์ชันตรวจสอบคุณภาพข้อมูล (Data Quality Checks) ที่สอดคล้องกับความเสี่ยง
ในสไลด์หน้า 5-6 พร้อมตัวช่วยแก้ความกำกวมของ "Zero-Sales"

ตรวจ 4 อย่างหลัก:
  1. Orphan FK         : sales ที่ product_id ไม่มีใน Product Master
  2. Ghost Inventory   : stock ในระบบ != ของจริง (system vs physical)
  3. Lead Time Variance: received_date เทียบ expected_arrival_date
  4. Zero / Censored   : ระบุวันที่ "ขาย=0 เพราะของหมด" (lost demand จริง)
"""

from __future__ import annotations
import pandas as pd


def check_orphan_fk(sales: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """คืน rows ของ sales ที่ product_id อ้างถึงสินค้าที่ไม่มีใน Product Master"""
    valid = set(products["product_id"])
    return sales[~sales["product_id"].isin(valid)]


def check_ghost_inventory(inventory: pd.DataFrame) -> pd.DataFrame:
    """
    คืนแถวที่ stock ในระบบ (stock_on_hand) ไม่ตรงกับของจริง
    (ในโลกจริงจะรู้จากการนับสต็อก/cycle count — ที่นี่ใช้คอลัมน์ truth ที่ฝังไว้)
    """
    inv = inventory.copy()
    inv["ghost_gap"] = inv["stock_on_hand"] - inv["stock_physical_truth"]
    return inv[inv["ghost_gap"] != 0]


def lead_time_report(purchase_orders: pd.DataFrame) -> pd.DataFrame:
    """
    สรุปความแม่นยำการส่งของของแต่ละซัพพลายเออร์ (Lead Time Variance)
    delay_days > 0 = ส่งช้ากว่าที่สัญญา
    """
    po = purchase_orders.copy()
    po["expected_arrival_date"] = pd.to_datetime(po["expected_arrival_date"])
    po["received_date"] = pd.to_datetime(po["received_date"])
    po["delay_days"] = (po["received_date"] - po["expected_arrival_date"]).dt.days
    return (po.groupby("supplier_id")
              .agg(n_orders=("po_id", "count"),
                   avg_delay_days=("delay_days", "mean"),
                   pct_late=("delay_days", lambda s: (s > 0).mean() * 100))
              .round(2)
              .reset_index())


def flag_censored_demand(sales: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """
    แก้ความกำกวม Zero-Sales (สไลด์หน้า 6 กล่อง 4):
    รวมยอดขายรายวัน-รายสินค้า-รายสาขา แล้ว join กับ inventory
    ถ้า qty_sold == 0 และ stockout_flag == 1  => 'censored' (มีดีมานด์แต่ของหมด)
    ถ้า qty_sold == 0 และ stockout_flag == 0  => 'true_zero' (ไม่มีดีมานด์จริง)
    """
    s = sales.copy()
    s["date"] = pd.to_datetime(s["datetime"]).dt.date
    daily = (s.groupby(["date", "product_id", "store_id"])["qty"]
               .sum().reset_index().rename(columns={"qty": "qty_sold"}))

    inv = inventory.copy()
    inv["date"] = pd.to_datetime(inv["date"]).dt.date
    merged = inv.merge(daily, on=["date", "product_id", "store_id"], how="left")
    merged["qty_sold"] = merged["qty_sold"].fillna(0)

    def label(row):
        if row["qty_sold"] == 0 and row["stockout_flag"] == 1:
            return "censored"        # ของหมด -> ดีมานด์ถูก "ตัดทิ้ง" จากข้อมูล
        if row["qty_sold"] == 0:
            return "true_zero"       # ไม่มีคนซื้อจริง
        return "has_sales"

    merged["demand_status"] = merged.apply(label, axis=1)
    return merged


if __name__ == "__main__":
    import os
    base = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
    sales = pd.read_csv(os.path.join(base, "sales_transaction.csv"))
    products = pd.read_csv(os.path.join(base, "product_master.csv"))
    inventory = pd.read_csv(os.path.join(base, "inventory.csv"))
    po = pd.read_csv(os.path.join(base, "purchase_order.csv"))

    print("Orphan FK rows      :", len(check_orphan_fk(sales, products)))
    print("Ghost Inventory rows:", len(check_ghost_inventory(inventory)))
    print("\nLead Time report:")
    print(lead_time_report(po).to_string(index=False))
