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
h2 { font-size: 14px; margin: 14px 0 3px; font-weight: bold; }
table { border-collapse: collapse; width: 100%; margin: 0 0 4px; }
th, td { padding: 3px 12px; font-size: 13px; line-height: 1.2; }
th { font-weight: bold; text-align: center; }
th:first-child, td:first-child { text-align: left; white-space: nowrap; }
td { text-align: center; }
table { border-top: 1.5px solid #000; border-bottom: 1.5px solid #000; }
thead tr.numrow th { border-bottom: 1px solid #000; }
th.depvar { border-bottom: 1px solid #000; font-weight: bold; }
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
    thead = "<thead>"
    gh = panel.get("group_header")
    if gh:
        thead += (f'<tr class="grouphdr"><th>{_html.escape(gh["label"])}</th>'
                  f'<th class="depvar" colspan="{len(cols)}">{_html.escape(gh["value"])}</th></tr>')
    thead += ('<tr class="numrow"><th>Variables</th>'
              + "".join(f'<th>{_html.escape(c["idx"])}</th>' for c in cols)
              + "</tr></thead><tbody>")
    out.append(thead)
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
def _clear_table_borders(table):
    """Remove all table borders (incl. inside vertical/horizontal) so only the
    booktabs horizontal rules we add explicitly are drawn — no cell grid."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tblPr = table._tbl.tblPr
    existing = tblPr.find(qn("w:tblBorders"))
    if existing is not None:
        tblPr.remove(existing)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "auto")
        borders.append(el)
    tblPr.append(borders)


def _set_cell_border(cell, *, top: bool = False, bottom: bool = False,
                     sz: int = 8):
    """Add a top/bottom single border to one docx table cell."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
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


def _set_row_border(row, *, top: bool = False, bottom: bool = False,
                    sz: int = 8):
    """Add top/bottom single borders to every cell in a docx table row."""
    for cell in row.cells:
        _set_cell_border(cell, top=top, bottom=bottom, sz=sz)


def _docx_cell(cell, text: str, *, bold: bool = False, center: bool = True,
               size: int = 10, color=None, sub: str = None, sup: str = None):
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    cell.text = ""
    # Tight cell paragraph — no extra spacing so two-row coef/(t) pairs stay compact.
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Times New Roman"
    if color is not None:
        run.font.color.rgb = RGBColor(*color)
    if sup:  # significance stars, raised
        ss = p.add_run(sup)
        ss.font.size = Pt(size)
        ss.font.name = "Times New Roman"
        ss.font.superscript = True
        ss.bold = bold
    if sub:  # lag indicator, lowered + small
        sr = p.add_run(" " + sub)
        sr.font.size = Pt(7)
        sr.font.name = "Times New Roman"
        sr.font.subscript = True
        sr.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


def _docx_panel(doc, panel: Dict[str, Any]):
    from docx.shared import Pt
    if panel["name"]:
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(8)
        h.paragraph_format.space_after = Pt(2)
        r = h.add_run(panel["name"])
        r.bold = True
        r.font.name = "Times New Roman"

    cols = panel["columns"]
    ncol = 1 + len(cols)
    gh = panel.get("group_header")
    header_rows = 2 if gh else 1
    body_rows = 2 * len(panel["rows"]) + len(panel["stat_rows"])
    table = doc.add_table(rows=header_rows + body_rows, cols=ncol)
    table.autofit = True
    _clear_table_borders(table)

    ridx = 0
    if gh:
        gr = table.rows[0]
        _docx_cell(gr.cells[0], gh["label"], bold=True, center=False)
        merged = gr.cells[1]
        for j in range(2, ncol):
            merged = merged.merge(gr.cells[j])
        _docx_cell(merged, gh["value"], bold=True, center=True)
        _set_row_border(gr, top=True, sz=10)      # full-width table top rule
        _set_cell_border(merged, bottom=True, sz=6)  # rule only under dep-var span
        ridx = 1

    # Column-number header
    hdr = table.rows[ridx]
    _docx_cell(hdr.cells[0], "Variables", bold=True, center=False)
    for j, c in enumerate(cols, 1):
        _docx_cell(hdr.cells[j], c["idx"], bold=True)
    _set_row_border(hdr, top=(not gh), bottom=True, sz=10 if not gh else 8)

    ri = ridx + 1
    for row in panel["rows"]:
        coef_r = table.rows[ri]
        _docx_cell(coef_r.cells[0], row["label"], center=False,
                   sub=(f"t−{row['lag']}" if row.get("lag") else None))
        for j, cell in enumerate(row["cells"], 1):
            if cell is None:
                _docx_cell(coef_r.cells[j], "")
            else:
                _docx_cell(coef_r.cells[j], f"{cell['coef']:.3f}",
                           sup=(cell["stars"] or None))
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
    npf = style.paragraph_format
    npf.space_before = Pt(0)
    npf.space_after = Pt(0)
    npf.line_spacing = 1.0

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

    note = doc.add_paragraph()
    note.paragraph_format.space_before = Pt(4)
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

        # Dependent-variable grouped header (journal layout)
        gh = panel.get("group_header")
        if gh:
            lc = ws.cell(r, 1, gh["label"])
            lc.font = Font(name=serif, bold=True)
            lc.alignment = left
            lc.border = Border(top=medium)
            vc = ws.cell(r, 2, gh["value"])
            vc.font = Font(name=serif, bold=True)
            vc.alignment = center
            if ncol > 2:
                ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=ncol)
            for j in range(2, ncol + 1):
                cc = ws.cell(r, j)
                cc.border = Border(top=medium, bottom=thin)
            ws.cell(r, 1).border = Border(top=medium)
            r += 1
            hdr_border = Border(bottom=thin)   # numbers row: no top rule (group has it)
        else:
            hdr_border = hdr_b

        # Column-number header
        ws.cell(r, 1, "Variables").font = Font(name=serif, bold=True)
        ws.cell(r, 1).alignment = left
        for j, c in enumerate(panel["columns"], 2):
            cell = ws.cell(r, j, c["idx"])
            cell.font = Font(name=serif, bold=True)
            cell.alignment = center
        for j in range(1, ncol + 1):
            ws.cell(r, j).border = hdr_border
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
        r += 1   # tight gap between stacked panels

    ws.cell(r, 1, spec["note"]).font = Font(name=serif, italic=True, size=8)

    ws.column_dimensions["A"].width = 30
    for j in range(2, max_cols + 1):
        ws.column_dimensions[get_column_letter(j)].width = 12

    wb.save(out_path)
    return out_path


# ──────────────────────────────────────────────────────────────────────────
# Correlation matrix (academic, heat-shaded by correlation value)
# ──────────────────────────────────────────────────────────────────────────
def _fmt_r(v) -> str:
    return "" if v is None else f"{v:.2f}"


def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _corr_fill(r, pos, neg):
    """Blend white→pos (r≥0) or white→neg (r<0) by |r|. Returns 6-hex (no #)."""
    if r is None:
        return None
    t = max(-1.0, min(1.0, float(r)))
    if t == 0:
        return None
    target = _hex_rgb(pos if t > 0 else neg)
    a = abs(t)
    rgb = tuple(255 + (target[i] - 255) * a for i in range(3))
    return "%02X%02X%02X" % tuple(int(round(x)) for x in rgb)


def _dark(fill_hex):
    if not fill_hex:
        return False
    r, g, b = _hex_rgb(fill_hex)
    return (0.299 * r + 0.587 * g + 0.114 * b) < 140


def render_correlation_html(spec: Dict[str, Any]) -> str:
    k = spec["n_vars"]
    pos, neg = spec["pos"], spec["neg"]
    css = """
    body { font-family: 'Times New Roman', Georgia, serif; color:#000; background:#fff;
           margin: 36px auto; padding: 0 20px; max-width: 1500px; }
    h1 { font-size: 17px; text-align:center; margin:0 0 6px; }
    .note { font-size: 12px; text-align: justify; margin: 0 0 14px; line-height:1.4; }
    table.corr { border-collapse: collapse; }
    table.corr th, table.corr td { border: 1px solid #000; padding: 2px 5px;
           font-size: 11px; text-align: center; min-width: 30px; }
    table.corr th { font-weight: bold; }
    .legend { margin: 10px 0; font-size: 12px; }
    .legend span.sw { display:inline-block; width:26px; height:12px; border:1px solid #000;
           vertical-align:middle; margin:0 4px 0 14px; }
    .varlist { font-size: 12px; line-height: 1.5; margin-top: 6px; }
    """
    head = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{_html.escape(spec['title'])}</title><style>{css}</style></head><body>")
    out = [head, f"<h1>{_html.escape(spec['title'])}</h1>",
           f"<p class='note'>{_html.escape(spec['note'])}</p>"]

    out.append("<table class='corr'><thead><tr><th>Var</th>"
               + "".join(f"<th>({j+1})</th>" for j in range(k)) + "</tr></thead><tbody>")
    for i, cells in enumerate(spec["rows"]):
        tds = [f"<th>({i+1})</th>"]
        for cell in cells:
            if cell is None:
                tds.append("<td></td>")
            else:
                fill = _corr_fill(cell["r"], pos, neg)
                style = []
                if fill:
                    style.append(f"background:#{fill}")
                    if _dark(fill):
                        style.append("color:#fff")
                if cell.get("bold"):
                    style.append("font-weight:bold")
                st = f" style='{';'.join(style)}'" if style else ""
                tds.append(f"<td{st}>{_fmt_r(cell['r'])}</td>")
        out.append("<tr>" + "".join(tds) + "</tr>")
    out.append("</tbody></table>")

    # legend: colour gradient endpoints
    out.append(
        "<div class='legend'>Correlation:"
        f"<span class='sw' style='background:#{_corr_fill(-1, pos, neg)}'></span>−1"
        "<span class='sw'></span>0"
        f"<span class='sw' style='background:#{_corr_fill(1, pos, neg)}'></span>+1"
        "&nbsp;&nbsp;·&nbsp;&nbsp;<b>bold</b> = significant at 5%</div>")

    vl = "; ".join(f"({n}) {_html.escape(name)}" for n, name in spec["var_list"])
    out.append(f"<p class='varlist'><b>Variable list:</b> {vl}.</p>")
    out.append("</body></html>")
    return "\n".join(out)


def _set_cell_shade(cell, fill_hex):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    tcPr.append(shd)


def _table_grid(table, sz: int = 4):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tblPr = table._tbl.tblPr
    ex = tblPr.find(qn("w:tblBorders"))
    if ex is not None:
        tblPr.remove(ex)
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), str(sz))
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "000000")
        b.append(e)
    tblPr.append(b)


