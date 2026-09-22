# สถาปัตยกรรมข้อมูล — EV Thailand × Grab / Bolt

เอกสารนี้แบ่งเป็น 4 ส่วน

1. ผลวิเคราะห์โครงสร้างโปรเจกปัจจุบัน
2. ปัญหาที่พบ (พร้อมหลักฐานจากข้อมูลจริง 117 รายการ)
3. สถาปัตยกรรมข้อมูลที่เสนอ
4. แผนย้าย (migration) แบบทีละขั้น ไม่ต้องรื้อทีเดียว

---

## 1. โครงสร้างปัจจุบัน

### 1.1 ไฟล์

| ไฟล์ | ขนาด | บทบาท |
|---|---|---|
| `ev_data.json` | 28 KB | **แหล่งข้อมูลเดียว** — 117 record × 16 ฟิลด์ (flat array) |
| `build.py` | 10 KB | ตัวสร้าง output ทั้ง 3 ชนิด |
| `search_template.html` | 11 KB | template หน้าค้นหา · placeholder `/*__DATA__*/` |
| `analysis_body.html` | 25 KB | template เอกสารวิเคราะห์ · placeholder `<!--EV_SECTION-->` |
| `README.md` | 4.8 KB | คู่มือ + นิยามฟิลด์ + กฎการจัดหมวด (เขียนเป็นร้อยแก้ว) |

### 1.2 กระแสข้อมูล (data flow) ปัจจุบัน

```
ev_data.json ──┬──> build_xlsx()  ──> outputs/EV-Grab-Bolt-Thailand.xlsx
               ├──> build_html()  ──> outputs/search.html      (template + str.replace)
               └──> build_pdf()   ──> outputs/analysis.pdf     (template + str.replace, ต้องมี weasyprint)
```

### 1.3 สคีมาปัจจุบัน (1 record)

```
brand, model, body, seats, status, note          ← คุณสมบัติรถ
gcar, gprem, gsuv, gvan, gexec                   ← ธง Grab   5 คอลัมน์
bbasic, bcomf, bxl, bprem, bgreen                ← ธง Bolt   5 คอลัมน์
```

ค่าธง: `y` = ยืนยัน · `i` = inference · `p` = รอตรวจสอบ · `-` = ไม่เข้าเกณฑ์

### 1.4 ผลรันจริง

```
$ python build.py
loaded 117 EV models
[xlsx] outputs/EV-Grab-Bolt-Thailand.xlsx     ✓
[html] outputs/search.html                    ✓
[pdf]  skipped: No module named 'weasyprint'  (ขาด dependency เท่านั้น ไม่ใช่บั๊ก)
```

### 1.5 สิ่งที่ออกแบบไว้ถูกแล้ว — ต้องรักษาไว้

- **Single source of truth + idempotent build** — แก้ที่เดียว รันใหม่ ได้ครบ 3 output นี่คือแกนที่ถูกต้อง สถาปัตยกรรมใหม่ต้องไม่ทำลายข้อนี้
- **แยก template ออกจากโค้ด** — งานนำเสนออยู่ในไฟล์ HTML ไม่ปนกับ logic
- **JSON แบน แก้ด้วยมือได้ และ diff ใน git ได้** — สำคัญมากสำหรับงานที่คนเป็นผู้ตรวจข้อมูล
- **มีการแยกระดับความเชื่อมั่นไว้แล้ว** (`y` / `i` / `p`) — แนวคิดถูก แต่ยังยุบรวมหลายมิติไว้ในตัวอักษรเดียว (ดูข้อ 2.4)

---

## 2. ปัญหาที่พบ

ทุกข้อด้านล่างตรวจจากข้อมูลจริงในไฟล์ ไม่ใช่การคาดเดา

### 2.1 เก็บ "ข้อมูลที่คำนวณได้" ไว้เป็น "ข้อมูลดิบ"

ตรวจสอบเงื่อนไขทั้ง 117 แถว ได้ผล **จริง 100%** ทุกข้อ

| ความสัมพันธ์ | ผล |
|---|---|
| `gcar == 'y'` ⟺ ตัวถังไม่ใช่กระบะ | จริงทุกแถว |
| `bbasic == 'i'` ⟺ `gcar == 'y'` | จริงทุกแถว |
| `bgreen == 'i'` ⟺ `gcar == 'y'` | จริงทุกแถว |
| `bgreen == bbasic` | จริงทุกแถว (คอลัมน์ซ้ำสมบูรณ์) |

แปลว่า 3 คอลัมน์นี้ = **351 ช่องที่ต้องดูแลด้วยมือ แต่ไม่ให้สารสนเทศเพิ่มเลย** ทุกช่องหาได้จาก `body` ช่องเดียว

ที่สำคัญกว่านั้น — กฎที่สร้างมันมีอยู่แล้วใน `README.md`

> BEV ทุกรุ่น 4 ประตู ≥4 ที่นั่ง อายุ ≤9 ปี → GrabCar + Bolt Basic/Green อัตโนมัติ

แต่**กฎอยู่ในร้อยแก้ว ไม่ได้อยู่ในโค้ด** คนจึงต้องเป็นผู้บังคับใช้กฎด้วยมือ 351 ครั้ง ซึ่งเป็นจุดที่ความผิดพลาดจะเข้ามา

