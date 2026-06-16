"""
forecasting.py
---------------------------------
ตัวอย่างฟังก์ชันพยากรณ์ความต้องการ (Demand Forecasting) และคำนวณยอดสั่งซื้อ
แนะนำ (Recommended Reorder Quantity) สำหรับ MVP / Lean Validation

แนวคิด (ตรงกับสไลด์หน้า 4 และ 8):
  - เฟส 1 เน้นวิธีที่ "อธิบายได้และต้นทุนต่ำ" เหมาะกับ SME
    => Moving Average + Safety Stock (เผื่อความผันผวนของดีมานด์และ Lead Time)
  - นี่คือสูตรเดียวกับที่ทีม Data Scientist ใช้ทำ "Wizard of Oz" บน Excel
    ก่อนจะลงทุนสร้างโมเดล AI ตัวเต็ม (เช่น Prophet / LightGBM / LSTM)

หมายเหตุ: ฟังก์ชันเหล่านี้คือ baseline ที่อ่านง่ายและ backtest ได้ ไม่ใช่โมเดลสุดท้าย
"""

from __future__ import annotations
import math
import pandas as pd

# z-score สำหรับระดับการบริการ (service level) ที่ต้องการ
#   95% -> 1.65, 90% -> 1.28, 99% -> 2.33
Z_SCORE = {0.90: 1.28, 0.95: 1.65, 0.99: 2.33}


def moving_average_forecast(daily_qty: pd.Series, window: int = 7) -> float:
    """
    พยากรณ์ดีมานด์เฉลี่ยต่อวัน ด้วย Simple Moving Average

    daily_qty : pd.Series ของยอดขายรายวัน (เรียงตามวันที่)
    window    : จำนวนวันย้อนหลังที่ใช้เฉลี่ย (ดีฟอลต์ 7 วัน = 1 สัปดาห์)
    return    : ค่าพยากรณ์ดีมานด์ต่อวัน (หน่วย/วัน)
    """
    if len(daily_qty) == 0:
        return 0.0
    return float(daily_qty.tail(window).mean())


def safety_stock(daily_qty: pd.Series,
                 lead_time_days: float,
                 service_level: float = 0.95) -> float:
    """
    Safety Stock = Z * sigma_demand * sqrt(lead_time)

    เผื่อสต็อกเพื่อรองรับความผันผวนของดีมานด์ระหว่างรอของ (ตรงสไลด์หน้า 6 กล่อง 2)
    """
    z = Z_SCORE.get(round(service_level, 2), 1.65)
    sigma = float(daily_qty.tail(28).std(ddof=0)) if len(daily_qty) > 1 else 0.0
    return z * sigma * math.sqrt(max(lead_time_days, 0.0))


def reorder_point(daily_qty: pd.Series,
                  lead_time_days: float,
                  service_level: float = 0.95) -> float:
    """
    Reorder Point (ROP) = (ดีมานด์เฉลี่ย * Lead Time) + Safety Stock

    เมื่อ stock_on_hand <= ROP => ควรสั่งซื้อ
    """
    avg = moving_average_forecast(daily_qty)
    return avg * lead_time_days + safety_stock(daily_qty, lead_time_days, service_level)


def recommend_order_qty(daily_qty: pd.Series,
                        stock_on_hand: float,
                        lead_time_days: float,
                        review_period_days: int = 7,
                        service_level: float = 0.95) -> dict:
    """
    คำนวณ "ยอดสั่งซื้อแนะนำ" แบบ Periodic Review (order-up-to level)

    target_level = ดีมานด์ * (lead_time + review_period) + safety_stock
    order_qty    = max(0, target_level - stock_on_hand)

    return dict สำหรับเอาไปแสดงบน Mock Dashboard ได้ทันที
    """
    avg = moving_average_forecast(daily_qty)
    ss = safety_stock(daily_qty, lead_time_days, service_level)
    target_level = avg * (lead_time_days + review_period_days) + ss
    rop = reorder_point(daily_qty, lead_time_days, service_level)
    qty = max(0, round(target_level - stock_on_hand))

    return {
        "avg_daily_demand": round(avg, 1),
        "safety_stock": round(ss, 1),
        "reorder_point": round(rop, 1),
        "stock_on_hand": stock_on_hand,
        "recommended_order_qty": int(qty),
        "should_reorder": bool(stock_on_hand <= rop),
    }


# ---------------------------------------------------------------------------
# pseudo-code ของ pipeline ระดับ production (เฟ ส 2) — เขียนไว้เป็น docstring
# ---------------------------------------------------------------------------
PIPELINE_PSEUDOCODE = """
ทุกเช้า 06:00 (batch job):
    for each (store, product):
        history   <- ดึงยอดขาย 28-90 วันล่าสุดจาก sales_transaction
        history   <- ปรับด้วย Zero-Sales correction (ดู data_quality.py)
                     # ถ้า qty=0 แต่ stockout_flag=1 -> ถือเป็น censored demand
        lead_time <- ค่ามัธยฐาน Lead Time จริงของซัพพลายเออร์ (จาก purchase_order)
        forecast  <- model.predict(history, calendar_features, promo_flag)
        rec       <- recommend_order_qty(forecast, stock_on_hand, lead_time)
        if rec.should_reorder:
            push_alert(store, product, rec)      # ส่งเข้า Mock Dashboard + Notify
"""

if __name__ == "__main__":
    # ตัวอย่างการเรียกใช้ด้วยข้อมูลสมมติ
    demo = pd.Series([40, 42, 38, 45, 50, 60, 55, 41, 39, 44])
    print("ตัวอย่างคำแนะนำการสั่งซื้อ:")
    for k, v in recommend_order_qty(demo, stock_on_hand=30, lead_time_days=3).items():
        print(f"  {k:24s}: {v}")
