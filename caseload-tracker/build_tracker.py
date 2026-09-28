"""Build the antenatal caseload tracker workbook (macro-free .xlsx).

Usage:
    python build_tracker.py [output.xlsx] [--sample]

--sample fills a few fictional rows so the formulas and flags can be checked;
--demo fills a fictional caseload (dates relative to TODAY()) to show how it works.
The file handed over for real use is built without either.
"""
import sys
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

ROWS = 400                     # pre-formatted patient rows
HEADER_ROW = 4
FIRST = HEADER_ROW + 1
LAST = FIRST + ROWS - 1
FONT = "Arial"

# --- palette --------------------------------------------------------------
def fill(hex_):
    return PatternFill("solid", start_color=hex_, end_color=hex_)

RED, RED_TXT = fill("F8CBCB"), "9C0006"
AMBER, AMBER_TXT = fill("FFE699"), "7F6000"
GREEN, GREEN_TXT = fill("C6EFCE"), "006100"
GREY, GREY_TXT = fill("E7E6E6"), "595959"
COMPLETE = fill("D0CECE")                     # whole row once delivered / no longer active
PURPLE = fill("E4DFEC")
ORANGE = fill("F8CBAD")
INPUT_YELLOW = fill("FFF2CC")
AUTO_FILL = fill("F2F2F2")
HEAD_FILL = fill("1F4E79")

G_PAT, G_AUTO, G_APPT, G_ACT, G_NOTES = (
    "Patient", "Auto (don't type)", "Appointments: date booked, DNA or N/A", "Actions", "Notes & audit")
GROUP_FILLS = {G_PAT: fill("DDEBF7"), G_AUTO: fill("EDEDED"), G_APPT: fill("E2EFDA"),
               G_ACT: fill("FCE4D6"), G_NOTES: fill("FFF2CC")}

# --- columns ----------------------------------------------------------------
# (header, width, group), left to right
APPTS = ["16/40", "25/40", "28/40", "31/40", "34/40", "36/40", "38/40", "40/40"]
CHAIN = ["Booking date"] + APPTS                              # read in this order
DATE_ACTIONS = ["GTT booked", "Anti-D ordered", "BP fortnightly", "BP weekly"]  # date, then 'Done'
COLUMNS = [
    ("Name", 22, G_PAT), ("NHS number", 14, G_PAT), ("DOB", 11, G_PAT), ("Parity", 8, G_PAT),
    ("MLC/CLC", 9, G_PAT), ("EDD", 11, G_PAT), ("Status", 13, G_PAT),
    ("Gestation today", 10, G_AUTO), ("Due in 7 days", 9, G_AUTO), ("Next appt", 11, G_AUTO),
    ("Next appt due", 11, G_AUTO),
    ("Booking date", 11, G_APPT), ("16/40", 10, G_APPT), ("25/40", 10, G_APPT),
    ("GTT booked", 11, G_ACT), ("Anti-D ordered", 11, G_ACT),
    ("28/40", 10, G_APPT), ("31/40", 10, G_APPT), ("34/40", 10, G_APPT), ("36/40", 10, G_APPT),
    ("38/40", 10, G_APPT), ("40/40", 10, G_APPT),
    ("IOL booked", 9, G_ACT), ("BP fortnightly", 11, G_ACT), ("BP weekly", 11, G_ACT),
    ("Risks", 40, G_NOTES), ("Last updated by", 15, G_NOTES), ("Overdue", 9, G_AUTO),
]
COL = {h: get_column_letter(i + 1) for i, (h, _, _) in enumerate(COLUMNS)}
LAST_COL = get_column_letter(len(COLUMNS))
EDD, STATUS, NAME = COL["EDD"], COL["Status"], COL["Name"]
UPD_BY, NHS, BOOK = COL["Last updated by"], COL["NHS number"], COL["Booking date"]

STATUSES = ["Active", "Delivered", "Transferred out", "Care ended"]
DATE_FMT = "dd/mm/yyyy"


def active(r):
    """Row has a patient and is Active (blank status counts as Active)."""
    return f'AND(${NAME}{r}<>"",OR(${STATUS}{r}="",${STATUS}{r}="Active"))'


def entered(x):
    """An appointment cell holds a date or DNA (N/A and blank don't count)."""
    return f'OR(ISNUMBER({x}),{x}="DNA")'


