"""
01_eda_and_outputs.py
---------------------------------
Simple EDA + Data Quality Check และสร้าง "mock output" (ตาราง Alert + กราฟ)
รันแล้วจะเขียนผลลัพธ์ลงโฟลเดอร์ outputs/ เพื่อใช้ประกอบสไลด์/เดโม

รัน:  python notebooks/01_eda_and_outputs.py

ทำอะไรบ้าง:
  1) Data Quality Summary  -> outputs/data_quality_summary.csv
  2) Demand status (Zero-Sales disambiguation) -> outputs/demand_status_breakdown.csv
  3) ตาราง Alert การสั่งซื้อ (mock dashboard data) -> outputs/reorder_alerts.csv
  4) กราฟยอดขายรายวัน + จุด Stockout ของสินค้าตัวอย่าง -> outputs/sales_stockout.png
  5) Backtesting: Min-Max rule เดิม vs AI baseline (Stockout days) -> พิมพ์สรุป
"""

import os
import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")                       # ไม่ต้องมีหน้าจอ
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import data_quality as dq                    # noqa: E402
import forecasting as fc                     # noqa: E402

BASE = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(BASE, "data", "raw")
OUT = os.path.join(BASE, "outputs")
os.makedirs(OUT, exist_ok=True)

sales = pd.read_csv(os.path.join(RAW, "sales_transaction.csv"))
products = pd.read_csv(os.path.join(RAW, "product_master.csv"))
inventory = pd.read_csv(os.path.join(RAW, "inventory.csv"))
po = pd.read_csv(os.path.join(RAW, "purchase_order.csv"))

print("ขนาดข้อมูล:",
      f"sales={len(sales):,}  inventory={len(inventory):,}  po={len(po):,}")

# ---------------------------------------------------------------------------
# 1) Data Quality Summary
# ---------------------------------------------------------------------------
orphan = dq.check_orphan_fk(sales, products)
ghost = dq.check_ghost_inventory(inventory)
lt = dq.lead_time_report(po)

dq_summary = pd.DataFrame([
    {"check": "Orphan FK (sales -> product master)", "issue_rows": len(orphan),
     "note": "พนักงานคีย์รหัสสินค้าที่ไม่มีในระบบ -> join ไม่ติด"},
    {"check": "Ghost Inventory (system != physical)", "issue_rows": len(ghost),
     "note": "ระบบคิดว่ามีของ แต่ของจริงหาย/ชำรุด -> AI ไม่เตือนสั่งซื้อ"},
    {"check": "Late delivery POs (delay_days > 0)",
     "issue_rows": int((pd.to_datetime(po["received_date"]) >
                        pd.to_datetime(po["expected_arrival_date"])).sum()),
     "note": "Lead Time จริง > ที่สัญญา -> ต้องเผื่อ Safety Stock"},
])
dq_summary.to_csv(os.path.join(OUT, "data_quality_summary.csv"),
                  index=False, encoding="utf-8-sig")
print("\n[1] Data Quality Summary:")
print(dq_summary.to_string(index=False))

# ---------------------------------------------------------------------------
# 2) Zero-Sales disambiguation
# ---------------------------------------------------------------------------
status = dq.flag_censored_demand(sales, inventory)
breakdown = status["demand_status"].value_counts().rename_axis("demand_status") \
                                   .reset_index(name="day_rows")
breakdown.to_csv(os.path.join(OUT, "demand_status_breakdown.csv"),
                 index=False, encoding="utf-8-sig")
print("\n[2] Zero-Sales disambiguation (รายวัน-สินค้า-สาขา):")
print(breakdown.to_string(index=False))
censored = (status["demand_status"] == "censored").sum()
print(f"    -> 'censored demand' (มีดีมานด์แต่ของหมด) = {censored} เคส "
      f"= โอกาสขายที่หายไปจริง ต้องนำกลับมาเทรนโมเดล")

# ---------------------------------------------------------------------------
# 3) ตาราง Alert การสั่งซื้อ (mock dashboard data)
# ---------------------------------------------------------------------------
# คำนวณ Lead Time มัธยฐานต่อสินค้า/สาขา จาก PO
po["lead_actual"] = (pd.to_datetime(po["received_date"]) -
                     pd.to_datetime(po["order_date"])).dt.days
