"""Render a table spec (from core.tables) to HTML / Word / Excel.

Academic "booktabs" styling: black text on white, horizontal rules only
(top / under header / above summary stats / bottom), no fills, no vertical
lines. Coefficient on one line, the chosen statistic in parentheses below.
"""
import html as _html
from pathlib import Path
from typing import Dict, Any, List


def _fmt_coef(coef: float, stars: str) -> str:
    return f"{coef:.3f}{stars}"


def _fmt_stat(stat: float) -> str:
    return f"({stat:.2f})"


# ──────────────────────────────────────────────────────────────────────────
# HTML
# ──────────────────────────────────────────────────────────────────────────
_HTML_CSS = """
:root { color-scheme: light; }
body { font-family: 'Times New Roman', Georgia, serif; color: #000;
       background: #fff; max-width: 920px; margin: 48px auto; padding: 0 24px; }
h1 { font-size: 20px; margin: 0 0 2px; }
.subtitle { color: #333; font-size: 13px; margin: 0 0 24px; }
h2 { font-size: 15px; margin: 26px 0 6px; font-weight: bold; }
table { border-collapse: collapse; width: 100%; margin: 0 0 6px; }
th, td { padding: 4px 12px; font-size: 13px; line-height: 1.25; }
th { font-weight: bold; text-align: center; }
th:first-child, td:first-child { text-align: left; white-space: nowrap; }
td { text-align: center; }
table { border-top: 1.5px solid #000; border-bottom: 1.5px solid #000; }
thead th { border-bottom: 1px solid #000; }
tr.statsep td { border-top: 1px solid #000; }
tr.tstat td { color: #333; padding-top: 0; padding-bottom: 6px; }
.lag { font-size: 0.72em; color: #555; }
sup { font-size: 0.7em; }
.note { font-size: 11px; color: #333; margin-top: 8px; line-height: 1.4;
        max-width: 720px; }
"""


def _html_panel(panel: Dict[str, Any]) -> str:
    cols = panel["columns"]
    out = []
    if panel["name"]:
        out.append(f'<h2>{_html.escape(panel["name"])}</h2>')
    out.append("<table>")
    out.append("<thead><tr><th>Variables</th>"
               + "".join(f'<th>{_html.escape(c["idx"])}</th>' for c in cols)
               + "</tr></thead><tbody>")
    for row in panel["rows"]:
        coef_cells, stat_cells = [], []
        for cell in row["cells"]:
            if cell is None:
                coef_cells.append("<td></td>")
                stat_cells.append("<td></td>")
            else:
                stars = f'<sup>{cell["stars"]}</sup>' if cell["stars"] else ""
                coef_cells.append(f'<td>{cell["coef"]:.3f}{stars}</td>')
                stat_cells.append(f'<td>{_fmt_stat(cell["stat"])}</td>')
        lag_lbl = f'<sub class="lag">t&minus;{row["lag"]}</sub>' if row.get("lag") else ""
        out.append(f'<tr class="coef"><td>{_html.escape(row["label"])}{lag_lbl}</td>'
                   + "".join(coef_cells) + "</tr>")
        out.append('<tr class="tstat"><td></td>' + "".join(stat_cells) + "</tr>")
    for i, srow in enumerate(panel["stat_rows"]):
        cls = ' class="statsep"' if i == 0 else ""
        out.append(f"<tr{cls}><td>{_html.escape(srow['label'])}</td>"
                   + "".join(f"<td>{_html.escape(str(v))}</td>" for v in srow["values"])
                   + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def render_html(spec: Dict[str, Any]) -> str:
    body = [f'<h1>{_html.escape(spec["title"])}</h1>']
    if spec.get("subtitle"):
        body.append(f'<p class="subtitle">{_html.escape(spec["subtitle"])}</p>')
    for panel in spec["panels"]:
        body.append(_html_panel(panel))
    body.append(f'<p class="note">{_html.escape(spec["note"])}</p>')
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{_html.escape(spec['title'])}</title>"
            f"<style>{_HTML_CSS}</style></head><body>"
            + "\n".join(body) + "</body></html>")