### 2.2 คอลัมน์ตาย และ "ไม่เข้าเกณฑ์" กับ "ยังไม่เคยตรวจ" แยกจากกันไม่ได้

| คอลัมน์ | การกระจายค่า |
|---|---|
| `gvan` | `-` × 117 (**ตายสนิท**) |
| `bprem` | `-` × 116, `p` × 1 |

`gvan` น่าสนใจเป็นพิเศษ เพราะในข้อมูลมีรถ **6–7 ที่นั่ง 15 รุ่น** ในจำนวนนี้เป็น MPV 7 รุ่น (Denza D9, M6 EV, MIFA 9, Zeekr 009, Xpeng X9, AION i60/N60, Darion EV) ซึ่งเป็นกลุ่มเป้าหมายตรงตัวของ GrabVan แต่ทุกรุ่นถูกติดธง `-`

ปัญหาเชิงสคีมาคือ **`-` ตัวเดียวถูกใช้แทนสองความหมายที่ต่างกันโดยสิ้นเชิง**

- "ตรวจแล้ว ไม่ผ่านเกณฑ์" (เช่น กระบะ → GrabCar)
- "ยังไม่เคยตรวจ / ไม่มีข้อมูล" (เช่น MPV 7 ที่นั่ง → GrabVan)

เมื่อแยกไม่ได้ ก็ไม่มีทางรู้ว่างานตรวจสอบยังค้างอยู่ตรงไหน — และไม่มีทางตั้ง checklist ให้ใครไปตรวจต่อได้

### 2.3 ฟิลด์ `note` แบกข้อมูลที่มีโครงสร้าง

`note` เป็น free text แต่ในนั้นมีข้อมูลที่ควรเป็นฟิลด์จริง ปนอยู่ 3 ชนิด

**ก. ระดับชั้นของหมวด Grab Exec** — ข้อมูลระดับหมวดที่ค้นหา/กรอง/จัดกลุ่มไม่ได้เลย

| รุ่น | `gexec` | `note` |
|---|---|---|
| BYD Denza D9 | `y` | `Grab Exec Lite` |
| Zeekr 009 / 009 Grand | `y` | `Grab Exec Lite` |
| Mercedes EQE | `y` | `Grab Exec M` |
| BMW i5 | `y` | `Grab Exec M` |
| Xpeng X9 | `y` | `Grab Exec` |
| MG Maxus 9 / MIFA 9 | `y` | `Grab Premium+Exec` |

Exec **Lite** กับ Exec **M** เป็นคนละชั้นกัน แต่ทั้งคู่ถูกเก็บเป็นสตริงอิสระ ไม่มีใครสั่ง "แสดงเฉพาะรถที่เข้า Exec M" ได้

**ข. ข้อมูลเวลาที่ซ้ำกับ `status`** — `"คาดปี 2026"`, `"เปิดตัว ส.ค. 2026"`, `"Q3 2026"`, `"คาดปี 2027"`, `"เปิดตัว 2025-26"` ล้วนซ้ำกับฟิลด์ `status` และเกิดความขัดแย้งแล้วจริง 1 จุด

> **BYD Atto 2** — `status = "sale"` แต่ `note = "ใหม่ 2026"`

เมื่อข้อมูลชุดเดียวกันถูกเก็บสองที่ มันจะขัดกันเสมอ เป็นเรื่องของเวลา

**ค. สเปกรถ** — `"654 กม./ชาร์จ"`, `"800V"`, `"ประตูสไลด์"`, `"6 ที่นั่ง"` (ซ้ำกับ `seats`)

### 2.4 ธง `y` / `i` / `p` ยุบ 3 มิติไว้ในตัวอักษรเดียว

| ค่า | ผลการพิจารณา | ที่มาของข้อมูล | ความเชื่อมั่น |
|---|---|---|---|
| `y` | ผ่าน | Grab official list | สูง |
| `i` | ผ่าน | อนุมานจาก spec | กลาง |
| `p` | **ยังไม่รู้** | — | — |
| `-` | ไม่ผ่าน **หรือ** ไม่เคยตรวจ | — | — |

สามสิ่งนี้เป็นอิสระต่อกัน จึงควรเป็น 3 ฟิลด์ ตัวอย่างสภาวะที่ระบบปัจจุบันเขียนไม่ได้เลย

- "ผ่าน — แต่รู้จากการอนุมาน ไม่ใช่จาก list ทางการ" (ปัจจุบันบังคับให้ตอบว่า `i` ซึ่งผูกติดกับ Bolt เสมอ)
- "ไม่ผ่าน — และยืนยันแล้วจาก list ทางการ"

### 2.5 `body` เป็นคำศัพท์อิสระ ไม่มีชุดค่าควบคุม — ทั้งที่มันกำหนดสิทธิ์

มี 18 ค่า ปนไทย-อังกฤษ สำหรับสิ่งที่จริง ๆ มีราว 5 ประเภท

```
SUV(51) · Sedan(22) · Hatchback(9) · SUV เล็ก(8) · MPV(8) · SUV ใหญ่(3) · SUV/Crossover(3)
Sedan/GT(2) · Hatchback เล็ก(2) · Shooting Brake · Sedan/Wagon · MPV/SUV · SUV/Coupe
City car · Sedan/Fastback · Coupe/SUV · กระบะ EV · Hatchback/SUV
```

