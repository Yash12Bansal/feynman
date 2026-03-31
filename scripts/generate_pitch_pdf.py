"""Generate Feynman 2-page investor pitch memo PDF."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
)
from reportlab.lib import colors
import os

OUTPUT_PATH = os.path.expanduser("~/Desktop/Feynman-Investor-Pitch.pdf")

# Colors
NAVY = HexColor("#1a2744")
DARK_GRAY = HexColor("#2d2d2d")
MID_GRAY = HexColor("#555555")
LIGHT_GRAY = HexColor("#e8e8e8")
ACCENT = HexColor("#1a5276")
WHITE = colors.white

# Page setup
PAGE_W, PAGE_H = letter
MARGIN_LEFT = 0.7 * inch
MARGIN_RIGHT = 0.7 * inch
MARGIN_TOP = 0.55 * inch
MARGIN_BOTTOM = 0.5 * inch


def build_styles():
    s = {}

    s["title"] = ParagraphStyle(
        "title",
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=NAVY,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle",
        fontName="Helvetica",
        fontSize=9.5,
        leading=12,
        textColor=MID_GRAY,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    s["h1"] = ParagraphStyle(
        "h1",
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        textColor=NAVY,
        spaceBefore=10,
        spaceAfter=4,
    )
    s["h2"] = ParagraphStyle(
        "h2",
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=ACCENT,
        spaceBefore=7,
        spaceAfter=2,
    )
    s["body"] = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=DARK_GRAY,
        alignment=TA_JUSTIFY,
        spaceAfter=4,
    )
    s["body_tight"] = ParagraphStyle(
        "body_tight",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=DARK_GRAY,
        alignment=TA_JUSTIFY,
        spaceAfter=2,
    )
    s["bullet"] = ParagraphStyle(
        "bullet",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=DARK_GRAY,
        leftIndent=12,
        spaceAfter=1.5,
    )
    s["bullet_bold_lead"] = ParagraphStyle(
        "bullet_bold_lead",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=DARK_GRAY,
        leftIndent=12,
        spaceAfter=1.5,
    )
    s["small"] = ParagraphStyle(
        "small",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=MID_GRAY,
        spaceAfter=2,
    )
    s["table_header"] = ParagraphStyle(
        "table_header",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=WHITE,
    )
    s["table_cell"] = ParagraphStyle(
        "table_cell",
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=DARK_GRAY,
    )
    s["table_cell_bold"] = ParagraphStyle(
        "table_cell_bold",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=DARK_GRAY,
    )
    return s


def bullet(text, style):
    return Paragraph(f"\u2022  {text}", style)


def bold_lead_bullet(bold_part, rest, style):
    return Paragraph(f"\u2022  <b>{bold_part}</b> {rest}", style)


def divider():
    return HRFlowable(
        width="100%", thickness=0.5, color=LIGHT_GRAY, spaceBefore=6, spaceAfter=6
    )


def build_page1(S):
    """The Story."""
    elements = []

    # Title
    elements.append(Paragraph("FEYNMAN", S["title"]))
    elements.append(
        Paragraph(
            "The AI Teacher That Makes Every Classroom World-Class",
            S["subtitle"],
        )
    )
    elements.append(divider())

    # The Hook
    elements.append(
        Paragraph(
            "India spends <b>$30B/year on private tutoring</b> because classroom teaching isn\u2019t enough. "
            "Not because teachers don\u2019t care \u2014 because one teacher physically cannot give world-class "
            "explanations, real-time visual aids, and individual attention to 40 students simultaneously. "
            "<b>Feynman can.</b>",
            S["body"],
        )
    )

    # The Problem
    elements.append(Paragraph("The Problem", S["h1"]))
    elements.append(
        Paragraph(
            "India faces a structural STEM teaching crisis. 25% of government school teaching positions are vacant. "
            "Even in premium private schools, finding teachers who can explain physics intuitively, draw diagrams in real-time, "
            "and adapt to each student\u2019s pace is nearly impossible. The result: a $30B private tutoring industry "
            "(Kota coaching, BYJU\u2019S, Allen, Unacademy) \u2014 proof that parents know classrooms aren\u2019t enough, "
            "and are desperate for better teaching.",
            S["body"],
        )
    )

    # The Solution
    elements.append(Paragraph("The Solution", S["h1"]))
    elements.append(
        Paragraph(
            "Feynman is an AI teacher that teaches from the classroom\u2019s big screen. It delivers real-time voice "
            "explanations paired with live visual aids \u2014 diagrams drawn stroke by stroke, equations built term by term, "
            "animated explanations that make abstract concepts tangible. Students interact verbally, just like a real classroom. "
            "The human teacher stays in the room as mentor and guide: Feynman handles the lecture, "
            "the teacher handles the humans. Think of it as giving every classroom a Richard Feynman-level explainer.",
            S["body"],
        )
    )

    # Why Now
    elements.append(Paragraph("Why Now", S["h1"]))
    elements.append(
        bold_lead_bullet(
            "Real-time voice AI latency &lt;200ms",
            "\u2014 natural, interruptible conversation is now possible (LiveKit/WebRTC)",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Frontier LLMs can genuinely teach,",
            "not just answer questions \u2014 they reason, adapt, and explain",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Post-pandemic tech comfort:",
            "smart classrooms are standard in premium Indian schools",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "NEP 2020",
            "mandates technology integration in Indian education",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "$30B coaching industry",
            "proves parents will pay for better teaching \u2014 demand is validated",
            S["bullet"],
        )
    )

    # How It Works
    elements.append(Paragraph("How It Works", S["h1"]))
    elements.append(
        Paragraph(
            "Feynman\u2019s architecture is purpose-built for real-time classroom teaching, not adapted from a chatbot:",
            S["body_tight"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Structured visual generation:",
            "AI generates typed instructions \u2192 deterministic renderer executes. No hallucinated visuals \u2014 every diagram is correct by construction.",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Tree-structured sessions:",
            "Main lesson flow continues linearly. When a student asks a doubt, Feynman branches (like git), resolves the doubt with new analogies and visuals, then merges back \u2014 never losing its place.",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Per-student knowledge graph:",
            "Tracks what each student knows, how they learn best, and where gaps exist. Teaching improves over time.",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Teacher dashboard:",
            "Real-time insights on student comprehension, class-wide gaps, and individual struggles. Teacher retains full control \u2014 can pause, redirect, or override anytime.",
            S["bullet"],
        )
    )

    # Technology (compact)
    elements.append(Paragraph("Built With", S["h2"]))
    elements.append(
        Paragraph(
            "Custom async state machine (Python/FastAPI) \u2022 LiveKit WebRTC (real-time voice) \u2022 "
            "React + Canvas/WebGL (visual rendering) \u2022 41-component diagram engine across 5 STEM domains \u2022 "
            "Dual Anthropic Claude + OpenAI GPT (frontier for teaching, efficient for sub-tasks)",
            S["small"],
        )
    )

    return elements


def build_page2(S):
    """The Business."""
    elements = []

    elements.append(Paragraph("The Business", S["title"]))
    elements.append(Spacer(1, 4))
    elements.append(divider())

    # Market
    elements.append(Paragraph("Market Opportunity", S["h1"]))

    table_data = [
        [
            Paragraph("Metric", S["table_header"]),
            Paragraph("Value", S["table_header"]),
        ],
        [
            Paragraph("India K-12 EdTech Market", S["table_cell"]),
            Paragraph("$6\u201310B (2025), 20%+ CAGR", S["table_cell_bold"]),
        ],
        [
            Paragraph("India Private Tutoring Market", S["table_cell"]),
            Paragraph("$30B+ (validated demand)", S["table_cell_bold"]),
        ],
        [
            Paragraph("Global AI in Education", S["table_cell"]),
            Paragraph(
                "$8B \u2192 $137B by 2035 (34\u201343% CAGR)", S["table_cell_bold"]
            ),
        ],
        [
            Paragraph("Our SAM (India Premium Private)", S["table_cell"]),
            Paragraph(
                "$1.35B (15K schools \u00d7 25 classrooms \u00d7 $3K/yr)",
                S["table_cell_bold"],
            ),
        ],
        [
            Paragraph("Year 1\u20132 Target (SOM)", S["table_cell"]),
            Paragraph(
                "100\u2013500 classrooms \u2192 $300K\u2013$1.5M ARR",
                S["table_cell_bold"],
            ),
        ],
    ]

    col_widths = [2.8 * inch, 3.8 * inch]
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("BACKGROUND", (0, 1), (-1, -1), HexColor("#f7f9fb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f7f9fb"), WHITE]),
                ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(t)

    # Go-to-Market
    elements.append(Paragraph("Go-to-Market", S["h1"]))
    elements.append(
        bold_lead_bullet(
            "Phase 1 \u2014 Premium Private K-12:",
            "~15,000\u201320,000 schools (DPS, Ryan, Amity, Podar). Infrastructure ready, budgets exist (INR 2\u201310L/yr tech spend), "
            "2\u20134 month sales cycle. Principal + Trust = fast decisions.",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Land:",
            "3\u20135 pilot school partners \u2192 prove learning outcome improvements with data.",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Expand:",
            "School chains create leverage \u2014 DPS has 200+ branches, one deal = hundreds of classrooms. "
            "Competitive pressure drives adoption within peer groups.",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Phase 2\u20133:",
            "Regular private schools (350K+) \u2192 Government schools (1M+, with policy partnerships) \u2192 Global.",
            S["bullet"],
        )
    )

    # Why Everyone Wins
    elements.append(Paragraph("Why Everyone Wins", S["h1"]))

    wins_data = [
        [
            Paragraph("Stakeholder", S["table_header"]),
            Paragraph("How They Win", S["table_header"]),
        ],
        [
            Paragraph("Teachers", S["table_cell_bold"]),
            Paragraph(
                "Empowered, not replaced. Stay in the room, stay in control. Dashboard gives superpowers: "
                "see who\u2019s struggling, who\u2019s ahead. Time freed for mentoring and individual attention.",
                S["table_cell"],
            ),
        ],
        [
            Paragraph("Students", S["table_cell_bold"]),
            Paragraph(
                "World-class STEM explanations every day, regardless of school or teacher. Doubts celebrated, "
                "not shushed. AI adapts pace to the class in real-time.",
                S["table_cell"],
            ),
        ],
        [
            Paragraph("Parents", S["table_cell_bold"]),
            Paragraph(
                "Reduces INR 50K\u20133L/yr coaching dependency. Full transparency on child\u2019s learning via "
                "knowledge graph. Consistent quality every day.",
                S["table_cell"],
            ),
        ],
        [
            Paragraph("Schools", S["table_cell_bold"]),
            Paragraph(
                "Competitive edge for admissions. Reduces great-teacher dependency (India\u2019s #1 school problem). "
                "NEP 2020 aligned. INR 2,500/classroom/month vs INR 50K+/month for a great teacher.",
                S["table_cell"],
            ),
        ],
    ]

    wins_table = Table(wins_data, colWidths=[1.1 * inch, 5.5 * inch])
    wins_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f7f9fb"), WHITE]),
                ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(wins_table)

    # Business Model
    elements.append(Paragraph("Business Model", S["h1"]))
    elements.append(
        bold_lead_bullet(
            "SaaS pricing:",
            "INR 2,500/classroom/month (~$30) \u2014 schools already pay more for smart board software",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Unit economics:",
            "Per-session AI cost ~$1.50\u20133.00. Gross margins 70\u201380% at scale.",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Expansion revenue:",
            "More subjects, more classrooms, tablet companion upsell, knowledge graph analytics for parents",
            S["bullet"],
        )
    )

    # Team
    elements.append(Paragraph("Team", S["h1"]))
    elements.append(
        Paragraph(
            "<b>Yash Bansal</b> \u2014 ML Engineer (Risa Labs), full-stack builder. "
            "Deep technical foundation already built: custom async teaching state machine, real-time visual engine "
            "with 41 components across 5 STEM domains, living whiteboard with hand-drawn rendering, "
            "LiveKit voice integration architecture. Shipped apps and products.",
            S["body_tight"],
        )
    )

    # The Ask
    elements.append(Paragraph("The Ask", S["h1"]))
    elements.append(
        Paragraph(
            "<b>Raising pre-seed</b> to go from working prototype to 5 pilot schools and first paying customers.",
            S["body_tight"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Milestones:",
            "5 pilot schools \u2192 50 paying schools \u2192 Series A",
            S["bullet"],
        )
    )
    elements.append(
        bold_lead_bullet(
            "Use of funds:",
            "Engineering (60%) \u2022 Pilot partnerships & sales (25%) \u2022 Operations (15%)",
            S["bullet"],
        )
    )

    # Footer
    elements.append(Spacer(1, 8))
    elements.append(divider())
    elements.append(
        Paragraph(
            "Contact: yash@feynman.ai  \u2022  Built in India, for the world",
            ParagraphStyle(
                "footer",
                fontName="Helvetica",
                fontSize=8,
                leading=10,
                textColor=MID_GRAY,
                alignment=TA_CENTER,
            ),
        )
    )

    return elements


def main():
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=letter,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
    )

    S = build_styles()
    elements = []
    elements.extend(build_page1(S))
    elements.append(PageBreak())
    elements.extend(build_page2(S))

    doc.build(elements)
    print(f"PDF generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
