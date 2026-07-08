#!/usr/bin/env python3
"""
University GPA & Placement Score Calculator Bot
================================================
A production-quality Telegram bot for calculating semester GPA,
CGPA, and placement scores with academic insights.
"""

# --- Imports ---

import os
import logging
import math
from typing import Optional

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest, Forbidden, NetworkError, TimedOut

# --- Configuration ---

load_dotenv()
BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# --- Constants & Subject Data ---

SEMESTER_SUBJECTS: dict[str, list[dict]] = {
    "first": [
        {"name": "English Skill 1", "credit": 3},
        {"name": "Economics",        "credit": 3},
        {"name": "Mathematics",      "credit": 3},
        {"name": "Critical Thinking", "credit": 3},
        {"name": "Geography",        "credit": 3},
        {"name": "Psychology",       "credit": 3},
    ],
    "second": [
        {"name": "English Skill 2",     "credit": 3},
        {"name": "Anthropology",        "credit": 2},
        {"name": "Entrepreneurship",    "credit": 3},
        {"name": "Emerging Tech",       "credit": 3},
        {"name": "Civic",               "credit": 2},
        {"name": "Global Trend",        "credit": 2},
        {"name": "Inclusiveness",       "credit": 2},
        {"name": "History",             "credit": 3},
    ],
}

GRADE_SCALE: list[tuple[int, int, str, float]] = [
    (90, 100, "A+", 4.0),
    (85, 89,  "A",  4.0),
    (80, 84,  "A-", 3.75),
    (75, 79,  "B+", 3.5),
    (70, 74,  "B",  3.0),
    (65, 69,  "B-", 2.75),
    (60, 64,  "C+", 2.5),
    (50, 59,  "C",  2.0),
    (45, 49,  "C-", 1.75),
    (40, 44,  "D",  1.0),
    (35, 39,  "Fx", 0.0),
    (0,  34,  "F",  0.0),
]

SEMESTER_LABELS: dict[str, str] = {
    "first":  "First Semester",
    "second": "Second Semester",
}

SEP = "-" * 28

# --- Session Management (in-memory) ---

user_sessions: dict[int, dict] = {}

def create_session() -> dict:
    return {
        "first_gpa":     None,
        "first_subjects": None,
        "second_gpa":     None,
        "second_subjects": None,
        "state":          "IDLE",
        "temp":           {},
    }

def get_session(user_id: int) -> dict:
    if user_id not in user_sessions:
        user_sessions[user_id] = create_session()
    return user_sessions[user_id]

def reset_session(user_id: int) -> dict:
    user_sessions[user_id] = create_session()
    return user_sessions[user_id]

# --- Calculation Functions ---

def get_grade(score: float) -> tuple[str, float]:
    for low, high, letter, point in GRADE_SCALE:
        if low <= score <= high:
            return letter, point
    return "F", 0.0

def calculate_gpa(scores: list[float], subjects: list[dict]) -> dict:
    total_quality = 0.0
    total_credits = 0
    subject_results: list[dict] = []

    for subject, score in zip(subjects, scores):
        letter, point = get_grade(score)
        credit = subject["credit"]
        quality = point * credit
        total_quality += quality
        total_credits += credit
        subject_results.append({
            "name":   subject["name"],
            "credit": credit,
            "score":  score,
            "letter": letter,
            "point":  point,
            "quality": quality,
        })

    gpa = total_quality / total_credits if total_credits else 0.0
    highest = max(subject_results, key=lambda s: (s["point"], s["score"]))
    lowest  = min(subject_results, key=lambda s: (s["point"], -s["score"]))

    return {
        "gpa":                 gpa,
        "subjects":            subject_results,
        "total_credits":       total_credits,
        "total_quality_points": total_quality,
        "highest":             highest,
        "lowest":              lowest,
    }

def calculate_cgpa(first_gpa: float, second_gpa: float) -> float:
    return (first_gpa + second_gpa) / 2