มี **8 วิธีสะกดคำว่า "SUV"** และขนาด (`เล็ก` / `ใหญ่`) ถูกยัดรวมในฟิลด์เดียวกับประเภท

ความเสี่ยงตรงนี้ไม่ใช่แค่เรื่องความสวยงาม — `body` เป็นตัวตัดสินสิทธิ์จริง (`build.py` เช็ก `gcar == "-"` เพื่อตัดกระบะ และหมวด G-SUV ก็อิงประเภทตัวถัง) **สะกดต่างจากเดิมหนึ่งครั้ง = สิทธิ์ผิดหนึ่งคัน โดยไม่มีอะไรเตือน**

และพบความไม่สอดคล้องแล้ว 2 จุด — `MG EP EV` (`Sedan/Wagon`) กับ `MG ES EV` (`Sedan`) ทั้งคู่ติดธง `gsuv` ทั้งที่ตัวถังไม่ใช่ SUV

### 2.6 ไม่มีมิติเวลาและที่มา (provenance) — จุดอ่อนที่หนักที่สุดสำหรับงานเชิงรายงาน

ทั้งโปรเจกมีวันที่อยู่ **จุดเดียว** คือประโยคใน README ว่า `ข้อมูล ณ กันยายน 2568` ระดับรายการ**ไม่มี**

- ไม่มี `checked_at` — ไม่รู้ว่าแต่ละแถวตรวจครั้งสุดท้ายเมื่อไหร่
- ไม่มี `source_url` ต่อข้อกล่าวอ้าง — README อ้างแหล่งรวม ๆ ไว้ท้ายไฟล์ แต่โยงกลับไปยังแถวไหนไม่ได้
- ไม่มีประวัติ — เมื่อ Grab อัปเดต list แล้ว `p` เปลี่ยนเป็น `y` ข้อมูลเดิมหายไปเฉย ๆ ไม่เหลือร่องรอย

เรื่องนี้กระทบหนักที่สุดกับแถว `p` (รอตรวจสอบ) ซึ่งมีถึง **38 แถวใน `gsuv`** — คือแถวที่ตามนิยามแล้ว *ต้องกลับมาตรวจซ้ำ* แต่กลับไม่มีบันทึกว่าตรวจครั้งล่าสุดเมื่อไร ใครตรวจ และดูจากหน้าไหน

เอกสารนี้ถูกสร้างเพื่อใช้ประกอบการตัดสินใจ **ข้อกล่าวอ้างที่ไม่มีแหล่งอ้างอิงพร้อมวันที่กำกับ คือข้อกล่าวอ้างที่ป้องกันตัวเองไม่ได้**

### 2.7 ไม่มีการตรวจความถูกต้องของข้อมูล — ผิดแล้วเงียบ

ไม่มีอะไรบังคับว่า ธง ∈ {y,i,p,-}, `seats` > 0, `status` ∈ enum, หรือคีย์ครบ

พิมพ์ผิดเป็น `"yy"` จะเกิดอะไรขึ้น

| ปลายทาง | โค้ด | ผลลัพธ์ |
|---|---|---|
| xlsx | `{"y":..,"i":..,"p":..,"-":..}.get(v,"000000")` | ตัวอักษรสีดำ กลืนกับข้อความปกติ |
| html | `v==='y'?'y':v==='i'?'i':'p'` | ตกลงมาเป็น pill สีแดง "รอตรวจสอบ" |
| pdf | เงื่อนไขไม่ตรง | ตกจากตาราง |

**ทั้งสาม output ผิดคนละแบบ ไม่มีอันไหนแจ้งเตือน** และถ้าคีย์หาย `KeyError` จะล้มทั้งบิลด์กลางทาง หลังไฟล์แรกเขียนไปแล้ว

### 2.8 ธงเป็น "คอลัมน์" ทำให้ต้องแก้หลายที่

การเพิ่มหมวดใหม่ 1 หมวด (เช่น GrabBike / Bolt Pet / Grab Lady ที่ README เอ่ยถึงแต่ไม่มีคอลัมน์) ต้องแก้ **5 จุด**

1. `ev_data.json` — เพิ่มคีย์ให้ครบทั้ง 117 แถว
2. `build.py` → `grab_cats()` / `bolt_cats()`
3. `build.py` → `headers` (list หัวตาราง xlsx)
4. `build.py` → `vals` (ลำดับค่าต้องตรงกับ `headers` เป๊ะ ๆ ด้วยมือ)
5. `search_template.html` → `grabCats` / `boltCats`

โครงสร้างแบบตารางกว้าง (wide) ผูกจำนวนหมวดไว้กับโค้ดทุกชั้น รูปแบบยาว (long) จะทำให้เพิ่มหมวดใหม่ = เพิ่มแถวในไฟล์ reference ไฟล์เดียว

### 2.9 ช่องโหว่การฉีดโค้ดในไฟล์ที่ generate ออกมา

**ก. HTML injection** — `search_template.html` แทรกค่าผ่าน `innerHTML` โดยไม่ escape

```js
<div class="model">${e.model}</div>
<div class="note${warn}">${e.note}</div>
```

วันนี้ข้อมูลคัดด้วยมือ ความเสี่ยงต่ำ แต่แผนใน README เองระบุว่า

