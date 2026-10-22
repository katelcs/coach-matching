import os
import json
from datetime import timezone as dt_timezone, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_dance.contrib.google import make_google_blueprint, google
from oauthlib.oauth2.rfc6749.errors import TokenExpiredError
from database import init_db, get_db, close_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")

# Trust Railway's HTTPS proxy so OAuth redirects use https://
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.jinja_env.filters["from_json"] = json.loads
app.teardown_appcontext(close_db)

EASTERN = ZoneInfo('America/New_York')


def _to_eastern(dt):
    if not dt:
        return '—'
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(EASTERN).strftime('%Y-%m-%d %H:%M ET')


def _business_hours_elapsed(start_dt, end_dt):
    """Hours between two timestamps counting only 9am–5pm ET each day."""
    if not start_dt or not end_dt:
        return None
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=dt_timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=dt_timezone.utc)
    start_et = start_dt.astimezone(EASTERN)
    end_et   = end_dt.astimezone(EASTERN)
    if end_et <= start_et:
        return 0.0
    total_secs = 0.0
    current = start_et
    while current.date() <= end_et.date():
        w_start = current.replace(hour=9,  minute=0, second=0, microsecond=0)
        w_end   = current.replace(hour=17, minute=0, second=0, microsecond=0)
        seg_start = max(current if current.date() == start_et.date() else w_start, w_start)
        seg_end   = min(end_et  if current.date() == end_et.date()   else w_end,   w_end)
        if seg_end > seg_start:
            total_secs += (seg_end - seg_start).total_seconds()
        current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return round(total_secs / 3600, 1)


STAFF_COACHES = [
    {"name": "Gaby",    "email": "gaby@lcs.internal",    "country": "", "timezone": "", "availability": "{}"},
    {"name": "Diana",   "email": "diana@lcs.internal",   "country": "", "timezone": "", "availability": "{}"},
    {"name": "Carla",   "email": "carla@lcs.internal",   "country": "", "timezone": "", "availability": "{}"},
    {"name": "Michael", "email": "michael@lcs.internal", "country": "", "timezone": "", "availability": "{}"},
    {"name": "Caro",    "email": "caro@lcs.internal",    "country": "", "timezone": "", "availability": "{}"},
    {"name": "Ailen",   "email": "ailen@lcs.internal",   "country": "", "timezone": "", "availability": "{}"},
    {"name": "Tamara",  "email": "tamara@lcs.internal",  "country": "", "timezone": "", "availability": "{}"},
]

APPROVED_COACH_EMAILS = [e.strip() for e in os.environ.get("APPROVED_COACH_EMAILS", "").split(",") if e.strip()]
APPROVED_ADMIN_EMAILS = [e.strip() for e in os.environ.get("APPROVED_ADMIN_EMAILS", "").split(",") if e.strip()]

@app.context_processor
def inject_user():
    email = session.get("user_email")
    is_admin = bool(email and (not APPROVED_ADMIN_EMAILS or email in APPROVED_ADMIN_EMAILS))
    return {"current_user": email, "is_admin": is_admin}

google_bp = make_google_blueprint(
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
    redirect_to="coach_form",
)
app.register_blueprint(google_bp, url_prefix="/login")

SPANISH_COUNTRIES = [
    "Argentina", "Bolivia", "Chile", "Colombia", "Costa Rica", "Cuba",
    "Dominican Republic", "Ecuador", "El Salvador", "Equatorial Guinea",
    "Guatemala", "Honduras", "Mexico", "Nicaragua", "Panama", "Paraguay",
    "Peru", "Puerto Rico", "Spain", "Uruguay", "Venezuela",
]

def _fmt_et(h):
    if h == 0:   return "12:00 AM"
    if h < 12:   return f"{h}:00 AM"
    if h == 12:  return "12:00 PM"
    return f"{h - 12}:00 PM"