lead_by = po.groupby(["product_id", "store_id"])["lead_actual"].median()

s = sales.copy()
s["date"] = pd.to_datetime(s["datetime"]).dt.date
daily = s.groupby(["product_id", "store_id", "date"])["qty"].sum().reset_index()

latest_inv = (inventory.sort_values("date")
              .groupby(["product_id", "store_id"]).tail(1))

alerts = []
prod_name = products.set_index("product_id")["product_name"].to_dict()
for _, row in latest_inv.iterrows():
    pid, sid = row["product_id"], row["store_id"]
    if pid not in prod_name:                 # ข้าม orphan
        continue
    series = daily[(daily["product_id"] == pid) &
                   (daily["store_id"] == sid)].sort_values("date")["qty"]
    lead = float(lead_by.get((pid, sid), 3))
    rec = fc.recommend_order_qty(series, stock_on_hand=row["stock_on_hand"],
                                 lead_time_days=lead)
    if rec["should_reorder"]:
        alerts.append({
            "store_id": sid,
            "product_id": pid,
            "product_name": prod_name[pid],
            "stock_on_hand": rec["stock_on_hand"],
            "reorder_point": rec["reorder_point"],
            "avg_daily_demand": rec["avg_daily_demand"],
            "lead_time_days": lead,
            "recommended_order_qty": rec["recommended_order_qty"],
            "status": "⚠ REORDER",
        })

alerts_df = pd.DataFrame(alerts).sort_values(
    ["store_id", "recommended_order_qty"], ascending=[True, False])
alerts_df.to_csv(os.path.join(OUT, "reorder_alerts.csv"),
                 index=False, encoding="utf-8-sig")
print(f"\n[3] Reorder Alerts (mock dashboard): {len(alerts_df)} รายการ")
print(alerts_df.head(10).to_string(index=False))

# ---------------------------------------------------------------------------
# 4) กราฟยอดขาย + จุด Stockout ของสินค้าตัวอย่าง
# ---------------------------------------------------------------------------
NAVY = "#1F3A5F"
pid, sid = "P1006", "S01"                     # ไข่ไก่ (สินค้า fresh ผันผวน)
d = daily[(daily["product_id"] == pid) & (daily["store_id"] == sid)].copy()
d["date"] = pd.to_datetime(d["date"])
inv_p = inventory[(inventory["product_id"] == pid) &
                  (inventory["store_id"] == sid)].copy()
inv_p["date"] = pd.to_datetime(inv_p["date"])
stockout_days = inv_p[inv_p["stockout_flag"] == 1]

fig, ax = plt.subplots(figsize=(10, 4))
ymax = max(d["qty"].max(), 1)
ax.plot(d["date"], d["qty"], color=NAVY, lw=1.4, label="Daily units sold")
ax.scatter(stockout_days["date"],
           [ymax * 1.05] * len(stockout_days),
           color="#C0392B", s=16, marker="v", label="Stockout day")
ax.set_title("Daily Sales & Stockout Events  (P1006 @ S01)",
             color=NAVY, fontsize=12)
ax.set_ylabel("Units sold")
ax.spines[["top", "right"]].set_visible(False)
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "sales_stockout.png"), dpi=120)
print("\n[4] บันทึกกราฟ -> outputs/sales_stockout.png")

# ---------------------------------------------------------------------------
# 5) Backtesting อย่างง่าย: นับ stockout days ที่ "หลีกเลี่ยงได้"
# ---------------------------------------------------------------------------
total_stockout_days = int(inventory["stockout_flag"].sum())
# สมมติฐาน MVP: ถ้าทำตามคำแนะนำ AI (เผื่อ safety stock) ลด stockout ได้ ~40-60%
print("\n[5] Backtesting (mock):")
print(f"    Stockout days ของระบบเดิม (Min-Max rule) = {total_stockout_days}")
print(f"    เป้าหมาย: ระบบ AI baseline ลด Stockout days ลง >= 15% (KPI สไลด์หน้า 1)")
print("\nเสร็จสิ้น — ดูผลลัพธ์ทั้งหมดในโฟลเดอร์ outputs/")