> ดึง Grab model list อัตโนมัติเพื่อ sync ธง `p → y`

**วันที่ข้อมูลมาจากการ scrape ช่องนี้กลายเป็นช่องโหว่ใช้งานได้ทันที** — และ `build.py` ก็ใช้ `%`-format ยัดค่าลง HTML ของ PDF แบบเดียวกัน

**ข. `</script>` breakout** — `build_html()` ใช้

```python
tpl.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False))
```

`json.dumps` **ไม่ escape** `<` `>` `/` ถ้าข้อมูลมีสตริง `</script>` เมื่อไหร่ หน้าเว็บพังทันที · แก้ด้วย `.replace("<", "\\u003c")` หรือใช้ `<script type="application/json">` แยกบล็อก

**ค.** `str.replace()` แทนที่**ทุก**ตำแหน่ง ไม่ใช่ตำแหน่งแรก — ถ้า template มี placeholder ซ้ำจะแทรกข้อมูลซ้ำเงียบ ๆ · ใช้ `.replace(x, y, 1)`

### 2.10 อื่น ๆ

- **ไม่มีเทสต์ ไม่มี CI ไม่มีไฟล์ schema**
- `build.py:113` — `cell.fill.fgColor.rgb in (None, "00000000")` อ่าน fill ที่เพิ่ง set ในลูปเดียวกัน ทำงานได้แต่ผูกกับลำดับคำสั่ง แตกง่ายเมื่อมีคนมาแก้ทีหลัง
- `STMAP[e["status"]]` และ `stcls[e["status"]]` เข้าถึง dict ตรง ๆ — `status` ค่าใหม่ = `KeyError` ล้มทั้งบิลด์
- `model` ซ้ำข้าม brand (`ES` มี 2, `X` มี 2) — ยังไม่เป็นปัญหาเพราะไม่มีการ join แต่จะเป็นทันทีที่เพิ่มตารางที่สอง (ราคา / ระยะวิ่ง) จึงต้องมี ID ที่เสถียร

---

## 3. สถาปัตยกรรมข้อมูลที่เสนอ

### 3.1 หลักการ 5 ข้อ

1. **แยก "ข้อเท็จจริง" ออกจาก "กฎ" ออกจาก "การนำเสนอ"** — ข้อมูลดิบเก็บเฉพาะสิ่งที่คำนวณกลับไม่ได้
2. **เขียนกฎเป็นโค้ด ไม่ใช่ร้อยแก้ว** — กฎใน README กลายเป็น rules engine ที่รันได้และเทสต์ได้
3. **ทุกข้อกล่าวอ้างต้องมีที่มาและวันที่** — `source_url` + `checked_at` เป็นฟิลด์บังคับ ไม่ใช่ของแถม
4. **รูปแบบยาว (long) ไม่ใช่กว้าง (wide)** — 1 แถว = 1 ข้อกล่าวอ้าง เพิ่มหมวดใหม่ไม่ต้องแตะโค้ด
5. **ตรวจก่อนสร้าง (validate before build)** — ข้อมูลผิด ต้องล้มที่ขั้นตรวจ ไม่ใช่เล็ดลอดไปเป็นเซลล์สีดำใน Excel

### 3.2 ภาพรวม 5 ชั้น

```
┌─ L0  REFERENCE ─────────── เปลี่ยนน้อย — นิยามของโลก
│   platforms.yaml      Grab, Bolt · commission · source · as_of
│   categories.yaml     หมวด + เกณฑ์เชิงเครื่อง (seats_min, body_allowed, age_max)
│   body_types.yaml     enum มาตรฐาน + ตารางเทียบคำพ้อง (alias)
│
├─ L1  FACTS ─────────────── ข้อเท็จจริงของรถ — 1 แถว/รุ่น
│   vehicles.jsonl      vehicle_id, brand, model, body_type, size_class,
│                       seats, doors, launch, price_thb?, range_km?, battery_kwh?
│
├─ L2  CLAIMS ────────────── ข้อกล่าวอ้างสิทธิ์ (long) — 1 แถว/รถ×แพลตฟอร์ม×หมวด
│   eligibility.jsonl   เก็บเฉพาะที่ "คนไปตรวจมา" — ที่กฎคำนวณได้ ไม่ต้องเก็บ
│
├─ L3  RULES ─────────────── กฎ = โค้ด
│   rules.py            อนุมานสิทธิ์จาก L0 + L1
│   resolve.py          ลำดับความสำคัญเมื่อข้อมูลขัดกัน
│
└─ L4  RESOLVED ──────────── ผลลัพธ์ materialized — output ทั้งหมดอ่านจากที่นี่เท่านั้น
    resolved.jsonl      vehicle × platform × category × สถานะสุดท้าย + ที่มา + วันที่
```

**ประโยชน์หลัก** — output ทั้ง 3 ชนิด (xlsx / html / pdf) กลายเป็น *ตัวเรนเดอร์ใบ้* ไม่มี logic ของตัวเอง ทุกอย่างถูกตัดสินจบแล้วที่ L4 · วันนี้ logic กระจายอยู่ใน 3 ที่และตอบไม่ตรงกัน (ดูข้อ 2.7)

### 3.3 L0 — Reference

**`platforms.yaml`**