def render_correlation_docx(spec: Dict[str, Any], out_path: Path) -> Path:
    from docx import Document
    from docx.shared import Pt, Inches
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(8)
    pf = style.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0

    # Landscape + narrow margins so a wide matrix fits.
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    sec.left_margin = sec.right_margin = Inches(0.5)
    sec.top_margin = sec.bottom_margin = Inches(0.6)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = title.add_run(spec["title"])
    tr.bold = True
    tr.font.size = Pt(12)
    tr.font.name = "Times New Roman"

    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    nr = note.add_run(spec["note"])
    nr.font.size = Pt(9)
    nr.font.name = "Times New Roman"
    doc.add_paragraph()

    pos, neg = spec["pos"], spec["neg"]
    k = spec["n_vars"]
    table = doc.add_table(rows=1 + k, cols=1 + k)
    _table_grid(table, sz=4)

    hdr = table.rows[0]
    _docx_cell(hdr.cells[0], "Var", bold=True, size=8)
    for j in range(k):
        _docx_cell(hdr.cells[j + 1], f"({j+1})", bold=True, size=8)
    for i, cells in enumerate(spec["rows"]):
        row = table.rows[i + 1]
        _docx_cell(row.cells[0], f"({i+1})", bold=True, size=8)
        for j, cell in enumerate(cells):
            c = row.cells[j + 1]
            fill = _corr_fill(cell["r"], pos, neg) if cell else None
            color = (0xFF, 0xFF, 0xFF) if (fill and _dark(fill)) else None
            _docx_cell(c, _fmt_r(cell["r"]) if cell else "", size=8,
                       bold=bool(cell and cell.get("bold")), color=color)
            if fill:
                _set_cell_shade(c, fill)

    # Legend: colour gradient endpoints
    doc.add_paragraph()
    leg_p = doc.add_paragraph()
    leg_p.add_run("Correlation: ").bold = True
    leg_tbl = doc.add_table(rows=1, cols=3)
    _table_grid(leg_tbl, sz=4)
    for ci, (label, rval) in enumerate([("−1", -1.0), ("0", 0.0), ("+1", 1.0)]):
        cell = leg_tbl.rows[0].cells[ci]
        fill = _corr_fill(rval, pos, neg)
        _docx_cell(cell, label, size=9,
                   color=((0xFF, 0xFF, 0xFF) if (fill and _dark(fill)) else None))
        if fill:
            _set_cell_shade(cell, fill)
    leg_p2 = doc.add_paragraph()
    leg_p2.add_run("Bold = significant at the 5% level (two-tailed).").italic = True

    # Variable list
    vp = doc.add_paragraph()
    vp.paragraph_format.space_before = Pt(6)
    vp.add_run("Variable list: ").bold = True
    vp.add_run("; ".join(f"({n}) {name}" for n, name in spec["var_list"]) + ".")

    doc.save(out_path)
    return out_path