def calculate_placement(
    first_gpa: float,
    second_gpa: float,
    entrance_score: float,
    placement_exam_score: float,
) -> dict:
    # Formula:
    # CGPA contribution       = (CGPA / 4.0) * 50
    # Entrance contribution   = (Entrance / 600) * 20
    # Placement contribution  = (Placement / 30) * 30
    # Final = sum of the three contributions
    
    cgpa = calculate_cgpa(first_gpa, second_gpa)

    cgpa_contribution       = (cgpa / 4.0) * 50
    entrance_contribution   = (entrance_score / 600) * 20
    placement_contribution  = (placement_exam_score / 30) * 30
    total = cgpa_contribution + entrance_contribution + placement_contribution

    return {
        "first_gpa":              first_gpa,
        "second_gpa":             second_gpa,
        "cgpa":                   cgpa,
        "cgpa_contribution":      cgpa_contribution,
        "entrance_score":         entrance_score,
        "entrance_contribution":  entrance_contribution,
        "placement_exam_score":   placement_exam_score,
        "placement_contribution": placement_contribution,
        "total":                  total,
    }

def calculate_target_gpa(
    current_cgpa: float,
    target_cgpa: float,
    completed_semesters: int = 2,
) -> Optional[float]:
    next_total = completed_semesters + 1
    required_total = target_cgpa * next_total
    required_gpa = required_total - (current_cgpa * completed_semesters)

    if required_gpa > 4.0:
        return None
    return max(required_gpa, 0.0)

# --- Academic Status & Insights ---

def get_academic_status(gpa: float) -> str:
    if gpa >= 3.75:
        return "Excellent"
    elif gpa >= 3.00:
        return "Very Good"
    elif gpa >= 2.00:
        return "Good"
    elif gpa >= 1.00:
        return "Satisfactory"
    else:
        return "Needs Improvement"

def get_class_of_degree(cgpa: float) -> str:
    if cgpa >= 3.75:
        return "First Class Honors"
    elif cgpa >= 3.00:
        return "Second Class Upper"
    elif cgpa >= 2.50:
        return "Second Class Lower"
    elif cgpa >= 2.00:
        return "Third Class"
    elif cgpa >= 1.00:
        return "Pass"
    else:
        return "Fail"

def get_placement_status(score: float) -> str:
    if score >= 85:
        return "Excellent performance"
    elif score >= 70:
        return "Very good performance"
    elif score >= 55:
        return "Good performance"
    elif score >= 40:
        return "Satisfactory performance"
    else:
        return "Needs improvement"

def progress_bar(value: float, maximum: float = 4.0, length: int = 20) -> str:
    ratio = max(0.0, min(value / maximum, 1.0))
    filled = int(ratio * length)
    return "█" * filled + "░" * (length - filled)

def build_grade_distribution(subjects: list[dict]) -> str:
    counts: dict[str, int] = {}
    for s in subjects:
        counts[s["letter"]] = counts.get(s["letter"], 0) + 1

    grade_order = [g[2] for g in GRADE_SCALE]
    sorted_items = sorted(
        counts.items(),
        key=lambda x: grade_order.index(x[0]) if x[0] in grade_order else 99,
    )

    lines = ["Grade Distribution:"]
    for grade, count in sorted_items:
        lines.append(f"  {grade:>3s}  {'█' * count}  {count}")
    return "\n".join(lines)

# --- Input Validation ---

def parse_scores(
    text: str, expected_count: int
) -> tuple[Optional[list[float]], Optional[str]]:
    text = text.strip()
    if not text:
        return None, "empty"

    if "," not in text and any(c.isspace() for c in text):
        return None, "wrong_separator"

    parts = [p.strip() for p in text.split(",")]

    if len(parts) != expected_count:
        return None, "count_mismatch"

    scores: list[float] = []
    for part in parts:
        if part == "":
            return None, "non_numeric"
        try:
            score = float(part)
        except ValueError:
            return None, "non_numeric"
        if score < 0:
            return None, "negative"
        if score > 100:
            return None, "over_100"
        scores.append(score)

    return scores, None

def get_score_error_message(error_type: str) -> str:
    return {
        "empty": (
            "Invalid input.\n\n"
            "Please enter all required scores separated by commas."
        ),
        "wrong_separator": (
            "Invalid separator detected.\n\n"
            "Please use commas to separate scores.\n"
            "Example: 89,78,95,70,85,90"
        ),
        "count_mismatch": (
            "Invalid input.\n\n"
            "Please enter all required scores separated by commas."
        ),
        "non_numeric": (
            "Invalid score detected.\n\n"
            "Only numbers are allowed.\n"
            "Please try again."
        ),
        "negative": (
            "Negative scores are not allowed.\n\n"
            "Please enter valid scores between 0 and 100."
        ),
        "over_100": (
            "Scores must be between 0 and 100.\n"
            "Please enter valid scores."
        ),
    }.get(error_type, "Invalid input. Please try again.")