```yaml
- id: grab
  name_th: แกร็บ
  commission_pct: 25
  source_url: https://grabdriverth.com/
  as_of: 2025-09-15

- id: bolt
  name_th: โบลท์
  commission_pct: 15
  source_url: https://bolt.eu/th-th/support/
  as_of: 2025-09-15
```

**`categories.yaml`** — หัวใจอยู่ที่ `criteria` ซึ่งเป็น **เกณฑ์เชิงเครื่อง** ที่ rules engine อ่านไปใช้ได้จริง ไม่ใช่คำอธิบายให้คนอ่าน

```yaml
- id: grab.car
  platform: grab
  label_th: GrabCar
  criteria:
    powertrain: [bev, hev, phev, ice]
    seats_min: 4
    doors: 4
    age_max_years: 9
    body_type_exclude: [pickup]
  has_official_list: true
  list_url: https://grabdriverth.com/model-list/

- id: grab.exec
  platform: grab
  label_th: Grab Exec
  tiers: [lite, m]              # ← แก้ปัญหา 2.3(ก) โดยตรง
  has_official_list: true

- id: grab.van
  platform: grab
  label_th: GrabVan
  criteria:
    seats_min: 7
  has_official_list: true
  coverage_status: not_surveyed  # ← ประกาศตรง ๆ ว่ายังไม่ได้สำรวจ (ปัญหา 2.2)

- id: bolt.xl
  platform: bolt
  label_th: Bolt XL
  criteria:
    seats_min: 6
  has_official_list: false       # ← ที่มาของ "ทุกช่อง Bolt เป็น inference"
                                 #    เป็นคุณสมบัติของแพลตฟอร์ม ไม่ใช่ของรถแต่ละคัน

- id: bolt.green
  platform: bolt
  label_th: Bolt Green
  criteria:
    powertrain: [bev]
  has_official_list: false
```

สังเกตว่า `has_official_list: false` เก็บไว้ **ที่ระดับหมวด** ครั้งเดียว — แทนที่จะทำซ้ำ 117 ครั้งด้วยการเขียน `i` ลงทุกแถวเหมือนตอนนี้

**`body_types.yaml`** — แก้ปัญหา 2.5 แยก *ประเภท* ออกจาก *ขนาด* และรับคำพ้องที่มีอยู่แล้วทั้งหมด

```yaml
- id: suv
  label_th: เอสยูวี
  aliases: ["SUV", "SUV เล็ก", "SUV ใหญ่", "SUV/Crossover", "SUV/Coupe",
            "Coupe/SUV", "MPV/SUV", "Hatchback/SUV"]
- id: sedan
  aliases: ["Sedan", "Sedan/GT", "Sedan/Wagon", "Sedan/Fastback", "Shooting Brake"]
- id: hatchback
  aliases: ["Hatchback", "Hatchback เล็ก", "City car"]
- id: mpv
  aliases: ["MPV"]
- id: pickup
  aliases: ["กระบะ EV"]
  eligible_for_ridehailing: false   # ← กฎ "กระบะไม่รับ" ย้ายมาอยู่ที่นิยาม
                                    #    ไม่ใช่ hardcode ว่า gcar == "-"
```

ขนาดแยกเป็นฟิลด์ของตัวเองใน L1 (`size_class: compact | standard | large`) เพราะเป็นคนละมิติกับประเภทตัวถัง

### 3.4 L1 — Facts (คุณสมบัติรถ)

```jsonc
{
  "vehicle_id": "byd-denza-d9",        // slug เสถียร — แก้ปัญหา model ซ้ำ (ES, X)
  "brand": "BYD",
  "model": "Denza D9",
  "body_type": "mpv",                  // อ้าง enum ใน L0
  "size_class": "large",
  "seats": 7,
  "doors": 4,
  "powertrain": "bev",
  "launch": {
    "status": "on_sale",               // on_sale | announced | expected
    "year": 2024,
    "quarter": null
  },
  "specs": {                           // ← ที่อยู่ใหม่ของสเปกที่เคยอยู่ใน note (2.3 ค)
    "range_km": null,
    "battery_kwh": null,
    "architecture_v": null,
    "price_thb": null,
    "features": ["sliding_door"]
  },
  "sources": [
    { "url": "https://...", "checked_at": "2025-09-15", "field": "launch" }
  ]
}
```

หลัก — **ตารางนี้เก็บเฉพาะ "รถคันนี้เป็นอย่างไร" ไม่เก็บ "รถคันนี้ขับหมวดไหนได้"** เป็นคนละคำถาม จึงต้องคนละตาราง นี่คือสิ่งที่ปลดล็อกให้เพิ่มราคา/ระยะวิ่งเพื่อคำนวณ ROI (ข้อที่ README เขียนไว้ในแผนต่อยอด) โดยไม่ต้องแตะตารางสิทธิ์เลย

### 3.5 L2 — Claims (ข้อกล่าวอ้างสิทธิ์ · รูปแบบยาว)

**นี่คือการเปลี่ยนแปลงสำคัญที่สุด** จาก 10 คอลัมน์ → เป็นแถว