# ──────────────────────────────────────────────────────────────────────────
# VIF table
# ──────────────────────────────────────────────────────────────────────────
_VIF_HEADERS = ["Variable", "VIF", "√VIF", "Tolerance"]


def render_vif_html(spec: Dict[str, Any]) -> str:
    css = """
    body { font-family:'Times New Roman',Georgia,serif; color:#000; background:#fff;
           margin:40px auto; padding:0 24px; max-width:640px; }
    h1 { font-size:16px; margin:0 0 2px; }
    .sub { font-size:13px; margin:0 0 14px; }
    table { border-collapse:collapse; }
    th,td { border:1px solid #000; padding:4px 14px; font-size:13px; text-align:left; }
    th { font-weight:bold; }
    .mean { font-size:13px; margin-top:8px; }
    """
    out = [f"<!doctype html><html><head><meta charset='utf-8'><title>{_html.escape(spec['title'])}</title>"
           f"<style>{css}</style></head><body>",
           f"<h1>{_html.escape(spec['title'])}</h1>",
           f"<p class='sub'>{_html.escape(spec['subtitle'])}</p>",
           "<table><thead><tr>"
           + "".join(f"<th>{_html.escape(h)}</th>" for h in _VIF_HEADERS)
           + "</tr></thead><tbody>"]
    for r in spec["rows"]:
        out.append(f"<tr><td>{_html.escape(r['name'])}</td><td>{r['vif']}</td>"
                   f"<td>{r['sqrt_vif']}</td><td>{r['tol']}</td></tr>")
    out.append("</tbody></table>")
    out.append(f"<p class='mean'>Mean VIF = {spec['mean_vif']}</p>")
    out.append("</body></html>")
    return "\n".join(out)


