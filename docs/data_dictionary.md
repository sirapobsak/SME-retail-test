# Data Dictionary

พจนานุกรมข้อมูลของชุดข้อมูลจำลอง (mock data) ในโฟลเดอร์ [`data/raw/`](../data/raw)
โครงสร้างอ้างอิงจาก Analytical Layer ในสไลด์หน้า 4–5 (Fact / Dimension tables)

> **PK** = Primary Key, **FK** = Foreign Key, **Fact** = ตารางข้อเท็จจริง (ธุรกรรม), **Dim** = ตารางมิติ (ข้อมูลอ้างอิง)

---

## 1. `sales_transaction.csv`  *(Fact)*
ธุรกรรมการขายระดับรายการ — แกนกลางที่ใช้พยากรณ์ดีมานด์

| คอลัมน์ | ชนิด | คำอธิบาย | คีย์ |
|---|---|---|---|
| `datetime` | datetime | วัน–เวลาที่ขาย | |
| `product_id` | string | รหัสสินค้า | FK → `product_master` |
| `store_id` | string | รหัสสาขา | FK → `store_master` |
| `qty` | int | จำนวนที่ขายได้ (units) | |
| `unit_price` | float | ราคาต่อหน่วย (บาท) | |
| `promotion_id` | string | รหัสโปรโมชั่น (ว่าง = ไม่มีโปร) | FK → `promotion_master` |
| `po_id` | string | อ้างอิงใบสั่งซื้อ (สงวนไว้) | FK → `purchase_order` |

> ⚠️ **ฝังปัญหาไว้:** มี 8 แถวที่ `product_id = P9999` ซึ่ง **ไม่มี**ใน `product_master` (จำลองพนักงานคีย์รหัสผิด → Orphan FK)

## 2. `inventory.csv`  *(Fact)*
สแน็ปช็อตสต็อกคงเหลือสิ้นวัน รายสินค้า–รายสาขา

| คอลัมน์ | ชนิด | คำอธิบาย |
|---|---|---|
| `date` | date | วันที่ของสแน็ปช็อต |
| `product_id` | string | รหัสสินค้า (FK) |
| `store_id` | string | รหัสสาขา (FK) |
| `stock_on_hand` | int | สต็อกคงเหลือ **ตามระบบ** (ค่าที่ระบบเชื่อ) |
| `stock_physical_truth` | int | สต็อกจริงบนชั้นวาง *(คอลัมน์สอน/ตรวจสอบ — โลกจริงต้องนับเอง)* |
| `reorder_point` | int | จุดสั่งซื้อของระบบเดิม (Min-Max rule) |
| `stockout_flag` | int | 1 = วันนั้นของขาด/ขายไม่ได้ตามดีมานด์, 0 = ปกติ |

> ⚠️ **Ghost Inventory:** `stock_on_hand` (ระบบ) อาจ > `stock_physical_truth` (ของจริง) เพราะของหาย/ชำรุด

## 3. `purchase_order.csv`  *(Fact)*
ใบสั่งซื้อ ใช้คำนวณ Lead Time จริงและความน่าเชื่อถือของซัพพลายเออร์

| คอลัมน์ | ชนิด | คำอธิบาย | คีย์ |
|---|---|---|---|
| `po_id` | string | รหัสใบสั่งซื้อ | PK |
| `product_id` | string | รหัสสินค้า | FK |
| `store_id` | string | รหัสสาขา | FK |
| `order_date` | date | วันที่ออกใบสั่งซื้อ | |
| `expected_arrival_date` | date | วันที่**คาดว่า**ของจะถึง | |
| `received_date` | date | วันที่ของ**ถึงจริง** | |
| `qty_ordered` | int | จำนวนที่สั่ง | |
| `supplier_id` | string | รหัสซัพพลายเออร์ | |

> ⚠️ **Lead Time Variance:** `received_date` อาจ > `expected_arrival_date` (ส่งช้า) → ใช้ให้คะแนนซัพพลายเออร์

## 4. `product_master.csv`  *(Dim)*

| คอลัมน์ | ชนิด | คำอธิบาย | คีย์ |
|---|---|---|---|
| `product_id` | string | รหัสสินค้า | PK |
| `product_name` | string | ชื่อสินค้า | |
| `category` | string | หมวดหมู่ (Beverage, Dairy, …) | |
| `base_demand` | int | ดีมานด์ฐานต่อวัน *(พารามิเตอร์จำลอง)* | |
| `unit_price` | float | ราคาตั้งต้น (บาท) | |

## 5. `store_master.csv`  *(Dim)*

| คอลัมน์ | ชนิด | คำอธิบาย | คีย์ |
|---|---|---|---|
| `store_id` | string | รหัสสาขา | PK |
| `store_name` | string | ชื่อสาขา | |
| `store_type` | string | ประเภททำเล | |
| `province` | string | จังหวัด | |

## 6. `promotion_master.csv`  *(Dim)*

| คอลัมน์ | ชนิด | คำอธิบาย | คีย์ |
|---|---|---|---|
| `promotion_id` | string | รหัสโปรโมชั่น | PK |
| `promotion_name` | string | ชื่อโปร | |
| `lift_factor` | float | ตัวคูณยอดขายช่วงโปร (เช่น 1.8 = +80%) | |
| `start_day` | int | วันเริ่ม (offset จากวันแรกของชุดข้อมูล) | |
| `duration` | int | จำนวนวันที่จัดโปร | |

---

### ความสัมพันธ์ (ER overview)

```
product_master (PK product_id) ─┐
store_master   (PK store_id)   ─┼─< sales_transaction (Fact)
promotion_master (PK promo_id) ─┘        │
                                         │
product_master ─┬─< inventory (Fact)     │ เชื่อมผ่าน product_id + store_id + date
store_master   ─┘                        │
                                         │
product_master ─┬─< purchase_order (Fact)
store_master   ─┘
```