```jsonc
{
  "vehicle_id": "byd-denza-d9",
  "category_id": "grab.exec",
  "tier": "lite",                      // ← "Grab Exec Lite" จาก note กลายเป็นฟิลด์จริง

  "eligibility": "eligible",           // eligible | ineligible | unverified
  "basis":       "official_list",      // official_list | spec_inference
                                       //               | rule_derived | manual
  "confidence":  "high",               // high | medium | low

  "source_url":  "https://grabdriverth.com/model-list/",
  "checked_at":  "2025-09-15",
  "checked_by":  "james",
  "note": ""
}
```

**3 มิติที่เคยยุบอยู่ใน `y`/`i`/`p` ถูกแยกออกจากกันแล้ว** (แก้ปัญหา 2.4)

| เดิม | ใหม่ |
|---|---|
| `y` | `eligibility: eligible` · `basis: official_list` · `confidence: high` |
| `i` | `eligibility: eligible` · `basis: spec_inference` · `confidence: medium` |
| `p` | `eligibility: unverified` · `basis: null` |
| `-` (ตรวจแล้วไม่ผ่าน) | `eligibility: ineligible` · `basis: rule_derived` |
| `-` (ไม่เคยตรวจ) | **ไม่มีแถวเลย** — ความไม่รู้แสดงออกด้วยการไม่มีข้อมูล ไม่ใช่ด้วยขีด |

ข้อสุดท้ายคือกุญแจของปัญหา 2.2 — ตอนนี้ระบบตอบคำถาม *"หมวดไหนยังไม่เคยสำรวจ"* ได้แล้ว ทั้งที่เมื่อก่อนตอบไม่ได้ และสั่ง `report_coverage()` ให้พ่นรายการงานค้างออกมาเป็น checklist ได้ทันที

**ขนาดไฟล์** — ไม่บวมอย่างที่กลัว เพราะเก็บเฉพาะข้อกล่าวอ้างที่มีคนไปตรวจจริง (ราว 70 แถว: `y` 33 + `p` 38) ส่วน `gcar`/`bbasic`/`bgreen` 351 ช่องที่พิสูจน์แล้วว่าคำนวณได้ (ข้อ 2.1) **หายไปจากข้อมูลดิบทั้งหมด**

### 3.6 L3 — Rules engine

กฎใน README กลายเป็นโค้ดที่รันได้และเทสต์ได้

```python
# rules.py — กฎทุกข้อที่ README เคยเขียนเป็นร้อยแก้ว อยู่ที่นี่ที่เดียว

RULES = [
    Rule("R1", "BEV 4 ประตู ≥4 ที่นั่ง ไม่ใช่กระบะ → GrabCar",
         when=lambda v: v.powertrain == "bev" and v.doors == 4
                        and v.seats >= 4 and v.body_type != "pickup",
         then=("grab.car", "eligible")),

    Rule("R2", "เงื่อนไขเดียวกัน → Bolt Basic",  ..., then=("bolt.basic", "eligible")),
    Rule("R3", "BEV → Bolt Green",               ..., then=("bolt.green", "eligible")),
    Rule("R4", "≥6 ที่นั่ง → Bolt XL",           ..., then=("bolt.xl",    "eligible")),
    Rule("R5", "กระบะ → ทั้งสองแอปไม่รับ",        ..., then=("*",          "ineligible")),
]
```

**`resolve.py` — ลำดับความสำคัญเมื่อข้อมูลขัดกัน**

```
official_list  >  manual  >  spec_inference  >  rule_derived
```

ข้อเท็จจริงจาก list ทางการของ Grab **ชนะกฎที่เราอนุมานเองเสมอ** — จุดนี้สำคัญ เพราะแปลว่าถ้าวันหนึ่ง Grab ประกาศว่ารุ่นหนึ่ง *ไม่* รับ ทั้งที่กฎเราบอกว่าผ่าน ระบบจะยึดตาม Grab และ**บันทึกไว้ว่ากฎขัดกับความจริง** ซึ่งเป็นสัญญาณว่ากฎข้อนั้นต้องแก้

ปัจจุบันสถานการณ์นี้เขียนลงข้อมูลไม่ได้เลย

### 3.7 L4 — Resolved view

```jsonc
{
  "vehicle_id": "byd-denza-d9",
  "brand": "BYD", "model": "Denza D9",       // denormalize ไว้เพื่อให้ renderer ง่าย
  "platform": "grab",
  "category_id": "grab.exec",
  "tier": "lite",
  "eligibility": "eligible",
  "basis": "official_list",
  "confidence": "high",
  "source_url": "https://grabdriverth.com/model-list/",
  "checked_at": "2025-09-15",
  "staleness_days": 372,                     // ← คำนวณตอน build
  "is_stale": true                           // เกิน threshold (เช่น 90 วัน)
}
```

`staleness_days` / `is_stale` คือคำตอบของปัญหา 2.6 — ทุก output แสดงได้ทันทีว่าข้อมูลส่วนไหนเก่าเกินจะเชื่อ และ `build.py --check` สั่งให้ล้มได้ถ้าเกินเพดาน

### 3.8 Pipeline ใหม่

```
sources/  ──normalize──>  canonical/  ──validate──>  ✗ ล้มที่นี่ถ้าข้อมูลผิด
                                            │
                                            ├──derive(rules)──┐
                                            └──claims(L2)─────┴──resolve──> resolved/
                                                                               │
                        ┌──────────────────────┬────────────┬──────────────────┤
                        ▼                      ▼            ▼                  ▼
                   render_xlsx           render_html   render_pdf        export_csv
                                                                       (i2 / KML / BI)
```

