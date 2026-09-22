# Car-rider-thai

วิเคราะห์การคัดเกรดรถและหมวดบริการของแอปเรียกรถในไทย (Grab / Bolt) สำหรับรถยนต์ไฟฟ้า (BEV)
รถ **117 รุ่น** × หมวดบริการ **10 หมวด** สร้างเป็น Excel · หน้าค้นหา · เอกสาร PDF · CSV สำหรับ i2

---

## เริ่มใช้งาน

```bash
pip install -r requirements.txt
python -m evbuild build
```

ผลลัพธ์ออกที่ `outputs/`

| ไฟล์ | เนื้อหา |
|---|---|
| `EV-Grab-Bolt-Thailand.xlsx` | 3 ชีต — เมทริกซ์ · ข้อกล่าวอ้างพร้อมที่มา · งานค้าง |
| `search.html` | หน้าค้นหา ใช้ได้แบบ standalone ไม่ต้องมีเซิร์ฟเวอร์ |
| `analysis.pdf` | เอกสารวิเคราะห์ (ต้องมีฟอนต์ Sarabun / TH SarabunPSK) |
| `resolved.csv` | ข้อสรุปทุกแถว รูปแบบยาว |
| `i2-links.csv` | ตาราง entity-link สำหรับ i2 Analyst's Notebook |

---

## คำสั่ง

```bash
python -m evbuild validate                 # ตรวจข้อมูลอย่างเดียว
python -m evbuild build                    # ตรวจ + สร้างครบทุกไฟล์
python -m evbuild build xlsx html          # เลือกเฉพาะบางชนิด (xlsx html pdf csv)
python -m evbuild report coverage          # หมวด/รุ่นไหนยังไม่ได้ตรวจ
python -m evbuild report stale --days 90   # ข้อมูลเก่าเกินกำหนด
python -m evbuild report qa                # จุดที่ต้องให้คนตัดสิน
python -m unittest discover -s tests -t .  # เทสต์ทั้งหมด (59 ข้อ)
python tools/diff_legacy.py                # เทียบผลลัพธ์กับระบบเดิม 1,170 ช่อง
```

ตัวเลือกร่วม — `--as-of YYYY-MM-DD` (ประเมินความสดของข้อมูล ณ วันไหน) ·
`--days N` (เพดานอายุข้อมูล) · `--strict` (ถือว่าคำเตือนเป็นข้อผิดพลาด)

---

## โครงสร้าง

```
data/
├── reference/          L0  นิยามของโลก — แพลตฟอร์ม · หมวด + เกณฑ์ · ประเภทตัวถัง
├── vehicles.jsonl      L1  ข้อเท็จจริงของรถ (117 แถว)
└── eligibility.jsonl   L2  ข้อกล่าวอ้างสิทธิ์ (200 แถว) พร้อมที่มาและวันที่

evbuild/                L3  กฎ + การตัดสิน   L4  ผลสุดท้าย + ตัวเรนเดอร์
tools/                  แปลงข้อมูลเดิม · เทียบผลลัพธ์กับระบบเดิม
tests/                  59 เทสต์ (unittest ของ stdlib ไม่ต้องลงอะไรเพิ่ม)
templates/              หน้าค้นหา · เอกสารวิเคราะห์
ev-project/             ระบบเดิม เก็บไว้เป็นตัวเทียบผลการทดสอบ
docs/                   เอกสารสถาปัตยกรรม
```

**[docs/DATA-ARCHITECTURE.md](docs/DATA-ARCHITECTURE.md)** — ผลวิเคราะห์โครงสร้างเดิม
ปัญหาที่พบพร้อมหลักฐาน สถาปัตยกรรม 5 ชั้น และสิ่งที่ค้นพบระหว่างสร้าง

---

## แก้ข้อมูลยังไง

| ต้องการ | แก้ที่ |
|---|---|
| เพิ่ม/แก้รถ | `data/vehicles.jsonl` — 1 บรรทัด = 1 รุ่น |
| บันทึกว่ารุ่นนี้ขับหมวดนี้ได้ | `data/eligibility.jsonl` — 1 บรรทัด = 1 ข้อกล่าวอ้าง |
| เพิ่มหมวดบริการใหม่ | `data/reference/categories.yaml` — ที่เดียว ไม่ต้องแตะโค้ด |
| แก้เกณฑ์การจัดหมวด | `criteria` ใน `categories.yaml` — กฎเป็นข้อมูล ไม่ใช่โค้ด |
| เพิ่มคำเรียกตัวถังแบบใหม่ | `aliases` ใน `body_types.yaml` |

แก้เสร็จรัน `python -m evbuild validate` ก่อนเสมอ — ข้อมูลผิดจะล้มพร้อมชี้จุดที่ผิด
ไม่เล็ดลอดไปเป็นผลลัพธ์ที่ดูปกติแต่ผิด

### ตัวอย่างข้อกล่าวอ้างหนึ่งแถว

```json
{"vehicle_id": "byd-denza-d9", "category_id": "grab.exec", "tier": "lite",
 "eligibility": "eligible", "basis": "official_list", "confidence": "high",
 "source_url": "https://grabdriverth.com/", "checked_at": "2025-09-15",
 "checked_by": "james", "note": ""}
```

`eligibility` (ผลการพิจารณา) · `basis` (ที่มา) · `confidence` (ความเชื่อมั่น)
เป็นคนละมิติกัน จึงแยกเป็นคนละฟิลด์ · `basis: official_list` **บังคับ**
ให้มี `source_url` และ `checked_at`

---

## หลักการที่ระบบยึด

- **ไม่รู้ ≠ ไม่ผ่าน** — สองอย่างนี้แยกจากกันตลอดทั้งระบบ และรายงานแยกกัน
- **กฎอยู่ในไฟล์ข้อมูล ไม่ใช่ในโค้ด** — แก้เกณฑ์ = แก้ YAML
- **สิ่งที่คำนวณได้ ไม่เก็บเป็นข้อมูลดิบ** — GrabCar / Bolt Basic / Bolt Green
  มาจากกฎ ไม่ใช่การกรอกมือ 351 ช่อง
- **ทุกข้อกล่าวอ้างมีที่มาและวันที่** — ข้อมูลที่ไม่มีวันที่กำกับ คือข้อมูลที่อ้างอิงไม่ได้
- **ข้อเท็จจริงชนะกฎ แต่ความขัดแย้งถูกบันทึก** — กฎที่ขัดกับความจริงคือกฎที่ต้องแก้
- **ระบบชี้จุดให้ ไม่ตัดสินแทนคน** — ข้อมูลขัดกันจะถูกรายงาน ไม่ใช่เดาให้

---

## แหล่งข้อมูล

Grab — [grabdriverth.com](https://grabdriverth.com/) (model list · ค่าคอมมิชชัน 25%) ·
Bolt — [bolt.eu/th-th/support](https://bolt.eu/th-th/support/) (ข้อกำหนดยานพาหนะ · ค่าคอมมิชชัน 15%)

ข้อมูลชุดปัจจุบันลงวันที่ **2025-09-15** ทั้งหมด · `python -m evbuild report stale` บอกว่าส่วนไหนเก่าเกินเพดานแล้ว
