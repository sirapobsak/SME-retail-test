"""
generate_mock_data.py
---------------------------------
สร้างชุดข้อมูลจำลอง (mock data) สำหรับโปรเจกต์
"ระบบจัดการปัญหาสินค้าขาดสต็อก (Stockout) สำหรับ SME ค้าปลีก"

ข้อมูลนี้ออกแบบให้สะท้อน schema จริงในสไลด์ (Fact/Dimension tables) และ
*จงใจ* ฝังปัญหาคุณภาพข้อมูล (Data Quality Issues) ไว้ เพื่อใช้ทดสอบ
ขั้นตอน EDA / Data Quality Check และพิสูจน์ว่าระบบจับปัญหาเหล่านี้ได้:

  1. Ghost Inventory   : ในระบบมีของ แต่ของจริงขาย/หายไปแล้ว
  2. Zero-Sales        : ยอดขาย = 0 แยกไม่ออกว่า "ไม่มีดีมานด์" หรือ "ของหมด"
  3. Lead Time Variance: ซัพพลายเออร์ส่งของช้ากว่ากำหนด (Actual vs Expected)
  4. Promotion Lift    : โปรโมชั่นดันยอดขายให้สูงกว่า baseline ชั่วคราว
  5. Orphan FK         : พนักงานคีย์ขายรหัสสินค้าที่ไม่มีใน Product Master

วิธีรัน:
    python data/generate_mock_data.py
ผลลัพธ์: ไฟล์ CSV ทั้งหมดถูกเขียนลง data/raw/
"""

import os
import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)          # fix seed เพื่อให้ผลลัพธ์ทำซ้ำได้ (reproducible)
OUT_DIR = os.path.join(os.path.dirname(__file__), "raw")
os.makedirs(OUT_DIR, exist_ok=True)

START_DATE = pd.Timestamp("2025-01-01")
N_DAYS = 180                              # ข้อมูลย้อนหลังประมาณ 6 เดือน

# ---------------------------------------------------------------------------
# 1) Dimension Tables
# ---------------------------------------------------------------------------
PRODUCTS = pd.DataFrame({
    "product_id":   [f"P{1000+i}" for i in range(10)],
    "product_name": [
        "น้ำดื่ม 600ml", "บะหมี่กึ่งสำเร็จรูป", "นมกล่อง UHT", "ขนมปัง",
        "ผงซักฟอก 1kg", "น้ำมันพืช 1L", "ไข่ไก่ เบอร์ 2 (แผง)", "กาแฟ 3in1",
        "ยาสีฟัน", "ข้าวสาร 5kg",
    ],
    "category": [
        "Beverage", "Dry Food", "Dairy", "Bakery", "Household",
        "Cooking", "Fresh", "Beverage", "Personal Care", "Staple",
    ],
    # baseline demand ต่อวัน (สินค้าขายเร็ว vs ขายช้า ต่างกัน)
    "base_demand": [40, 35, 25, 30, 12, 10, 18, 22, 8, 6],
    "unit_price":  [7, 6, 12, 15, 45, 55, 120, 8, 35, 220],
})

STORES = pd.DataFrame({
    "store_id":     ["S01", "S02"],
    "store_name":   ["สาขาตลาดสด", "สาขาหมู่บ้าน"],
    "store_type":   ["Community Market", "Residential"],
    "province":     ["Bangkok", "Nonthaburi"],
})

PROMOTIONS = pd.DataFrame({
    "promotion_id": ["PR01", "PR02", "PR03"],
    "promotion_name": ["ลด 10%", "ซื้อ 1 แถม 1", "โปรต้นเดือน"],
    "lift_factor":  [1.4, 1.8, 1.3],      # ตัวคูณยอดขายช่วงโปร
    "start_day":    [30, 75, 120],         # offset วันจาก START_DATE
    "duration":     [7, 5, 10],
})

# ---------------------------------------------------------------------------
# 2) สร้าง Sales + Inventory วันต่อวัน รายสินค้า รายสาขา
# ---------------------------------------------------------------------------
sales_rows, inv_rows = [], []
po_rows = []
po_counter = 0

