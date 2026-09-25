"""
Build docs/TradeSense_AI_Workflow.pdf — the system workflow reference.

    pip install reportlab        # (listed in requirements-dev.txt)
    python docs/build_workflow_pdf.py

The repository is public: this document describes how the system works and is
operated, but deliberately contains no server addresses, credentials, chat ids
or other environment-specific values. Setting NAMES are listed, never values.
Text is ASCII/WinAnsi only so the built-in Helvetica font renders every glyph.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
    TableStyle, BaseDocTemplate, Frame,
)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "TradeSense_AI_Workflow.pdf")

# ── Palette ──────────────────────────────────────────────────────────────────
INK = colors.HexColor("#1b1f24")
INK2 = colors.HexColor("#4a5058")
MUTED = colors.HexColor("#6f767f")
ACCENT = colors.HexColor("#256abf")
ACCENT_SOFT = colors.HexColor("#e8f1fb")
CORAL = colors.HexColor("#b9472a")
CORAL_SOFT = colors.HexColor("#fbece6")
TEAL = colors.HexColor("#0f6e56")
TEAL_SOFT = colors.HexColor("#e3f4ee")
GRAY_SOFT = colors.HexColor("#f2f2ef")
RULE = colors.HexColor("#d9dbdf")
DARK = colors.HexColor("#12151a")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


def commit_id() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, text=True).strip()
    except Exception:
        return "unknown"


# ── Styles ───────────────────────────────────────────────────────────────────
ss = getSampleStyleSheet()
BODY = ParagraphStyle("Body", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.5,
                      textColor=INK, spaceAfter=5)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=8.2, leading=11, textColor=INK2, spaceAfter=0)
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=8.4, leading=11, spaceAfter=0)
CELL_B = ParagraphStyle("CellB", parent=CELL, fontName="Helvetica-Bold")
HEAD_CELL = ParagraphStyle("HeadCell", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
H1 = ParagraphStyle("H1", parent=BODY, fontName="Helvetica-Bold", fontSize=17, leading=22, textColor=INK,
                    spaceBefore=4, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=BODY, fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=ACCENT,
                    spaceBefore=10, spaceAfter=4)
BULLET = ParagraphStyle("Bullet", parent=BODY, leftIndent=12, bulletIndent=2, spaceAfter=2.5)
CODE = ParagraphStyle("Code", parent=BODY, fontName="Courier", fontSize=8.2, leading=10.8, textColor=INK,
                      backColor=GRAY_SOFT, borderPadding=(5, 6, 5, 6), leftIndent=4, rightIndent=4,
                      spaceBefore=3, spaceAfter=8)
NOTE = ParagraphStyle("Note", parent=BODY, fontSize=8.8, leading=12.3, backColor=ACCENT_SOFT,
                      borderPadding=(6, 7, 6, 7), leftIndent=4, rightIndent=4, spaceBefore=4, spaceAfter=9)
WARN = ParagraphStyle("Warn", parent=NOTE, backColor=CORAL_SOFT)


# ── Doc template with TOC + header/footer ────────────────────────────────────
class WorkflowDoc(BaseDocTemplate):
    def __init__(self, path: str, **kw):
        super().__init__(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=MARGIN + 6, bottomMargin=MARGIN, title="TradeSense AI - System Workflow",
                         author="TradeSense AI", subject="System workflow reference", **kw)
        frame = Frame(MARGIN, MARGIN, PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN - 6, id="f")
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[frame], onPage=self._cover),
            PageTemplate(id="body", frames=[frame], onPage=self._chrome),
        ])

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in ("H1", "H2"):
            level = 0 if flowable.style.name == "H1" else 1
            text = flowable.getPlainText()
            key = f"h{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
            self.notify("TOCEntry", (level, text, self.page, key))

    @staticmethod
    def _cover(canv, doc):
        canv.saveState()
        canv.setFillColor(DARK)
        canv.rect(0, PAGE_H - 118 * mm, PAGE_W, 118 * mm, fill=1, stroke=0)
        draw_logo(canv, MARGIN, PAGE_H - 28 * mm, 30 * mm)
        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 30)
        canv.drawString(MARGIN, PAGE_H - 78 * mm, "TradeSense AI")
        canv.setFont("Helvetica", 15)
        canv.setFillColor(colors.HexColor("#a3a9b1"))
        canv.drawString(MARGIN, PAGE_H - 89 * mm, "System workflow reference")
        canv.setFont("Helvetica", 9.5)
        canv.drawString(MARGIN, PAGE_H - 104 * mm,
                        f"Version: commit {commit_id()}   |   {date.today():%d %b %Y}   |   Paper trading mode")
        canv.restoreState()

    @staticmethod
    def _chrome(canv, doc):
        canv.saveState()
        draw_logo(canv, MARGIN, PAGE_H - MARGIN + 12.5, 4.2 * mm)
        canv.setFont("Helvetica-Bold", 8.5)
        canv.setFillColor(INK)
        canv.drawString(MARGIN + 6 * mm, PAGE_H - MARGIN + 2.6, "TradeSense AI")
        canv.setFont("Helvetica", 8.5)
        canv.setFillColor(MUTED)
        canv.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN + 2.6, "System workflow reference")
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.5)
        canv.line(MARGIN, PAGE_H - MARGIN - 1.5, PAGE_W - MARGIN, PAGE_H - MARGIN - 1.5)
        canv.line(MARGIN, MARGIN - 5, PAGE_W - MARGIN, MARGIN - 5)
        canv.drawString(MARGIN, MARGIN - 13, "Paper trading only. Not investment advice.")
        canv.drawRightString(PAGE_W - MARGIN, MARGIN - 13, f"Page {doc.page}")
        canv.restoreState()


def draw_logo(canv, x, y_top, size):
    """TradeSense AI mark (same drawing as web_dashboard/frontend/public/favicon.svg)."""
    s = size / 32.0
    canv.saveState()
    canv.translate(x, y_top)
    canv.scale(s, -s)  # SVG coordinates: y grows downward
    canv.setFillColor(DARK)
    canv.roundRect(0, 0, 32, 32, 8, fill=1, stroke=0)
    canv.setLineCap(1)
    canv.setLineJoin(1)
    canv.setStrokeColor(colors.HexColor("#3987e5"))
    canv.setLineWidth(2.6)
    p = canv.beginPath()
    p.moveTo(6, 23); p.lineTo(11.5, 17); p.lineTo(15.5, 20); p.lineTo(21, 13)
    canv.drawPath(p, stroke=1, fill=0)
    canv.setStrokeColor(colors.HexColor("#6da7ec"))
    canv.setLineWidth(1.7)
    canv.arc(24.2 - 4.5, 13 - 4.5, 24.2 + 4.5, 13 + 4.5, -45, 90)
    canv.setStrokeColor(colors.Color(0.427, 0.655, 0.925, alpha=0.5))
    canv.arc(26.6 - 7.9, 13 - 7.9, 26.6 + 7.9, 13 + 7.9, -45, 90)
    canv.setFillColor(colors.HexColor("#1fb85a"))
    canv.setStrokeColor(DARK)
    canv.setLineWidth(1.5)
    canv.circle(21, 13, 3, fill=1, stroke=1)
    canv.restoreState()


# ── Helpers ──────────────────────────────────────────────────────────────────
def p(text, style=BODY):
    return Paragraph(text, style)


def bullets(items, style=BULLET):
    return [Paragraph(i, style, bulletText="•") for i in items]


def table(rows, widths, header=True, zebra=True, first_col_bold=False, head_color=ACCENT):
    data = []
    for r_i, row in enumerate(rows):
        out = []
        for c_i, cell in enumerate(row):
            if isinstance(cell, str):
                if header and r_i == 0:
                    style = HEAD_CELL
                elif first_col_bold and c_i == 0:
                    style = CELL_B
                else:
                    style = CELL
                out.append(Paragraph(cell, style))
            else:
                out.append(cell)
        data.append(out)
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
    ]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), head_color)]
    if zebra:
        start = 1 if header else 0
        for i in range(start, len(data)):
            if (i - start) % 2 == 1:
                cmds.append(("BACKGROUND", (0, i), (-1, i), GRAY_SOFT))
    t.setStyle(TableStyle(cmds))
    return t


def arrow_down(d, x, y1, y2, color=MUTED):
    d.add(Line(x, y1, x, y2 + 4, strokeColor=color, strokeWidth=0.9))
    d.add(Polygon([x - 3, y2 + 5, x + 3, y2 + 5, x, y2], fillColor=color, strokeColor=color, strokeWidth=0.5))


def arrow_right(d, x1, x2, y, color=MUTED):
    d.add(Line(x1, y, x2 - 4, y, strokeColor=color, strokeWidth=0.9))
    d.add(Polygon([x2 - 5, y - 3, x2 - 5, y + 3, x2, y], fillColor=color, strokeColor=color, strokeWidth=0.5))


def box(d, x, y, w, h, title, sub="", fill=GRAY_SOFT, stroke=RULE, title_color=INK):
    d.add(Rect(x, y, w, h, rx=4, ry=4, fillColor=fill, strokeColor=stroke, strokeWidth=0.7))
    ty = y + h / 2 + (3 if sub else -3)
    d.add(String(x + w / 2, ty, title, fontName="Helvetica-Bold", fontSize=8.6, fillColor=title_color,
                 textAnchor="middle"))
    if sub:
        d.add(String(x + w / 2, y + h / 2 - 8, sub, fontName="Helvetica", fontSize=7.2, fillColor=INK2,
                     textAnchor="middle"))


# ── Diagrams ─────────────────────────────────────────────────────────────────
def architecture_diagram():
    W, H = 174 * mm, 88 * mm
    d = Drawing(W, H)
    col_w = 42 * mm
    # Column 1: data sources
    box(d, 0, H - 20 * mm, col_w, 14 * mm, "Yahoo Finance", "free market data (default)", ACCENT_SOFT)
    box(d, 0, H - 38 * mm, col_w, 14 * mm, "Dhan API", "optional: real-time + options", GRAY_SOFT)
    box(d, 0, H - 56 * mm, col_w, 14 * mm, "Global markets", "US / Asia / FX / commodities", ACCENT_SOFT)
    # Column 2: engine
    ex = 60 * mm
    box(d, ex, H - 64 * mm, col_w + 6 * mm, 58 * mm, "Trading engine", "", TEAL_SOFT, TEAL, TEAL)
    for i, (t, s) in enumerate([("Scheduler (IST)", "cycles + EOD jobs"), ("Decision pipeline", "12 stages"),
                                ("Paper order manager", "no real orders"), ("Learning (15:35)", "updates models")]):
        box(d, ex + 3 * mm, H - 17 * mm - i * 10 * mm, col_w, 8.5 * mm, t, "", colors.white, RULE)
    for y in (H - 13 * mm, H - 31 * mm, H - 49 * mm):
        arrow_right(d, col_w, ex, y)
    # Column 3: outputs
    ox = 126 * mm
    box(d, ox, H - 20 * mm, col_w + 6 * mm, 14 * mm, "data/ folder", "telemetry DB + trade journal", GRAY_SOFT)
    box(d, ox, H - 44 * mm, col_w + 6 * mm, 14 * mm, "Web dashboard", "read-only, password login", ACCENT_SOFT)
    box(d, ox, H - 66 * mm, col_w + 6 * mm, 14 * mm, "Telegram bot", "alerts + commands", ACCENT_SOFT)
    arrow_right(d, ex + col_w + 6 * mm, ox, H - 13 * mm)
    arrow_down(d, ox + 24 * mm, H - 20 * mm, H - 30 * mm)
    arrow_right(d, ex + col_w + 6 * mm, ox, H - 59 * mm)
    # Bottom: users
    box(d, ox, 0, col_w + 6 * mm, 12 * mm, "You (browser / phone)", "via HTTPS reverse proxy", colors.white)
    arrow_down(d, ox + 24 * mm, H - 66 * mm, 12 * mm)
    return d


def pipeline_diagram():
    stages = [
        ("1  Market data & context", "indices, VIX, breadth, regime, global cues", GRAY_SOFT),
        ("2  Strategy weights (ML)", "k-NN meta-learning picks today's mix", GRAY_SOFT),
        ("3  Scanner", "candidates with entry, stop, target", GRAY_SOFT),
        ("4  StrategyLab", "backtest + health filter", CORAL_SOFT),
        ("5  Capital & risk checks", "confidence, R:R >= 2, sizing, stress", CORAL_SOFT),
        ("6  Monte Carlo simulation", "stability under stress scenarios", CORAL_SOFT),
        ("7  RiskGuardian kill switch", "VIX > 45 or day loss >= 2% blocks all", CORAL_SOFT),
        ("8  Correlation & exposure", "max 1 per sector, exposure caps", CORAL_SOFT),
        ("9  5-agent debate + decision", "weighted score >= 6.5 (VIX-adaptive)", CORAL_SOFT),
        ("10 Paper order", "timing: immediate / pullback / confirm", GRAY_SOFT),
        ("11 Trade monitor (5 min)", "stop / target / square-off", TEAL_SOFT),
        ("12 End-of-day learning", "scores strategies for tomorrow", TEAL_SOFT),
    ]
    bw, bh, gap = 92 * mm, 9.2 * mm, 3.2 * mm
    H = len(stages) * (bh + gap)
    W = 174 * mm
    d = Drawing(W, H)
    x = 6 * mm
    for i, (t, s, fill) in enumerate(stages):
        y = H - (i + 1) * (bh + gap) + gap
        box(d, x, y, bw, bh, t, s, fill)
        if i < len(stages) - 1:
            arrow_down(d, x + bw / 2, y, y - gap)
    # Rejection bracket
    top = H - 4 * (bh + gap) + gap + bh
    bottom = H - 9 * (bh + gap) + gap
    bx = x + bw + 10 * mm
    d.add(Rect(bx, bottom, 52 * mm, top - bottom, rx=4, ry=4, fillColor=None, strokeColor=CORAL,
               strokeWidth=0.8, strokeDashArray=[3, 2]))
    d.add(String(bx + 26 * mm, (top + bottom) / 2 + 6, "Any of stages 4-9", fontName="Helvetica-Bold",
                 fontSize=8.6, fillColor=CORAL, textAnchor="middle"))
    d.add(String(bx + 26 * mm, (top + bottom) / 2 - 6, "can reject the trade", fontName="Helvetica",
                 fontSize=8, fillColor=INK2, textAnchor="middle"))
    d.add(String(bx + 26 * mm, (top + bottom) / 2 - 17, "(reason is logged)", fontName="Helvetica",
                 fontSize=7.5, fillColor=MUTED, textAnchor="middle"))
    # Feedback loop
    fy_bottom = gap + bh / 2
    fy_top = H - 3 * (bh + gap) + gap + bh / 2
    lx = x - 3 * mm
    d.add(Line(x, fy_bottom, lx, fy_bottom, strokeColor=TEAL, strokeWidth=0.9, strokeDashArray=[3, 2]))
    d.add(Line(lx, fy_bottom, lx, H - (bh + gap) - 12 * mm, strokeColor=TEAL, strokeWidth=0.9, strokeDashArray=[3, 2]))
    d.add(Line(lx, H - (bh + gap) - 12 * mm, lx, fy_top, strokeColor=TEAL, strokeWidth=0.9, strokeDashArray=[3, 2]))
    arrow_right(d, lx, x, fy_top + 0.01, TEAL)
    return d


# ── Content ──────────────────────────────────────────────────────────────────
def build():
    doc = WorkflowDoc(OUT)
    s = []

    # Cover
    s.append(Spacer(1, 108 * mm))
    s.append(p("<b>What this document covers</b>", ParagraphStyle("cv", parent=BODY, fontSize=11)))
    s += bullets([
        "What TradeSense AI is and how its parts fit together",
        "The full daily timeline, from pre-market to end-of-day learning",
        "Every stage of a trading cycle, including the 5-agent debate and the decision math",
        "Risk limits and safety controls, and how the system learns from outcomes",
        "Market data, the web dashboard, Telegram alerts and commands",
        "How it is deployed and operated, with a runbook for common tasks",
    ])
    s.append(Spacer(1, 8))
    s.append(p("The system trades in <b>paper mode</b>: it simulates orders and records results, but never "
               "sends real orders. Nothing in this document is investment advice.", NOTE))
    s.append(NextPageTemplate("body"))
    s.append(PageBreak())

    # TOC
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("t0", parent=BODY, fontName="Helvetica-Bold", fontSize=9.8, leading=12.5, leftIndent=0,
                       spaceBefore=4, spaceAfter=0),
        ParagraphStyle("t1", parent=BODY, fontSize=8.8, leading=11.5, leftIndent=12, textColor=INK2, spaceAfter=0),
    ]
    # Not the "H1" style, so the Contents heading does not list itself in the TOC.
    s.append(p("Contents", ParagraphStyle("TocHead", parent=H1)))
    s.append(toc)
    s.append(PageBreak())

    # 1 Overview
    s.append(p("1. System overview", H1))
    s.append(p("TradeSense AI is an automated trading system for Indian equities (NSE). Several times each "
               "trading day it scans the market, puts every trade idea through a chain of filters and a vote by "
               "five specialist scoring agents, and records the approved trades as <b>paper trades</b>. Every "
               "evening it learns from how those trades turned out and adjusts the next day's behaviour."))
    s.append(architecture_diagram())
    s.append(Spacer(1, 6))
    s.append(p("Main building blocks", H2))
    s.append(table([
        ["Component", "What it does", "Where in the code"],
        ["Scheduler / orchestrator", "Runs every job at its IST time slot; the single entry point for a cycle",
         "orchestrator/master_orchestrator.py"],
        ["Market intelligence", "Indices, VIX, breadth, PCR, sector flows, market regime",
         "market_intelligence/, global_intelligence/"],
        ["Opportunity engine", "Scans stocks and builds trade signals (entry, stop, target)", "opportunity_engine/"],
        ["StrategyLab", "Assigns a strategy, applies backtest and health gates", "strategy_lab/"],
        ["Risk control", "Capital allocation, risk rules, stress tests, correlation, exposure", "risk_control/"],
        ["Simulation", "Monte Carlo stability check", "market_simulation/"],
        ["RiskGuardian", "Portfolio kill switch", "risk_guardian/"],
        ["Debate + Decision", "5 scoring agents and the weighted decision", "debate_system/, decision_ai/"],
        ["Execution (paper)", "Order timing, paper journal, fill records", "execution_engine/"],
        ["Monitoring + learning", "Open-position checks, EOD learning, strategy tracking",
         "trade_monitoring/, learning_system/, meta_learning/"],
        ["Web dashboard", "Read-only UI + API with password login", "web_dashboard/"],
        ["Telegram", "Alerts to a group, operator commands", "notifications/"],
    ], [38 * mm, 78 * mm, 58 * mm], first_col_bold=True))
    s.append(PageBreak())

    # 2 Daily timeline
    s.append(p("2. Daily timeline (IST)", H1))
    s.append(p("All times are India Standard Time. The engine runs continuously; the scheduler fires each job at "
               "its slot. No action is needed from you on a normal day."))
    s.append(table([
        ["Time", "Job", "What happens"],
        ["08:00", "Pre-market start", "Loads data and state, runs start-up health checks"],
        ["08:30 - 09:10", "Warm-up", "Pre-fetches global markets; pre-market refiner updates the watchlist (08:45)"],
        ["09:15", "Market opens", "Open notification and data-feed readiness probe. No trading yet"],
        ["09:45", "First trading cycle", "Full 12-stage decision pipeline (section 3). Trading is blocked before "
                                          "09:45 to avoid the opening volatility"],
        ["10:30, 11:30, 13:00, 14:00, 15:00", "Trading cycles", "Same pipeline; each cycle takes roughly 20-40 s"],
        ["Every 5 min", "Trade monitor", "Checks open positions against stop-loss and target"],
        ["15:05", "Intraday square-off", "Closes intraday (short) positions before the close"],
        ["15:30", "Market close", "Close notification"],
        ["15:35", "End-of-day learning", "Scores strategies, updates models (section 6). Retries at 16:00 and "
                                          "17:10 if needed; alert at 17:50 if still incomplete"],
        ["16:45", "Post-market scan", "Scans about 500 stocks (about 20 min) to prepare the next day's universe"],
        ["Saturday 08:00", "Weekend intelligence", "Deeper accumulation and study cycle"],
        ["Sunday 09:00", "Monday preparation", "Tactical preparation for the week"],
    ], [34 * mm, 38 * mm, 102 * mm], first_col_bold=True))
    s.append(p("The exact slot times live in <font face='Courier'>SCHEDULE</font> in "
               "<font face='Courier'>config.py</font>; the dashboard's schedule panel reads them from there.", SMALL))
    s.append(PageBreak())

    # 3 Trading cycle
    s.append(p("3. One trading cycle, stage by stage", H1))
    s.append(p("A trading cycle takes the day's candidate stocks and narrows them down. Most stages can only "
               "<b>reject</b> a trade or <b>reduce its size</b>; the price levels (entry, stop, target) are set once "
               "by the scanner and never changed downstream. Approved trades become paper orders; the trade "
               "monitor and end-of-day learning close the loop."))
    s.append(pipeline_diagram())
    s.append(p("Stage details", H2))
    s.append(table([
        ["#", "Stage", "What it does", "Can reject?"],
        ["1", "Market data & context", "Pre-checks (execution window, kill switch, stale orders). Fetches "
         "indices, VIX, breadth, PCR, events and global cues; validates data integrity (aborts on hard errors); "
         "classifies the regime (bull trend, range, bear, volatile).", "Aborts cycle on bad data"],
        ["2", "Strategy weights", "A k-nearest-neighbour meta-learning model (trained on the system's own "
         "results) blends with regime rules to weight strategies for today.", "No"],
        ["3", "Scanner", "Scores the prepared universe using technical and fundamental factors. Sets entry, "
         "stop-loss and target (ATR-based), direction, confidence and reward:risk. A knowledge layer records its "
         "own evidence-based view of each signal alongside.", "No (creates signals)"],
        ["4", "StrategyLab", "Assigns the best-fit strategy, applies evolved parameters, and filters by "
         "backtest quality and strategy health (strategies that keep losing are disabled).", "Yes"],
        ["5", "Capital & risk checks", "Caps the number of new positions; RiskManager requires confidence "
         "&gt;= 6.0, reward:risk &gt;= 2.0, a defined stop and available risk budget; position sizing; stress "
         "tests. Rejections are logged for later analysis.", "Yes"],
        ["6", "Monte Carlo simulation", "Simulates each trade across stress scenarios and rejects unstable "
         "ones.", "Yes"],
        ["7", "RiskGuardian", "Hard kill switch at portfolio level: blocks everything if VIX &gt; 45 or the "
         "day's loss reaches 2% of capital. Cannot be bypassed.", "Yes (blocks all)"],
        ["8", "Correlation & exposure", "At most one position per sector; exposure caps and VIX-adjusted "
         "allocation.", "Yes"],
        ["9", "Debate + decision", "Five scoring agents vote; the Decision Engine combines them into a "
         "weighted score and decides full, half or no size (section 4). A data-truth governor then blocks "
         "trades built on synthetic prices.", "Yes"],
        ["10", "Paper order", "Order manager chooses timing (immediate, wait for pullback, or wait for "
         "confirmation), re-checks the kill switch before any deferred placement, and writes the trade to "
         "the paper journal.", "Kill switch re-check"],
        ["11", "Trade monitor", "Every 5 minutes: exits at stop-loss or target, applies square-off rules.",
         "-"],
        ["12", "End-of-day learning", "Updates strategy statistics and models (section 6).", "-"],
    ], [8 * mm, 34 * mm, 104 * mm, 28 * mm], first_col_bold=False))
    s.append(p("Who sets what", H2))
    s.append(table([
        ["Parameter", "Set by"],
        ["Entry, stop-loss, target, direction, confidence, reward:risk", "Scanner (stage 3)"],
        ["Strategy name", "StrategyLab (stage 4)"],
        ["Position size", "Capital/risk sizing (stage 5), exposure engine (stage 8), decision modifier (stage 9)"],
        ["Final go / no-go", "Decision Engine (stage 9), then data-truth governor and order manager"],
    ], [92 * mm, 82 * mm], first_col_bold=True))
    s.append(PageBreak())

    # 4 Agents
    s.append(p("4. The five agents and the decision", H1))
    s.append(p("The agents are <b>rule-based scoring programs</b>, not calls to an external AI service. Each looks "
               "at the trade from one angle and returns a score from 0 to 10, a vote (approve, reduce size, hedge, "
               "reject), a suggested size modifier and a written reason. No AI API key is required and there is no "
               "per-use cost. Code: <font face='Courier'>debate_system/multi_agent_debate.py</font>."))
    s.append(table([
        ["Agent", "Weight", "Question it answers", "Key rules"],
        ["Technical Analyst", "30%", "Is the trade structurally sound?",
         "Buy: stop &lt; entry &lt; target (inverse for sells), else reject (3.0). Stop distance must be 0.5-4x "
         "the stock's ATR, else weak (5.0, size 70%). Sound: 8.0."],
        ["Risk", "25%", "Is volatility acceptable and the payoff worth it?",
         "VIX &lt; 18: base 7.0; 18-22: 6.0 at 75% size; 22+: 4.5 at 50% size. Reward:risk bonus: &gt;= 4: +1.5, "
         "&gt;= 3: +1.0, &gt;= 2: +0.5, &lt; 1.5: -1.5 (and 50% size)."],
        ["Macro", "20%", "What are global markets saying?",
         "Event day (RBI, results, expiry): hedge, 5.0 at 60% size. Bear market: reject (3.0). Otherwise 7.0 "
         "adjusted by overnight global sentiment, range 5-9."],
        ["Sentiment", "15%", "How is the crowd positioned?",
         "For buys: PCR &gt; 1.2 is contrarian bullish (7.0); breadth &lt; 35% means risk-off (5.5 at 60% size); "
         "otherwise neutral 7.0."],
        ["Regime", "10%", "Does the strategy suit today's market?",
         "Strategy matches the regime's allowed list: 8.0; mismatch: 5.0 at 70% size. Signals already approved by "
         "the evidence-based knowledge layer score 8.0."],
    ], [27 * mm, 14 * mm, 38 * mm, 95 * mm], first_col_bold=True))
    s.append(p("How the Decision Engine decides", H2))
    s += bullets([
        "<b>Weighted score</b> = sum of (agent score x agent weight). The weights add up to 1.",
        "<b>Size modifier</b> = geometric mean of the agents' suggested modifiers.",
        "<b>Threshold</b> depends on VIX: 6.5 (VIX &lt; 20), 6.6 (20-25), 6.7 (25-30), 6.9 (30+). "
        "High reward:risk lowers it: -0.5 for R:R &gt;= 3, -1.0 (and +10% size) for R:R &gt;= 4.",
        "<b>Outcome</b>: score &gt;= threshold: approve at full size. Within 0.2 below: approve at <b>half</b> size. "
        "Otherwise reject.",
    ])
    s.append(p("<b>Note:</b> <font face='Courier'>config.py</font> also defines MIN_CONFIDENCE_SCORE = 6.8, but the "
               "Decision Engine only prints it at start-up; the gate actually applied is the VIX-adaptive threshold "
               "above. This mismatch is worth tidying up in the code.", WARN))
    s.append(p("Worked example", H2))
    s.append(p("Buy SBIN; VIX 12; bull trend; reward:risk 2.0; a momentum strategy; neutral sentiment; mildly "
               "positive global cues (+0.2)."))
    s.append(KeepTogether(table([
        ["Agent", "Score", "x Weight", "Contribution"],
        ["Technical", "8.0", "0.30", "2.40"],
        ["Risk", "7.5 (7.0 + 0.5)", "0.25", "1.88"],
        ["Macro", "7.4 (7.0 + 0.2 x 2)", "0.20", "1.48"],
        ["Sentiment", "7.0", "0.15", "1.05"],
        ["Regime", "8.0", "0.10", "0.80"],
        ["<b>Weighted score</b>", "", "", "<b>7.6 &gt;= 6.5: APPROVED, full size</b>"],
    ], [40 * mm, 46 * mm, 30 * mm, 58 * mm], first_col_bold=True)))
    s.append(Spacer(1, 6))
    s.append(p("With VIX at 20, reward:risk 1.4 and a strategy that does not suit the regime, the same trade scores "
               "about 6.5 against a raised threshold and is rejected."))
    s.append(PageBreak())

    # 5 Risk
    s.append(p("5. Risk limits and safety controls", H1))
    s.append(p("Values below are the code defaults. Position sizes scale with TOTAL_CAPITAL (set per "
               "installation; the current deployment uses Rs 2,00,000)."))
    s.append(table([
        ["Control", "Limit", "Effect"],
        ["Paper trading", "PAPER_TRADING=true (default)", "Orders are simulated. Live orders additionally need "
         "PAPER_TRADING=false <b>and</b> LIVE_TRADING_AUTHORIZED=true; otherwise the system forces paper mode."],
        ["Risk per trade", "0.25% of capital", "Quantity = risk amount / stop distance (e.g. Rs 500 on Rs 2 lakh)"],
        ["Daily loss kill switch", "2% of capital", "RiskGuardian halts all new trades for the day"],
        ["Volatility kill switch", "India VIX &gt; 45", "RiskGuardian blocks all new trades"],
        ["Risk at stake", "5% of capital (RiskGuardian)", "Caps combined open risk"],
        ["Max positions", "8 for capital above Rs 1 lakh (3 / 5 for smaller)", "Override with MAX_POSITIONS"],
        ["Drawdown halt", "10%", "Trading halts on a 10% drawdown"],
        ["Sector correlation", "1 position per sector", "Avoids concentrated bets"],
        ["Minimum quality", "Confidence &gt;= 6.0, reward:risk &gt;= 2.0", "RiskManager rejects weaker trades"],
        ["Execution window", "No trades before 09:45", "Avoids the opening volatility"],
        ["Data truth", "Synthetic equity prices", "Trade approval is suppressed if prices are not real"],
    ], [36 * mm, 46 * mm, 92 * mm], first_col_bold=True))
    s.append(p("Trade lifecycle", H2))
    s += bullets([
        "<b>Entry:</b> buys use delivery (CNC) so they can be held for the strategy's planned 3-7 day horizon; "
        "shorts are intraday, as SEBI requires for uncovered cash-market shorts.",
        "<b>While open:</b> the trade monitor checks stop-loss and target every 5 minutes.",
        "<b>Exit:</b> stop hit, target hit, intraday square-off at 15:05 (shorts), or end of the holding period.",
        "<b>Record:</b> every open and close is written to <font face='Courier'>data/paper_trades.csv</font> with "
        "entry, exit, P&amp;L and reason.",
    ])
    s.append(PageBreak())

    # 6 Learning
    s.append(p("6. How the system learns", H1))
    s.append(p("Learning uses only the system's own trade outcomes, processed on the server. No external AI "
               "service is involved."))
    s.append(table([
        ["When", "Learning step", "Effect on future trades"],
        ["15:35 daily", "Strategy performance tracker", "Updates each strategy's win rate and expectancy; "
         "persistently losing strategies are <b>disabled</b> in StrategyLab the next day"],
        ["15:35 daily", "Regime-strategy map", "Learns which strategies work in which market regime"],
        ["15:35 daily", "Meta-learning model", "Retrains the k-NN strategy-weighting model when due"],
        ["15:35 daily", "Edge discovery", "Mines outcomes for improved strategy variants; promoted variants go "
         "into the next day's strategy pool"],
        ["15:35 daily", "Knowledge outcomes", "Fills in what each earlier signal actually did over the next 1-5 "
         "days; feeds the evidence-based knowledge layer"],
        ["Each cycle", "Rejection tracker", "Records why trades were rejected; used by knowledge fusion"],
        ["After 30+ trades", "Validation engine", "Statistical validation of the strategy set"],
    ], [26 * mm, 42 * mm, 106 * mm], first_col_bold=True))
    s.append(p("Research modules that are not yet connected", H2))
    s.append(p("The repository also contains research pipelines (autonomous research, options research, "
               "production-readiness gates) that run or can be run, but whose output does not yet change live "
               "decisions. <font face='Courier'>SYSTEM_OPERATING_MAP.md</font> lists exactly which pipelines "
               "feed decisions and which do not."))
    s.append(p("How to judge performance", H2))
    s.append(p("Judge over weeks, not days. The project's own bar before considering live trading: win rate "
               "&gt;= 50%, Sharpe ratio &gt; 0.8 and maximum drawdown &lt; 15%. Few or no trades in the first days "
               "is normal while the filters have no history."))
    s.append(PageBreak())

    # 7 Data
    s.append(p("7. Market data", H1))
    s.append(p("Without a broker connection the system uses <b>Yahoo Finance</b> through the open-source "
               "<font face='Courier'>yfinance</font> library: no account, no key, no cost."))
    s.append(table([
        ["Data", "Yahoo symbol", "Refresh"],
        ["NSE stocks", "SYMBOL.NS (e.g. SBIN.NS)", "Prices cached 60 s; history on demand"],
        ["NIFTY 50 / Bank Nifty", "^NSEI / ^NSEBANK", "Each cycle"],
        ["India VIX", "^INDIAVIX", "Each cycle"],
        ["Global markets", "^GSPC, ^N225, USDINR=X, GC=F, CL=F ...", "Every 5 min in the background"],
    ], [42 * mm, 72 * mm, 60 * mm], first_col_bold=True))
    s.append(p("Fallback order", H2))
    s.append(p("Dhan (if a token is configured) &gt; Yahoo Finance &gt; last good cached price &gt; built-in "
               "estimate. If equity prices become synthetic, the data-truth governor <b>blocks new trades</b> "
               "rather than trading on bad data.", CODE))
    s.append(p("Limitations of free data", H2))
    s += bullets([
        "Yahoo NSE quotes are delayed (typically around 15 minutes), so paper fills are approximate.",
        "No NSE option chain: options strategies stay switched off; only stock trades are taken.",
        "No market depth, so slippage cannot be modelled precisely.",
        "Unofficial source: occasional throttling shows up as degraded feed status on the dashboard.",
    ])
    s.append(p("Adding a Dhan account and API token later gives real-time prices, the option chain and exact tick "
               "sizes, with no code changes.", NOTE))
    s.append(PageBreak())

    # 8 Dashboard
    s.append(p("8. Web dashboard", H1))
    s.append(p("A read-only web app (FastAPI backend + React frontend) that reads the engine's telemetry "
               "database and trade journal. It cannot place, change or cancel trades. It refreshes every 5 "
               "seconds and works on phones."))
    s.append(table([
        ["Page", "What you see"],
        ["Overview", "Total and today's P&amp;L, win rate, open positions, account equity, equity curve, latest "
         "cycle (regime, VIX, PCR, breadth, signal funnel), today's schedule, recent decisions"],
        ["Trades &amp; P&amp;L", "Profit factor, average win/loss, max drawdown, daily P&amp;L, P&amp;L by "
         "strategy, exit reasons, searchable closed-trades table"],
        ["Signals &amp; decisions", "Where signals drop out, top rejection reasons, decisions by strategy, "
         "decision log with each agent's score"],
        ["System health", "Engine status, cycle durations, agent health, live event stream, end-of-day report"],
    ], [34 * mm, 140 * mm], first_col_bold=True))
    s.append(p("Login and security", H2))
    s += bullets([
        "Password stored only as a salted PBKDF2-SHA256 hash (DASHBOARD_PASSWORD_HASH); set it with "
        "<font face='Courier'>python -m web_dashboard.set_password</font>.",
        "Session: signed HttpOnly, SameSite=Strict cookie; expires after 12 hours; changing the password signs "
        "everyone out.",
        "Fails closed: with no password configured, no data can be read.",
        "Brute-force protection: 5 wrong attempts lock that visitor out for 15 minutes. Behind a reverse proxy "
        "the real visitor IP is taken from X-Forwarded-For only for proxies listed in DASHBOARD_TRUSTED_PROXIES.",
    ])
    s.append(PageBreak())

    # 9 Telegram
    s.append(p("9. Telegram alerts and commands", H1))
    s.append(p("The engine posts alerts to a Telegram group and answers commands. In a group, add "
               "<font face='Courier'>@&lt;bot username&gt;</font> after a command (for example "
               "<font face='Courier'>/status@TradeSenseAI_bot</font>); in a private chat it is not needed."))
    s.append(p("Alerts", H2))
    s += bullets([
        "Engine start-up and online status (plus a Dhan token prompt while no broker is connected)",
        "Trade approvals and exits with entry, stop, target and P&amp;L",
        "Kill-switch and data-feed warnings",
        "End-of-day summary after 15:35",
    ])
    s.append(p("Who can run what", H2))
    s.append(table([
        ["Sender", "Read-only commands", "Control: /pause /resume /rescan", "/token"],
        ["Any member of the registered group", "Yes", "No (restricted to administrators)", "No"],
        ["Admin (listed in TELEGRAM_WHITELIST_IDS), in the group", "Yes", "Yes", "No (send it privately)"],
        ["Admin, private chat with the bot", "Yes", "Yes", "Yes"],
        ["Anyone else, private chat", "No (Unauthorized)", "No", "No"],
    ], [60 * mm, 32 * mm, 50 * mm, 32 * mm], first_col_bold=True))
    s.append(p("Useful read-only commands: /status, /pnl, /positions, /cycle, /perf, /market, /learn, /report, "
               "/eod, /help. Never post a broker token in a group; the bot refuses /token there.", SMALL))
    s.append(PageBreak())

    # 10 Deployment
    s.append(p("10. Deployment", H1))
    s.append(p("The system runs as two Docker containers on a Linux VPS, alongside other applications that must "
               "not be disturbed. A shared Caddy reverse proxy owns ports 80/443 and serves HTTPS; each "
               "application is added as one site block."))
    s.append(table([
        ["Item", "Setup"],
        ["Folder", "/opt/tradesense (a clone of the main branch)"],
        ["Docker project", "tradesense (COMPOSE_PROJECT_NAME in .env keeps every compose command scoped)"],
        ["Containers", "ai-trading-brain (engine, capped at 3 GB / 1 CPU) and trading-dashboard (1 GB / 0.5 CPU)"],
        ["Networking", "Dashboard has no public port; it joins the shared proxy network via a server-only "
         "docker-compose.override.yml"],
        ["HTTPS", "Reverse proxy site block for the dashboard domain with an automatic Let's Encrypt certificate; "
         "DNS record is DNS-only (not proxied)"],
        ["Settings", ".env on the server only (never committed): paper mode, capital, dashboard hash, Telegram"],
        ["Image build", "Multi-stage Dockerfile: Node builds the React frontend; the Python image serves it"],
    ], [34 * mm, 140 * mm], first_col_bold=True))
    s.append(p("Isolation rules for a shared server", H2))
    s += bullets([
        "Run compose commands only inside /opt/tradesense; never docker system prune, and never touch other "
        "projects' containers, files or databases.",
        "Change the reverse proxy only by: back up the Caddyfile, append the site block in place, validate, then "
        "reload (graceful, no downtime). Never restart the shared proxy container.",
        "Snapshot the list of running containers before and after any change and compare.",
    ])
    s.append(p("Update to the latest main", H2))
    s.append(p("cd /opt/tradesense &amp;&amp; git pull &amp;&amp; docker compose build &amp;&amp; docker compose up -d",
               CODE))
    s.append(p("Remove completely (undo)", H2))
    s.append(p("cd /opt/tradesense &amp;&amp; docker compose down<br/>"
               "# restore the Caddyfile backup, validate and reload the proxy<br/>"
               "rm -rf /opt/tradesense", CODE))
    s.append(p("Development workflow", H2))
    s += bullets([
        "Changes are made on a feature branch, tested (pytest + frontend build), and merged to main by pull "
        "request; the server then pulls main.",
        "Frontend: <font face='Courier'>cd web_dashboard/frontend &amp;&amp; pnpm install &amp;&amp; pnpm build</font>.",
        "Local run (Windows, no Docker): set RUNNING_IN_DOCKER=1 and run "
        "<font face='Courier'>python main.py --paper</font>; dashboard: "
        "<font face='Courier'>python -m web_dashboard.server</font>.",
    ])
    s.append(PageBreak())

    # 11 Settings
    s.append(p("11. Settings reference", H1))
    s.append(p("All settings are environment variables in <font face='Courier'>.env</font>, which is git-ignored. "
               "<font face='Courier'>.env.example</font> in the repository documents them without real values."))
    s.append(table([
        ["Setting", "Purpose"],
        ["PAPER_TRADING / LIVE_TRADING_AUTHORIZED", "Paper mode unless BOTH are set for live trading"],
        ["TOTAL_CAPITAL", "Capital used for sizing (rupees)"],
        ["MAX_POSITIONS", "Optional override of the max simultaneous positions"],
        ["ACTIVE_BROKER, DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN", "Broker selection and Dhan credentials (optional)"],
        ["TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID", "Bot token and the chat (or group) that receives alerts"],
        ["TELEGRAM_WHITELIST_IDS", "Telegram user ids allowed to run control commands"],
        ["DASHBOARD_PASSWORD_HASH", "Dashboard login (hash only)"],
        ["DASHBOARD_SESSION_HOURS", "Login lifetime (default 12)"],
        ["DASHBOARD_COOKIE_SECURE", "true when served over HTTPS"],
        ["DASHBOARD_TRUSTED_PROXIES", "Reverse-proxy IPs/CIDRs trusted for the real visitor IP"],
        ["DASHBOARD_PORT / DASHBOARD_HOST", "Dashboard listen address (default 0.0.0.0:8501)"],
        ["COMPOSE_PROJECT_NAME", "Docker project name on the server (tradesense)"],
    ], [72 * mm, 102 * mm], first_col_bold=True))
    s.append(PageBreak())

    # 12 Runbook
    s.append(p("12. Operations runbook", H1))
    s.append(table([
        ["Task", "How"],
        ["Daily check", "Dashboard header shows Engine online and Market open from 09:45; Telegram posts "
         "appear; System health shows cycles completing"],
        ["Set / change dashboard password", "On the server: <font face='Courier'>docker compose exec "
         "ai-trading-brain python -m web_dashboard.set_password</font>, then restart the dashboard container"],
        ["View engine logs", "<font face='Courier'>docker logs --tail 200 ai-trading-brain</font>"],
        ["Restart only TradeSense", "<font face='Courier'>cd /opt/tradesense &amp;&amp; docker compose "
         "restart</font>"],
        ["Pause / resume trading", "Telegram (admin): /pause or /resume"],
        ["Connect Dhan data", "Add DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN to the server .env and restart the engine, "
         "or send /token to the bot in a private chat"],
        ["Change capital", "Edit TOTAL_CAPITAL in the server .env and restart the engine"],
        ["Server reboot", "Only at a quiet time (it restarts every application on the server); all containers "
         "restart automatically"],
    ], [44 * mm, 130 * mm], first_col_bold=True))
    s.append(p("Troubleshooting", H2))
    s.append(table([
        ["Symptom", "Likely cause and fix"],
        ["Dashboard shows 'No dashboard password is set'", "DASHBOARD_PASSWORD_HASH missing: run set_password "
         "and restart the dashboard"],
        ["Engine offline / idle in the header", "No telemetry for 10+ min: check "
         "<font face='Courier'>docker compose ps</font> and the engine logs"],
        ["No trades for days", "Normal early on; check Signals &amp; decisions for the stage rejecting most "
         "signals"],
        ["Feed degraded / YAHOO_FALLBACK", "Yahoo throttling or outage; system falls back and blocks trades "
         "on synthetic prices"],
        ["Telegram silent", "Check the engine log for 'Telegram=enabled'; a basic group converted to a "
         "supergroup gets a new -100... id, so update TELEGRAM_CHAT_ID"],
        ["Locked out of the dashboard", "5 failed attempts: wait 15 minutes"],
    ], [58 * mm, 116 * mm], first_col_bold=True))

    doc.multiBuild(s)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