def validate_number(
    text: str, min_val: float, max_val: float
) -> tuple[Optional[float], Optional[str]]:
    text = text.strip()
    if not text:
        return None, "empty"
    try:
        value = float(text)
    except ValueError:
        return None, "non_numeric"
    if value < min_val:
        return None, "below_min"
    if value > max_val:
        return None, "above_max"
    return value, None

def get_number_error_message(
    error_type: str, min_val: float, max_val: float
) -> str:
    return {
        "empty":      "Please enter a value.",
        "non_numeric": "Invalid input.\n\nOnly numbers are allowed.",
        "below_min":  f"Value cannot be below {min_val}.\nPlease try again.",
        "above_max":  f"Value cannot exceed {max_val}.\nPlease try again.",
    }.get(error_type, "Invalid input. Please try again.")

# --- Formatting Helpers ---

def fmt(n: float) -> str:
    s = f"{n:.10f}".rstrip("0").rstrip(".")
    if not s or s == "-0":
        s = "0"
    return s

# --- Keyboard Builders ---

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Calculate GPA", callback_data="menu_gpa")],
        [InlineKeyboardButton("Calculate Placement Score", callback_data="menu_placement")],
        [InlineKeyboardButton("Academic Dashboard", callback_data="menu_dashboard")],
    ])

def gpa_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("First Semester", callback_data="gpa_first")],
        [InlineKeyboardButton("Second Semester", callback_data="gpa_second")],
        [InlineKeyboardButton("Back", callback_data="menu_main")],
    ])

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Cancel", callback_data="menu_main")],
    ])

def gpa_result_kb(semester: str) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if semester == "first":
        buttons.append([
            InlineKeyboardButton("Calculate Second Semester GPA",
                                 callback_data="gpa_second")
        ])
    elif semester == "second":
        buttons.append([
            InlineKeyboardButton("Calculate First Semester GPA",
                                 callback_data="gpa_first")
        ])
    buttons.append([
        InlineKeyboardButton("Calculate Placement Score",
                             callback_data="menu_placement")
    ])
    buttons.append([
        InlineKeyboardButton("Academic Dashboard",
                             callback_data="menu_dashboard")
    ])
    buttons.append([
        InlineKeyboardButton("Main Menu", callback_data="menu_main")
    ])
    return InlineKeyboardMarkup(buttons)

def gpa_result_from_placement_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Continue to Placement Score",
                              callback_data="menu_placement")],
        [InlineKeyboardButton("Main Menu", callback_data="menu_main")],
    ])

def placement_options_kb(both_exist: bool) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if both_exist:
        buttons.append([
            InlineKeyboardButton("Use Saved GPA",
                                 callback_data="placement_use_saved")
        ])
    buttons.append([
        InlineKeyboardButton("Enter GPA Manually",
                             callback_data="placement_manual")
    ])
    buttons.append([
        InlineKeyboardButton("Calculate Semester GPA",
                             callback_data="placement_calculate")
    ])
    buttons.append([
        InlineKeyboardButton("Back", callback_data="menu_main")
    ])
    return InlineKeyboardMarkup(buttons)

def placement_missing_kb(session: dict) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if session["first_gpa"] is None:
        buttons.append([
            InlineKeyboardButton("Calculate First Semester",
                                 callback_data="gpa_first")
        ])
    if session["second_gpa"] is None:
        buttons.append([
            InlineKeyboardButton("Calculate Second Semester",
                                 callback_data="gpa_second")
        ])
    buttons.append([
        InlineKeyboardButton("Back", callback_data="menu_placement")
    ])
    return InlineKeyboardMarkup(buttons)

def placement_result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Target CGPA Calculator",
                              callback_data="menu_target")],
        [InlineKeyboardButton("Academic Dashboard",
                              callback_data="menu_dashboard")],
        [InlineKeyboardButton("Main Menu", callback_data="menu_main")],
    ])

def dashboard_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Target CGPA Calculator",
                              callback_data="menu_target")],
        [InlineKeyboardButton("Calculate GPA",
                              callback_data="menu_gpa")],
        [InlineKeyboardButton("Calculate Placement Score",
                              callback_data="menu_placement")],
        [InlineKeyboardButton("Main Menu", callback_data="menu_main")],
    ])