for _, store in STORES.iterrows():
    for _, prod in PRODUCTS.iterrows():
        # สต็อกเริ่มต้น + จุดสั่งซื้อ (reorder point) แบบระบบเดิม (Min-Max ที่ตั้งต่ำไป)
        # ตั้ง ROP ต่ำกว่าที่ควร -> สะท้อน "ระบบเดิมที่ใช้คนเดา" ที่ stockout บ่อย
        stock = int(prod["base_demand"] * RNG.uniform(3.5, 4.5))
        reorder_point = int(prod["base_demand"] * 2.2)
        order_qty = int(prod["base_demand"] * 5)

        pending = {}            # {arrival_day: qty}  ของที่สั่งแล้วกำลังเดินทางมา
        has_open_po = False

        for d in range(N_DAYS):
            date = START_DATE + pd.Timedelta(days=d)
            dow = date.dayofweek

            # ----- ของล็อตใหม่มาถึงวันนี้ไหม -----
            if d in pending:
                stock += pending.pop(d)
                has_open_po = False

            # ดีมานด์ตามฤดู: เสาร์-อาทิตย์ขายดีขึ้น + สัญญาณรบกวน
            weekend_boost = 1.25 if dow >= 5 else 1.0

            # โปรโมชั่น?
            promo_id = ""
            lift = 1.0
            for _, pr in PROMOTIONS.iterrows():
                if pr["start_day"] <= d < pr["start_day"] + pr["duration"]:
                    promo_id = pr["promotion_id"]
                    lift = pr["lift_factor"]
                    break

            true_demand = RNG.poisson(prod["base_demand"] * weekend_boost * lift)

            # ขายได้จริง = min(ดีมานด์, ของในสต็อก)  -> ถ้าของหมดจะเกิด Stockout
            sold = min(true_demand, max(stock, 0))
            stockout_flag = int(stock <= 0 or sold < true_demand)

            # ----- ฝังปัญหา Ghost Inventory -----
            # ระบบบันทึกสต็อก (system) อาจสูงกว่าของจริง (physical) เพราะของหาย/ชำรุด
            ghost_gap = 0
            if RNG.random() < 0.02 and stock > 3:    # ~2% ของวัน เกิด shrinkage
                ghost_gap = int(RNG.integers(1, 4))
            stock_after = max(0, stock - sold)
            stock_physical = max(0, stock_after - ghost_gap)
            stock_system = stock_after               # ระบบยังคิดว่ามีเท่าเดิม (ghost)

            # บันทึก Inventory (snapshot สิ้นวัน)
            inv_rows.append({
                "date": date.date(),
                "product_id": prod["product_id"],
                "store_id": store["store_id"],
                "stock_on_hand": stock_system,    # <-- ค่าในระบบ (อาจเป็น ghost)
                "stock_physical_truth": stock_physical,  # ความจริง (มีไว้ตรวจสอบ EDA)
                "reorder_point": reorder_point,
                "stockout_flag": stockout_flag,
            })

            # บันทึก Sales transaction (ถ้ามีการขาย)
            if sold > 0:
                sales_rows.append({
                    "datetime": (date + pd.Timedelta(hours=int(RNG.integers(8, 20)))),
                    "product_id": prod["product_id"],
                    "store_id": store["store_id"],
                    "qty": int(sold),
                    "unit_price": float(prod["unit_price"]),
                    "promotion_id": promo_id,
                    "po_id": "",
                })

            # ----- ปรับสต็อกจริงหลังขาย/หาย + ตัดสินใจสั่งซื้อ (Min-Max rule) -----
            stock = stock_physical
            if stock <= reorder_point and not has_open_po:
                po_counter += 1
                po_id = f"PO{5000+po_counter}"
                # ----- ฝังปัญหา Lead Time Variance -----
                planned_lead = 3
                actual_lead = planned_lead + (int(RNG.integers(1, 6)) if RNG.random() < 0.4 else 0)
                expected = date + pd.Timedelta(days=planned_lead)
                received = date + pd.Timedelta(days=actual_lead)
                po_rows.append({
                    "po_id": po_id,
                    "product_id": prod["product_id"],
                    "store_id": store["store_id"],
                    "order_date": date.date(),
                    "expected_arrival_date": expected.date(),
                    "received_date": received.date(),
                    "qty_ordered": order_qty,
                    "supplier_id": f"SUP{int(prod['product_id'][-1]) % 3 + 1}",
                })
                pending[d + actual_lead] = pending.get(d + actual_lead, 0) + order_qty
                has_open_po = True

sales = pd.DataFrame(sales_rows)
inventory = pd.DataFrame(inv_rows)
purchase_orders = pd.DataFrame(po_rows)

# ---------------------------------------------------------------------------
# 3) ฝังปัญหา Orphan FK: คีย์ขายสินค้ารหัสที่ไม่มีใน Product Master
# ---------------------------------------------------------------------------
orphan = sales.sample(8, random_state=1).copy()
orphan["product_id"] = "P9999"            # รหัสกลาง/รหัสผิดที่ไม่มีใน dim
sales = pd.concat([sales, orphan], ignore_index=True)
sales = sales.sort_values("datetime").reset_index(drop=True)

# ---------------------------------------------------------------------------
# 4) เขียนไฟล์
# ---------------------------------------------------------------------------
def save(df, name):
    path = os.path.join(OUT_DIR, name)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  - {name:28s} {len(df):>6,} rows")

print("เขียนไฟล์ข้อมูลจำลองลง data/raw/ :")
save(PRODUCTS, "product_master.csv")
save(STORES, "store_master.csv")
save(PROMOTIONS, "promotion_master.csv")
save(sales, "sales_transaction.csv")
save(inventory, "inventory.csv")
save(purchase_orders, "purchase_order.csv")
print("เสร็จสิ้น (done)")
