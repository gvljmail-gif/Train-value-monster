"""Build the import helper: rearranges an old caseload sheet into the tracker's columns.

Usage:
    python build_import_helper.py [output.xlsx] [--sample]

The old sheet is pasted (header row in row 1) onto 'Paste old sheet'. 'Converted' looks up
each old column by its header and lays the data out in the tracker's column order, ready to
paste as values into the Caseload tab. --sample fills a fictional old sheet for testing.
"""
import sys
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

import build_tracker as bt

ROWS = 400
DATA0 = 6                      # first data row on 'Converted'
PASTE = "'Paste old sheet'"
PASTE_RANGE = f"{PASTE}!$A$2:$BZ${ROWS + 1}"

# Tracker column -> start of the matching header in the old sheet (case-insensitive).
OLD_HEADERS = {
    "Name": "name", "NHS number": "nhs", "DOB": "dob", "Parity": "parity", "MLC/CLC": "mlc",
    "EDD": "edd", "Booking date": "booking", "Risks": "info",
    **{a: a for a in bt.APPTS},
}
AUTO = {c for c, _, g in bt.COLUMNS if g == bt.G_AUTO}
DATE_COLS = {"DOB", "EDD", *bt.CHAIN, *bt.DATE_ACTIONS}


def blocks():
    """Runs of consecutive tracker input columns: [(first_header, last_header), ...]."""
    runs, cur = [], []
    for h, _, _ in bt.COLUMNS:
        if h in AUTO:
            if cur:
                runs.append((cur[0], cur[-1]))
            cur = []
        else:
            cur.append(h)
    if cur:
        runs.append((cur[0], cur[-1]))
    return runs