def last_entry(r):
    """Latest date/DNA along Booking date..40/40 ("" if none). The appointment columns
    aren't contiguous (GTT and Anti-D sit between them), so this is a nested IF."""
    acc = '""'
    for c in CHAIN:
        x = f"${COL[c]}{r}"
        acc = f'IF({entered(x)},{x},{acc})'
    return acc


def build(path, sample=False, demo=False):
    wb = Workbook()
    ws = wb.active
    ws.title = "Caseload"
    base = Font(name=FONT, size=10)

    # ---- rows 1-2: title, summary, legend ---------------------------------
    ws["A1"] = "Antenatal Caseload Tracker"
    ws["A1"].font = Font(name=FONT, size=14, bold=True, color="1F4E79")
    rng = lambda c: f"${c}${FIRST}:${c}${LAST}"
    summary = [
        ("Today", "=TODAY()"),
        ("Active", f'=SUMPRODUCT(({rng(NAME)}<>"")*(({rng(STATUS)}="")+({rng(STATUS)}="Active")))'),
        ("Pts overdue", f'=COUNTIF({rng(COL["Overdue"])},">0")'),
        ("Pts due ≤7d", f'=COUNTIF({rng(COL["Due in 7 days"])},">0")'),
    ]
    for i, (label, formula) in enumerate(summary):
        c = get_column_letter(3 + i)  # C..F
        ws[f"{c}1"], ws[f"{c}2"] = label, formula
        ws[f"{c}1"].font = Font(name=FONT, size=8, color="595959")
        ws[f"{c}2"].font = Font(name=FONT, size=12, bold=True)
        ws[f"{c}1"].alignment = ws[f"{c}2"].alignment = Alignment(horizontal="center")
    ws["C2"].number_format = DATE_FMT
    ws["C2"].font = Font(name=FONT, size=10, bold=True)
    ws["E2"].font = Font(name=FONT, size=12, bold=True, color=RED_TXT)
    ws["F2"].font = Font(name=FONT, size=12, bold=True, color=AMBER_TXT)

    legend = [("Overdue / not confirmed", RED, RED_TXT), ("Due in next 7 days", AMBER, AMBER_TXT),
              ("Confirmed / done", GREEN, GREEN_TXT), ("N/A", GREY, GREY_TXT), ("Delivered / not active", COMPLETE, "808080"),
              ("NHS no. duplicate", PURPLE, "403151")]
    key_col = ws[f"{BOOK}1"].column
    ws.cell(row=1, column=key_col, value="Key:").font = Font(name=FONT, size=9, bold=True)
    for i, (label, f, t) in enumerate(legend):
        cell = ws.cell(row=2, column=key_col + i)
        cell.value, cell.fill = label, f
        cell.font = Font(name=FONT, size=8, color=t)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 26

    # ---- row 3: group bands, row 4: headers --------------------------------
    prev = None
    for i, (h, w, g) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
        band = ws.cell(row=3, column=i)
        band.fill = GROUP_FILLS[g]
        if g != prev:
            band.value = g
            band.font = Font(name=FONT, size=9, bold=True, color="404040")
        prev = g
        hc = ws.cell(row=HEADER_ROW, column=i, value=h)
        hc.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
        hc.fill = HEAD_FILL
        hc.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[HEADER_ROW].height = 30

    # ---- data rows: formats + auto formulas -------------------------------
    date_cols = [COL[c] for c in ["DOB", "EDD", "Next appt due"] + CHAIN + DATE_ACTIONS]
    auto_cols = [COL[c] for c in ("Gestation today", "Overdue", "Due in 7 days", "Next appt", "Next appt due")]
    for r in range(FIRST, LAST + 1):
        for i in range(1, len(COLUMNS) + 1):
            ws.cell(row=r, column=i).font = base
        for c in date_cols + [COL["IOL booked"]]:
            ws[f"{c}{r}"].number_format = DATE_FMT
            ws[f"{c}{r}"].alignment = Alignment(horizontal="center")
        ws[f"{NHS}{r}"].number_format = "@"
        for c in ("Risks",):
            ws[f"{COL[c]}{r}"].alignment = Alignment(wrap_text=True, vertical="top")
        for c in auto_cols:
            ws[f"{c}{r}"].fill = AUTO_FILL
            ws[f"{c}{r}"].alignment = Alignment(horizontal="center")

        act = active(r)
        chain = [f"${COL[c]}{r}" for c in CHAIN]
        acts = [f"${COL[c]}{r}" for c in DATE_ACTIONS]
        # A past appointment only counts as attended once something later has been entered
        # (the next date can only be booked at that visit). So if the latest entry is a past
        # date, it was either missed or the next one wasn't booked.
        last = last_entry(r)
        ws[f"{COL['Gestation today']}{r}"] = (
            f'=IF(OR(NOT({act}),${EDD}{r}=""),"",'
            f'INT((TODAY()-${EDD}{r}+280)/7)&"+"&MOD(TODAY()-${EDD}{r}+280,7))')
        passed_actions = "+".join(f"ISNUMBER({x})*({x}<TODAY())" for x in acts)
        ws[f"{COL['Overdue']}{r}"] = (
            f'=IF(NOT({act}),"",IF(OR({last}="DNA",AND(ISNUMBER({last}),{last}<TODAY())),1,0)'
            f'+{passed_actions})')
        soon = "+".join(f"ISNUMBER({x})*({x}>=TODAY())*({x}<=TODAY()+7)" for x in chain + acts)
        ws[f"{COL['Due in 7 days']}{r}"] = f'=IF(NOT({act}),"",{soon})'
        # earliest appointment date on or after today
        m = "MIN(" + ",".join(f"IF(AND(ISNUMBER({x}),{x}>=TODAY()),{x},99999)" for x in chain) + ")"
        ws[f"{COL['Next appt due']}{r}"] = f'=IF(NOT({act}),"",IF({m}=99999,"",{m}))'
        nd = f"${COL['Next appt due']}{r}"
        label = '""'
        for c, x in reversed(list(zip(CHAIN, chain))):
            name = "Booking" if c == "Booking date" else c
            label = f'IF({x}={nd},"{name}",{label})'
        ws[f"{COL['Next appt']}{r}"] = (
            f'=IF(NOT({act}),"",IF({nd}<>"",{label},'
            f'IF({last}="DNA","Rebook DNA",IF(ISNUMBER({last}),'
            f'IF(ISNUMBER(${COL["40/40"]}{r}),"Update status","Missed/not booked?"),""))))')

    ws.freeze_panes = f"B{FIRST}"

    table = Table(displayName="CaseloadTable", ref=f"A{HEADER_ROW}:{LAST_COL}{LAST}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    ws.add_table(table)

    # ---- conditional formatting (first matching rule wins) ----------------
    def cf(area, formula, f=None, color=None, bold=False, italic=False):
        ws.conditional_formatting.add(area, FormulaRule(
            formula=[formula], stopIfTrue=True, fill=f,
            font=Font(color=color, bold=bold, italic=italic) if (color or bold or italic) else None))

    r = FIRST
    act = active(r)
    col_area = lambda c: f"{COL[c]}{FIRST}:{COL[c]}{LAST}"
    # Delivered / transferred / care ended: grey out the whole row. Added first so it takes
    # priority over every other colour on the row.
    cf(f"A{r}:{LAST_COL}{LAST}", f'AND(${NAME}{r}<>"",${STATUS}{r}<>"",${STATUS}{r}<>"Active")',
       COMPLETE, "808080", italic=True)
    # Appointments: a past date is confirmed once anything later in the chain is entered.
    # 40/40 has nothing after it, so a past 40/40 stays red until Status changes.
    for i, name in enumerate(CHAIN):
        x = f"{COL[name]}{r}"
        later = [f"${COL[c]}{r}" for c in CHAIN[i + 1:]]
        confirmed = "OR(" + ",".join(entered(y) for y in later) + ")" if later else "FALSE"
        area = col_area(name)
        cf(area, f'{x}="N/A"', GREY, GREY_TXT)
        cf(area, f'AND({x}="DNA",{confirmed})', GREY, RED_TXT)          # DNA, since rebooked
        cf(area, f'AND({act},{x}="DNA")', RED, RED_TXT, bold=True)
        cf(area, f'AND({act},ISNUMBER({x}),{x}<TODAY(),NOT({confirmed}))', RED, RED_TXT, bold=True)
        cf(area, f'AND({act},ISNUMBER({x}),{x}>=TODAY(),{x}<=TODAY()+7)', AMBER, AMBER_TXT, bold=True)
        cf(area, f'AND(ISNUMBER({x}),{x}<TODAY())', GREEN, GREEN_TXT)

    for name in DATE_ACTIONS:
        x, area = f"{COL[name]}{r}", col_area(name)
        cf(area, f'{x}="N/A"', GREY, GREY_TXT)
        cf(area, f'AND({act},ISNUMBER({x}),{x}<TODAY())', RED, RED_TXT)
        cf(area, f'AND({act},ISNUMBER({x}),{x}>=TODAY(),{x}<=TODAY()+7)', AMBER, AMBER_TXT)
        cf(area, f'AND(ISTEXT({x}),{x}<>"")', GREEN, GREEN_TXT)
    iol = f"{COL['IOL booked']}{r}"
    cf(col_area("IOL booked"), f'{iol}="Yes"', GREEN, GREEN_TXT)

    ov, sn, nd, na = COL["Overdue"], COL["Due in 7 days"], COL["Next appt due"], COL["Next appt"]
    cf(f"{ov}{r}:{ov}{LAST}", f'AND(ISNUMBER({ov}{r}),{ov}{r}>0)', RED, RED_TXT, bold=True)
    cf(f"{sn}{r}:{sn}{LAST}", f'AND(ISNUMBER({sn}{r}),{sn}{r}>0)', AMBER, AMBER_TXT, bold=True)
    cf(f"{na}{r}:{na}{LAST}", f'OR({na}{r}="Missed/not booked?",{na}{r}="Rebook DNA",{na}{r}="Update status")',
       RED, RED_TXT, bold=True)
    cf(f"{nd}{r}:{nd}{LAST}", f'AND(ISNUMBER({nd}{r}),{nd}{r}<=TODAY()+7)', AMBER, AMBER_TXT, bold=True)
    cf(f"{EDD}{r}:{EDD}{LAST}", f'AND({act},ISNUMBER({EDD}{r}),{EDD}{r}<TODAY())', AMBER, AMBER_TXT, bold=True)

    nhs_area = f"{NHS}{r}:{NHS}{LAST}"
    cf(nhs_area, f'AND({NHS}{r}<>"",COUNTIF(${NHS}${FIRST}:${NHS}${LAST},{NHS}{r})>1)', PURPLE, "403151")


    # ---- data validation ---------------------------------------------------
    def dv(area, **kw):
        v = DataValidation(allow_blank=True, **kw)
        v.add(area)
        ws.add_data_validation(v)

    dv(col_area("MLC/CLC"), type="list", formula1='"MLC,CLC"')
    dv(col_area("IOL booked"), type="list", formula1='"Yes,No"')
    dv(col_area("Status"), type="list", formula1="StatusList",
       promptTitle="Status", prompt="Blank counts as Active. Anything else stops the flags for this patient.",
       showInputMessage=True)
    dv(col_area("Last updated by"), type="list", formula1="StaffList",
       promptTitle="Who updated this row?", prompt="Pick your name (names live on the Staff tab).",
       showInputMessage=True)
    for c in ("DOB", "EDD", "Booking date"):
        dv(col_area(c), type="date", operator="between", formula1="DATE(1900,1,1)",
           formula2="DATE(2100,12,31)", errorStyle="warning", showErrorMessage=True,
           errorTitle="Not a date", error="Enter a date like 14/03/2026.")
    for c in APPTS:
        x = f"{COL[c]}{FIRST}"
        dv(col_area(c), type="custom", formula1=f'OR({x}="",ISNUMBER({x}),{x}="DNA",{x}="N/A")',
           errorStyle="warning", showErrorMessage=True, errorTitle="Appointment",
           error="Expected a date, DNA or N/A.", showInputMessage=True,
           promptTitle="Appointment", prompt="Enter the date once it's booked (usually at the previous "
                                             "appointment). Adding it confirms the previous one happened. "
                                             "DNA if missed. N/A if not needed.")
    for c in DATE_ACTIONS:
        dv(col_area(c), type="custom", formula1="TRUE", showInputMessage=True,
           promptTitle="Action", prompt="Enter the date booked/due. Once complete, type Done (or e.g. "
                                        "'Done 12/3 SW'). N/A if not needed.")
        ws.data_validations.dataValidation[-1].showErrorMessage = False

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{HEADER_ROW}:{HEADER_ROW}"

    # ---- Log sheet --------------------------------------------------------
    log = wb.create_sheet("Log")
    log["A1"] = "Update log: one line per action taken, newest at the bottom"
    log["A1"].font = Font(name=FONT, size=12, bold=True, color="1F4E79")
    log_cols = [("Date", 12), ("Staff", 16), ("Patient name", 22), ("NHS number", 14), ("What was done / changed", 70)]
    for i, (h, w) in enumerate(log_cols, start=1):
        log.column_dimensions[get_column_letter(i)].width = w
        c = log.cell(row=3, column=i, value=h)
        c.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
        c.fill = HEAD_FILL
    for rr in range(4, 504):
        for i in range(1, 6):
            log.cell(row=rr, column=i).font = base
        log[f"A{rr}"].number_format = DATE_FMT
        log[f"D{rr}"].number_format = "@"
        log[f"E{rr}"].alignment = Alignment(wrap_text=True)
    lt = Table(displayName="UpdateLog", ref="A3:E503")
    lt.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    log.add_table(lt)
    for area, kw in (("A4:A503", dict(type="date", operator="greaterThan", formula1="DATE(2000,1,1)")),
                     ("B4:B503", dict(type="list", formula1="StaffList"))):
        v = DataValidation(allow_blank=True, **kw)
        v.add(area)
        log.add_data_validation(v)
    log.freeze_panes = "A4"

    # ---- Staff & lists ----------------------------------------------------
    st = wb.create_sheet("Staff")
    st["A1"] = "Staff names"
    st["C1"] = "Status options"
    for c in ("A1", "C1"):
        st[c].font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
        st[c].fill = HEAD_FILL
    st["E1"] = ("Type one name per row in column A with no gaps. They appear in the "
                "'Last updated by' and Log dropdowns automatically.")
    st["E1"].font = Font(name=FONT, size=9, italic=True, color="595959")
    st.column_dimensions["A"].width = 24
    st.column_dimensions["C"].width = 18
    for i in range(2, 102):
        st[f"A{i}"].fill = INPUT_YELLOW
        st[f"A{i}"].font = base
    for i, s_ in enumerate(STATUSES, start=2):
        st[f"C{i}"] = s_
        st[f"C{i}"].font = base
    wb.defined_names["StaffList"] = DefinedName(
        "StaffList", attr_text="OFFSET(Staff!$A$2,0,0,MAX(1,COUNTA(Staff!$A$2:$A$101)),1)")
    wb.defined_names["StatusList"] = DefinedName(
        "StatusList", attr_text=f"Staff!$C$2:$C${len(STATUSES) + 1}")

    # ---- How to use -------------------------------------------------------
    hw = wb.create_sheet("How to use")
    hw.column_dimensions["A"].width = 3
    hw.column_dimensions["B"].width = 110
    lines = [
        ("h", "How to use the caseload tracker"),
        ("", "Nothing here uses macros, so it works in Excel desktop, Excel Online and Teams, including "
             "with several people editing at once."),
        ("s", "Daily use"),
        ("", "1. Sort or filter the 'Overdue' (last column), 'Next appt' or 'Next appt due' column to see who "
             "needs something first. The counts along the top show the totals."),
        ("", "2. When you change a row, pick your name in 'Last updated by'."),
        ("", "3. For anything more than a date, add a line to the Log tab (date, name, patient, what you did)."),
        ("", "4. To see exactly what changed and when, use Review > Show Changes (see below)."),
        ("s", "What to type where"),
        ("", "• Patient columns (Name to Status): as now. EDD drives the gestation. "
             "Leave Status blank or set Active while pregnant. Setting Delivered, Transferred out or Care ended "
             "greys out the whole row to show it's complete, and stops its flags."),
        ("", "• Grey columns (Gestation, Due in 7 days, Next appt, Next appt due, Overdue) are calculated, "
             "so don't type in them."),
        ("", "• Booking date and appointments (16/40 to 40/40): enter each date when it's booked. 16/40 is "
             "added at booking, 25/40 at the 16/40 appointment, and so on. Empty future columns are fine."),
        ("", "  – An appointment only counts as attended once a later date has been entered, because the "
             "next date can only be booked at that appointment. So a past date turns green only when "
             "something is entered after it."),
        ("", "  – Red date: the appointment date has passed and nothing later has been entered. Either it was "
             "missed (type DNA over it) or the next appointment hasn't been booked yet (add it). "
             "'Next appt' shows 'Missed/not booked?'."),
        ("", "  – Amber: the appointment is in the next 7 days. Plain: booked, more than a week away. "
             "N/A slots are skipped (e.g. 25/40 or 31/40 for multips)."),
        ("", "  – DNA: red until a later date is entered. Either type the rebooked date over the DNA, or "
             "leave DNA in place and put the new date in the next column; the DNA then stays visible in grey."),
        ("", "  – 40/40 has nothing after it, so once it has passed it stays red ('Update status') until "
             "Status is changed, e.g. to Delivered."),
        ("", "• GTT booked, Anti-D ordered, BP fortnightly, BP weekly: enter the date it's booked or due. It turns amber "
             "within 7 days and red once the date has passed. When it's done, overwrite it with 'Done' "
             "(or 'Done 12/3 SW'), which turns it green. N/A turns it grey."),
        ("", "• IOL booked: Yes or No from the dropdown (Yes shows green)."),
        ("", "• Risks: free text."),
        ("", "• NHS number: purple means the same number appears twice."),
        ("", "• EDD turns amber if it has passed and the patient is still Active, as a reminder to update Status."),
        ("s", "Colour key"),
        ("red", "Red: appointment passed but not confirmed (nothing entered after it), DNA not yet rebooked, "
                "or an action date that has passed and isn't marked Done"),
        ("amber", "Amber: due in the next 7 days"),
        ("green", "Green: appointment confirmed (a later date has been entered), action Done, or IOL Yes"),
        ("grey", "Light grey: N/A"),
        ("complete", "Dark grey row: Delivered, Transferred out or Care ended (complete)"),
        ("s", "Example row (format only, fictional)"),
        ("", "Jane Example | 943 476 5919 | 02/05/1994 | G2P1 | MLC | 10/01/2027 | (Status blank) | "
             "Booking date: 18/06/2026 | 16/40: 11/08/2026 | 25/40: N/A | GTT booked: 14/10/2026 | "
             "Anti-D ordered: Done 20/09 | 28/40: 01/10/2026 | IOL booked: No | BP fortnightly: N/A | "
             "BP weekly: N/A | Risks: Previous PPH | "
             "Last updated by: (your name)"),
        ("s", "Seeing exactly who changed what"),
        ("", "If the file is stored on SharePoint, OneDrive or Teams (not a shared drive), Excel keeps a full "
             "audit trail automatically:"),
        ("", "• Review ▸ Show Changes lists every edit with who made it and when. Right-click a cell and choose "
             "Show Changes to see that cell's history."),
        ("", "• File ▸ Info ▸ Version History lets you open or restore any earlier version."),
        ("", "• @mentioning a colleague in a comment (Review ▸ New Comment) sends them an email."),
        ("", "'Last updated by' and the Log are the human-readable layer on top of that."),
        ("s", "Adding rows"),
        ("", f"The table is pre-formatted for {ROWS} patients. Don't insert, delete or reorder "
             "columns: the formulas and colours refer to them by position."),
        ("s", "Information governance"),
        ("", "This holds patient-identifiable data. Keep it in the approved team location with access limited "
             "to the team, and follow your trust's IG policy."),
    ]
    styles = {"red": (RED, RED_TXT), "amber": (AMBER, AMBER_TXT), "green": (GREEN, GREEN_TXT),
              "grey": (GREY, GREY_TXT), "complete": (COMPLETE, "808080")}
    for i, (kind, text) in enumerate(lines, start=2):
        c = hw.cell(row=i, column=2, value=text)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if kind == "h":
            c.font = Font(name=FONT, size=14, bold=True, color="1F4E79")
        elif kind == "s":
            c.font = Font(name=FONT, size=11, bold=True, color="1F4E79")
            hw.row_dimensions[i].height = 22
        elif kind in styles:
            c.fill, color = styles[kind]
            c.font = Font(name=FONT, size=10, color=color)
        else:
            c.font = Font(name=FONT, size=10)

    if sample:
        add_sample(ws)
    if demo:
        add_demo(wb)
    wb.save(path)


def add_sample(ws):
    """Fictional rows used only to test flags (never in the delivered file)."""
    t = date.today()
    d = lambda n: t + timedelta(days=n)
    rows = [
        # 16/40 passed, nothing after it -> 16/40 red, plus a passed GTT: overdue 2
        ("Test Unconfirmed", "9434765919", {"Booking date": d(-60), "16/40": d(-10), "GTT booked": d(-2)}),
        # 16/40 confirmed by 28/40 (25/40 N/A); 28/40 in 3 days; Anti-D in 4 days
        ("Test Upcoming", "9434765918", {"Booking date": d(-100), "16/40": d(-40), "25/40": "N/A",
                                         "28/40": d(3), "Anti-D ordered": d(4)}),
        ("Test Delivered", "943 476 5919", {"Status": "Delivered", "Booking date": d(-250),
                                            **{a: d(-200 + i * 20) for i, a in enumerate(APPTS)},
                                            "IOL booked": "Yes"}),
        # booking in 5 days only
        ("Test JustBooked", "4010232137", {"Booking date": d(5), "BP fortnightly": "N/A"}),
        # past booking, 16/40 not added -> booking red
        ("Test BookingOnly", "", {"Booking date": d(-3)}),
        # 25/40 DNA, nothing later -> DNA red, Rebook DNA
        ("Test DNA", "", {"Booking date": d(-100), "16/40": d(-50), "25/40": "DNA"}),
        # DNA left in place, rebooked in next column -> DNA grey, 28/40 plain (future)
        ("Test DNARebooked", "", {"Booking date": d(-100), "16/40": d(-50), "25/40": "DNA", "28/40": d(20)}),
        # 25/40 passed; only a GTT/Anti-D date after it -> 25/40 still red (actions don't confirm)
        ("Test ActionBetween", "", {"Booking date": d(-100), "16/40": d(-50), "25/40": d(-5),
                                    "GTT booked": d(10), "Anti-D ordered": "Done"}),
        # past 40/40 still Active -> 40/40 red, Update status
        ("Test Past40", "", {"Booking date": d(-250), **{a: d(-200 + i * 25) for i, a in enumerate(APPTS)}}),
    ]
    for i, (name, nhs, vals) in enumerate(rows):
        r = FIRST + i
        ws[f"{NAME}{r}"], ws[f"{EDD}{r}"] = name, d(84)
        if nhs:
            ws[f"{NHS}{r}"] = nhs
        for k, v in vals.items():
            ws[f"{COL[k]}{r}"] = v

# Fictional caseload. NHS numbers are in the 999 test range (not issued to real people).
# Each entry: name, NHS no., DOB, parity, MLC/CLC, weeks pregnant today, status,
# {column: value}. Appointment values: week number -> date at that gestation (+ jitter days),
# or a literal string (N/A, DNA). Other date values are days from today.
DEMO_STAFF = ["Sarah Jones", "Priya Kaur", "Emma Lawson", "Nadia Brooks"]
DEMO = [
    ("Amelia Hart", "9993982598", date(1995, 3, 14), "G1P0", "MLC", 30, "",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": ("wk", 25), "28/40": ("wk", 28),
      "31/40": ("wk", 31), "GTT booked": "Done 02/09", "Anti-D ordered": "N/A", "BP fortnightly": "N/A",
      "Risks": "None identified", "by": 0}),
    ("Bethany Clarke", "9997919076", date(1990, 7, 2), "G2P1", "MLC", 26, "",
     {"Booking date": ("wk", 9), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28),
      "GTT booked": 3, "Anti-D ordered": "N/A", "Risks": "Previous GDM",
      "by": 1}),
    ("Chloe Ahmed", "9994833782", date(1998, 11, 20), "G1P0", "CLC", 29, "",
     {"Booking date": ("wk", 11), "16/40": ("wk", 16), "25/40": ("wk", 25), "28/40": ("wk", 28),
      "BP weekly": 2,
      "GTT booked": -3, "Risks": "Raised BP at 25/40 - PET risk",
      "by": 2}),
    ("Daisy Okafor", "9998762324", date(1988, 1, 9), "G3P2", "CLC", 34, "",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28),
      "31/40": "N/A", "34/40": "DNA", "Anti-D ordered": "Done 20/08",
      "Risks": "Rh negative. Safeguarding",
      "by": 3}),
    ("Ella Morgan", "9998601290", date(1996, 5, 30), "G1P0", "MLC", 35, "",
     {"Booking date": ("wk", 9), "16/40": ("wk", 16), "25/40": ("wk", 25), "28/40": ("wk", 28),
      "31/40": ("wk", 31), "34/40": "DNA", "36/40": ("wk", 36), "GTT booked": "N/A",
      "BP fortnightly": 6,
      "Risks": "BMI 38", "by": 0}),
    ("Freya Wilson", "9990404798", date(1993, 9, 12), "G2P1", "MLC", 12, "",
     {"Booking date": ("wk", 10, -4), "Risks": "Previous LSCS", "by": 1}),
    ("Grace Patel", "9996669726", date(2000, 2, 25), "G1P0", "MLC", 9, "",
     {"Booking date": 4, "Risks": "Awaiting booking", "by": 2}),
    ("Hannah Lewis", "9995102730", date(1991, 12, 3), "G2P1", "CLC", 39, "",
     {"Booking date": ("wk", 8), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28), "31/40": "N/A",
      "34/40": ("wk", 34), "36/40": ("wk", 36), "38/40": ("wk", 38), "40/40": ("wk", 40),
      "IOL booked": "Yes", "Anti-D ordered": "N/A", "Risks": "Age 40+. IOL booked", "by": 3}),
    ("Isla Thompson", "9994646869", date(1994, 4, 18), "G1P0", "CLC", 41, "",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": ("wk", 25), "28/40": ("wk", 28),
      "31/40": ("wk", 31), "34/40": ("wk", 34), "36/40": ("wk", 36), "38/40": ("wk", 38),
      "40/40": ("wk", 40), "IOL booked": "No",
      "Risks": "Past 40/40 - check if delivered",
      "by": 0}),
    ("Jasmine Evans", "9999589693", date(1989, 8, 8), "G2P1", "MLC", 43, "Delivered",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28), "31/40": "N/A",
      "34/40": ("wk", 34), "36/40": ("wk", 36), "38/40": ("wk", 38), "IOL booked": "No",
      "Risks": "Delivered 39+2", "by": 2}),
    ("Katie Brown", "9993504921", date(1997, 6, 21), "G2P1", "MLC", 20, "",
     {"Booking date": ("wk", 9), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28),
      "Risks": "None identified", "by": 1}),
    ("Lucy Hughes", "9997919076", date(1999, 10, 5), "G1P0", "MLC", 23, "",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": ("wk", 25),
      "Risks": "NHS no. same as Bethany Clarke (shows purple)", "by": 3}),
]
DEMO_LOG = [
    (-30, 3, "Lucy Hughes", "9997919076", "16/40 seen. 25/40 booked."),
    (-9, 2, "Chloe Ahmed", "9994833782", "BP 148/95 at 25/40. Referred to obs clinic. Bloods requested."),
    (-6, 1, "Katie Brown", "9993504921", "16/40 seen, 28/40 booked (multip, no 25/40)."),
    (-5, 1, "Bethany Clarke", "9997919076", "GTT booked."),
    (-3, 0, "Ella Morgan", "9998601290", "DNA 34/40. Phoned, rebooked 36/40."),
    (-2, 3, "Daisy Okafor", "9998762324", "DNA 34/40. Left voicemail, letter sent."),
    (-1, 0, "Amelia Hart", "9993982598", "28/40 seen. 31/40 booked."),
    (-1, 3, "Hannah Lewis", "9995102730", "38/40 seen. IOL booked. 40/40 booked."),
    (0, 2, "Grace Patel", "9996669726", "New referral - booking appointment made."),
]


