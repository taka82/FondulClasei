import csv
import hmac
import io
import json
import os
import re
import secrets
import time
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import wraps
from pathlib import Path

from flask import (Flask, Response, abort, flash, g, make_response, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db

BASE_DIR = Path(__file__).parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["DATABASE"] = os.environ.get("FOND_DB", str(INSTANCE_DIR / "fond.db"))
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)

_key_file = INSTANCE_DIR / "secret_key"
if not _key_file.exists():
    _key_file.write_text(secrets.token_hex(32))
app.secret_key = _key_file.read_text().strip()

db.init_app(app)


# ---------------------------------------------------------------- utilitare

def parse_money(text):
    """'150', '150,50', '1.234,50' -> bani (int). ValueError daca e invalid."""
    s = (text or "").strip().lower().replace("lei", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        value = Decimal(s)
    except InvalidOperation:
        raise ValueError("Suma nu este validă.")
    if not value.is_finite() or value <= 0:
        raise ValueError("Suma trebuie să fie mai mare ca zero.")
    if value > Decimal("1000000"):
        raise ValueError("Suma este prea mare.")
    return int((value * 100).to_integral_value(ROUND_HALF_UP))


def parse_date(text, required=True):
    text = (text or "").strip()
    if not text:
        if required:
            raise ValueError("Data este obligatorie.")
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError("Data nu este validă.")


def money_to_input(bani):
    return f"{bani // 100}" if bani % 100 == 0 else f"{bani / 100:.2f}".replace(".", ",")


@app.template_filter("money")
def fmt_money(bani):
    bani = bani or 0
    sign = "-" if bani < 0 else ""
    bani = abs(bani)
    return f"{sign}{bani // 100:,}".replace(",", ".") + f",{bani % 100:02d} lei"


@app.template_filter("ro_date")
def fmt_date(iso):
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return iso


app.jinja_env.globals["money_to_input"] = money_to_input


# ---------------------------------------------------------------- securitate

def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def load_user_and_check_csrf():
    g.user = None
    uid = session.get("uid")
    if uid:
        g.user = db.one("SELECT * FROM users WHERE id = ?", (uid,))
        if g.user is None:
            session.clear()
    if request.method == "POST":
        sent = request.form.get("csrf", "")
        if not hmac.compare_digest(sent, session.get("csrf", "")):
            abort(400, "Sesiunea a expirat. Reîncarcă pagina și încearcă din nou.")


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if g.user is None:
            if db.scalar("SELECT COUNT(*) FROM users") == 0:
                return redirect(url_for("setup"))
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapper


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(*a, **kw):
        if g.user["role"] != "admin":
            abort(403)
        return view(*a, **kw)
    return wrapper


def is_admin():
    return g.user is not None and g.user["role"] == "admin"


@app.context_processor
def inject_globals():
    return {
        "user": g.get("user"),
        "is_admin": is_admin(),
        "class_name": db.get_setting("class_name", "Fondul clasei"),
        "has_logo": (BASE_DIR / "static" / "logo.png").exists(),  # sigla optionala: pune fisierul static/logo.png
    }


def safe_next(target):
    """Permite doar redirectionari catre pagini din acelasi site."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


PASSWORD_MIN = 8
_failed = {}  # ip -> [timestamps]


def too_many_attempts(ip):
    now = time.time()
    recent = [t for t in _failed.get(ip, []) if now - t < 300]
    _failed[ip] = recent
    return len(recent) >= 5


# ---------------------------------------------------------------- autentificare

@app.route("/setup", methods=["GET", "POST"])
def setup():
    if db.scalar("SELECT COUNT(*) FROM users") > 0:
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        class_name = request.form.get("class_name", "").strip() or "Fondul clasei"
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
            flash("Utilizatorul trebuie să aibă 3-32 caractere (litere, cifre, . _ -).", "error")
        elif len(password) < PASSWORD_MIN:
            flash(f"Parola trebuie să aibă minim {PASSWORD_MIN} caractere.", "error")
        else:
            db.execute(
                "INSERT INTO users(username, password_hash, role) VALUES (?, ?, 'admin')",
                (username, generate_password_hash(password)),
            )
            db.set_setting("class_name", class_name)
            flash("Cont de casier creat. Te poți autentifica.", "ok")
            return redirect(url_for("login"))
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if db.scalar("SELECT COUNT(*) FROM users") == 0:
        return redirect(url_for("setup"))
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if too_many_attempts(ip):
            flash("Prea multe încercări. Așteaptă 5 minute.", "error")
            return render_template("login.html"), 429
        row = db.one("SELECT * FROM users WHERE username = ?",
                     (request.form.get("username", "").strip(),))
        if row and check_password_hash(row["password_hash"], request.form.get("password", "")):
            session.clear()
            session.permanent = True
            session["uid"] = row["id"]
            return redirect(safe_next(request.args.get("next")) or url_for("dashboard"))
        _failed.setdefault(ip, []).append(time.time())
        flash("Utilizator sau parolă greșite.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- panou

@app.route("/")
@login_required
def dashboard():
    opening = int(db.get_setting("opening_balance", "0") or 0)
    collected = db.scalar("SELECT COALESCE(SUM(amount), 0) FROM payments")
    spent = db.scalar("SELECT COALESCE(SUM(amount), 0) FROM expenses")
    outstanding = db.scalar(
        "SELECT COALESCE(SUM(MAX(b.amount - b.paid, 0)), 0) FROM balances b "
        "JOIN students s ON s.id = b.student_id WHERE s.active = 1"
    )
    by_category = db.query(
        "SELECT category, SUM(amount) AS total FROM expenses "
        "GROUP BY category ORDER BY total DESC"
    )
    recent_expenses = db.query(
        "SELECT * FROM expenses ORDER BY spent_on DESC, id DESC LIMIT 5"
    )
    recent_payments = []
    my_student = None
    if is_admin():
        recent_payments = db.query(
            "SELECT p.*, s.name AS student, c.name AS contribution FROM payments p "
            "JOIN students s ON s.id = p.student_id "
            "JOIN contributions c ON c.id = p.contribution_id "
            "ORDER BY p.paid_on DESC, p.id DESC LIMIT 8"
        )
    elif g.user["student_id"]:
        my_student = db.one("SELECT * FROM students WHERE id = ?", (g.user["student_id"],))
    return render_template(
        "dashboard.html", opening=opening, collected=collected, spent=spent, supply_stats=supply_stats(),
        balance=opening + collected - spent, outstanding=outstanding,
        by_category=by_category, recent_expenses=recent_expenses,
        recent_payments=recent_payments, my_student=my_student,
    )


# ---------------------------------------------------------------- elevi

@app.route("/students", methods=["GET", "POST"])
@admin_required
def students():
    if request.method == "POST":
        names = [n.strip() for n in request.form.get("names", "").splitlines() if n.strip()]
        names = [n[:100] for n in names]
        if not names:
            flash("Introdu cel puțin un nume.", "error")
        else:
            conn = db.get_db()
            conn.executemany("INSERT INTO students(name) VALUES (?)", [(n,) for n in names])
            conn.commit()
            flash(f"Au fost adăugați {len(names)} elevi.", "ok")
        return redirect(url_for("students"))
    rows = db.query(
        "SELECT s.*, "
        " COALESCE((SELECT SUM(amount) FROM payments WHERE student_id = s.id), 0) AS paid, "
        " CASE WHEN s.active THEN COALESCE((SELECT SUM(MAX(amount - paid, 0)) "
        "   FROM balances WHERE student_id = s.id), 0) ELSE 0 END AS owed "
        "FROM students s ORDER BY s.active DESC, s.name COLLATE NOCASE"
    )
    return render_template("students.html", students=rows)


def student_or_403(student_id):
    student = db.one("SELECT * FROM students WHERE id = ?", (student_id,))
    if student is None:
        abort(404)
    if not is_admin() and g.user["student_id"] != student_id:
        abort(403)
    return student


@app.route("/students/<int:student_id>")
@login_required
def student_detail(student_id):
    student = student_or_403(student_id)
    rows = db.query(
        "SELECT c.id, c.name, c.due_date, b.amount, b.paid FROM balances b "
        "JOIN contributions c ON c.id = b.contribution_id "
        "WHERE b.student_id = ? ORDER BY c.due_date, c.id", (student_id,)
    )
    payments = db.query(
        "SELECT p.*, c.name AS contribution FROM payments p "
        "JOIN contributions c ON c.id = p.contribution_id "
        "WHERE p.student_id = ? ORDER BY p.paid_on DESC, p.id DESC", (student_id,)
    )
    return render_template("student_detail.html", student=student, rows=rows,
                           payments=payments, today=date.today().isoformat())


@app.route("/me")
@login_required
def me():
    if is_admin() or not g.user["student_id"]:
        return redirect(url_for("dashboard"))
    return redirect(url_for("student_detail", student_id=g.user["student_id"]))


@app.post("/students/<int:student_id>/edit")
@admin_required
def student_edit(student_id):
    student_or_403(student_id)
    name = request.form.get("name", "").strip()[:100]
    if not name:
        flash("Numele nu poate fi gol.", "error")
    else:
        db.execute("UPDATE students SET name = ? WHERE id = ?", (name, student_id))
        flash("Nume actualizat.", "ok")
    return redirect(url_for("student_detail", student_id=student_id))


@app.post("/students/<int:student_id>/toggle")
@admin_required
def student_toggle(student_id):
    student_or_403(student_id)
    db.execute("UPDATE students SET active = 1 - active WHERE id = ?", (student_id,))
    return redirect(request.referrer or url_for("students"))


@app.post("/students/<int:student_id>/delete")
@admin_required
def student_delete(student_id):
    student_or_403(student_id)
    if db.scalar("SELECT COUNT(*) FROM payments WHERE student_id = ?", (student_id,)):
        flash("Elevul are plăți înregistrate și nu poate fi șters. Dezactiveaz-l în schimb.", "error")
        return redirect(url_for("student_detail", student_id=student_id))
    db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    flash("Elev șters.", "ok")
    return redirect(url_for("students"))


# ---------------------------------------------------------------- contributii

def read_contribution_form():
    name = request.form.get("name", "").strip()[:100]
    if not name:
        raise ValueError("Denumirea este obligatorie.")
    amount = parse_money(request.form.get("amount"))
    due = parse_date(request.form.get("due_date"), required=False)
    note = request.form.get("note", "").strip()[:300]
    return name, amount, due, note


@app.route("/contributions", methods=["GET", "POST"])
@admin_required
def contributions():
    if request.method == "POST":
        try:
            db.execute(
                "INSERT INTO contributions(name, amount, due_date, note) VALUES (?, ?, ?, ?)",
                read_contribution_form(),
            )
            flash("Contribuție adăugată.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("contributions"))
    rows = db.query(
        "SELECT c.*, "
        " COALESCE((SELECT SUM(amount) FROM payments WHERE contribution_id = c.id), 0) AS collected, "
        " COALESCE((SELECT SUM(MAX(b.amount - b.paid, 0)) FROM balances b "
        "   JOIN students s ON s.id = b.student_id "
        "   WHERE b.contribution_id = c.id AND s.active = 1), 0) AS owed, "
        " (SELECT COUNT(*) FROM balances b JOIN students s ON s.id = b.student_id "
        "   WHERE b.contribution_id = c.id AND s.active = 1 AND b.paid < b.amount) AS unpaid "
        "FROM contributions c ORDER BY c.due_date DESC, c.id DESC"
    )
    return render_template("contributions.html", contributions=rows)


def contribution_or_404(cid):
    row = db.one("SELECT * FROM contributions WHERE id = ?", (cid,))
    if row is None:
        abort(404)
    return row


@app.route("/contributions/<int:cid>")
@admin_required
def contribution_detail(cid):
    contribution = contribution_or_404(cid)
    rows = db.query(
        "SELECT s.id, s.name, s.active, b.paid FROM balances b "
        "JOIN students s ON s.id = b.student_id "
        "WHERE b.contribution_id = ? AND (s.active = 1 OR b.paid > 0) "
        "ORDER BY s.name COLLATE NOCASE", (cid,)
    )
    return render_template("contribution_detail.html", contribution=contribution,
                           rows=rows, today=date.today().isoformat())


@app.route("/contributions/<int:cid>/edit", methods=["GET", "POST"])
@admin_required
def contribution_edit(cid):
    contribution = contribution_or_404(cid)
    if request.method == "POST":
        try:
            name, amount, due, note = read_contribution_form()
            db.execute(
                "UPDATE contributions SET name = ?, amount = ?, due_date = ?, note = ? WHERE id = ?",
                (name, amount, due, note, cid),
            )
            flash("Contribuție actualizată.", "ok")
            return redirect(url_for("contribution_detail", cid=cid))
        except ValueError as e:
            flash(str(e), "error")
    return render_template("contribution_edit.html", contribution=contribution)


@app.post("/contributions/<int:cid>/delete")
@admin_required
def contribution_delete(cid):
    contribution_or_404(cid)
    if db.scalar("SELECT COUNT(*) FROM payments WHERE contribution_id = ?", (cid,)):
        flash("Există plăți pentru această contribuție. Șterge întâi plățile.", "error")
        return redirect(url_for("contribution_detail", cid=cid))
    db.execute("DELETE FROM contributions WHERE id = ?", (cid,))
    flash("Contribuție ștearsă.", "ok")
    return redirect(url_for("contributions"))


# ---------------------------------------------------------------- plati

@app.post("/payments")
@admin_required
def payment_add():
    back = safe_next(request.form.get("next")) or url_for("students")
    try:
        student_id = int(request.form.get("student_id", ""))
        contribution_id = int(request.form.get("contribution_id", ""))
        if not db.one("SELECT 1 FROM students WHERE id = ?", (student_id,)) or \
           not db.one("SELECT 1 FROM contributions WHERE id = ?", (contribution_id,)):
            raise ValueError("Elev sau contribuție inexistente.")
        amount = parse_money(request.form.get("amount"))
        paid_on = parse_date(request.form.get("paid_on"))
        note = request.form.get("note", "").strip()[:300]
        db.execute(
            "INSERT INTO payments(student_id, contribution_id, amount, paid_on, note, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, contribution_id, amount, paid_on, note, g.user["id"]),
        )
        flash("Plată înregistrată.", "ok")
    except ValueError as e:
        flash(str(e) if str(e) and not str(e).startswith("invalid literal") else "Date invalide.", "error")
    return redirect(back)


@app.post("/payments/<int:payment_id>/delete")
@admin_required
def payment_delete(payment_id):
    db.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    flash("Plată ștearsă.", "ok")
    return redirect(safe_next(request.form.get("next")) or url_for("students"))


# ---------------------------------------------------------------- cheltuieli

def read_expense_form():
    spent_on = parse_date(request.form.get("spent_on"))
    category = request.form.get("category", "").strip()[:50]
    if not category:
        raise ValueError("Categoria este obligatorie.")
    amount = parse_money(request.form.get("amount"))
    description = request.form.get("description", "").strip()[:300]
    return spent_on, category, amount, description


def expense_categories():
    return [r["category"] for r in db.query(
        "SELECT category FROM expenses GROUP BY category ORDER BY COUNT(*) DESC")]


@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    if request.method == "POST":
        if not is_admin():
            abort(403)
        try:
            db.execute(
                "INSERT INTO expenses(spent_on, category, amount, description, created_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (*read_expense_form(), g.user["id"]),
            )
            flash("Cheltuială înregistrată.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("expenses"))
    rows = db.query("SELECT * FROM expenses ORDER BY spent_on DESC, id DESC")
    return render_template("expenses.html", expenses=rows, total=sum(r["amount"] for r in rows),
                           categories=expense_categories(), today=date.today().isoformat())


@app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
@admin_required
def expense_edit(expense_id):
    expense = db.one("SELECT * FROM expenses WHERE id = ?", (expense_id,))
    if expense is None:
        abort(404)
    if request.method == "POST":
        try:
            spent_on, category, amount, description = read_expense_form()
            db.execute(
                "UPDATE expenses SET spent_on = ?, category = ?, amount = ?, description = ? WHERE id = ?",
                (spent_on, category, amount, description, expense_id),
            )
            flash("Cheltuială actualizată.", "ok")
            return redirect(url_for("expenses"))
        except ValueError as e:
            flash(str(e), "error")
    return render_template("expense_edit.html", expense=expense, categories=expense_categories())


@app.post("/expenses/<int:expense_id>/delete")
@admin_required
def expense_delete(expense_id):
    db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    flash("Cheltuială ștearsă.", "ok")
    return redirect(url_for("expenses"))


# ---------------------------------------------------------------- utilizatori

@app.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "parent")
        student_id = request.form.get("student_id") or None
        if role not in ("admin", "parent"):
            role = "parent"
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
            flash("Utilizatorul trebuie să aibă 3-32 caractere (litere, cifre, . _ -).", "error")
        elif len(password) < PASSWORD_MIN:
            flash(f"Parola trebuie să aibă minim {PASSWORD_MIN} caractere.", "error")
        elif db.one("SELECT 1 FROM users WHERE username = ?", (username,)):
            flash("Există deja un utilizator cu acest nume.", "error")
        elif role == "parent" and not student_id:
            flash("Alege elevul asociat contului de părinte.", "error")
        else:
            db.execute(
                "INSERT INTO users(username, password_hash, role, student_id) VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), role,
                 int(student_id) if role == "parent" else None),
            )
            flash("Cont creat.", "ok")
        return redirect(url_for("users"))
    rows = db.query(
        "SELECT u.*, s.name AS student FROM users u "
        "LEFT JOIN students s ON s.id = u.student_id ORDER BY u.role, u.username"
    )
    kids = db.query("SELECT id, name FROM students WHERE active = 1 ORDER BY name COLLATE NOCASE")
    return render_template("users.html", users=rows, students=kids)


@app.post("/users/<int:user_id>/password")
@admin_required
def user_password(user_id):
    password = request.form.get("password", "")
    if len(password) < PASSWORD_MIN:
        flash(f"Parola trebuie să aibă minim {PASSWORD_MIN} caractere.", "error")
    else:
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                   (generate_password_hash(password), user_id))
        flash("Parolă schimbată.", "ok")
    return redirect(url_for("users"))


@app.post("/users/<int:user_id>/delete")
@admin_required
def user_delete(user_id):
    target = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if target is None:
        abort(404)
    if target["role"] == "admin" and db.scalar("SELECT COUNT(*) FROM users WHERE role = 'admin'") <= 1:
        flash("Nu poți șterge ultimul cont de casier.", "error")
    elif target["id"] == g.user["id"]:
        flash("Nu îți poți șterge propriul cont.", "error")
    else:
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        flash("Cont șters.", "ok")
    return redirect(url_for("users"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        if not check_password_hash(g.user["password_hash"], request.form.get("current", "")):
            flash("Parola curentă este greșită.", "error")
        elif len(request.form.get("new", "")) < PASSWORD_MIN:
            flash(f"Parola nouă trebuie să aibă minim {PASSWORD_MIN} caractere.", "error")
        else:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(request.form["new"]), g.user["id"]))
            flash("Parolă schimbată.", "ok")
            return redirect(url_for("dashboard"))
    return render_template("account.html")


# ---------------------------------------------------------------- setari

@app.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        class_name = request.form.get("class_name", "").strip()[:80] or "Fondul clasei"
        raw = request.form.get("opening_balance", "").strip()
        try:
            opening = 0 if raw in ("", "0") else parse_money(raw.lstrip("-"))
            if raw.startswith("-"):
                opening = -opening
            db.set_setting("class_name", class_name)
            db.set_setting("opening_balance", str(opening))
            flash("Setări salvate.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("settings"))
    opening = int(db.get_setting("opening_balance", "0") or 0)
    return render_template("settings.html", opening=opening)


# ---------------------------------------------------------------- export CSV

def csv_response(filename, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    # BOM + ';' ca Excel in varianta romaneasca sa deschida corect diacriticele
    return Response("﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


def csv_safe(value):
    """Neutralizeaza formulele (=, +, -, @) la deschiderea in Excel."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


@app.route("/export/expenses.csv")
@login_required
def export_expenses():
    rows = db.query("SELECT * FROM expenses ORDER BY spent_on, id")
    return csv_response("cheltuieli.csv", ["Data", "Categorie", "Suma (lei)", "Descriere"],
                        [(r["spent_on"], csv_safe(r["category"]), f"{r['amount'] / 100:.2f}".replace(".", ","),
                          csv_safe(r["description"] or "")) for r in rows])


@app.route("/export/payments.csv")
@admin_required
def export_payments():
    rows = db.query(
        "SELECT p.*, s.name AS student, c.name AS contribution FROM payments p "
        "JOIN students s ON s.id = p.student_id JOIN contributions c ON c.id = p.contribution_id "
        "ORDER BY p.paid_on, p.id"
    )
    return csv_response("plati.csv", ["Data", "Elev", "Contribuție", "Suma (lei)", "Observații"],
                        [(r["paid_on"], csv_safe(r["student"]), csv_safe(r["contribution"]),
                          f"{r['amount'] / 100:.2f}".replace(".", ","), csv_safe(r["note"] or ""))
                         for r in rows])


@app.route("/export/restante.csv")
@admin_required
def export_outstanding():
    rows = db.query(
        "SELECT s.name AS student, c.name AS contribution, b.amount, b.paid FROM balances b "
        "JOIN students s ON s.id = b.student_id JOIN contributions c ON c.id = b.contribution_id "
        "WHERE s.active = 1 AND b.paid < b.amount ORDER BY s.name COLLATE NOCASE, c.due_date"
    )
    return csv_response("restante.csv", ["Elev", "Contribuție", "De plătit (lei)", "Plătit (lei)", "Rest (lei)"],
                        [(csv_safe(r["student"]), csv_safe(r["contribution"]),
                          f"{r['amount'] / 100:.2f}".replace(".", ","),
                          f"{r['paid'] / 100:.2f}".replace(".", ","),
                          f"{(r['amount'] - r['paid']) / 100:.2f}".replace(".", ",")) for r in rows])


# ---------------------------------------------------------------- rechizite

SUPPLY_STATUS = {
    "necesar": ("De cumpărat", "bad"),
    "partial": ("Parțial", "warn"),
    "cumparat": ("Cumpărat", "ok"),
}
SUPPLY_STATUS_ORDER = {"necesar": 0, "partial": 1, "cumparat": 2}


def supply_status(bought, qty):
    if bought <= 0:
        return "necesar"
    return "cumparat" if bought >= qty else "partial"


def initials(name):
    words = [w for w in name.replace("-", " ").split() if w]
    return "".join(w[0] for w in words[:2]).upper() or "?"


app.jinja_env.globals.update(SUPPLY_STATUS=SUPPLY_STATUS, supply_status=supply_status)
app.jinja_env.filters["initials"] = initials


def parse_int(text, default, minimum=0, maximum=10000):
    try:
        value = int((text or "").strip())
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def supply_rows(supply_id=None):
    """Rechizitele cu numarul de elevi (activi) care au ales / platit / primit."""
    rows = db.query(
        "SELECT s.*, COALESCE(SUM(t.chosen), 0) AS chosen, COALESCE(SUM(t.paid), 0) AS paid, "
        "       COALESCE(SUM(t.received), 0) AS received "
        "FROM supplies s "
        "LEFT JOIN (SELECT t.* FROM supply_tracking t "
        "           JOIN students st ON st.id = t.student_id AND st.active = 1) t ON t.supply_id = s.id "
        + ("WHERE s.id = ? " if supply_id else "") + "GROUP BY s.id",
        (supply_id,) if supply_id else (),
    )
    return [dict(r, status=supply_status(r["bought"], r["qty"])) for r in rows]


def supply_or_404(supply_id):
    rows = supply_rows(supply_id)
    if not rows:
        abort(404)
    return rows[0]


def active_student_count():
    return db.scalar("SELECT COUNT(*) FROM students WHERE active = 1")


def my_tracking():
    """Bifele copilului asociat contului de parinte: {supply_id: rand}."""
    if is_admin() or not g.user["student_id"]:
        return {}
    return {r["supply_id"]: r for r in db.query(
        "SELECT * FROM supply_tracking WHERE student_id = ?", (g.user["student_id"],))}


def supply_stats():
    stats = {"total": 0, "necesar": 0, "partial": 0, "cumparat": 0}
    for r in db.query("SELECT qty, bought FROM supplies"):
        stats["total"] += 1
        stats[supply_status(r["bought"], r["qty"])] += 1
    return stats


def wants_fragment():
    return request.headers.get("X-Requested-With") == "fetch"


def read_supply_form():
    name = request.form.get("name", "").strip()[:100]
    if not name:
        raise ValueError("Denumirea este obligatorie.")
    category = request.form.get("category", "").strip()[:50] or "General"
    qty = parse_int(request.form.get("qty"), 1, minimum=1)
    bought = parse_int(request.form.get("bought"), 0, maximum=qty)
    note = request.form.get("note", "").strip()[:300]
    return name, category, qty, bought, note


@app.route("/supplies", methods=["GET", "POST"])
@login_required
def supplies():
    if request.method == "POST":
        if not is_admin():
            abort(403)
        try:
            db.execute("INSERT INTO supplies(name, category, qty, bought, note) VALUES (?, ?, ?, ?, ?)",
                       read_supply_form())
            flash("Rechizit adăugat.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("supplies"))

    everything = supply_rows()
    stats = supply_stats()
    categories = sorted({r["category"] for r in everything}, key=str.lower)

    q = request.args.get("q", "").strip().lower()
    cat = request.args.get("cat", "")
    status = request.args.get("status", "")
    sort = request.args.get("sort", "name")
    direction = "desc" if request.args.get("dir") == "desc" else "asc"

    rows = [r for r in everything
            if (not q or q in r["name"].lower() or q in r["category"].lower())
            and (not cat or r["category"] == cat)
            and (not status or r["status"] == status)]
    keys = {
        "name": lambda r: r["name"].lower(),
        "cat": lambda r: (r["category"].lower(), r["name"].lower()),
        "qty": lambda r: (r["qty"], r["name"].lower()),
        "status": lambda r: (SUPPLY_STATUS_ORDER[r["status"]], r["name"].lower()),
    }
    rows.sort(key=keys.get(sort, keys["name"]), reverse=direction == "desc")

    return render_template(
        "supplies.html", supplies=rows, stats=stats, categories=categories, total=active_student_count(),
        mine=my_tracking(), q=request.args.get("q", ""), cat=cat, status=status,
        sort=sort if sort in keys else "name", direction=direction,
    )


@app.route("/supplies/<int:supply_id>")
@login_required
def supply_detail(supply_id):
    supply = supply_or_404(supply_id)
    rows = db.query(
        "SELECT st.id, st.name, st.active, COALESCE(t.chosen, 0) AS chosen, "
        "       COALESCE(t.paid, 0) AS paid, COALESCE(t.received, 0) AS received "
        "FROM students st LEFT JOIN supply_tracking t ON t.student_id = st.id AND t.supply_id = ? "
        "WHERE st.active = 1 OR t.chosen OR t.paid OR t.received "
        "ORDER BY st.name COLLATE NOCASE", (supply_id,)
    )
    if not is_admin():
        rows = [r for r in rows if r["id"] == g.user["student_id"]]
    return render_template("supply_detail.html", supply=supply, rows=rows, total=active_student_count())


@app.route("/supplies/<int:supply_id>/edit", methods=["GET", "POST"])
@admin_required
def supply_edit(supply_id):
    supply = supply_or_404(supply_id)
    if request.method == "POST":
        try:
            name, category, qty, bought, note = read_supply_form()
            db.execute("UPDATE supplies SET name = ?, category = ?, qty = ?, bought = ?, note = ? WHERE id = ?",
                       (name, category, qty, bought, note, supply_id))
            flash("Rechizit actualizat.", "ok")
            return redirect(url_for("supplies"))
        except ValueError as e:
            flash(str(e), "error")
    categories = sorted({r["category"] for r in supply_rows()}, key=str.lower)
    return render_template("supply_edit.html", supply=supply, categories=categories)


@app.post("/supplies/<int:supply_id>/delete")
@admin_required
def supply_delete(supply_id):
    supply_or_404(supply_id)
    db.execute("DELETE FROM supplies WHERE id = ?", (supply_id,))
    flash("Rechizit șters.", "ok")
    return redirect(url_for("supplies"))


@app.post("/supplies/<int:supply_id>/adjust")
@admin_required
def supply_adjust(supply_id):
    """Butoanele − / + pentru cantitate si numar cumparat."""
    supply = supply_or_404(supply_id)
    field = request.form.get("field")
    delta = {"1": 1, "-1": -1}.get(request.form.get("delta"))
    if field not in ("qty", "bought") or delta is None:
        abort(400, "Cerere invalidă.")
    qty, bought = supply["qty"], supply["bought"]
    if field == "qty":
        qty = max(1, qty + delta)
        bought = min(bought, qty)
    else:
        bought = min(qty, max(0, bought + delta))
    db.execute("UPDATE supplies SET qty = ?, bought = ? WHERE id = ?", (qty, bought, supply_id))
    if wants_fragment():
        resp = make_response(render_template("_supply_row.html", s=supply_or_404(supply_id), mine=my_tracking(),
                                             total=active_student_count()))
        resp.headers["X-Supply-Stats"] = json.dumps(supply_stats())  # ca sa se actualizeze si cifrele de sus
        return resp
    return redirect(safe_next(request.form.get("next")) or url_for("supplies"))


@app.post("/supplies/<int:supply_id>/track")
@admin_required
def supply_track(supply_id):
    """Salveaza bifele Ales / Plătit / Primit ale unui elev pentru un rechizit."""
    supply_or_404(supply_id)
    try:
        student_id = int(request.form.get("student_id", ""))
    except ValueError:
        abort(400, "Cerere invalidă.")
    if not db.one("SELECT 1 FROM students WHERE id = ?", (student_id,)):
        abort(404)
    chosen, paid, received = (1 if request.form.get(k) else 0 for k in ("chosen", "paid", "received"))
    db.execute(
        "INSERT INTO supply_tracking(supply_id, student_id, chosen, paid, received) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(supply_id, student_id) DO UPDATE SET "
        "chosen = excluded.chosen, paid = excluded.paid, received = excluded.received",
        (supply_id, student_id, chosen, paid, received),
    )
    if wants_fragment():
        counts = supply_or_404(supply_id)
        return {k: counts[k] for k in ("chosen", "paid", "received")}
    return redirect(url_for("supply_detail", supply_id=supply_id))


@app.route("/export/supplies.csv")
@admin_required
def export_supplies():
    def names_for(column):
        rows = db.query(
            f"SELECT t.supply_id, st.name FROM supply_tracking t JOIN students st ON st.id = t.student_id "
            f"WHERE t.{column} = 1 ORDER BY st.name COLLATE NOCASE")
        out = {}
        for r in rows:
            out.setdefault(r["supply_id"], []).append(r["name"])
        return out

    chosen, paid, received = names_for("chosen"), names_for("paid"), names_for("received")
    rows = sorted(supply_rows(), key=lambda r: (r["category"].lower(), r["name"].lower()))
    return csv_response(
        "rechizite.csv",
        ["Rechizit", "Categorie", "Cantitate", "Cumpărat", "Status", "Ales de", "Plătit de", "Primit de", "Observații"],
        [(csv_safe(r["name"]), csv_safe(r["category"]), r["qty"], r["bought"], SUPPLY_STATUS[r["status"]][0],
          csv_safe("; ".join(chosen.get(r["id"], []))), csv_safe("; ".join(paid.get(r["id"], []))),
          csv_safe("; ".join(received.get(r["id"], []))), csv_safe(r["note"] or "")) for r in rows],
    )


# ---------------------------------------------------------------- erori

@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, message="Nu ai acces la această pagină."), 403


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, message="Pagina nu a fost găsită."), 404


@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, message=e.description), 400


if __name__ == "__main__":
    host = os.environ.get("FOND_HOST", "127.0.0.1")
    port = int(os.environ.get("FOND_PORT", "5000"))
    try:
        from waitress import serve
        print(f"Serverul rulează pe http://{host}:{port}")
        serve(app, host=host, port=port)
    except ImportError:
        app.run(host=host, port=port)