def build(path, sample=False):
    wb = Workbook()
    font = Font(name=bt.FONT, size=10)
    runs = blocks()

    # ---- Start here -------------------------------------------------------
    st = wb.active
    st.title = "Start here"
    st.column_dimensions["A"].width = 3
    st.column_dimensions["B"].width = 105
    steps = [
        ("h", "Moving the old caseload sheet into the new tracker"),
        ("", "Everything happens inside Excel on your work computer. Patient data never needs to be "
             "emailed or uploaded anywhere."),
        ("s", "1. Paste the old sheet"),
        ("", "Open the old sheet, click the grey box top-left of the grid (selects everything) and Ctrl+C. "
             "Come back here, click cell A1 on the 'Paste old sheet' tab and Ctrl+V."),
        ("", "The column headings (Name, NHS number, edd, 16/40 ...) must end up in row 1. If the old sheet "
             "has a title above the headings, delete those rows on the 'Paste old sheet' tab."),
        ("s", "2. Check the matching"),
        ("", "On the 'Converted' tab, row 4 shows which old heading was found for each new column."),
        ("", "• 'NOT FOUND' (red): the old heading is spelled differently. Change the yellow cell in row 3 "
             "to the start of the old heading (capitals don't matter)."),
        ("", "• '(new column)': the old sheet didn't have it (GTT, Anti-D, IOL ...), so it's left blank."),
        ("", "• Orange cells in the data: a date column holds text Excel can't read as a date "
             "(e.g. '12/3' or 'seen'). Fix these in the tracker after pasting."),
        ("s", "3. Copy into the tracker (paste as VALUES)"),
    ]
    for i, (a, b) in enumerate(runs, start=1):
        rng = f"{bt.COL[a]}{DATA0}:{bt.COL[b]}{DATA0 + ROWS - 1}"
        steps.append(("", f"Block {i}: on 'Converted' select {rng} ({a} to {b}), Ctrl+C. In the tracker's "
                          f"Caseload tab click {bt.COL[a]}{bt.FIRST}, then Home > Paste > Paste Values "
                          f"(the clipboard icon with 123). Or right-click > Paste Options > Values."))
    steps += [
        ("", "Paste Values keeps the tracker's formatting and doesn't overwrite the grey calculated "
             "columns, which is why there are separate blocks."),
        ("s", "4. Tidy up in the tracker"),
        ("", "• Set Status for anyone who has delivered or left, so their rows grey out."),
        ("", "• Past appointment dates with nothing after them will show red. That's the tracker doing "
             "its job: check each one."),
        ("", "• Fill in the new columns (GTT, Anti-D, IOL, BP, Last updated by) as you go. The old info column goes into Risks."),
        ("s", "5. Delete this helper file"),
        ("", "It now holds a copy of patient data. Delete it once the tracker looks right."),
    ]
    for i, (kind, text) in enumerate(steps, start=2):
        c = st.cell(row=i, column=2, value=text)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        c.font = (Font(name=bt.FONT, size=14, bold=True, color="1F4E79") if kind == "h" else
                  Font(name=bt.FONT, size=11, bold=True, color="1F4E79") if kind == "s" else font)

    # ---- Paste old sheet --------------------------------------------------
    ps = wb.create_sheet("Paste old sheet")

    # ---- Converted --------------------------------------------------------
    cv = wb.create_sheet("Converted")
    block_of = {}
    for i, (a, b) in enumerate(runs, start=1):
        first, last = cv[f"{bt.COL[a]}1"].column, cv[f"{bt.COL[b]}1"].column
        for c in range(first, last + 1):
            block_of[c] = i
    for idx, (h, w, _) in enumerate(bt.COLUMNS, start=1):
        L = get_column_letter(idx)
        cv.column_dimensions[L].width = max(w, 12)
        skip = h in AUTO
        b1 = cv[f"{L}1"]
        b1.value = "calculated: skip" if skip else f"BLOCK {block_of[idx]}"
        b1.fill = bt.GREY if skip else bt.fill("DDEBF7" if block_of[idx] % 2 else "E2EFDA")
        b1.font = Font(name=bt.FONT, size=9, bold=True, color="595959")
        hdr = cv[f"{L}2"]
        hdr.value, hdr.fill = h, bt.HEAD_FILL
        hdr.font = Font(name=bt.FONT, size=10, bold=True, color="FFFFFF")
        hdr.alignment = Alignment(horizontal="center", wrap_text=True)
        if skip:
            for r in range(3, 6):
                cv[f"{L}{r}"].fill = bt.GREY
            continue
        look = cv[f"{L}3"]
        look.value, look.fill = OLD_HEADERS.get(h, ""), bt.INPUT_YELLOW
        look.font = Font(name=bt.FONT, size=9, color="0000FF")
        cv[f"{L}5"] = f'=IF({L}3="","",IFERROR(MATCH({L}3&"*",{PASTE}!$A$1:$BZ$1,0),""))'
        cv[f"{L}4"] = (f'=IF({L}3="","(new column)",IF(ISNUMBER({L}5),INDEX({PASTE}!$A$1:$BZ$1,{L}5),'
                       f'"NOT FOUND"))')
        cv[f"{L}4"].font = Font(name=bt.FONT, size=9, italic=True)
        cv[f"{L}5"].font = Font(name=bt.FONT, size=8, color="A6A6A6")
        get = f"INDEX({PASTE_RANGE},ROW()-{DATA0 - 1},{L}$5)"
        for r in range(DATA0, DATA0 + ROWS):
            cv[f"{L}{r}"] = f'=IF(ISNUMBER({L}$5),IF({get}="","",{get}),"")'
            cv[f"{L}{r}"].font = font
            if h in DATE_COLS:
                cv[f"{L}{r}"].number_format = bt.DATE_FMT
        if h in DATE_COLS:
            x = f"{L}{DATA0}"
            cv.conditional_formatting.add(
                f"{L}{DATA0}:{L}{DATA0 + ROWS - 1}",
                FormulaRule(formula=[f'AND(ISTEXT({x}),{x}<>"",{x}<>"DNA",{x}<>"N/A")'],
                            fill=bt.ORANGE, font=Font(color="833C0B")))
    last_col = get_column_letter(len(bt.COLUMNS))
    cv.conditional_formatting.add(f"A4:{last_col}4", FormulaRule(
        formula=['A4="NOT FOUND"'], fill=bt.RED, font=Font(color=bt.RED_TXT, bold=True)))
    cv.freeze_panes = f"B{DATA0}"
    cv.row_dimensions[2].height = 30

    if sample:
        add_sample(ps)
    wb.active = 0
    wb.save(path)


def add_sample(ps):
    """Fictional old sheet in the old column order, with messy headers and a text date."""
    t = date.today()
    headers = ["Name", "NHS number", "dob", "parity", "mlc/clc", "edd", "booking date",
               "16/40 ", "25/40 ", "28/40 ", "31/40 ", "34/40 ", "36/40 ", "38/40 ", "40/40 ", "info"]
    ps.append(headers)
    ps.append(["Test One", 9993982598, date(1995, 3, 14), "G1P0", "MLC", t + timedelta(days=70),
               t - timedelta(days=150), t - timedelta(days=100), t - timedelta(days=35), t + timedelta(days=5),
               None, None, None, None, None, "note one"])
    ps.append(["Test Two", "999 791 9076", date(1990, 7, 2), "G2P1", "CLC", t + timedelta(days=20),
               t - timedelta(days=180), t - timedelta(days=150), "N/A", "12/3", "DNA", None, None, None, None, ""])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    build(args[0] if args else "Import_Helper.xlsx", sample="--sample" in sys.argv)
