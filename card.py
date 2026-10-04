"""Render a single-store data card (PNG) from a Feishu bitable record."""
import html
from datetime import date
from pathlib import Path

CARD_WIDTH = 1000

STYLE = """
* { box-sizing: border-box; }
body { margin: 0; background: #eef1f5; }
.card { width: %dpx; background: #ffffff; padding: 30px 34px 26px; }
.header { border-bottom: 2px solid #3370ff; padding-bottom: 14px; margin-bottom: 6px; }
.store { font-size: 32px; font-weight: 700; color: #1f2329; line-height: 1.25; }
.meta { margin-top: 6px; color: #8f959e; font-size: 14px; }
table { width: 100%%; border-collapse: collapse; table-layout: fixed; }
td { width: 25%%; padding: 12px 14px 10px; border-bottom: 1px solid #eef0f3;
     vertical-align: top; }
.label { display: block; color: #8f959e; font-size: 13px; margin-bottom: 5px;
         white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.val { font-size: 20px; font-weight: 600; color: #1f2329; line-height: 1.2;
       word-break: break-all; }
.val.small { font-size: 16px; }
.good { color: #00875a; }
.bad { color: #d83931; }
.warn { color: #d9730d; }
.muted { color: #a3a8b0; font-weight: 400; }
""" % CARD_WIDTH


def fmt_value(key, v):
    if v is None or v == "":
        return "-", "muted", "small"
    if isinstance(v, bool):
        return ("是" if v else "否"), "", ""
    if isinstance(v, (int, float)):
        if key.endswith("率") or key.endswith("进度"):
            return f"{round(v * 100)}%", "", ""
        if isinstance(v, float) and abs(v - round(v)) < 1e-9:
            v = int(round(v))
        if isinstance(v, float):
            text = f"{v:.2f}".rstrip("0").rstrip(".")
        else:
            text = str(v)
        if abs(float(text)) >= 10000:
            text = f"{float(text):,.0f}"
        return text, "", ""
    text = str(v)
    cls = ""
    if key == "交易达标":
        if text == "达标":
            cls = "good"
        elif text == "不达标":
            cls = "bad"
    if text in ("暂无等级", "无", "N/A"):
        cls = "muted"
    size_cls = "small" if len(text) > 10 else ""
    return text, cls, size_cls


def build_html(store_name: str, values: dict, field_order: list, subtitle: str = None) -> str:
    if subtitle is None:
        subtitle = f"数据日期 {date.today():%Y/%m/%d}"
    cells = []
    for key in field_order:
        val, cls, size_cls = fmt_value(key, values.get(key))
        cells.append(
            f'<td><span class="label">{html.escape(key)}</span>'
            f'<span class="val {cls} {size_cls}">{html.escape(str(val))}</span></td>'
        )
    rows = []
    for i in range(0, len(cells), 4):
        rows.append("<tr>" + "".join(cells[i:i + 4]) + "</tr>")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{STYLE}</style></head>
<body><div class="card">
  <div class="header">
    <div class="store">{html.escape(store_name)}</div>
    <div class="meta">{html.escape(subtitle)}</div>
  </div>
  <table>{''.join(rows)}</table>
</div></body></html>"""


def render_png(html_text: str, out_path: Path) -> Path:
    from playwright.sync_api import sync_playwright

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(
            viewport={"width": CARD_WIDTH, "height": 800},
            device_scale_factor=2,
        )
        page.set_content(html_text, wait_until="load")
        page.wait_for_timeout(120)
        el = page.query_selector(".card")
        el.screenshot(path=str(out_path))
        browser.close()
    return out_path


def make_card(store_name: str, values: dict, field_order: list, out_path: Path,
              subtitle: str = None) -> Path:
    return render_png(build_html(store_name, values, field_order, subtitle), out_path)
