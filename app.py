import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_dance.contrib.google import make_google_blueprint, google
from database import init_db, get_db, close_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")

# Trust Railway's HTTPS proxy so OAuth redirects use https://
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.jinja_env.filters["from_json"] = json.loads
app.teardown_appcontext(close_db)

APPROVED_COACH_EMAILS  = os.environ.get("APPROVED_COACH_EMAILS", "").split(",")
APPROVED_ADMIN_EMAILS  = os.environ.get("APPROVED_ADMIN_EMAILS", "").split(",")

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

ET_HOURS   = list(range(4, 24))          # 4 AM … 11 PM ET; last slot = 11 PM–midnight
TIME_SLOTS = [_fmt_et(h) for h in ET_HOURS]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

TIMEZONES = [
    ("America/New_York",              "Eastern Time (ET)"),
    ("America/Chicago",               "Central Time (CT)"),
    ("America/Denver",                "Mountain Time (MT)"),
    ("America/Los_Angeles",           "Pacific Time (PT)"),
    ("America/Anchorage",             "Alaska Time"),
    ("Pacific/Honolulu",              "Hawaii Time"),
    ("America/Mexico_City",           "Mexico City"),
    ("America/Bogota",                "Bogotá"),
    ("America/Lima",                  "Lima"),
    ("America/Santiago",              "Santiago"),
    ("America/Argentina/Buenos_Aires","Buenos Aires"),
    ("America/Caracas",               "Caracas"),
    ("America/La_Paz",                "La Paz"),
    ("America/Guayaquil",             "Guayaquil"),
    ("America/Asuncion",              "Asunción"),
    ("America/Montevideo",            "Montevideo"),
    ("America/Panama",                "Panama"),
    ("America/Costa_Rica",            "Costa Rica"),
    ("America/Managua",               "Managua"),
    ("America/Tegucigalpa",           "Tegucigalpa"),
    ("America/Guatemala",             "Guatemala City"),
    ("America/El_Salvador",           "El Salvador"),
    ("America/Havana",                "Havana"),
    ("America/Santo_Domingo",         "Santo Domingo"),
    ("Europe/Madrid",                 "Madrid"),
    ("UTC",                           "UTC"),
]


@app.route("/")
def index():
    return render_template("index.html")


def _coach_covered_slots():
    """Return the set of ET time-slot labels that at least one coach marked definite/maybe."""
    db = get_db()
    coaches = db.execute("SELECT availability FROM coach_submissions").fetchall()
    covered = set()
    for coach in coaches:
        av = json.loads(coach["availability"] or "{}")
        for key, status in av.items():
            if status in ("definite", "maybe") and "|" in key:
                covered.add(key.split("|", 1)[1])
    return covered


@app.route("/student", methods=["GET", "POST"])
def student_form():
    covered = _coach_covered_slots()
    # Pairs of (ET hour int, ET label string) for the grid rows
    available_slots = [
        (h, s) for h, s in zip(ET_HOURS, TIME_SLOTS)
        if not covered or s in covered
    ]

    if request.method == "POST":
        name      = request.form.get("name", "").strip()
        email     = request.form.get("email", "").strip()
        timezone  = request.form.get("timezone", "")
        countries = request.form.get("countries_ranked", "[]")
        notes     = request.form.get("notes", "").strip()
        availability = request.form.get("availability", "{}")

        if not name or not email or countries == "[]":
            return render_template(
                "student.html",
                error="Please fill in all required fields.",
                countries=SPANISH_COUNTRIES, available_slots=available_slots,
                days=DAYS, timezones=TIMEZONES,
            )

        db = get_db()
        db.execute(
            "INSERT INTO student_submissions (name, email, timezone, countries, availability, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, timezone, countries, availability, notes),
        )
        db.commit()
        return render_template("thank_you.html", role="student")

    return render_template("student.html", countries=SPANISH_COUNTRIES,
                           available_slots=available_slots, days=DAYS, timezones=TIMEZONES)


@app.route("/coach/demo")
def coach_demo():
    """Preview-only route — remove before production."""
    return render_template("coach.html", name="Demo Coach", email="demo@example.com",
                           time_slots=TIME_SLOTS, days=DAYS, timezones=TIMEZONES,
                           countries=SPANISH_COUNTRIES,
                           prefill_availability='{"Monday|9:00 AM":"definite","Tuesday|10:00 AM":"maybe"}',
                           prefill_country="Mexico")


@app.route("/coach")
def coach_form():
    if not google.authorized:
        return redirect(url_for("google.login"))

    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        return redirect(url_for("google.login"))

    user_info = resp.json()
    email = user_info.get("email", "")

    if APPROVED_COACH_EMAILS and email not in APPROVED_COACH_EMAILS:
        return render_template("unauthorized.html", email=email)

    db = get_db()
    existing = db.execute("SELECT availability, country FROM coach_submissions WHERE email = ?", (email,)).fetchone()
    prefill_availability = existing["availability"] if existing else "{}"
    prefill_country = existing["country"] if existing else ""

    return render_template("coach.html", name=user_info.get("name", ""), email=email,
                           time_slots=TIME_SLOTS, days=DAYS, timezones=TIMEZONES,
                           countries=SPANISH_COUNTRIES,
                           prefill_availability=prefill_availability,
                           prefill_country=prefill_country)


@app.route("/coach/submit", methods=["POST"])
def coach_submit():
    if not google.authorized:
        return redirect(url_for("google.login"))

    resp = google.get("/oauth2/v2/userinfo")
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
    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        return None, redirect(url_for("google.login"))
    email = resp.json().get("email", "")
    if APPROVED_ADMIN_EMAILS and email not in APPROVED_ADMIN_EMAILS:
        return None, render_template("unauthorized.html", email=email)
    return email, None


@app.route("/admin")
def admin():
    email, err = _require_admin()
    if err:
        return err
    db = get_db()
    students = db.execute("SELECT * FROM student_submissions ORDER BY created_at DESC").fetchall()
    coaches = db.execute("SELECT * FROM coach_submissions ORDER BY updated_at DESC").fetchall()
    return render_template("admin.html", students=students, coaches=coaches,
                           days=DAYS, time_slots=TIME_SLOTS)


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