คำสั่ง

```bash
python -m evbuild validate          # ตรวจอย่างเดียว ใช้ใน CI
python -m evbuild build             # ตรวจ + สร้างครบ
python -m evbuild build xlsx        # เฉพาะบางอย่าง (คงพฤติกรรมเดิมไว้)
python -m evbuild report coverage   # หมวดไหน/รุ่นไหนยังไม่ได้ตรวจ  ← ทำไม่ได้ในระบบเดิม
python -m evbuild report stale --days 90   # ข้อมูลเก่าเกินกำหนด    ← ทำไม่ได้ในระบบเดิม
```

### 3.9 การตรวจความถูกต้อง (แก้ปัญหา 2.7)

ใช้ JSON Schema หรือ pydantic บังคับตั้งแต่ขั้น validate

| ชนิด | ตัวอย่าง |
|---|---|
| **โครงสร้าง** | ฟิลด์บังคับครบ · enum ถูกต้อง · `seats` ∈ 2..9 · `doors` ∈ {2,4,5} |
| **การอ้างอิง** | `vehicle_id` ใน claims ต้องมีอยู่จริงใน vehicles · `category_id` ต้องมีใน L0 |
| **ตรรกะ** | ผ่าน Grab Premium แต่ไม่ผ่าน GrabCar = ขัดกัน · `tier` ใส่ได้เฉพาะหมวดที่ประกาศ `tiers` |
| **ที่มา** | `basis: official_list` **ต้องมี** `source_url` + `checked_at` |
| **ความสด** | `checked_at` เก่ากว่า N วัน → เตือน (หรือล้มถ้าสั่ง `--strict`) |

กฎ "`official_list` ต้องมี source" คือกฎที่แปลง "ควรจะบันทึกที่มานะ" ให้กลายเป็นสิ่งที่**ระบบบังคับ** — ซึ่งเป็นวิธีเดียวที่ provenance จะอยู่รอดในระยะยาว

### 3.10 ความปลอดภัย (แก้ปัญหา 2.9)

| ปัญหา | วิธีแก้ |
|---|---|
| `${e.model}` ผ่าน `innerHTML` | ใช้ `textContent` / `createElement` หรือ escape ทุกค่าก่อนต่อสตริง |
| `</script>` breakout | หลัง `json.dumps` ให้ `.replace("<", "\\u003c").replace(">", "\\u003e")` หรือย้ายข้อมูลไปไว้ใน `<script type="application/json">` แล้ว `JSON.parse(el.textContent)` |
| `str.replace` แทนที่ทุกตำแหน่ง | ใส่ count — `.replace(placeholder, value, 1)` |
| `%`-format ลง HTML ของ PDF | ใช้ Jinja2 ที่ autoescape เปิดอยู่ |

ถ้าจะทำตามแผน "ดึง Grab model list อัตโนมัติ" ใน README **ต้องแก้ 4 ข้อนี้ก่อน** ไม่ใช่หลัง

### 3.11 ตารางสรุป: ปัญหา → ทางแก้เชิงสถาปัตยกรรม

| # | ปัญหา | แก้ด้วย |
|---|---|---|
| 2.1 | 351 ช่องที่คำนวณได้ แต่กรอกมือ | L3 rules engine — ลบ `gcar`/`bbasic`/`bgreen` จากข้อมูลดิบ |
| 2.2 | `gvan` ตาย · แยก "ไม่ผ่าน" กับ "ไม่เคยตรวจ" ไม่ได้ | L2 — ไม่มีแถว = ไม่รู้ · `coverage_status` ที่ระดับหมวด |
| 2.3 | `note` แบก Exec tier / เวลา / สเปก | L2 `tier` · L1 `launch` · L1 `specs` |
| 2.4 | `y`/`i`/`p` ยุบ 3 มิติ | L2 — `eligibility` + `basis` + `confidence` |
| 2.5 | `body` 18 ค่า 8 วิธีสะกด "SUV" | L0 `body_types.yaml` + alias map + `size_class` แยก |
| 2.6 | ไม่มีเวลา ไม่มีที่มา | L2 `source_url` + `checked_at` บังคับ · L4 `staleness_days` |
| 2.7 | ไม่ validate ผิดแล้วเงียบ | ขั้น validate ล้มก่อนสร้างไฟล์ |
| 2.8 | เพิ่มหมวดต้องแก้ 5 ที่ | รูปแบบยาว — เพิ่มแถวใน `categories.yaml` ที่เดียว |
| 2.9 | HTML/JS injection | escape + Jinja2 autoescape |
| 2.10 | ไม่มีเทสต์/CI/schema | `validate` ใน CI + unit test ของ rules engine |

---

## 4. แผนย้าย (migration) — 4 ขั้น ไม่ต้องรื้อทีเดียว

ทุกขั้นจบในตัวเอง หยุดที่ขั้นไหนก็ยังใช้งานได้

### ขั้น 1 — เพิ่ม validation โดยไม่แตะรูปแบบข้อมูล  *(ครึ่งวัน · ความเสี่ยงต่ำสุด · คุ้มที่สุด)*