def render_vif_docx(spec: Dict[str, Any], out_path: Path) -> Path:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)
    npf = style.paragraph_format
    npf.space_before = Pt(0)
    npf.space_after = Pt(0)
    npf.line_spacing = 1.0

    h = doc.add_paragraph()
    hr = h.add_run(spec["title"])
    hr.bold = True
    hr.font.size = Pt(13)
    hr.font.name = "Times New Roman"
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(6)
    sp.add_run(spec["subtitle"]).font.size = Pt(11)

    rows = spec["rows"]
    table = doc.add_table(rows=1 + len(rows), cols=4)
    _table_grid(table, sz=4)
    for j, head in enumerate(_VIF_HEADERS):
        _docx_cell(table.rows[0].cells[j], head, bold=True, center=False, size=11)
    for i, r in enumerate(rows, 1):
        cells = table.rows[i].cells
        _docx_cell(cells[0], r["name"], center=False, size=11)
        _docx_cell(cells[1], r["vif"], center=False, size=11)
        _docx_cell(cells[2], r["sqrt_vif"], center=False, size=11)
        _docx_cell(cells[3], r["tol"], center=False, size=11)

    mp = doc.add_paragraph()
    mp.paragraph_format.space_before = Pt(4)
    mp.add_run(f"Mean VIF = {spec['mean_vif']}")

    doc.save(out_path)
    return out_path