ET_HOURS   = list(range(3, 24)) + [0, 1]  # 3 AM … 11 PM ET, then 12 AM, 1 AM
TIME_SLOTS = [_fmt_et(h) for h in ET_HOURS]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

TIMEZONES = [
    ("America/New_York",              "UTC -5 (New York)"),
    ("America/Chicago",               "UTC -6 (Chicago)"),
    ("America/Denver",                "UTC -7 (Denver)"),
    ("America/Los_Angeles",           "UTC -8 (Los Angeles)"),
    ("America/Anchorage",             "UTC -9 (Anchorage)"),
    ("Pacific/Honolulu",              "UTC -10 (Honolulu)"),
    ("America/Mexico_City",           "UTC -6 (Mexico City)"),
    ("America/Bogota",                "UTC -5 (Bogotá)"),
    ("America/Lima",                  "UTC -5 (Lima)"),
    ("America/Santiago",              "UTC -4 (Santiago)"),
    ("America/Argentina/Buenos_Aires","UTC -3 (Buenos Aires)"),
    ("America/Caracas",               "UTC -4 (Caracas)"),
    ("America/La_Paz",                "UTC -4 (La Paz)"),
    ("America/Guayaquil",             "UTC -5 (Guayaquil)"),
    ("America/Asuncion",              "UTC -4 (Asunción)"),
    ("America/Montevideo",            "UTC -3 (Montevideo)"),
    ("America/Panama",                "UTC -5 (Panama City)"),
    ("America/Costa_Rica",            "UTC -6 (San José)"),
    ("America/Managua",               "UTC -6 (Managua)"),
    ("America/Tegucigalpa",           "UTC -6 (Tegucigalpa)"),
    ("America/Guatemala",             "UTC -6 (Guatemala City)"),
    ("America/El_Salvador",           "UTC -6 (San Salvador)"),
    ("America/Havana",                "UTC -5 (Havana)"),
    ("America/Santo_Domingo",         "UTC -4 (Santo Domingo)"),
    ("Europe/Madrid",                 "UTC +1 (Madrid)"),
    ("UTC",                           "UTC +0 (UTC)"),
]


@app.route("/")
def index():
    return render_template("index.html")


def _coach_covered_slots():
    """Return ({day|slot covered}, {day|slot: [country, ...]})."""
    db = get_db()
    coaches = db.execute("SELECT country, availability FROM coach_submissions").fetchall()
    covered = set()
    slot_countries = {}
    for coach in coaches:
        country = coach["country"] or ""
        av = json.loads(coach["availability"] or "{}")
        for key, status in av.items():
            if status in ("definite", "maybe") and "|" in key:
                covered.add(key)
                if country:
                    if key not in slot_countries:
                        slot_countries[key] = []
                    if country not in slot_countries[key]:
                        slot_countries[key].append(country)
    return covered, slot_countries