def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Main Menu", callback_data="menu_main")],
    ])

# --- Message Builders ---

def build_gpa_result_message(semester: str, result: dict) -> str:
    sem_label = SEMESTER_LABELS[semester]
    status = get_academic_status(result["gpa"])

    lines: list[str] = [
        f"Your {sem_label} GPA: {fmt(result['gpa'])}",
        "",
        f"Total Credits: {result['total_credits']}",
        f"Total Quality Points: {fmt(result['total_quality_points'])}",
        "",
        SEP,
        "Subject Breakdown:",
        "",
    ]

    for s in result["subjects"]:
        lines.append(
            f"  {s['name']}\n"
            f"    Score: {fmt(s['score'])}  |  "
            f"Grade: {s['letter']} ({fmt(s['point'])})  |  "
            f"Credit: {s['credit']}"
        )

    lines += [
        "",
        SEP,
        "",
        f"Highest Subject:",
        f"   {result['highest']['name']} - "
        f"{result['highest']['letter']} ({fmt(result['highest']['point'])})",
        "",
        f"Lowest Subject:",
        f"   {result['lowest']['name']} - "
        f"{result['lowest']['letter']} ({fmt(result['lowest']['point'])})",
        "",
        build_grade_distribution(result["subjects"]),
        "",
        SEP,
        "",
        f"Academic Status: {status}",
        "",
        f"GPA Progress: {progress_bar(result['gpa'])}  "
        f"{fmt(result['gpa'])}/4.0",
        "",
        f"Projected Class: {get_class_of_degree(result['gpa'])}",
        "",
        "Keep improving!",
    ]

    return "\n".join(lines)

def build_placement_result_message(result: dict) -> str:
    status = get_placement_status(result["total"])

    lines: list[str] = [
        "Placement Result:",
        SEP,
        "",
        "First Semester GPA:",
        f"   {fmt(result['first_gpa'])}",
        "",
        "Second Semester GPA:",
        f"   {fmt(result['second_gpa'])}",
        "",
        "CGPA:",
        f"   {fmt(result['cgpa'])}",
        f"   {progress_bar(result['cgpa'])}  {fmt(result['cgpa'])}/4.0",
        f"   Class: {get_class_of_degree(result['cgpa'])}",
        "",
        SEP,
        "",
        "CGPA Contribution:",
        f"   ({fmt(result['cgpa'])} / 4.0) * 50 = "
        f"{fmt(result['cgpa_contribution'])} / 50",
        "",
        "Entrance Exam:",
        f"   {fmt(result['entrance_score'])}/600",
        f"   Entrance Contribution:",
        f"   ({fmt(result['entrance_score'])} / 600) * 20 = "
        f"{fmt(result['entrance_contribution'])} / 20",
        "",
        "Placement Exam:",
        f"   {fmt(result['placement_exam_score'])}/30",
        f"   Placement Contribution:",
        f"   ({fmt(result['placement_exam_score'])} / 30) * 30 = "
        f"{fmt(result['placement_contribution'])} / 30",
        "",
        SEP,
        "",
        "Final Placement Score:",
        f"   {fmt(result['total'])} / 100",
        f"   {progress_bar(result['total'], 100)}  "
        f"{fmt(result['total'])}%",
        "",
        f"{status}",
    ]

    return "\n".join(lines)

