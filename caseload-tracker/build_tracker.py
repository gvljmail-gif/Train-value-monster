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
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
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
BLUE, BLUE_TXT = fill("BDD7EE"), "1F3864"
PURPLE = fill("E4DFEC")
ORANGE = fill("F8CBAD")
INPUT_YELLOW = fill("FFF2CC")
AUTO_FILL = fill("F2F2F2")
HEAD_FILL = fill("1F4E79")

GROUP_FILLS = {
    "Patient": fill("DDEBF7"),
    "Auto (don't type)": fill("EDEDED"),
    "Appointments: enter date booked, DNA or N/A": fill("E2EFDA"),
    "Actions: enter date booked/due, then 'Done'": fill("FCE4D6"),
    "Notes & audit": fill("FFF2CC"),
}

# --- columns ----------------------------------------------------------------
# (header, width, group)
APPTS = ["16/40", "25/40", "28/40", "31/40", "34/40", "36/40", "38/40", "40/40"]
ACTIONS = ["GTT booked", "Anti-D ordered", "BP fortnightly", "Bloods needed", "IOL booked"]
COLUMNS = (
    [("Name", 22, "Patient"), ("NHS number", 14, "Patient"), ("DOB", 11, "Patient"),
     ("Parity", 8, "Patient"), ("MLC/CLC", 9, "Patient"), ("EDD", 11, "Patient"),
     ("Status", 13, "Patient"),
     ("Gestation today", 10, "Auto (don't type)"), ("Overdue", 9, "Auto (don't type)"),
     ("Due in 7 days", 9, "Auto (don't type)"), ("Next appt", 9, "Auto (don't type)"),
     ("Next appt due", 11, "Auto (don't type)"),
     ("Booking date", 11, "Appointments: enter date booked, DNA or N/A")]
    + [(a, 10, "Appointments: enter date booked, DNA or N/A") for a in APPTS]
    + [(a, 11, "Actions: enter date booked/due, then 'Done'") for a in ACTIONS]
    + [("Info", 40, "Notes & audit"), ("Last updated by", 15, "Notes & audit"),
       ("Last updated on", 12, "Notes & audit")]
)
COL = {h: get_column_letter(i + 1) for i, (h, _, _) in enumerate(COLUMNS)}
LAST_COL = get_column_letter(len(COLUMNS))
A1, AN = COL[APPTS[0]], COL[APPTS[-1]]       # appointment block
BOOK = COL["Booking date"]                   # sits directly before 16/40
X1, XN = COL[ACTIONS[0]], COL[ACTIONS[-1]]   # action block
EDD, STATUS, NAME = COL["EDD"], COL["Status"], COL["Name"]
UPD_ON, UPD_BY, NHS = COL["Last updated on"], COL["Last updated by"], COL["NHS number"]

STATUSES = ["Active", "Delivered", "Transferred out", "Care ended"]
DATE_FMT = "dd/mm/yyyy"


def active(r):
    """Row has a patient and is Active (blank status counts as Active)."""
    return f'AND(${NAME}{r}<>"",OR(${STATUS}{r}="",${STATUS}{r}="Active"))'


