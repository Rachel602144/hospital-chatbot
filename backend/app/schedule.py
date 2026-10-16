"""Mock OPD schedule. This is the data the backend validates appointment
requests against. It mirrors the "OPD departments and days" section of
knowledge/hospital_info.md. In a real deployment this would come from the
hospital's appointment system instead of a hard-coded dict.
"""
from datetime import datetime

from .config import IST

MON, TUE, WED, THU, FRI, SAT = range(6)  # Python: Monday=0 ... Sunday=6
ALL_WEEK = {MON, TUE, WED, THU, FRI, SAT}

DEPARTMENTS: dict[str, set[int]] = {
    "General Medicine": ALL_WEEK,
    "Cardiology": ALL_WEEK,
    "Orthopaedics": {MON, WED, FRI, SAT},
    "Paediatrics": ALL_WEEK,
    "Obstetrics and Gynaecology": ALL_WEEK,
    "ENT": {TUE, THU, SAT},
    "Diabetes and Endocrinology": {TUE, THU},
    "Ophthalmology": {MON, TUE, WED, THU, FRI},
}

# Common ways patients say a department name -> the official name.
ALIASES = {
    "general medicine": "General Medicine", "general": "General Medicine",
    "medicine": "General Medicine", "physician": "General Medicine",
    "cardiology": "Cardiology", "heart": "Cardiology", "cardio": "Cardiology",
    "orthopaedics": "Orthopaedics", "orthopedics": "Orthopaedics",
    "ortho": "Orthopaedics", "bones": "Orthopaedics",
    "paediatrics": "Paediatrics", "pediatrics": "Paediatrics",
    "child": "Paediatrics", "children": "Paediatrics",
    "obstetrics and gynaecology": "Obstetrics and Gynaecology",
    "gynaecology": "Obstetrics and Gynaecology", "gynecology": "Obstetrics and Gynaecology",
    "obgyn": "Obstetrics and Gynaecology", "ob-gyn": "Obstetrics and Gynaecology",
    "ent": "ENT", "ear nose throat": "ENT",
    "diabetes and endocrinology": "Diabetes and Endocrinology",
    "diabetes": "Diabetes and Endocrinology", "endocrinology": "Diabetes and Endocrinology",
    "ophthalmology": "Ophthalmology", "eye": "Ophthalmology", "eyes": "Ophthalmology",
}

SLOTS = {"morning", "evening"}
MAX_DAYS_AHEAD = 30


def normalise_department(name: str) -> str | None:
    key = " ".join(name.lower().replace("&", "and").split())
    if key in ALIASES:
        return ALIASES[key]
    for official in DEPARTMENTS:
        if official.lower() == key:
            return official
    return None


def validate_slot(department: str, date_str: str, slot: str | None, today: datetime) -> str | None:
    """Return an error message, or None if the department/date/slot combination is valid."""
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=IST)
    except ValueError:
        return "date must be in YYYY-MM-DD format"
    delta = (day.date() - today.date()).days
    if delta < 0:
        return "that date is in the past"
    if delta > MAX_DAYS_AHEAD:
        return f"requests can only be made up to {MAX_DAYS_AHEAD} days ahead"
    weekday = day.weekday()
    if weekday == 6:
        return "there is no OPD on Sunday"
    if weekday not in DEPARTMENTS[department]:
        days = ", ".join(n for i, n in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]) if i in DEPARTMENTS[department])
        return f"{department} OPD does not run on {day.strftime('%A')}; it runs on {days}"
    if slot == "evening" and weekday == SAT:
        return "Saturday has a morning session only"
    return None