def build_dashboard_message(session: dict) -> str:
    has_first = session["first_gpa"] is not None
    has_second = session["second_gpa"] is not None

    lines: list[str] = [
        "Academic Dashboard",
        SEP,
        "",
    ]

    if not has_first and not has_second:
        lines += [
            "No GPA data found yet.",
            "",
            "Calculate your semester GPAs to see insights,",
            "progress bars, grade distribution, and more!",
        ]
        return "\n".join(lines)

    if has_first:
        gpa = session["first_gpa"]
        lines += [
            "First Semester GPA:",
            f"   {fmt(gpa)}",
            f"   {progress_bar(gpa)}  {fmt(gpa)}/4.0",
            f"   Status: {get_academic_status(gpa)}",
        ]
        if session["first_subjects"]:
            highest = max(session["first_subjects"], key=lambda s: s["point"])
            lowest  = min(session["first_subjects"], key=lambda s: s["point"])
            lines += [
                f"   Best: {highest['name']} ({highest['letter']})",
                f"   Needs work: {lowest['name']} ({lowest['letter']})",
            ]
        lines.append("")

    if has_second:
        gpa = session["second_gpa"]
        lines += [
            "Second Semester GPA:",
            f"   {fmt(gpa)}",
            f"   {progress_bar(gpa)}  {fmt(gpa)}/4.0",
            f"   Status: {get_academic_status(gpa)}",
        ]
        if session["second_subjects"]:
            highest = max(session["second_subjects"], key=lambda s: s["point"])
            lowest  = min(session["second_subjects"], key=lambda s: s["point"])
            lines += [
                f"   Best: {highest['name']} ({highest['letter']})",
                f"   Needs work: {lowest['name']} ({lowest['letter']})",
            ]
        lines.append("")

    if has_first and has_second:
        cgpa = calculate_cgpa(session["first_gpa"], session["second_gpa"])
        lines += [
            SEP,
            "",
            "CGPA (Cumulative GPA):",
            f"   {fmt(cgpa)}",
            f"   {progress_bar(cgpa)}  {fmt(cgpa)}/4.0",
            f"   Class: {get_class_of_degree(cgpa)}",
            f"   Status: {get_academic_status(cgpa)}",
            "",
        ]

        diff = session["second_gpa"] - session["first_gpa"]
        if diff > 0.001:
            lines.append(f"Trend: +{fmt(diff)}  (improving!)")
        elif diff < -0.001:
            lines.append(f"Trend: {fmt(diff)}  (declining - keep pushing!)")
        else:
            lines.append("Trend: Stable")
        lines.append("")

        next_quarter = math.ceil(cgpa * 4 + 0.001) / 4
        if next_quarter <= 4.0 and next_quarter > cgpa + 0.001:
            needed = calculate_target_gpa(cgpa, next_quarter)
            if needed is not None and needed <= 4.0:
                lines += [
                    "Quick Insight:",
                    f"   To reach CGPA {fmt(next_quarter)}, you need",
                    f"   at least {fmt(needed)} in your next semester.",
                    "",
                ]

    lines += [
        SEP,
        "",
    ]

    if not (has_first and has_second):
        missing = []
        if not has_first:
            missing.append("First Semester")
        if not has_second:
            missing.append("Second Semester")
        lines.append(f"Missing: {', '.join(missing)}")
        lines.append("Calculate remaining GPA(s) for full insights!")
        lines.append("")

    return "\n".join(lines)

def build_score_prompt(semester: str) -> str:
    subjects = SEMESTER_SUBJECTS[semester]
    sem_label = SEMESTER_LABELS[semester]

    lines: list[str] = [
        f"{sem_label} GPA Calculation",
        "",
        "Enter your scores in the exact order below.",
        "Separate each score using commas.",
        "",
    ]
    for i, subj in enumerate(subjects, 1):
        lines.append(f"{i}. {subj['name']} ({subj['credit']} credits)")

    example_scores = ", ".join("90" for _ in subjects)
    lines += [
        "",
        "Example:",
        example_scores,
        "",
        "Decimals are accepted (e.g. 89.5)",
        "Type /start at any time to cancel",
    ]
    return "\n".join(lines)

# --- Safe Edit Helper ---