COURSES = {
    "private-coaching": {
        "name": "Private Coaching",
        "has_motivation": True,
        "has_study_background": True,
        "has_previous_study": False,
        "has_assessment": True,
        "has_continue": False,
        "has_notes": True,
        "motivation_label": "What is your motivation for learning Spanish and what is your overall fluency goal(s) for this course?",
    },
    "premier-coaching": {
        "name": "Premier Coaching",
        "has_motivation": True,
        "has_study_background": False,
        "has_previous_study": False,
        "has_assessment": True,
        "has_continue": False,
        "has_notes": False,
        "motivation_label": "What is your motivation for learning Spanish and what is your overall fluency goal(s) for this course?",
    },
    "one-month-challenge": {
        "name": "One Month Challenge",
        "has_motivation": True,
        "has_study_background": False,
        "has_previous_study": True,
        "has_assessment": False,
        "has_continue": False,
        "has_notes": False,
        "motivation_label": "What is your motivation for learning Spanish and what is your overall fluency goal(s) for this challenge?",
        "previous_study_label": "If you've taken any LCS lessons, which ones have you completed?",
    },
    "subjunctive-challenge": {
        "name": "Subjunctive Challenge",
        "has_motivation": True,
        "has_study_background": False,
        "has_previous_study": True,
        "has_assessment": False,
        "has_continue": False,
        "has_notes": False,
        "motivation_label": "What is your motivation for taking this course and what is your overall fluency goal?",
        "previous_study_label": "If you've taken any LCS lessons, which ones have you completed?",
    },
    "cohort-program": {
        "name": "Cohort Program",
        "has_motivation": True,
        "has_study_background": False,
        "has_previous_study": False,
        "has_assessment": False,
        "has_continue": False,
        "has_notes": False,
        "motivation_label": "What is your fluency goal for this program?",
    },
    "post-cohort-program": {
        "name": "Post-Cohort Program",
        "has_motivation": False,
        "has_study_background": False,
        "has_previous_study": False,
        "has_assessment": False,
        "has_continue": True,
        "has_notes": False,
    },
    "post-subjunctive-challenge": {
        "name": "Post-Subjunctive Challenge",
        "has_motivation": True,
        "has_study_background": False,
        "has_previous_study": False,
        "has_assessment": True,
        "has_continue": False,
        "has_notes": False,
        "motivation_label": "What is your motivation for taking this challenge?",
    },
    "intensive-program": {
        "name": "Intensive Program",
        "has_motivation": True,
        "has_study_background": False,
        "has_previous_study": False,
        "has_assessment": True,
        "has_continue": False,
        "has_notes": False,
        "motivation_label": "What is your motivation for learning Spanish and what is your overall fluency goal(s) for this program?",
    },
}


@app.route("/student")
def student_index():
    return redirect(url_for("student_course", course_slug="private-coaching"))


@app.route("/student/<course_slug>", methods=["GET", "POST"])
def student_course(course_slug):
    course_config = COURSES.get(course_slug)
    if not course_config:
        return "Course not found", 404
    if course_slug == "private-coaching":
        return _student_private(course_config)
    return _student_generic(course_config, course_slug)