def add_demo(wb):
    """Fictional caseload whose dates are formulas off TODAY(), so the flags stay current."""
    ws, log, st = wb["Caseload"], wb["Log"], wb["Staff"]
    ws["A1"] = "Antenatal Caseload Tracker: DEMO (fictional patients)"
    ws["A1"].font = Font(name=FONT, size=14, bold=True, color="C00000")
    rel = lambda n: f"=TODAY(){n:+d}" if n else "=TODAY()"
    for i, name in enumerate(DEMO_STAFF, start=2):
        st[f"A{i}"] = name
    for i, (name, nhs, dob, parity, model, gest, status, vals) in enumerate(DEMO):
        r = FIRST + i
        ws[f"{NAME}{r}"], ws[f"{NHS}{r}"], ws[f"{COL['DOB']}{r}"] = name, nhs, dob
        ws[f"{COL['Parity']}{r}"], ws[f"{COL['MLC/CLC']}{r}"] = parity, model
        ws[f"{EDD}{r}"] = rel(280 - gest * 7)
        if status:
            ws[f"{STATUS}{r}"] = status
        for k, v in vals.items():
            if k == "by":
                ws[f"{UPD_BY}{r}"] = DEMO_STAFF[v]
            elif isinstance(v, tuple):          # ("wk", week, jitter)
                ws[f"{COL[k]}{r}"] = rel((v[1] - gest) * 7 + (v[2] if len(v) > 2 else 0))
            elif isinstance(v, int):
                ws[f"{COL[k]}{r}"] = rel(v)
            else:
                ws[f"{COL[k]}{r}"] = v
    for i, (days, who, name, nhs, what) in enumerate(DEMO_LOG):
        rr = 4 + i
        log[f"A{rr}"], log[f"B{rr}"], log[f"C{rr}"] = rel(days), DEMO_STAFF[who], name
        log[f"D{rr}"], log[f"E{rr}"] = nhs, what


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    build(args[0] if args else "Antenatal_Caseload_Tracker.xlsx",
          sample="--sample" in sys.argv, demo="--demo" in sys.argv)