async def safe_edit(query, text: str, reply_markup=None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            logger.debug("Message content unchanged - skipping edit.")
        else:
            logger.warning(f"Edit failed ({exc}); sending new message.")
            try:
                await query.message.reply_text(text, reply_markup=reply_markup)
            except Exception:
                pass

# --- Menu Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /start - reset session and show the main menu.
    user_id = update.effective_user.id
    reset_session(user_id)
    logger.info(f"User {user_id} started/restarted the bot.")

    welcome = (
        "Welcome!\n\n"
        "I'm your University GPA & Placement Score Calculator.\n\n"
        "I can help you:\n"
        "- Calculate semester GPA\n"
        "- Calculate CGPA & placement score\n"
        "- Track your academic performance\n\n"
        "Choose an option:"
    )
    await update.message.reply_text(welcome, reply_markup=main_menu_kb())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    session = get_session(user_id)
    data = query.data
    logger.info(f"User {user_id} pressed: {data}")

    MENU_RESET_CALLBACKS = {
        "menu_main", "menu_gpa", "menu_placement",
        "menu_dashboard", "menu_target",
    }
    if data in MENU_RESET_CALLBACKS:
        session["state"] = "IDLE"
        session["temp"] = {}

    if data == "menu_main":
        await show_main_menu(query)
    elif data == "menu_gpa":
        await show_gpa_menu(query)
    elif data == "menu_placement":
        await show_placement_menu(query, session)
    elif data == "menu_dashboard":
        await show_dashboard(query, session)
    elif data == "menu_target":
        await show_target_calculator(query, session)
    elif data == "gpa_first":
        await start_gpa_calculation(query, session, "first")
    elif data == "gpa_second":
        await start_gpa_calculation(query, session, "second")
    elif data == "placement_use_saved":
        await placement_use_saved(query, session)
    elif data == "placement_manual":
        await placement_manual_start(query, session)
    elif data == "placement_calculate":
        await placement_calculate_missing(query, session)
    else:
        logger.warning(f"Unknown callback data: {data}")

async def show_main_menu(query) -> None:
    text = "Welcome!\n\nChoose an option:"
    await safe_edit(query, text, main_menu_kb())

async def show_gpa_menu(query) -> None:
    text = "GPA Calculator\n\nChoose semester:"
    await safe_edit(query, text, gpa_menu_kb())

async def start_gpa_calculation(query, session: dict, semester: str) -> None:
    session["state"] = f"AWAITING_{semester.upper()}_SCORES"
    session["temp"]["current_semester"] = semester
    text = build_score_prompt(semester)
    await safe_edit(query, text, cancel_kb())

async def show_placement_menu(query, session: dict) -> None:
    has_first = session["first_gpa"] is not None
    has_second = session["second_gpa"] is not None
    both_exist = has_first and has_second

    lines: list[str] = ["Placement Score Calculator", ""]

    if both_exist:
        lines += [
            "I found your saved GPA:",
            "",
            f"First Semester GPA: {fmt(session['first_gpa'])}",
            f"Second Semester GPA: {fmt(session['second_gpa'])}",
            "",
            "Would you like to use these values?",
        ]
    elif has_first or has_second:
        lines += [
            "I found partial GPA data:",
            "",
        ]
        if has_first:
            lines.append(f"First Semester GPA: {fmt(session['first_gpa'])}")
        else:
            lines.append("First Semester GPA: Not calculated")
        if has_second:
            lines.append(f"Second Semester GPA: {fmt(session['second_gpa'])}")
        else:
            lines.append("Second Semester GPA: Not calculated")
        lines += [
            "",
            "You need both semester GPAs to calculate placement score.",
            "Choose an option:",
        ]
    else:
        lines += [
            "No GPA data found.",
            "",
            "You need both semester GPAs to calculate placement score.",
            "Choose an option:",
        ]

    await safe_edit(query, "\n".join(lines), placement_options_kb(both_exist))

async def placement_use_saved(query, session: dict) -> None:
    session["temp"]["first_gpa"] = session["first_gpa"]
    session["temp"]["second_gpa"] = session["second_gpa"]
    session["state"] = "AWAITING_ENTRANCE_SCORE"

    text = (
        "Using saved GPA values.\n\n"
        f"First Semester GPA: {fmt(session['first_gpa'])}\n"
        f"Second Semester GPA: {fmt(session['second_gpa'])}\n\n"
        f"CGPA: {fmt(calculate_cgpa(session['first_gpa'], session['second_gpa']))}\n\n"
        "Now enter your entrance exam score (out of 600):"
    )
    await safe_edit(query, text, cancel_kb())

async def placement_manual_start(query, session: dict) -> None:
    session["state"] = "AWAITING_FIRST_GPA_MANUAL"
    text = (
        "Manual GPA Entry\n\n"
        "Enter your First Semester GPA (0.0 - 4.0):"
    )
    await safe_edit(query, text, cancel_kb())

async def placement_calculate_missing(query, session: dict) -> None:
    has_first = session["first_gpa"] is not None
    has_second = session["second_gpa"] is not None

    session["temp"]["from_placement"] = True

    lines: list[str] = ["Calculate Missing Semester GPA", ""]

    if has_first and has_second:
        lines += [
            "Both semester GPAs are already calculated!",
            "",
            f"First Semester GPA: {fmt(session['first_gpa'])}",
            f"Second Semester GPA: {fmt(session['second_gpa'])}",
            "",
            "You can proceed with placement calculation.",
        ]
        await show_placement_menu(query, session)
        return

    if not has_first and not has_second:
        lines.append("You need to calculate both semester GPAs.")
        lines.append("Start with either semester:")
    elif not has_first:
        lines.append("You need to calculate your First Semester GPA.")
    elif not has_second:
        lines.append("You need to calculate your Second Semester GPA.")

    await safe_edit(query, "\n".join(lines), placement_missing_kb(session))

async def show_dashboard(query, session: dict) -> None:
    text = build_dashboard_message(session)
    await safe_edit(query, text, dashboard_kb())

async def show_target_calculator(query, session: dict) -> None:
    has_first = session["first_gpa"] is not None
    has_second = session["second_gpa"] is not None

    if not has_first or not has_second:
        text = (
            "Target CGPA Calculator\n\n"
            "You need both semester GPAs calculated first.\n"
            "Please calculate your GPAs before using this feature."
        )
        await safe_edit(query, text, back_to_main_kb())
        return

    cgpa = calculate_cgpa(session["first_gpa"], session["second_gpa"])
    session["state"] = "AWAITING_TARGET_CGPA"

    text = (
        "Target CGPA Calculator\n"
        f"{SEP}\n\n"
        f"Current CGPA: {fmt(cgpa)}\n"
        f"Class: {get_class_of_degree(cgpa)}\n\n"
        "Enter your target CGPA (0.0 - 4.0):\n\n"
        "This will calculate the GPA you need\n"
        "in your next semester to reach your target."
    )
    await safe_edit(query, text, cancel_kb())

# --- Text-Input Handlers ---

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session = get_session(user_id)
    text = update.message.text
    state = session.get("state", "IDLE")

    logger.info(f"User {user_id} text in state {state}: {text[:60]}...")

    if state == "IDLE":
        await update.message.reply_text(
            "Please use the menu buttons to navigate.\n"
            "Type /start to see the main menu.",
            reply_markup=main_menu_kb(),
        )
        return

    if state == "AWAITING_FIRST_SCORES":
        await process_gpa_scores(update, session, "first", text)
    elif state == "AWAITING_SECOND_SCORES":
        await process_gpa_scores(update, session, "second", text)
    elif state == "AWAITING_FIRST_GPA_MANUAL":
        await process_manual_gpa(update, session, "first", text)
    elif state == "AWAITING_SECOND_GPA_MANUAL":
        await process_manual_gpa(update, session, "second", text)
    elif state == "AWAITING_ENTRANCE_SCORE":
        await process_entrance_score(update, session, text)
    elif state == "AWAITING_PLACEMENT_SCORE":
        await process_placement_exam_score(update, session, text)
    elif state == "AWAITING_TARGET_CGPA":
        await process_target_cgpa(update, session, text)
    else:
        await update.message.reply_text(
            "Something went wrong. Type /start to restart.",
            reply_markup=main_menu_kb(),
        )

async def process_gpa_scores(
    update: Update, session: dict, semester: str, text: str
) -> None:
    subjects = SEMESTER_SUBJECTS[semester]
    scores, error = parse_scores(text, len(subjects))

    if error:
        await update.message.reply_text(get_score_error_message(error))
        return

    result = calculate_gpa(scores, subjects)

    session[f"{semester}_gpa"] = result["gpa"]
    session[f"{semester}_subjects"] = result["subjects"]
    session["state"] = "IDLE"

    result_text = build_gpa_result_message(semester, result)

    if session["temp"].get("from_placement"):
        session["temp"].pop("from_placement", None)
        kb = gpa_result_from_placement_kb()
    else:
        kb = gpa_result_kb(semester)

    await update.message.reply_text(result_text, reply_markup=kb)

async def process_manual_gpa(
    update: Update, session: dict, semester: str, text: str
) -> None:
    value, error = validate_number(text, 0.0, 4.0)
    if error:
        await update.message.reply_text(
            get_number_error_message(error, 0.0, 4.0)
        )
        return

    session["temp"][f"{semester}_gpa"] = value

    if semester == "first":
        session["state"] = "AWAITING_SECOND_GPA_MANUAL"
        await update.message.reply_text(
            f"First Semester GPA: {fmt(value)}\n\n"
            "Now enter your Second Semester GPA (0.0 - 4.0):"
        )
    else:
        session["state"] = "AWAITING_ENTRANCE_SCORE"
        first = session["temp"].get("first_gpa", session["first_gpa"])
        await update.message.reply_text(
            f"Second Semester GPA: {fmt(value)}\n\n"
            f"First Semester GPA: {fmt(first)}\n"
            f"Second Semester GPA: {fmt(value)}\n"
            f"CGPA: {fmt(calculate_cgpa(first, value))}\n\n"
            "Now enter your entrance exam score (out of 600):"
        )

async def process_entrance_score(
    update: Update, session: dict, text: str
) -> None:
    value, error = validate_number(text, 0, 600)
    if error:
        await update.message.reply_text(get_number_error_message(error, 0, 600))
        return

    session["temp"]["entrance_score"] = value
    session["state"] = "AWAITING_PLACEMENT_SCORE"

    await update.message.reply_text(
        f"Entrance Exam Score: {fmt(value)}/600\n\n"
        "Now enter your placement exam score (out of 30):"
    )

async def process_placement_exam_score(
    update: Update, session: dict, text: str
) -> None:
    value, error = validate_number(text, 0, 30)
    if error:
        await update.message.reply_text(get_number_error_message(error, 0, 30))
        return

    first_gpa = session["temp"].get("first_gpa", session["first_gpa"])
    second_gpa = session["temp"].get("second_gpa", session["second_gpa"])
    entrance = session["temp"]["entrance_score"]

    result = calculate_placement(first_gpa, second_gpa, entrance, value)

    if session["first_gpa"] is None:
        session["first_gpa"] = first_gpa
    if session["second_gpa"] is None:
        session["second_gpa"] = second_gpa

    session["state"] = "IDLE"
    session["temp"] = {}

    result_text = build_placement_result_message(result)
    await update.message.reply_text(result_text, reply_markup=placement_result_kb())

async def process_target_cgpa(
    update: Update, session: dict, text: str
) -> None:
    target, error = validate_number(text, 0.0, 4.0)
    if error:
        await update.message.reply_text(
            get_number_error_message(error, 0.0, 4.0)
        )
        return

    cgpa = calculate_cgpa(session["first_gpa"], session["second_gpa"])

    lines: list[str] = [
        "Target CGPA Analysis",
        SEP,
        "",
        f"Current CGPA: {fmt(cgpa)}",
        f"Target CGPA:  {fmt(target)}",
        "",
    ]

    if target <= cgpa + 0.0001:
        lines += [
            "You've already reached this target!",
            f"Your current CGPA ({fmt(cgpa)}) >= Target ({fmt(target)})",
        ]
    else:
        needed = calculate_target_gpa(cgpa, target)
        if needed is None:
            lines += [
                "This target is unreachable in one semester.",
                "You would need a GPA above 4.0, which is not possible.",
                "",
                "Consider adjusting your target or extending your timeline.",
            ]
        else:
            lines += [
                f"You need a GPA of at least {fmt(needed)}",
                f"   in your next semester to reach {fmt(target)}.",
                "",
            ]
            if needed >= 3.75:
                lines.append("This is a very challenging target!")
                lines.append("   You'll need near-perfect performance.")
            elif needed >= 3.0:
                lines.append("This is achievable with consistent effort!")
            elif needed >= 2.0:
                lines.append("This is a realistic target!")
            else:
                lines.append("This target is easily achievable!")

    lines += ["", SEP]
    session["state"] = "IDLE"
    await update.message.reply_text("\n".join(lines), reply_markup=back_to_main_kb())

# --- Error Handler ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    logger.error(f"Exception while handling update: {error}", exc_info=error)

    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning("Network issue - request will be retried automatically.")
        return
    if isinstance(error, Forbidden):
        logger.warning("Bot was blocked by the user.")
        return

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "An unexpected error occurred.\n"
                    "Type /start to restart the bot."
                ),
                reply_markup=main_menu_kb(),
            )
        except Exception:
            pass

# --- Main Entry Point ---

def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found! Set it in your .env file.")
        raise SystemExit("Missing BOT_TOKEN - exiting.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    app.add_error_handler(error_handler)

    logger.info("Bot is starting... Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