def _student_private(course_config):
    covered, slot_countries = _coach_covered_slots()
    covered_times = {key.split("|", 1)[1] for key in covered}
    available_slots = [
        (h, s) for h, s in zip(ET_HOURS, TIME_SLOTS)
        if not covered or s in covered_times
    ]

    db = get_db()
    coach_countries_rows = db.execute(
        "SELECT DISTINCT country FROM coach_submissions WHERE country IS NOT NULL AND country != ''"
    ).fetchall()
    coach_countries = [r["country"] for r in coach_countries_rows]
    available_countries = [c for c in SPANISH_COUNTRIES if c in coach_countries] or SPANISH_COUNTRIES

    coaches_all = db.execute("SELECT country, availability FROM coach_submissions").fetchall()
    country_slots = {}
    for coach in coaches_all:
        country = coach["country"]
        if not country:
            continue
        av = json.loads(coach["availability"] or "{}")
        for key, status in av.items():
            if status in ("definite", "maybe") and "|" in key:
                if country not in country_slots:
                    country_slots[country] = []
                if key not in country_slots[country]:
                    country_slots[country].append(key)

    error = None
    if request.method == "POST":
        name                    = request.form.get("name", "").strip()
        email                   = request.form.get("email", "").strip()
        location                = request.form.get("location", "").strip()
        timezone                = request.form.get("timezone", "")
        countries               = request.form.get("countries_ranked", "[]")
        motivation              = request.form.get("motivation", "").strip()
        study_background        = request.form.get("study_background", "").strip()
        accommodations          = request.form.get("accommodations", "").strip()
        agreement_acknowledged  = request.form.get("agreement_acknowledged", "") == "yes"
        assessment_acknowledged = request.form.get("assessment_acknowledged", "") == "yes"
        notes                   = request.form.get("notes", "").strip()
        availability            = request.form.get("availability", "{}")

        if not name or not email or countries == "[]":
            error = "Please fill in all required fields."
        if not error:
            db = get_db()
            db.execute(
                """INSERT INTO student_submissions
                   (course, name, email, location, timezone, countries, motivation, study_background,
                    accommodations, agreement_acknowledged, assessment_acknowledged, availability, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("private-coaching", name, email, location, timezone, countries, motivation,
                 study_background, accommodations, agreement_acknowledged, assessment_acknowledged,
                 availability, notes),
            )
            db.commit()
            return render_template("thank_you.html", role="student")

    return render_template("student.html", countries=available_countries,
                           available_slots=available_slots, days=DAYS, timezones=TIMEZONES,
                           covered_keys=covered, country_slots=json.dumps(country_slots),
                           slot_countries=slot_countries, course_config=course_config, error=error)


def _student_generic(course_config, course_slug):
    covered, slot_countries = _coach_covered_slots()
    covered_times = {key.split("|", 1)[1] for key in covered}
    available_slots = [
        (h, s) for h, s in zip(ET_HOURS, TIME_SLOTS)
        if not covered or s in covered_times
    ]

    db = get_db()
    coach_countries_rows = db.execute(
        "SELECT DISTINCT country FROM coach_submissions WHERE country IS NOT NULL AND country != ''"
    ).fetchall()
    coach_countries = [r["country"] for r in coach_countries_rows]
    available_countries = [c for c in SPANISH_COUNTRIES if c in coach_countries] or SPANISH_COUNTRIES

    coaches_all = db.execute("SELECT country, availability FROM coach_submissions").fetchall()
    country_slots = {}
    for coach in coaches_all:
        country = coach["country"]
        if not country:
            continue
        av = json.loads(coach["availability"] or "{}")
        for key, status in av.items():
            if status in ("definite", "maybe") and "|" in key:
                if country not in country_slots:
                    country_slots[country] = []
                if key not in country_slots[country]:
                    country_slots[country].append(key)

    error = None
    if request.method == "POST":
        name                    = request.form.get("name", "").strip()
        email                   = request.form.get("email", "").strip()
        location                = request.form.get("location", "").strip()
        timezone                = request.form.get("timezone", "")
        countries               = request.form.get("countries_ranked", "[]")
        motivation              = request.form.get("motivation", "").strip() if course_config.get("has_motivation") else ""
        previous_study          = request.form.get("previous_study", "").strip() if course_config.get("has_previous_study") else ""
        accommodations          = request.form.get("accommodations", "").strip()
        agreement_acknowledged  = request.form.get("agreement_acknowledged", "") == "yes"
        assessment_acknowledged = request.form.get("assessment_acknowledged", "") == "yes"
        availability            = request.form.get("availability", "{}")
        continue_same_coach     = request.form.get("continue_same_coach", "")
        continue_same_time      = request.form.get("continue_same_time", "")

        if not name or not email or countries == "[]":
            error = "Please fill in all required fields."
        if not error:
            db = get_db()
            db.execute(
                """INSERT INTO student_submissions
                   (course, name, email, location, timezone, countries, motivation,
                    previous_study, accommodations, agreement_acknowledged, assessment_acknowledged,
                    availability, continue_same_coach, continue_same_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (course_slug, name, email, location, timezone, countries, motivation,
                 previous_study, accommodations, agreement_acknowledged, assessment_acknowledged,
                 availability, continue_same_coach, continue_same_time)
            )
            db.commit()
            return render_template("thank_you.html", role="student")

    return render_template("student_generic.html",
                           course_config=course_config,
                           course_slug=course_slug,
                           countries=available_countries,
                           available_slots=available_slots,
                           days=DAYS,
                           timezones=TIMEZONES,
                           covered_keys=covered,
                           country_slots=json.dumps(country_slots),
                           slot_countries=slot_countries,
                           error=error)


@app.route("/coach/demo")
def coach_demo():
    """Preview-only route — remove before production."""
    return render_template("coach.html", name="Demo Coach", email="demo@example.com",
                           slot_pairs=list(zip(ET_HOURS, TIME_SLOTS)), days=DAYS, timezones=TIMEZONES,
                           countries=SPANISH_COUNTRIES,
                           prefill_availability='{"Monday|9:00 AM":"definite","Tuesday|10:00 AM":"maybe"}',
                           prefill_country="Mexico", prefill_timezone="")


@app.route("/coach")
def coach_form():
    if not google.authorized:
        return redirect(url_for("google.login"))

    try:
        resp = google.get("/oauth2/v2/userinfo")
    except TokenExpiredError:
        return redirect(url_for("google.login"))
    if not resp.ok:
        return redirect(url_for("google.login"))

    user_info = resp.json()
    email = user_info.get("email", "")

    if APPROVED_COACH_EMAILS and email not in APPROVED_COACH_EMAILS:
        return render_template("unauthorized.html", email=email)

    session["user_email"] = email

    db = get_db()
    existing = db.execute("SELECT availability, country, timezone FROM coach_submissions WHERE email = ?", (email,)).fetchone()
    prefill_availability = existing["availability"] if existing else "{}"
    prefill_country      = existing["country"]       if existing else ""
    prefill_timezone     = existing["timezone"]      if existing else ""

    return render_template("coach.html", name=user_info.get("name", ""), email=email,
                           slot_pairs=list(zip(ET_HOURS, TIME_SLOTS)), days=DAYS, timezones=TIMEZONES,
                           countries=SPANISH_COUNTRIES,
                           prefill_availability=prefill_availability,
                           prefill_country=prefill_country,
                           prefill_timezone=prefill_timezone)


@app.route("/coach/submit", methods=["POST"])
def coach_submit():
    if not google.authorized:
        return redirect(url_for("google.login"))

    try:
        resp = google.get("/oauth2/v2/userinfo")
    except TokenExpiredError:
        return redirect(url_for("google.login"))
    if not resp.ok:
        return redirect(url_for("google.login"))

    user_info = resp.json()
    email = user_info.get("email", "")
    name = user_info.get("name", "")

    if APPROVED_COACH_EMAILS and email not in APPROVED_COACH_EMAILS:
        return render_template("unauthorized.html", email=email)

    timezone = request.form.get("timezone", "")
    country = request.form.get("country", "")
    availability = request.form.get("availability", "{}")

    db = get_db()
    existing = db.execute("SELECT id FROM coach_submissions WHERE email = ?", (email,)).fetchone()
    if existing:
        db.execute(
            "UPDATE coach_submissions SET name=?, timezone=?, country=?, availability=?, updated_at=CURRENT_TIMESTAMP WHERE email=?",
            (name, timezone, country, availability, email),
        )
    else:
        db.execute(
            "INSERT INTO coach_submissions (name, email, timezone, country, availability) VALUES (?, ?, ?, ?, ?)",
            (name, email, timezone, country, availability),
        )
    db.commit()
    return render_template("thank_you.html", role="coach")


_STUDENT_PREF_WEIGHT = {"pref-first": 3, "pref-second": 2, "pref-third": 1}
_COACH_STATUS_WEIGHT = {"definite": 2, "maybe": 1}


def _score_match(student, coach):
    """Return a match dict with total_score and overlapping_slots."""
    student_av = json.loads(student["availability"] or "{}")
    student_countries = json.loads(student["countries"] or "[]")
    country_rank = {c: i for i, c in enumerate(student_countries)}

    # Country score: 3 pts for 1st pref, 2 for 2nd, 1 for 3rd+, 0 for no match
    rank = country_rank.get(coach["country"])
    if rank is None:
        country_score = 0
    else:
        country_score = max(1, 3 - rank)

    # Availability overlap score
    coach_av = json.loads(coach["availability"] or "{}")
    overlapping = []
    av_score = 0
    for key, student_pref in student_av.items():
        coach_status = coach_av.get(key)
        if coach_status not in _COACH_STATUS_WEIGHT:
            continue
        s_w = _STUDENT_PREF_WEIGHT.get(student_pref, 0)
        c_w = _COACH_STATUS_WEIGHT[coach_status]
        slot_score = s_w * c_w
        av_score += slot_score
        day, time = key.split("|", 1)
        overlapping.append({
            "day": day, "time": time,
            "student_pref": student_pref,
            "coach_status": coach_status,
            "score": slot_score,
        })

    overlapping.sort(key=lambda x: -x["score"])
    # Country is weighted 5× a single slot to ensure accent fit matters
    total = country_score * 5 + av_score
    return {
        "coach": dict(coach),
        "country_score": country_score,
        "av_score": av_score,
        "total_score": total,
        "overlapping_slots": overlapping,
    }


def compute_matches(student, coaches):
    results = [_score_match(student, c) for c in coaches]
    results.sort(key=lambda x: -x["total_score"])
    return results


def _require_admin():
    """Returns the admin's email if authorized, or a redirect response if not."""
    if not google.authorized:
        return None, redirect(url_for("google.login"))
    try:
        resp = google.get("/oauth2/v2/userinfo")
    except TokenExpiredError:
        return None, redirect(url_for("google.login"))
    if not resp.ok:
        return None, redirect(url_for("google.login"))
    email = resp.json().get("email", "")
    if APPROVED_ADMIN_EMAILS and email not in APPROVED_ADMIN_EMAILS:
        return None, render_template("unauthorized.html", email=email)
    session["user_email"] = email
    return email, None


@app.route("/logout")
def logout():
    try:
        del google_bp.token
    except Exception:
        pass
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
def admin():
    email, err = _require_admin()
    if err:
        return err
    db = get_db()

    students_raw = db.execute("SELECT * FROM student_submissions ORDER BY created_at DESC").fetchall()
    students = []
    for s in students_raw:
        d = dict(s)
        d['submitted_et']    = _to_eastern(s['created_at'])
        d['assigned_at_et']  = _to_eastern(s.get('assigned_at'))
        d['response_hours']  = _business_hours_elapsed(s['created_at'], s.get('assigned_at'))
        students.append(d)

    coaches = db.execute("SELECT * FROM coach_submissions ORDER BY updated_at DESC").fetchall()
    coaches_json = json.dumps([{
        "name": c["name"], "email": c["email"],
        "country": c["country"] or "", "timezone": c["timezone"] or "",
        "availability": c["availability"] or "{}",
    } for c in coaches])

    db_emails = {c["email"] for c in coaches}
    staff_only = [s for s in STAFF_COACHES if s["email"] not in db_emails]
    all_coaches = staff_only + [dict(c) for c in coaches]

    return render_template("admin.html", students=students, coaches=coaches,
                           all_coaches=all_coaches, coaches_json=coaches_json,
                           days=DAYS, time_slots=TIME_SLOTS, courses=COURSES)


@app.route("/admin/coach-slots/<coach_email>")
def admin_coach_slots(coach_email):
    _, err = _require_admin()
    if err:
        return jsonify({"error": "unauthorized"}), 403
    db = get_db()
    coach = db.execute(
        "SELECT availability FROM coach_submissions WHERE email = ?", (coach_email,)
    ).fetchone()
    if not coach:
        return jsonify([])
    av = json.loads(coach["availability"] or "{}")
    slots = sorted(k for k, v in av.items() if v in ("definite", "maybe"))
    return jsonify(slots)


@app.route("/admin/assign", methods=["POST"])
def admin_assign():
    _, err = _require_admin()
    if err:
        return jsonify({"error": "unauthorized"}), 403
    data       = request.json
    student_id = data.get("student_id")
    new_coach  = data.get("coach_email", "") or None
    new_time   = data.get("assigned_time", "") or None

    db = get_db()
    current = db.execute(
        "SELECT assigned_coach, assigned_time FROM student_submissions WHERE id = ?",
        (student_id,)
    ).fetchone()
    old_coach = current["assigned_coach"] if current else None
    old_time  = current["assigned_time"]  if current else None

    # Restore old slot to old coach when the assignment changes
    if old_coach and old_time and (old_coach != new_coach or old_time != new_time):
        old_row = db.execute(
            "SELECT availability FROM coach_submissions WHERE email = ?", (old_coach,)
        ).fetchone()
        if old_row:
            av = json.loads(old_row["availability"] or "{}")
            av[old_time] = "definite"
            db.execute(
                "UPDATE coach_submissions SET availability = ? WHERE email = ?",
                (json.dumps(av), old_coach)
            )

    # Remove new slot from new coach
    if new_coach and new_time:
        new_row = db.execute(
            "SELECT availability FROM coach_submissions WHERE email = ?", (new_coach,)
        ).fetchone()
        if new_row:
            av = json.loads(new_row["availability"] or "{}")
            av.pop(new_time, None)
            db.execute(
                "UPDATE coach_submissions SET availability = ? WHERE email = ?",
                (json.dumps(av), new_coach)
            )

    db.execute(
        "UPDATE student_submissions SET assigned_coach = ?, assigned_time = ? WHERE id = ?",
        (new_coach, new_time, student_id)
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/admin/student/<int:student_id>/toggle-assigned", methods=["POST"])
def admin_toggle_assigned(student_id):
    _, err = _require_admin()
    if err:
        return jsonify({"error": "unauthorized"}), 403
    data = request.json
    is_assigned = bool(data.get("is_assigned"))
    db = get_db()
    if is_assigned:
        db.execute(
            "UPDATE student_submissions SET is_assigned = ?, assigned_at = CURRENT_TIMESTAMP WHERE id = ?",
            (True, student_id)
        )
    else:
        db.execute(
            "UPDATE student_submissions SET is_assigned = ?, assigned_at = NULL WHERE id = ?",
            (False, student_id)
        )
    db.commit()
    row = db.execute(
        "SELECT created_at, assigned_at FROM student_submissions WHERE id = ?", (student_id,)
    ).fetchone()
    assigned_at_et = _to_eastern(row['assigned_at']) if row else '—'
    response_hours = _business_hours_elapsed(row['created_at'], row['assigned_at']) if row else None
    return jsonify({"ok": True, "assigned_at_et": assigned_at_et, "response_hours": response_hours})


@app.route("/admin/import-student", methods=["POST"])
def admin_import_student():
    _, err = _require_admin()
    if err:
        return jsonify({"error": "unauthorized"}), 403
    d = request.json
    db = get_db()
    db.execute(
        """INSERT INTO student_submissions
           (name, email, location, timezone, countries, motivation, study_background,
            accommodations, agreement_acknowledged, assessment_acknowledged, availability, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (d.get("name",""), d.get("email",""), d.get("location",""), d.get("timezone",""),
         d.get("countries","[]"), d.get("motivation",""), d.get("study_background",""),
         d.get("accommodations",""), d.get("agreement_acknowledged", False),
         d.get("assessment_acknowledged", False), d.get("availability","{}"), d.get("notes",""))
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/admin/match/<int:student_id>")
def admin_match(student_id):
    email, err = _require_admin()
    if err:
        return err
    db = get_db()
    student = db.execute("SELECT * FROM student_submissions WHERE id = ?", (student_id,)).fetchone()
    if not student:
        return "Student not found", 404
    coaches = db.execute("SELECT * FROM coach_submissions").fetchall()
    matches = compute_matches(student, coaches)
    return render_template("match.html", student=student, matches=matches,
                           days=DAYS)


@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Database ready.")


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True, port=5050)
