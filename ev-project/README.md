> ## ⚠️ ระบบนี้ถูกแทนที่แล้ว
>
> โฟลเดอร์นี้คือ **ระบบเดิม** เก็บไว้เป็น *ตัวเทียบผลการทดสอบ* (regression oracle)
> ของระบบใหม่ — `tests/test_regression.py` และ `tools/diff_legacy.py`
> อ่าน `ev_data.json` จากที่นี่เพื่อยืนยันว่าไม่มีข้อสรุปใดหายหรือเพี้ยน
>
> **ห้ามแก้ไฟล์ในโฟลเดอร์นี้** — แก้แล้วเทสต์การถดถอยจะไม่มีความหมาย
> ข้อมูลที่ใช้งานจริงอยู่ที่ `data/` · วิธีใช้อยู่ใน [README หลัก](../README.md)
> · เหตุผลที่ย้ายอยู่ใน [docs/DATA-ARCHITECTURE.md](../docs/DATA-ARCHITECTURE.md)

---

# EV Thailand × Grab / Bolt — Category Mapper

ระบบวิเคราะห์ว่ารถยนต์ไฟฟ้า (BEV) แต่ละรุ่นในไทย สมัครขับหมวดไหนได้บ้างของ Grab และ Bolt
สร้างผลลัพธ์ทั้งหมดจาก **ไฟล์ข้อมูลเดียว** (`ev_data.json`) — แก้ที่เดียว รันใหม่ อัปเดตครบทุก output

---

## โครงสร้างโปรเจกต์

```
ev-project/
├── ev_data.json           # ← แหล่งข้อมูลเดียว (117 รุ่น) แก้ที่นี่
├── build.py               # สคริปต์สร้างผลลัพธ์ทั้งหมด
├── search_template.html   # template หน้าค้นหา (มี placeholder /*__DATA__*/)
├── analysis_body.html     # template เอกสารวิเคราะห์ (มี <!--EV_SECTION-->)
├── README.md
└── outputs/               # ← ผลลัพธ์ถูกสร้างที่นี่
    ├── EV-Grab-Bolt-Thailand.xlsx
    ├── search.html
    └── analysis.pdf
```

---

## ติดตั้ง

```bash
pip install openpyxl weasyprint
```

PDF ต้องมีฟอนต์ **Sarabun** / **TH SarabunPSK** ในระบบ:

```bash
# Ubuntu/Debian
sudo apt install fonts-thai-tlwg   # หรือวาง Sarabun-Regular.ttf, Sarabun-Bold.ttf ใน ~/.fonts แล้ว fc-cache -f
```

---

## ใช้งาน

```bash
python build.py          # สร้างทั้งหมด (xlsx + search html + pdf)
python build.py xlsx     # เฉพาะ xlsx
python build.py html     # เฉพาะ search html
python build.py pdf      # เฉพาะ pdf
```

---

## อัปเดตข้อมูล

แก้ `ev_data.json` แล้วรัน `python build.py` ใหม่ · 1 รายการมีฟิลด์:

| ฟิลด์ | ความหมาย |
|---|---|
| `brand`, `model`, `body`, `seats` | ยี่ห้อ, รุ่น, ตัวถัง, จำนวนที่นั่ง |
| `status` | `sale` (ขายแล้ว 24–25) · `2026` · `2027` |
| `note` | หมายเหตุ (แสดงบน card / ตาราง) |
| **Grab:** `gcar` `gprem` `gsuv` `gvan` `gexec` | ธงหมวด Grab |
| **Bolt:** `bbasic` `bcomf` `bxl` `bprem` `bgreen` | ธงหมวด Bolt |

**ค่าของธง:**

| ค่า | ความหมาย | สี |
|---|---|---|
| `y` | ยืนยันจาก Grab official model list | เขียว |
| `i` | inference จาก Bolt spec (Bolt ไม่เปิด list ไทย) | เหลือง/ทอง |
| `p` | รอตรวจสอบ — รุ่นใหม่ยังไม่อยู่ใน Grab list | แดง |
| `-` | ไม่เข้าเกณฑ์ | เทา |

---

## Logic การจัดหมวด (สรุป)

- **BEV ทุกรุ่น** 4 ประตู ≥4 ที่นั่ง อายุ ≤9 ปี → `GrabCar` + `Bolt Basic/Green` อัตโนมัติ
- **รถกระบะ EV** (เช่น Riddara RD6) → ทั้ง 2 แอปไม่รับ (`gcar='-'`)
- **Grab Premium/SUV** — ยืนยัน (`y`) เฉพาะรุ่นใน grabdriverth.com · รุ่นใหม่ = `p`
- **Bolt** ทุกช่อง = `i` เพราะไม่เปิดเผย model list ของไทย
- **Bolt Comfort** มี list จริงแต่เห็นได้เฉพาะในแอปตอนเพิ่มรถ

---

## แหล่งข้อมูล

- Grab: grabdriverth.com (model list, ค่าคอมมิชชัน 25%)
- Bolt: bolt.eu/th-th/support (ข้อกำหนดยานพาหนะ, ค่าคอมมิชชัน 15%)
- รายชื่อ EV: car250.com, motorexpo.co.th, ev.iphonemod.net, autoinfo.co.th ฯลฯ
- ข้อมูล ณ กันยายน 2568 (2025)

---

## ไอเดียต่อยอด

- เพิ่มคอลัมน์ราคา / ระยะวิ่ง (range) ต่อรุ่น เพื่อคำนวณ ROI คนขับ
- เพิ่มตัวคำนวณรายได้: `รายได้สุทธิ = ค่าโดยสาร × (1 − commission) × งาน/วัน`
- ดึง Grab model list อัตโนมัติเพื่อ sync ธง `p → y`
- export เป็น i2 CSV / KML ถ้าต้องการ map เชิงพื้นที่ของ demand