def build(path, sample=False, demo=False):
    wb = Workbook()
    ws = wb.active
    ws.title = "Caseload"
    base = Font(name=FONT, size=10)

    # ---- row 1-2: title, controls, summary, legend ------------------------
    ws["A1"] = "Antenatal Caseload Tracker"
    ws["A1"].font = Font(name=FONT, size=14, bold=True, color="1F4E79")
    ws["A2"] = "Highlight updates since:"
    ws["A2"].font = Font(name=FONT, size=10, bold=True)
    ws["A2"].alignment = Alignment(horizontal="right")
    ws["B2"].fill = INPUT_YELLOW
    ws["B2"].number_format = DATE_FMT
    ws["B2"].font = Font(name=FONT, size=10, bold=True, color="0000FF")
    ws["B2"].border = Border(*(Side(style="thin", color="7F7F7F"),) * 4)
    ws["B2"].comment = Comment(
        "Type the date you last checked the sheet (Ctrl+; for today). Rows whose "
        "'Last updated on' is on or after it turn blue, and the count appears to the right.",
        "Tracker")
    ws["C1"], ws["C2"] = "Today", "=TODAY()"
    ws["C2"].number_format = DATE_FMT

    rng = lambda c: f"${c}${FIRST}:${c}${LAST}"
    summary = [
        ("Active", f'=SUMPRODUCT(({rng(NAME)}<>"")*(({rng(STATUS)}="")+({rng(STATUS)}="Active")))'),
        ("Pts overdue", f'=COUNTIF({rng(COL["Overdue"])},">0")'),
        ("Pts due ≤7d", f'=COUNTIF({rng(COL["Due in 7 days"])},">0")'),
        ("Updated since", f'=IF($B$2="","-",COUNTIF({rng(UPD_ON)},">="&$B$2))'),
    ]
    for i, (label, formula) in enumerate(summary):
        c = get_column_letter(5 + i)  # E..H
        ws[f"{c}1"], ws[f"{c}2"] = label, formula
    for c in "CDEFGH":
        ws[f"{c}1"].font = Font(name=FONT, size=8, color="595959")
        ws[f"{c}2"].font = Font(name=FONT, size=12, bold=True)
        ws[f"{c}1"].alignment = ws[f"{c}2"].alignment = Alignment(horizontal="center")
    ws["F2"].font = Font(name=FONT, size=12, bold=True, color=RED_TXT)
    ws["G2"].font = Font(name=FONT, size=12, bold=True, color=AMBER_TXT)
    ws["H2"].font = Font(name=FONT, size=12, bold=True, color=BLUE_TXT)

    legend = [("Overdue / not confirmed", RED, RED_TXT), ("Due in next 7 days", AMBER, AMBER_TXT),
              ("Confirmed / done", GREEN, GREEN_TXT), ("N/A or not active", GREY, GREY_TXT),
              ("Updated since your date", BLUE, BLUE_TXT), ("NHS no. invalid", ORANGE, "833C0B"),
              ("NHS no. duplicate", PURPLE, "403151")]
    ws[f"{A1}1"] = "Key:"
    ws[f"{A1}1"].font = Font(name=FONT, size=9, bold=True)
    for i, (label, f, t) in enumerate(legend):
        cell = ws.cell(row=2, column=ws[f"{A1}1"].column + i)
        cell.value, cell.fill = label, f
        cell.font = Font(name=FONT, size=8, color=t)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 26

    # ---- row 3: group bands, row 4: headers --------------------------------
    prev = None
    for i, (h, w, g) in enumerate(COLUMNS, start=1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = w
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
    date_cols = [COL[c] for c in ("DOB", "EDD", "Booking date", "Next appt due", "Last updated on")]
    date_cols += [COL[c] for c in APPTS + ACTIONS]
    auto_cols = [COL[c] for c in ("Gestation today", "Overdue", "Due in 7 days", "Next appt", "Next appt due")]
    appt_hdr = f"${A1}${HEADER_ROW}:${AN}${HEADER_ROW}"
    for r in range(FIRST, LAST + 1):
        for i in range(1, len(COLUMNS) + 1):
            ws.cell(row=r, column=i).font = base
        for c in date_cols:
            ws[f"{c}{r}"].number_format = DATE_FMT
            ws[f"{c}{r}"].alignment = Alignment(horizontal="center")
        ws[f"{NHS}{r}"].number_format = "@"
        ws[f"{COL['Info']}{r}"].alignment = Alignment(wrap_text=True, vertical="top")
        for c in auto_cols:
            ws[f"{c}{r}"].fill = AUTO_FILL
            ws[f"{c}{r}"].alignment = Alignment(horizontal="center")

        act = active(r)
        appts = f"${A1}{r}:${AN}{r}"
        chain = f"${BOOK}{r}:${AN}{r}"          # booking date + appointments, in date order
        acts = f"${X1}{r}:${XN}{r}"
        # Latest entry in the chain (a date or DNA; N/A skipped). A past date only counts as
        # attended once something later has been entered, so if this latest entry is a past
        # date the appointment was either missed or the next one wasn't booked.
        last = f'IFERROR(LOOKUP(2,1/(ISNUMBER({chain})+({chain}="DNA")),{chain}),"")'
        ws[f"{COL['Gestation today']}{r}"] = (
            f'=IF(OR(NOT({act}),${EDD}{r}=""),"",'
            f'INT((TODAY()-${EDD}{r}+280)/7)&"+"&MOD(TODAY()-${EDD}{r}+280,7))')
        ws[f"{COL['Overdue']}{r}"] = (
            f'=IF(NOT({act}),"",IF(OR({last}="DNA",AND(ISNUMBER({last}),{last}<TODAY())),1,0)'
            f'+COUNTIF({acts},"<"&TODAY()))')
        ws[f"{COL['Due in 7 days']}{r}"] = (
            f'=IF(NOT({act}),"",COUNTIFS({chain},">="&TODAY(),{chain},"<="&TODAY()+7)'
            f'+COUNTIFS({acts},">="&TODAY(),{acts},"<="&TODAY()+7))')
        nd = f"${COL['Next appt due']}{r}"
        ws[f"{COL['Next appt']}{r}"] = (
            f'=IF(NOT({act}),"",IF({nd}<>"",IF({nd}=${BOOK}{r},"Booking",'
            f'INDEX({appt_hdr},MATCH({nd},{appts},0))),'
            f'IF({last}="DNA","Rebook DNA",IF(ISNUMBER({last}),'
            f'IF(ISNUMBER(${AN}{r}),"Update status","Missed/not booked?"),""))))')
        # earliest date on or after today = next booked appointment
        ws[f"{COL['Next appt due']}{r}"] = (
            f'=IF(NOT({act}),"",IFERROR(SMALL({chain},COUNTIF({chain},"<"&TODAY())+1),""))')

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
    # Booking date and 16/40..38/40: a past date is confirmed once anything later is entered.
    # 40/40 has nothing after it, so a past 40/40 stays red until Status changes.
    for area_start, area_end, has_next in ((BOOK, get_column_letter(ws[f"{AN}1"].column - 1), True),
                                           (AN, AN, False)):
        c = area_start
        area = f"{c}{r}:{area_end}{LAST}"
        if has_next:
            later = f"{get_column_letter(ws[f'{c}1'].column + 1)}{r}:${AN}{r}"
            confirmed = f'(COUNT({later})+COUNTIF({later},"DNA"))>0'
        else:
            confirmed = "FALSE"
        cf(area, f'{c}{r}="N/A"', GREY, GREY_TXT)
        cf(area, f'AND({c}{r}="DNA",{confirmed})', GREY, RED_TXT)          # DNA, since rebooked
        cf(area, f'AND({act},{c}{r}="DNA")', RED, RED_TXT, bold=True)
        cf(area, f'AND({act},ISNUMBER({c}{r}),{c}{r}<TODAY(),NOT({confirmed}))', RED, RED_TXT, bold=True)
        cf(area, f'AND({act},ISNUMBER({c}{r}),{c}{r}>=TODAY(),{c}{r}<=TODAY()+7)', AMBER, AMBER_TXT, bold=True)
        cf(area, f'AND(ISNUMBER({c}{r}),{c}{r}<TODAY())', GREEN, GREEN_TXT)

    act_area = f"{X1}{r}:{XN}{LAST}"
    cf(act_area, f'{X1}{r}="N/A"', GREY, GREY_TXT)
    cf(act_area, f'AND({act},ISNUMBER({X1}{r}),{X1}{r}<TODAY())', RED, RED_TXT)
    cf(act_area, f'AND({act},ISNUMBER({X1}{r}),{X1}{r}>=TODAY(),{X1}{r}<=TODAY()+7)', AMBER, AMBER_TXT)
    cf(act_area, f'AND(ISTEXT({X1}{r}),{X1}{r}<>"")', GREEN, GREEN_TXT)

    ov, sn, nd = COL["Overdue"], COL["Due in 7 days"], COL["Next appt due"]
    cf(f"{ov}{r}:{ov}{LAST}", f'AND(ISNUMBER({ov}{r}),{ov}{r}>0)', RED, RED_TXT, bold=True)
    cf(f"{sn}{r}:{sn}{LAST}", f'AND(ISNUMBER({sn}{r}),{sn}{r}>0)', AMBER, AMBER_TXT, bold=True)
    na = COL["Next appt"]
    cf(f"{na}{r}:{na}{LAST}", f'OR({na}{r}="Missed/not booked?",{na}{r}="Rebook DNA",{na}{r}="Update status")', RED, RED_TXT, bold=True)
    cf(f"{nd}{r}:{nd}{LAST}", f'AND(ISNUMBER({nd}{r}),{nd}{r}<=TODAY()+7)', AMBER, AMBER_TXT, bold=True)
    cf(f"{EDD}{r}:{EDD}{LAST}", f'AND({act},ISNUMBER({EDD}{r}),{EDD}{r}<TODAY())', AMBER, AMBER_TXT, bold=True)

    s = f'SUBSTITUTE({NHS}{r}," ","")'
    weighted = "+".join(f"MID({s},{i},1)*{11 - i}" for i in range(1, 10))
    valid = f'AND(LEN({s})=10,ISNUMBER(VALUE({s})),MOD(11-MOD({weighted},11),11)=VALUE(RIGHT({s},1)))'
    nhs_area = f"{NHS}{r}:{NHS}{LAST}"
    cf(nhs_area, f'AND({NHS}{r}<>"",NOT(IFERROR({valid},FALSE)))', ORANGE, "833C0B")
    cf(nhs_area, f'AND({NHS}{r}<>"",COUNTIF(${NHS}${FIRST}:${NHS}${LAST},{NHS}{r})>1)', PURPLE, "403151")

    upd = f'AND(ISNUMBER($B$2),ISNUMBER(${UPD_ON}{r}),${UPD_ON}{r}>=$B$2)'
    cf(f"{NAME}{r}:{NAME}{LAST}", upd, BLUE, BLUE_TXT, bold=True)
    cf(f"{UPD_BY}{r}:{UPD_ON}{LAST}", upd, BLUE, BLUE_TXT, bold=True)

    # Greys out patients who are no longer active (lowest priority, font only).
    cf(f"A{r}:{LAST_COL}{LAST}", f'AND(${NAME}{r}<>"",${STATUS}{r}<>"",${STATUS}{r}<>"Active")',
       color="A6A6A6", italic=True)

    # ---- data validation ---------------------------------------------------
    def dv(area, **kw):
        v = DataValidation(allow_blank=True, **kw)
        v.add(area)
        ws.add_data_validation(v)

    col_area = lambda c: f"{COL[c]}{FIRST}:{COL[c]}{LAST}"
    dv(col_area("MLC/CLC"), type="list", formula1='"MLC,CLC"')
    dv(col_area("Status"), type="list", formula1="StatusList",
       promptTitle="Status", prompt="Blank counts as Active. Anything else stops the flags for this patient.",
       showInputMessage=True)
    dv(col_area("Last updated by"), type="list", formula1="StaffList",
       promptTitle="Who updated this row?", prompt="Pick your name (names live on the Staff tab).",
       showInputMessage=True)
    for c in ("DOB", "EDD", "Booking date", "Last updated on"):
        extra = {}
        if c == "Last updated on":
            extra = dict(promptTitle="Date you changed this row", prompt="Ctrl + ; enters today's date.",
                         showInputMessage=True)
        dv(col_area(c), type="date", operator="between", formula1="DATE(1900,1,1)",
           formula2="DATE(2100,12,31)", errorStyle="warning", showErrorMessage=True,
           errorTitle="Not a date", error="Enter a date like 14/03/2026.", **extra)
    dv(f"{A1}{FIRST}:{AN}{LAST}", type="custom",
       formula1=f'OR({A1}{FIRST}="",ISNUMBER({A1}{FIRST}),{A1}{FIRST}="DNA",{A1}{FIRST}="N/A")',
       errorStyle="warning", showErrorMessage=True, errorTitle="Appointment",
       error="Expected a date, DNA or N/A.", showInputMessage=True,
       promptTitle="Appointment", prompt="Enter the date once it's booked (usually at the previous "
                                         "appointment). Adding it confirms the previous one happened. "
                                         "DNA if missed. N/A if not needed.")
    dv(f"{X1}{FIRST}:{XN}{LAST}", type="custom", formula1="TRUE", showInputMessage=True,
       promptTitle="Action", prompt="Enter the date booked/due. Once complete, type Done (or e.g. "
                                    "'Done 12/3 SW'). N/A if not needed.")
    ws.data_validations.dataValidation[-1].showErrorMessage = False
    v = DataValidation(type="date", operator="greaterThan", formula1="DATE(2000,1,1)", allow_blank=True)
    v.add("B2")
    ws.add_data_validation(v)

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
        ("", "1. Sort or filter the 'Overdue', 'Next appt' or 'Next appt due' column to see who needs something first. "
             "The counts along the top show the totals."),
        ("", "2. When you change a row, pick your name in 'Last updated by' and press Ctrl + ; in "
             "'Last updated on'. That's the only way anyone can see you touched it."),
        ("", "3. For anything more than a date, add a line to the Log tab (date, name, patient, what you did)."),
        ("", "4. To see what's changed since you last looked: type that date in the yellow box at the top "
             "of Caseload (cell B2). Changed rows turn blue and the 'Updated since' count shows how many."),
        ("s", "What to type where"),
        ("", "• Patient columns (Name to Status): as now. EDD drives the gestation. "
             "Leave Status blank or set Active while pregnant. Setting Delivered, Transferred out or Care ended "
             "greys out the row and stops its flags."),
        ("", "• Grey columns (Gestation, Overdue, Due in 7 days, Next appt, Next appt due) are calculated, "
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
        ("", "• Action columns (GTT, Anti-D, BP, Bloods, IOL): enter the date it's booked or due. It turns amber "
             "within 7 days and red once the date has passed. When it's done, overwrite it with 'Done' "
             "(or 'Done 12/3 SW'), which turns it green. N/A turns it grey."),
        ("", "• NHS number: orange means it isn't a valid 10-digit NHS number (checksum). Purple means it "
             "appears twice."),
        ("", "• EDD turns amber if it has passed and the patient is still Active, as a reminder to update Status."),
        ("s", "Colour key"),
        ("red", "Red: appointment passed but not confirmed (nothing entered after it), DNA not yet rebooked, "
                "or an action date that has passed and isn't marked Done"),
        ("amber", "Amber: due in the next 7 days"),
        ("green", "Green: appointment confirmed (a later date has been entered) or action Done"),
        ("grey", "Grey: N/A, or the patient is no longer active"),
        ("blue", "Blue: row updated on or after the date in cell B2"),
        ("s", "Example row (format only, fictional)"),
        ("", "Jane Example | 943 476 5919 | 02/05/1994 | G2P1 | MLC | 10/01/2027 | (Status blank) | "
             "Booking date: 18/06/2026 | 16/40: 11/08/2026 | 25/40: N/A | 28/40: 01/10/2026 | "
             "GTT booked: 14/10/2026 | Anti-D ordered: Done 20/09 | BP fortnightly: N/A | "
             "Last updated by: (your name) | Last updated on: 26/09/2026"),
        ("s", "Seeing exactly who changed what"),
        ("", "If the file is stored on SharePoint, OneDrive or Teams (not a shared drive), Excel keeps a full "
             "audit trail automatically:"),
        ("", "• Review ▸ Show Changes lists every edit with who made it and when. Right-click a cell and choose "
             "Show Changes to see that cell's history."),
        ("", "• File ▸ Info ▸ Version History lets you open or restore any earlier version."),
        ("", "• @mentioning a colleague in a comment (Review ▸ New Comment) sends them an email."),
        ("", "The 'Last updated by' columns and the Log are the human-readable layer on top of that."),
        ("s", "Adding rows"),
        ("", f"The table is pre-formatted for {ROWS} patients. Don't insert or reorder columns "
             "between Booking date and 40/40, because the confirmation check reads them left to right."),
        ("s", "Information governance"),
        ("", "This holds patient-identifiable data. Keep it in the approved team location with access limited "
             "to the team, and follow your trust's IG policy."),
    ]
    styles = {"red": (RED, RED_TXT), "amber": (AMBER, AMBER_TXT), "green": (GREEN, GREEN_TXT),
              "grey": (GREY, GREY_TXT), "blue": (BLUE, BLUE_TXT)}
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
                                            "IOL booked": "Done"}),
        # booking in 5 days only
        ("Test JustBooked", "4010232137", {"Booking date": d(5), "BP fortnightly": "N/A"}),
        # past booking, 16/40 not added -> booking red
        ("Test BookingOnly", "", {"Booking date": d(-3)}),
        # 25/40 DNA, nothing later -> DNA red, Rebook DNA
        ("Test DNA", "", {"Booking date": d(-100), "16/40": d(-50), "25/40": "DNA"}),
        # DNA left in place, rebooked in next column -> DNA grey, 28/40 plain (future)
        ("Test DNARebooked", "", {"Booking date": d(-100), "16/40": d(-50), "25/40": "DNA", "28/40": d(20)}),
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
        ws[f"{UPD_ON}{r}"] = t - timedelta(days=i)
    ws["B2"] = t - timedelta(days=1)

