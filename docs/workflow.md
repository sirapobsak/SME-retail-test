# System Workflow & Architecture

ไดอะแกรมอธิบายการไหลของข้อมูลและตรรกะการตัดสินใจ (อ้างอิงสไลด์หน้า 4)
GitHub เรนเดอร์ Mermaid ด้านล่างให้อัตโนมัติ

## 1. ภาพรวมสถาปัตยกรรม (Data → Decision → Action)

```mermaid
flowchart LR
    subgraph SRC["แหล่งข้อมูล (เฟส 1: POS ในร้าน)"]
        POS[(Sales<br/>Transaction)]
        INV[(Inventory)]
        PO[(Purchase<br/>Order)]
    end

    subgraph DIM["Dimension Tables"]
        PM[Product Master]
        SM[Store Master]
        CM[Customer Master]
        PRM[Promotion Master]
    end

    subgraph DL["1 - Data Layer"]
        CLEAN[ทำความสะอาด +<br/>Data Quality Check<br/>Ghost Inv / Zero-Sales / FK]
    end

    subgraph AI["2 - Predictive AI"]
        FC[Demand Forecasting<br/>Moving Avg → ML]
        ROP[Recommended<br/>Reorder Qty<br/>+ Safety Stock]
    end

    subgraph ACT["Actionable Insight"]
        ALERT[/⚠ Reorder Alert<br/>+ ปุ่ม Approve/]
        PROMO[3 - Promotion Engine<br/>กระตุ้นยอดเมื่อของล็อตใหม่มาถึง]
    end

    POS & INV & PO --> CLEAN
    PM & SM & CM & PRM -. join .-> CLEAN
    CLEAN --> FC --> ROP --> ALERT
    ALERT --> PROMO
```

## 2. ตรรกะการตัดสินใจสั่งซื้อรายวัน (Daily Reorder Logic)

```mermaid
flowchart TD
    A[เริ่มรอบเช้า 06:00<br/>ต่อ สินค้า x สาขา] --> B[ดึงยอดขายย้อนหลัง 28-90 วัน]
    B --> C{qty=0 และ<br/>stockout_flag=1 ?}
    C -- ใช่ --> D[ทำเครื่องหมาย censored<br/>= ดีมานด์ที่หายไป]
    C -- ไม่ --> E[ใช้ยอดขายตามจริง]
    D --> F[พยากรณ์ดีมานด์/วัน<br/>Moving Average]
    E --> F
    F --> G[คำนวณ ROP =<br/>ดีมานด์ x LeadTime + SafetyStock]
    G --> H{stock_on_hand<br/>&le; ROP ?}
    H -- ใช่ --> I[สร้าง Reorder Alert<br/>+ ยอดสั่งแนะนำ]
    H -- ไม่ --> J[ข้าม - ยังไม่ต้องสั่ง]
    I --> K[ส่งเข้า Dashboard + Notify<br/>รออนุมัติ Approve]
```

## 3. การทำงานแบบ Phased Approach

| เฟส | ขอบเขตข้อมูล | โมเดล | เป้าหมาย |
|---|---|---|---|
| **Phase 1 (MVP)** | POS ในร้าน (sales, inventory, PO) | Moving Average + Safety Stock | พิสูจน์ว่าลด Stockout ได้ ต้นทุนต่ำ เหมาะ SME |
| **Phase 2 (Scale)** | + Store Traffic, Zone, สภาพอากาศ, ปฏิทินท้องถิ่น | ML (Prophet / LightGBM) + Promotion Lift | แม่นยำขึ้น + วัด Lost Sales ได้จริง |