# ──────────────────────────────────────────────────────────────────────────
# Word (.docx)
# ──────────────────────────────────────────────────────────────────────────
def _set_row_border(row, *, top: bool = False, bottom: bool = False,
                    sz: int = 8):
    """Add top/bottom single borders to every cell in a docx table row."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    for cell in row.cells:
        tcPr = cell._tc.get_or_add_tcPr()
        borders = tcPr.find(qn("w:tcBorders"))
        if borders is None:
            borders = OxmlElement("w:tcBorders")
            tcPr.append(borders)
        for edge, on in (("top", top), ("bottom", bottom)):
            if not on:
                continue
            el = borders.find(qn(f"w:{edge}"))
            if el is None:
                el = OxmlElement(f"w:{edge}")
                borders.append(el)
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(sz))
            el.set(qn("w:color"), "000000")


def _docx_cell(cell, text: str, *, bold: bool = False, center: bool = True,
               size: int = 10, color=None, sub: str = None):
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Times New Roman"
    if color is not None:
        run.font.color.rgb = RGBColor(*color)
    if sub:
        sr = p.add_run(" " + sub)
        sr.font.size = Pt(7)
        sr.font.name = "Times New Roman"
        sr.font.subscript = True
        sr.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


def _docx_panel(doc, panel: Dict[str, Any]):
    if panel["name"]:
        h = doc.add_paragraph()
        r = h.add_run(panel["name"])
        r.bold = True
        r.font.name = "Times New Roman"

    cols = panel["columns"]
    ncol = 1 + len(cols)
    body_rows = 2 * len(panel["rows"]) + len(panel["stat_rows"])
    table = doc.add_table(rows=1 + body_rows, cols=ncol)
    table.autofit = True

    # Header
    hdr = table.rows[0]
    _docx_cell(hdr.cells[0], "Variables", bold=True, center=False)
    for j, c in enumerate(cols, 1):
        _docx_cell(hdr.cells[j], c["idx"], bold=True)
    _set_row_border(hdr, top=True, bottom=True, sz=10)

    ri = 1
    for row in panel["rows"]:
        coef_r = table.rows[ri]
        _docx_cell(coef_r.cells[0], row["label"], center=False,
                   sub=(f"t−{row['lag']}" if row.get("lag") else None))
        for j, cell in enumerate(row["cells"], 1):
            txt = "" if cell is None else _fmt_coef(cell["coef"], cell["stars"])
            _docx_cell(coef_r.cells[j], txt)
        ri += 1
        stat_r = table.rows[ri]
        _docx_cell(stat_r.cells[0], "", center=False)
        for j, cell in enumerate(row["cells"], 1):
            txt = "" if cell is None else _fmt_stat(cell["stat"])
            _docx_cell(stat_r.cells[j], txt, color=(0x33, 0x33, 0x33))
        ri += 1

    for k, srow in enumerate(panel["stat_rows"]):
        r = table.rows[ri]
        _docx_cell(r.cells[0], srow["label"], center=False)
        for j, v in enumerate(srow["values"], 1):
            _docx_cell(r.cells[j], str(v))
        if k == 0:
            _set_row_border(r, top=True, sz=8)
        if k == len(panel["stat_rows"]) - 1:
            _set_row_border(r, bottom=True, sz=10)
        ri += 1


def render_docx(spec: Dict[str, Any], out_path: Path) -> Path:
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(10)

    title = doc.add_paragraph()
    tr = title.add_run(spec["title"])
    tr.bold = True
    tr.font.size = Pt(13)
    tr.font.name = "Times New Roman"
    if spec.get("subtitle"):
        sp = doc.add_paragraph()
        sr = sp.add_run(spec["subtitle"])
        sr.font.size = Pt(10)
        sr.font.name = "Times New Roman"

    for panel in spec["panels"]:
        _docx_panel(doc, panel)
        doc.add_paragraph()

    note = doc.add_paragraph()
    nr = note.add_run(spec["note"])
    nr.italic = True
    nr.font.size = Pt(8)
    nr.font.name = "Times New Roman"

    doc.save(out_path)
    return out_path


# ──────────────────────────────────────────────────────────────────────────
# Excel (.xlsx) — minimal academic styling
# ──────────────────────────────────────────────────────────────────────────
def render_xlsx(spec: Dict[str, Any], out_path: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    def _label_value(cell_ref, label, lag, font_name):
        """Set a variable label, with the lag as an inline subscript if present."""
        if not lag:
            cell_ref.value = label
            cell_ref.font = Font(name=font_name)
            return
        try:
            from openpyxl.cell.rich_text import CellRichText, TextBlock
            from openpyxl.cell.text import InlineFont
            cell_ref.value = CellRichText(
                TextBlock(InlineFont(rFont=font_name), label),
                TextBlock(InlineFont(rFont=font_name, sz=8, color="555555",
                                     vertAlign="subscript"), f" t-{lag}"),
            )
        except Exception:
            cell_ref.value = f"{label} (t-{lag})"
            cell_ref.font = Font(name=font_name)

    wb = Workbook()
    ws = wb.active
    ws.title = "Table"

    thin = Side(style="thin", color="000000")
    medium = Side(style="medium", color="000000")
    top_b = Border(top=medium)
    bot_b = Border(bottom=medium)
    hdr_b = Border(top=medium, bottom=thin)
    stat_top = Border(top=thin)

    serif = "Times New Roman"
    center = Alignment(horizontal="center")
    left = Alignment(horizontal="left")

    r = 1
    ws.cell(r, 1, spec["title"]).font = Font(name=serif, bold=True, size=13)
    r += 1
    if spec.get("subtitle"):
        ws.cell(r, 1, spec["subtitle"]).font = Font(name=serif, size=10)
        r += 1
    r += 1

    max_cols = 1
    for panel in spec["panels"]:
        ncol = 1 + len(panel["columns"])
        max_cols = max(max_cols, ncol)

        if panel["name"]:
            ws.cell(r, 1, panel["name"]).font = Font(name=serif, bold=True, size=11)
            r += 1

        # Header
        ws.cell(r, 1, "Variables").font = Font(name=serif, bold=True)
        ws.cell(r, 1).alignment = left
        for j, c in enumerate(panel["columns"], 2):
            cell = ws.cell(r, j, c["idx"])
            cell.font = Font(name=serif, bold=True)
            cell.alignment = center
        for j in range(1, ncol + 1):
            ws.cell(r, j).border = hdr_b
        r += 1

        for row in panel["rows"]:
            _label_value(ws.cell(r, 1), row["label"], row.get("lag"), serif)
            ws.cell(r, 1).alignment = left
            for j, cell in enumerate(row["cells"], 2):
                txt = "" if cell is None else _fmt_coef(cell["coef"], cell["stars"])
                c = ws.cell(r, j, txt)
                c.font = Font(name=serif)
                c.alignment = center
            r += 1
            # stat (t-stat) line
            for j, cell in enumerate(row["cells"], 2):
                txt = "" if cell is None else _fmt_stat(cell["stat"])
                c = ws.cell(r, j, txt)
                c.font = Font(name=serif, color="333333")
                c.alignment = center
            r += 1

        for k, srow in enumerate(panel["stat_rows"]):
            ws.cell(r, 1, srow["label"]).font = Font(name=serif)
            ws.cell(r, 1).alignment = left
            for j, v in enumerate(srow["values"], 2):
                c = ws.cell(r, j, str(v))
                c.font = Font(name=serif)
                c.alignment = center
            if k == 0:
                for j in range(1, ncol + 1):
                    ws.cell(r, j).border = stat_top
            if k == len(panel["stat_rows"]) - 1:
                for j in range(1, ncol + 1):
                    ws.cell(r, j).border = bot_b
            r += 1
        r += 2

    ws.cell(r, 1, spec["note"]).font = Font(name=serif, italic=True, size=8)

    ws.column_dimensions["A"].width = 30
    for j in range(2, max_cols + 1):
        ws.column_dimensions[get_column_letter(j)].width = 12

    wb.save(out_path)
    return out_path