# Fictional caseload. NHS numbers are in the 999 test range (not issued to real people).
# Each entry: name, NHS no., DOB, parity, MLC/CLC, weeks pregnant today, status,
# {column: value}. Appointment values: week number -> date at that gestation (+ jitter days),
# or a literal string (N/A, DNA). Other date values are days from today.
DEMO_STAFF = ["Sarah Jones", "Priya Kaur", "Emma Lawson", "Nadia Brooks"]
DEMO = [
    ("Amelia Hart", "9993982598", date(1995, 3, 14), "G1P0", "MLC", 30, "",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": ("wk", 25), "28/40": ("wk", 28),
      "31/40": ("wk", 31), "GTT booked": "Done 02/09", "Anti-D ordered": "N/A", "BP fortnightly": "N/A",
      "Info": "31/40 this week.", "by": 0, "on": -1}),
    ("Bethany Clarke", "9997919076", date(1990, 7, 2), "G2P1", "MLC", 26, "",
     {"Booking date": ("wk", 9), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28),
      "GTT booked": 3, "Anti-D ordered": "N/A", "Info": "Multip, no 25/40. GTT booked (previous GDM).",
      "by": 1, "on": -5}),
    ("Chloe Ahmed", "9994833782", date(1998, 11, 20), "G1P0", "CLC", 29, "",
     {"Booking date": ("wk", 11), "16/40": ("wk", 16), "25/40": ("wk", 25), "28/40": ("wk", 28),
      "BP fortnightly": 2, "Bloods needed": -3, "Info": "Raised BP at 25/40. Obs clinic review.",
      "by": 2, "on": -9}),
    ("Daisy Okafor", "9998762324", date(1988, 1, 9), "G3P2", "CLC", 34, "",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28),
      "31/40": "N/A", "34/40": "DNA", "Anti-D ordered": "Done 20/08", "Info": "Rh neg. DNA 34/40 - tried phone.",
      "by": 3, "on": -2}),
    ("Ella Morgan", "9998601290", date(1996, 5, 30), "G1P0", "MLC", 35, "",
     {"Booking date": ("wk", 9), "16/40": ("wk", 16), "25/40": ("wk", 25), "28/40": ("wk", 28),
      "31/40": ("wk", 31), "34/40": "DNA", "36/40": ("wk", 36), "GTT booked": "N/A",
      "Info": "DNA 34/40, rebooked for 36/40.", "by": 0, "on": -3}),
    ("Freya Wilson", "9990404798", date(1993, 9, 12), "G2P1", "MLC", 12, "",
     {"Booking date": ("wk", 10, -4), "Info": "Booked. 16/40 still to arrange.", "by": 1, "on": -12}),
    ("Grace Patel", "9996669726", date(2000, 2, 25), "G1P0", "MLC", 9, "",
     {"Booking date": 4, "Info": "New referral.", "by": 2, "on": 0}),
    ("Hannah Lewis", "9995102730", date(1991, 12, 3), "G2P1", "CLC", 39, "",
     {"Booking date": ("wk", 8), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28), "31/40": "N/A",
      "34/40": ("wk", 34), "36/40": ("wk", 36), "38/40": ("wk", 38), "40/40": ("wk", 40),
      "IOL booked": 10, "Anti-D ordered": "N/A", "Info": "IOL booked for T+10.", "by": 3, "on": -1}),
    ("Isla Thompson", "9994646869", date(1994, 4, 18), "G1P0", "CLC", 41, "",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": ("wk", 25), "28/40": ("wk", 28),
      "31/40": ("wk", 31), "34/40": ("wk", 34), "36/40": ("wk", 36), "38/40": ("wk", 38),
      "40/40": ("wk", 40), "IOL booked": -1, "Info": "IOL date passed - check if delivered.",
      "by": 0, "on": -8}),
    ("Jasmine Evans", "9999589693", date(1989, 8, 8), "G2P1", "MLC", 43, "Delivered",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28), "31/40": "N/A",
      "34/40": ("wk", 34), "36/40": ("wk", 36), "38/40": ("wk", 38), "IOL booked": "N/A",
      "Info": "Delivered at 39+2. Handed to postnatal team.", "by": 2, "on": -20}),
    ("Katie Brown", "9993504921", date(1997, 6, 21), "G2P1", "MLC", 20, "",
     {"Booking date": ("wk", 9), "16/40": ("wk", 16), "25/40": "N/A", "28/40": ("wk", 28),
      "Info": "NHS no. has a typo (shows orange).", "by": 1, "on": -6}),
    ("Lucy Hughes", "9997919076", date(1999, 10, 5), "G1P0", "MLC", 23, "",
     {"Booking date": ("wk", 10), "16/40": ("wk", 16), "25/40": ("wk", 25),
      "Info": "NHS no. same as Bethany Clarke (shows purple).", "by": 3, "on": -30}),
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
    ws["B2"] = "=TODAY()-3"
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
            elif k == "on":
                ws[f"{UPD_ON}{r}"] = rel(v)
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
