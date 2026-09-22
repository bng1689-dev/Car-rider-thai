"""ตัวเรนเดอร์ — อ่านจากชั้น L4 อย่างเดียว ไม่มี logic การตัดสินสิทธิ์เป็นของตัวเอง"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES = ROOT / "templates"
OUTPUTS = ROOT / "outputs"


def html_escape(value) -> str:
    """escape สำหรับฝั่ง Python — ใช้กับทุกค่าที่ต่อเข้า HTML ของ PDF

    ระบบเดิมใช้ %-format ยัดค่าลง HTML ตรง ๆ ทั้งชื่อรุ่นและหมายเหตุ
    """
    return (
        str("" if value is None else value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def json_for_script(payload) -> str:
    """ฝัง JSON ลงใน <script> อย่างปลอดภัย

    json.dumps ไม่ escape '<' '>' — ถ้าข้อมูลมีสตริง '</script>' เมื่อไหร่
    หน้าเว็บพังทันที และกลายเป็นช่องโหว่เมื่อข้อมูลมาจาก scraper
    """
    import json

    return (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def fill_template(template: str, replacements: dict[str, str]) -> str:
    """แทนที่ placeholder ทีละตัว ตัวละครั้งเดียว

    str.replace() แทนที่ 'ทุก' ตำแหน่ง — ถ้า template มี placeholder ซ้ำ
    ข้อมูลจะถูกแทรกซ้ำเงียบ ๆ
    """
    for placeholder, value in replacements.items():
        if placeholder not in template:
            raise ValueError(f"ไม่พบ placeholder {placeholder!r} ใน template")
        template = template.replace(placeholder, value, 1)
    return template