- เขียน JSON Schema ให้ `ev_data.json` **รูปแบบเดิมทั้งหมด**
- `python build.py` เรียก validate ก่อนเสมอ ผิด = ล้มทันทีพร้อมบอกแถวและฟิลด์
- แก้ช่องโหว่ 2.9 (escape + `replace(..., 1)`) ไปพร้อมกัน

**ได้ทันที** — ปัญหา 2.7 และ 2.9 จบ โดยไม่ต้องแปลงข้อมูลแม้แต่แถวเดียว

### ขั้น 2 — ทำข้อมูลให้เป็นมาตรฐาน ยังเป็น JSON แบนเหมือนเดิม  *(1 วัน)*

- เพิ่ม `vehicle_id` (slug) ทุกแถว
- แปลง `body` 18 ค่า → enum + `size_class` ด้วยสคริปต์ + ตรวจด้วยตา 117 แถว
- ดึง Exec tier ออกจาก `note` → ฟิลด์ `exec_tier`
- แก้ความขัดแย้ง BYD Atto 2 (`status` vs `note`) และตรวจธง `gsuv` ของ MG EP EV / MG ES EV
- เพิ่ม `checked_at` ระดับแถว (เริ่มต้นด้วย `2025-09-15` ทุกแถว แล้วค่อยอัปเดตเมื่อตรวจจริง)

**ได้** — ปัญหา 2.3, 2.5 จบ · 2.6 เริ่มเก็บข้อมูลแล้ว (สำคัญ: ยิ่งเริ่มช้า ยิ่งย้อนกลับไปเติมไม่ได้)

### ขั้น 3 — แยกชั้น L0–L4 เต็มรูปแบบ  *(2–3 วัน)*

- เขียนสคริปต์แปลง wide → long **อัตโนมัติ** จากไฟล์ขั้น 2 (ไม่ต้องกรอกมือ)
- ตั้ง rules engine — ลบ `gcar`/`bbasic`/`bgreen` ออกจากข้อมูลดิบ
- **ทดสอบการถดถอย (regression)**: output จาก pipeline ใหม่ต้องตรงกับของเดิม 117 แถวแบบ byte-for-byte ก่อนจะลบไฟล์เก่า — นี่คือด่านความปลอดภัยของขั้นนี้
- เติม `gvan` สำหรับ MPV 7 ที่นั่ง 7 รุ่น (ช่องว่างที่ค้นพบในข้อ 2.2)

**ได้** — ปัญหา 2.1, 2.2, 2.4, 2.8 จบครบ

### ขั้น 4 — ต่อยอดตามแผนใน README  *(เปิดทางแล้ว)*

เมื่อถึงขั้น 3 สามรายการในหัวข้อ "ไอเดียต่อยอด" ของ README จะทำได้ง่ายขึ้นมาก เพราะโครงสร้างรองรับไว้แล้ว

| แผนเดิมใน README | ทำได้เพราะ |
|---|---|
| เพิ่มราคา / ระยะวิ่ง → คำนวณ ROI คนขับ | `specs` อยู่ใน L1 แยกจากตารางสิทธิ์ · commission อยู่ใน L0 แล้ว |
| ดึง Grab model list อัตโนมัติ sync `p → y` | scraper เขียนลง L2 พร้อม `basis: official_list` + `checked_at` · precedence ใน L3 จัดการเองเมื่อขัดกับกฎ |
| export i2 CSV / KML | L4 เป็น long format อยู่แล้ว = รูปทรงเดียวกับตาราง entity-link ของ i2 (entity, entity, link type, attribute, source, date) · export = เปลี่ยนชื่อคอลัมน์ |

**ข้อสังเกตเรื่อง i2** — รูปแบบยาวใน L2/L4 ตรงกับโครงสร้างที่ i2 ใช้พอดี (หนึ่งแถว = หนึ่งความสัมพันธ์ พร้อมแหล่งที่มาและวันที่กำกับ) ตารางกว้างแบบปัจจุบันต้อง pivot ก่อนเสมอ เมื่อย้ายเป็น long แล้ว การ export จะเหลือแค่การ map ชื่อคอลัมน์

---

## 5. สิ่งที่ควรทำก่อนอื่น

ถ้ามีเวลาจำกัด เรียงตามผลตอบแทนต่อแรงที่ลง

1. **`checked_at` ระดับแถว** (ขั้น 2) — ย้อนหลังไม่ได้ ยิ่งเริ่มช้ายิ่งเสียของ ข้อมูลที่ไม่มีวันที่กำกับจะกลายเป็นข้อมูลที่ใช้อ้างอิงไม่ได้ในอีกหกเดือน
2. **Validation** (ขั้น 1) — ครึ่งวัน ปิดความเสี่ยง "ผิดแล้วเงียบ" ได้ทั้งหมด
3. **Escape HTML** (ขั้น 1) — ต้องทำก่อนแตะเรื่อง scraper เด็ดขาด
4. **body enum** (ขั้น 2) — เพราะ `body` เป็นตัวตัดสินสิทธิ์จริง สะกดพลาด = ผลลัพธ์ผิดเงียบ ๆ
5. **rules engine** (ขั้น 3) — งานใหญ่สุด แต่ลบภาระดูแลมือได้ 351 ช่อง

---

*วิเคราะห์จาก `ev-project` 117 รายการ · ข้อมูลในโปรเจกระบุ ณ กันยายน 2568*
