from datetime import datetime
import os
import secrets
import sqlite3
import re
import sys

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_FOLDER = os.path.join(PROJECT_ROOT, "frontend")
if __package__ in (None, ""):
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from backend import database
    from backend.auth import admin_required, csrf_token, login_required, user_required, valid_csrf_token
    from backend.models import Bike, Car, ParkingLot, ParkingSlot, ParkingTicket, Payment, Vehicle
else:
    from . import database
    from .auth import admin_required, csrf_token, login_required, user_required, valid_csrf_token
    from .models import Bike, Car, ParkingLot, ParkingSlot, ParkingTicket, Payment, Vehicle

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_FOLDER, "templates"),
    static_folder=os.path.join(FRONTEND_FOLDER, "static"),
)
app.config["SECRET_KEY"] = os.environ.get("SMART_PARKING_SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SMART_PARKING_HTTPS") == "1"
app.config["PROPAGATE_EXCEPTIONS"] = False


@app.context_processor
def provide_csrf_token():
    return {"csrf_token": csrf_token()}


database_ready = True
try:
    database.init_db()
except sqlite3.Error:
    app.logger.exception("Unable to initialize the parking database")
    database_ready = False
parking_lot = ParkingLot(0)
if database_ready:
    parking_lot.slots = [ParkingSlot(row["slot_id"]) for row in database.get_parking_slots()]


def restore_parked_vehicles():
    vehicles_by_number = {
        vehicle["vehicle_number"]: vehicle["vehicle_type"]
        for vehicle in database.get_vehicles()
    }
    records_by_slot = {
        record["slot_id"]: record
        for record in database.get_parking_records()
        if record["status"] == "Parked"
    }

    for slot in parking_lot.slots:
        record = records_by_slot.get(slot.slot_id)
        if record is None:
            database.update_parking_slot_status(slot.slot_id, "Available")
            continue

        vehicle_number = record["vehicle_number"]
        vehicle_type = vehicles_by_number.get(vehicle_number, "Vehicle")
        if vehicle_type == "Car":
            vehicle = Car(vehicle_number, vehicle_type)
        elif vehicle_type == "Bike":
            vehicle = Bike(vehicle_number, vehicle_type)
        else:
            vehicle = Vehicle(vehicle_number, vehicle_type)

        slot.occupy_slot(vehicle)
        ticket = ParkingTicket(vehicle, slot.slot_id)
        ticket.entry_time = datetime.fromisoformat(record["entry_time"])
        slot.ticket = ticket
        database.update_parking_slot_status(slot.slot_id, "Occupied")


if database_ready:
    try:
        restore_parked_vehicles()
    except sqlite3.Error:
        app.logger.exception("Unable to restore parked vehicles")
        database_ready = False


@app.route("/login", methods=["GET", "POST"])
def login():
    portal = request.values.get("portal", "user").strip().lower()
    if portal not in ("user", "admin"):
        portal = "user"
    error = None

    if request.method == "POST":
        submitted_token = request.form.get("csrf_token", "")
        if not valid_csrf_token(submitted_token):
            error = "This form has expired. Please try again."
        else:
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            try:
                user = database.get_user_by_email(email)
            except sqlite3.Error:
                app.logger.exception("Unable to look up login account")
                return render_template("500.html"), 500

            if (
                user is None
                or not check_password_hash(user["password_hash"], password)
                or user["role"] != portal
                or not user.get("is_active", 1)
            ):
                error = "Email or password is incorrect for this login."
            else:
                session.clear()
                session["csrf_token"] = secrets.token_urlsafe(32)
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                if user["role"] == "admin":
                    return redirect(url_for("admin_home"))
                return redirect(url_for("user_dashboard"))

    return render_template(
        "login.html",
        portal=portal,
        error=error,
        registered=request.args.get("registered") == "1",
        csrf_token=csrf_token(),
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    form_values = {"name": "", "email": "", "mobile": "", "vehicle_number": "", "vehicle_type": ""}

    if request.method == "POST":
        form_values = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "mobile": request.form.get("mobile", "").strip(),
            "vehicle_number": request.form.get("vehicle_number", "").strip().upper(),
            "vehicle_type": request.form.get("vehicle_type", "").strip(),
        }
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not valid_csrf_token(request.form.get("csrf_token", "")):
            error = "This form has expired. Please try again."
        elif not form_values["name"] or not form_values["email"] or not password:
            error = "Please complete all required fields."
        elif "@" not in form_values["email"] or "." not in form_values["email"].split("@")[-1]:
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must contain at least 8 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif not form_values["mobile"].isdigit() or len(form_values["mobile"]) < 10:
            error = "Please enter a valid mobile number."
        elif form_values["vehicle_type"] not in ["Car", "Bike", "Scooter", "Other"]:
            error = "Please select a vehicle type."
        elif not form_values["vehicle_number"]:
            error = "Please enter your vehicle number."
        else:
            try:
                created = database.create_user(
                    form_values["name"],
                    form_values["email"],
                    generate_password_hash(password),
                    role="user",
                    mobile=form_values["mobile"],
                    vehicle_number=form_values["vehicle_number"],
                    vehicle_type=form_values["vehicle_type"],
                )
            except sqlite3.Error:
                app.logger.exception("Unable to create user account")
                return render_template("500.html"), 500
            if not created:
                error = "An account with that email already exists."
            else:
                return redirect(url_for("login", portal="user", registered="1"))

    return render_template(
        "register.html",
        error=error,
        form_values=form_values,
        csrf_token=csrf_token(),
    )


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    if not valid_csrf_token(request.form.get("csrf_token", "")):
        return "This form has expired. Please sign in again.", 400
    session.clear()
    return redirect(url_for("login"))


@app.route("/user/dashboard")
@user_required
def user_dashboard():
    try:
        slots = database.get_slot_overview()
        active = database.get_user_active_parking(g.current_user["id"])
        records = database.get_user_parking_records(g.current_user["id"])
        bookings = database.get_user_bookings(g.current_user["id"])
    except sqlite3.Error:
        app.logger.exception("Unable to load user dashboard")
        return render_template("500.html"), 500
    return render_template("user_dashboard.html", slots=slots, active=active,
                           total_slots=len(slots),
                           available_slots=sum(s["display_status"] == "available" for s in slots),
                           occupied_slots=sum(s["display_status"] == "occupied" for s in slots),
                           total_spent=sum(float(record.get("amount_paid") or record.get("fee") or 0) for record in records),
                           bookings=bookings,
                           recent_records=records[:5], csrf_token=csrf_token())


@app.route("/admin/dashboard")
@admin_required
def dashboard():
    try:
        return render_template(
            "index.html",
            total_slots=database.get_total_slots(),
            available_slots=database.get_available_slots_count(),
            occupied_slots=database.get_occupied_slots_count(),
            currently_parked=database.get_currently_parked_count(),
            completed_records=database.get_completed_records_count(),
            total_revenue=database.get_total_revenue(),
            recent_records=database.get_recent_parking_records(5),
            recent_bookings=database.get_all_bookings()[:5],
            slots=database.get_slot_overview(),
            total_users=database._get_count("SELECT COUNT(*) FROM users WHERE role = ?", ("user",)),
            total_vehicles=database._get_count("SELECT COUNT(*) FROM vehicles"),
            reserved_slots=database._get_count("SELECT COUNT(*) FROM bookings WHERE status = ?", ("Booked",)),
            today_revenue=database.get_today_revenue(),
            today_entries=database.get_today_entry_count(),
            today_exits=database.get_today_exit_count(),
            csrf_token=csrf_token(),
        )
    except sqlite3.Error:
        app.logger.exception("Unable to load dashboard data")
        return render_template("500.html"), 500


@app.route("/admin")
@admin_required
def admin_home():
    return redirect(url_for("dashboard"))


@app.route("/")
def landing():
    user_id = session.get("user_id")
    if user_id is not None:
        try:
            current_user = database.get_user_by_id(user_id)
        except sqlite3.Error:
            app.logger.exception("Unable to check current login session")
            return render_template("500.html"), 500
        if current_user and current_user.get("is_active", 1):
            endpoint = "admin_home" if current_user["role"] == "admin" else "user_dashboard"
            return redirect(url_for(endpoint))
        session.clear()
    return render_template("landing.html")


@app.route("/user/parking")
@user_required
def user_parking():
    try:
        slots = database.get_slot_overview()
    except sqlite3.Error:
        app.logger.exception("Unable to load user parking map")
        return render_template("500.html"), 500
    safe_slots = [{key: value for key, value in slot.items()
                   if key not in ("vehicle_number", "vehicle_type", "entry_time", "booking_vehicle_number", "booking_time")}
                  for slot in slots]
    return render_template("portal_page.html", title="Parking slots", subtitle="Live facility availability",
                           mode="user", slots=safe_slots, csrf_token=csrf_token())


@app.route("/user/entry", methods=["GET", "POST"])
@user_required
def user_entry():
    user_id = g.current_user["id"]
    error = None
    success = None
    active = None
    try:
        active = database.get_user_active_parking(user_id)
        slots = database.get_slot_overview()
        own_vehicle = (g.current_user.get("vehicle_number") or "").upper()
        own_booking_slots = {
            booking["slot_id"]
            for booking in database.get_user_bookings(user_id)
            if booking["status"] == "Booked"
            and booking["vehicle_number"].upper() == own_vehicle
        }
        available = [
            slot for slot in slots
            if slot["display_status"] == "available" or slot["slot_id"] in own_booking_slots
        ]
        rates = {"Car": float(database.get_setting("car_session_rate", "40")),
                 "Bike": float(database.get_setting("bike_session_rate", "20"))}
    except (sqlite3.Error, ValueError):
        app.logger.exception("Unable to prepare vehicle entry")
        return render_template("500.html"), 500

    if request.method == "POST":
        vehicle_number = request.form.get("vehicle_number", "").strip().upper()
        vehicle_type = request.form.get("vehicle_type", "").strip()
        slot_id = request.form.get("slot_id", "").strip()
        payment_method = request.form.get("payment_method", "").strip()
        if active:
            error = "You already have an active parking session."
        elif not vehicle_number:
            error = "Please enter vehicle number."
        elif vehicle_type not in ["Car", "Bike", "Scooter", "Other"]:
            error = "Please select a valid vehicle type."
        elif payment_method not in ["UPI", "Card", "Cash"]:
            error = "Please select a payment method."
        elif slot_id not in {slot["slot_id"] for slot in available}:
            error = "Please select an available parking slot."
        elif database.is_vehicle_currently_parked(vehicle_number):
            error = "This vehicle is already parked."
        else:
            amount = rates.get(vehicle_type, rates["Car"])
            now = datetime.now().isoformat(timespec="seconds")
            transaction_id = "SP" + secrets.token_hex(5).upper()
            try:
                result, record_id = database.create_paid_parking_entry(
                    user_id, vehicle_number, vehicle_type, slot_id, now,
                    amount, payment_method, transaction_id,
                )
            except sqlite3.Error:
                app.logger.exception("Unable to save paid vehicle entry")
                return render_template("500.html"), 500
            if result == "created":
                vehicle = Car(vehicle_number, vehicle_type) if vehicle_type == "Car" else (
                    Bike(vehicle_number, vehicle_type) if vehicle_type == "Bike" else Vehicle(vehicle_number, vehicle_type)
                )
                assigned_slot = next((slot for slot in parking_lot.slots if slot.slot_id == slot_id), None)
                if assigned_slot is not None:
                    assigned_slot.occupy_slot(vehicle)
                    assigned_slot.ticket = ParkingTicket(vehicle, slot_id)
                    assigned_slot.ticket.entry_time = datetime.fromisoformat(now)
                success = {"vehicle_number": vehicle_number, "vehicle_type": vehicle_type,
                           "slot_id": slot_id, "amount": amount, "method": payment_method,
                           "transaction_id": transaction_id, "record_id": record_id}
                active = database.get_user_active_parking(user_id)
            else:
                error = "The selected slot or vehicle is no longer available. Please refresh and try again."

    return render_template("user_entry.html", available_slots=available, rates=rates,
                           selected_slot=request.args.get("slot", ""),
                           error=error, success=success, active=active, csrf_token=csrf_token())


@app.route("/user/exit", methods=["GET", "POST"])
@user_required
def user_exit():
    user_id = g.current_user["id"]
    try:
        active = database.get_user_active_parking(user_id)
    except sqlite3.Error:
        app.logger.exception("Unable to load active parking")
        return render_template("500.html"), 500
    error = None
    if request.method == "POST":
        if not valid_csrf_token(request.form.get("csrf_token", "")):
            error = "This form has expired. Please try again."
        elif active is None:
            error = "No vehicle is currently parked."
        else:
            try:
                ticket = ParkingTicket(Vehicle(active["vehicle_number"], active.get("vehicle_type") or "Vehicle"), active["slot_id"])
                ticket.entry_time = datetime.fromisoformat(active["entry_time"])
                ticket.record_exit()
                duration = ticket.calculate_duration()
                completed = database.complete_user_parking(
                    active["id"], user_id, ticket.exit_time.isoformat(timespec="seconds"), duration
                )
            except (sqlite3.Error, ValueError):
                app.logger.exception("Unable to complete user vehicle exit")
                return render_template("500.html"), 500
            if completed:
                parking_lot.remove_vehicle(active["slot_id"])
                return redirect(url_for("user_receipt", record_id=active["id"]))
            error = "This parking session has already ended."
    return render_template("user_exit.html", active=active, error=error, csrf_token=csrf_token())


@app.route("/user/payment")
@user_required
def user_payments():
    try:
        payments = database.get_user_payment_records(g.current_user["id"])
    except sqlite3.Error:
        app.logger.exception("Unable to load user payments")
        return render_template("500.html"), 500
    return render_template("portal_page.html", title="Payments", subtitle="Demo payments made at vehicle entry",
                           mode="user", payments=payments, csrf_token=csrf_token())


@app.route("/user/bookings")
@user_required
def user_bookings():
    try:
        bookings = database.get_user_bookings(g.current_user["id"])
    except sqlite3.Error:
        app.logger.exception("Unable to load user bookings")
        return render_template("500.html"), 500
    return render_template("portal_page.html", title="My bookings", subtitle="Your reservations only",
                           mode="user", bookings=bookings)


@app.route("/user/current")
@user_required
def user_current_parking():
    return redirect(url_for("user_exit"))


@app.route("/user/receipt")
@user_required
def latest_user_receipt():
    try:
        records = database.get_user_parking_records(g.current_user["id"])
    except sqlite3.Error:
        app.logger.exception("Unable to load user receipts")
        return render_template("500.html"), 500
    completed = next((record for record in records if record["status"] == "Completed"), None)
    if completed is None:
        flash("Your receipt will be available after a parking session ends.", "warning")
        return redirect(url_for("user_history"))
    return redirect(url_for("user_receipt", record_id=completed["id"]))


@app.route("/user/history")
@user_required
def user_history():
    try:
        records = database.get_user_parking_records(g.current_user["id"])
    except sqlite3.Error:
        app.logger.exception("Unable to load user parking history")
        return render_template("500.html"), 500
    return render_template("portal_page.html", title="My parking history", subtitle="Your parking sessions only",
                           mode="user", records=records, csrf_token=csrf_token())


@app.route("/user/receipt/<int:record_id>")
@user_required
def user_receipt(record_id):
    try:
        record = database.get_user_parking_record_by_id(record_id, g.current_user["id"])
    except sqlite3.Error:
        app.logger.exception("Unable to load user receipt")
        return render_template("500.html"), 500
    if record is None:
        abort(404)
    return render_template("user_receipt.html", record=record)


@app.route("/user/profile", methods=["GET", "POST"])
@user_required
def user_profile():
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        vehicle_number = request.form.get("vehicle_number", "").strip().upper()
        vehicle_type = request.form.get("vehicle_type", "").strip()
        if not valid_csrf_token(request.form.get("csrf_token", "")):
            error = "This form has expired. Please try again."
        elif not name or not mobile.isdigit() or len(mobile) < 10 or not vehicle_number or vehicle_type not in ["Car", "Bike", "Scooter", "Other"]:
            error = "Please complete all profile fields with valid details."
        else:
            try:
                database.update_user_profile(g.current_user["id"], name, mobile, vehicle_number, vehicle_type)
            except sqlite3.Error:
                app.logger.exception("Unable to update user profile")
                return render_template("500.html"), 500
            return redirect(url_for("user_profile", saved="1"))
    profile = database.get_user_by_id(g.current_user["id"])
    return render_template("user_profile.html", profile=profile, error=error,
                           saved=request.args.get("saved") == "1", csrf_token=csrf_token())


@app.route("/admin/<section>", methods=["GET", "POST"])
@admin_required
def admin_section(section):
    allowed_sections = {
        "parking-map", "vehicles", "users", "bookings", "records", "payments",
        "history", "revenue", "analytics", "reports", "settings",
    }
    if section not in allowed_sections:
        abort(404)
    if section == "history":
        section = "records"
    try:
        context = {
            "slots": database.get_slot_overview(),
            "vehicles": database.get_admin_vehicles(
                request.args.get("vehicle_number", "").strip() or None,
                request.args.get("vehicle_status", "").strip() if request.args.get("vehicle_status", "") in ("Active", "Completed") else None,
            ),
            "users": database.get_admin_users(request.args.get("user_search", "").strip() or None),
            "bookings": database.get_all_bookings(),
            "records": database.search_parking_records(
                request.args.get("record_search", "").strip() or None,
                request.args.get("record_status", "") if request.args.get("record_status", "") in ("Parked", "Completed") else None,
            ),
            "payments": database.get_all_payment_records(
                request.args.get("payment_search", "").strip() or None,
                request.args.get("payment_status", ""),
            ),
            "revenue": database.get_completed_payment_revenue(),
            "today_revenue": database.get_today_revenue(),
            "week_revenue": database.get_week_revenue(),
            "month_revenue": database.get_month_revenue(),
            "total_users": database.get_total_users(),
            "total_slots": database.get_total_slots(),
            "available_slots": database.get_available_slots_count(),
            "occupied_slots": database.get_occupied_slots_count(),
            "csrf_token": csrf_token(),
        }
        if section == "parking-map" and request.method == "POST":
            if not valid_csrf_token(request.form.get("csrf_token", "")):
                flash("This form has expired. Please try again.", "error")
            elif request.form.get("action") == "add-slot":
                slot_id = request.form.get("slot_id", "").strip().upper()
                if not re.fullmatch(r"P[0-9]{1,3}", slot_id):
                    flash("Use a slot ID such as P11.", "error")
                else:
                    try:
                        created = database.add_parking_slot(slot_id)
                    except sqlite3.Error:
                        app.logger.exception("Unable to add parking slot")
                        return render_template("500.html"), 500
                    if created:
                        parking_lot.slots.append(ParkingSlot(slot_id))
                        flash("Parking slot added.", "success")
                        return redirect(url_for("admin_section", section=section))
                    flash("That slot ID already exists.", "error")
            elif request.form.get("action") == "remove-slot":
                slot_id = request.form.get("slot_id", "").strip().upper()
                try:
                    removed = database.remove_available_parking_slot(slot_id)
                except sqlite3.Error:
                    app.logger.exception("Unable to remove parking slot")
                    return render_template("500.html"), 500
                if removed:
                    parking_lot.slots = [slot for slot in parking_lot.slots if slot.slot_id != slot_id]
                    flash("Available parking slot removed.", "success")
                    return redirect(url_for("admin_section", section=section))
                flash("Only an available, unreserved slot can be removed.", "error")
        if section == "settings" and request.method == "POST":
            if not valid_csrf_token(request.form.get("csrf_token", "")):
                flash("This form has expired. Please try again.", "error")
            elif request.form.get("settings_action") == "account":
                admin = database.get_user_by_id(g.current_user["id"])
                name = request.form.get("name", "").strip()
                email = request.form.get("email", "").strip().lower()
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                confirm_password = request.form.get("confirm_password", "")
                if not name or "@" not in email or not check_password_hash(admin["password_hash"], current_password):
                    flash("Enter a valid name and email, and confirm your current password.", "error")
                elif new_password and (len(new_password) < 8 or new_password != confirm_password):
                    flash("New password must be at least 8 characters and match the confirmation.", "error")
                else:
                    try:
                        password_hash = generate_password_hash(new_password) if new_password else None
                        updated = database.update_admin_account(g.current_user["id"], name, email, password_hash)
                    except sqlite3.Error:
                        app.logger.exception("Unable to update admin account")
                        return render_template("500.html"), 500
                    if updated:
                        flash("Admin account settings updated.", "success")
                        return redirect(url_for("admin_section", section=section))
                    flash("That email address is already in use.", "error")
            else:
                try:
                    car_rate = float(request.form.get("car_session_rate", ""))
                    bike_rate = float(request.form.get("bike_session_rate", ""))
                    if car_rate <= 0 or bike_rate <= 0 or car_rate > 10000 or bike_rate > 10000:
                        raise ValueError
                    database.set_setting("car_session_rate", car_rate)
                    database.set_setting("bike_session_rate", bike_rate)
                    flash("Parking session rates updated.", "success")
                    return redirect(url_for("admin_section", section=section))
                except (ValueError, sqlite3.Error):
                    flash("Enter valid positive parking rates.", "error")
            context["car_session_rate"] = database.get_setting("car_session_rate", "40")
            context["bike_session_rate"] = database.get_setting("bike_session_rate", "20")
        elif section == "settings":
            context["car_session_rate"] = database.get_setting("car_session_rate", "40")
            context["bike_session_rate"] = database.get_setting("bike_session_rate", "20")
        if section == "settings":
            admin_profile = database.get_user_by_id(g.current_user["id"])
            context["admin_profile"] = {"name": admin_profile["name"], "email": admin_profile["email"]}
        context["section"] = section
    except sqlite3.Error:
        app.logger.exception("Unable to load admin section")
        return render_template("500.html"), 500
    return render_template("admin_section.html", **context)


@app.route("/admin/users/<int:user_id>/status", methods=["POST"])
@admin_required
def admin_user_status(user_id):
    if not valid_csrf_token(request.form.get("csrf_token", "")):
        abort(400)
    try:
        database.toggle_user_active(user_id)
    except sqlite3.Error:
        app.logger.exception("Unable to update user account status")
        return render_template("500.html"), 500
    return redirect(url_for("admin_section", section="users"))


@app.route("/slots")
@admin_required
def show_slots():
    try:
        slots = database.get_slot_overview()
    except sqlite3.Error:
        app.logger.exception("Unable to load parking slot data")
        return render_template("500.html"), 500
    summary = {
        "total": len(slots),
        "available": sum(1 for slot in slots if slot["display_status"] == "available"),
        "occupied": sum(1 for slot in slots if slot["display_status"] == "occupied"),
        "booked": sum(1 for slot in slots if slot["display_status"] == "booked"),
    }
    return render_template("slots.html", slots=slots, summary=summary)


@app.route("/records")
@admin_required
def records():
    vehicle_number = request.args.get("vehicle_number", "").strip()
    status = request.args.get("status", "").strip()
    if status not in ["", "Parked", "Completed"]:
        status = ""

    try:
        parking_records = database.search_parking_records(
            vehicle_number=vehicle_number or None,
            status=status or None,
        )
    except sqlite3.Error:
        app.logger.exception("Unable to search parking records")
        return render_template(
            "records.html",
            records=[],
            vehicle_number=vehicle_number,
            selected_status=status,
            error="Unable to load parking records. Please try again.",
        ), 500
    return render_template(
        "records.html",
        records=parking_records,
        vehicle_number=vehicle_number,
        selected_status=status,
    )


@app.route("/receipt/<int:record_id>")
@admin_required
def parking_receipt(record_id):
    try:
        record = database.get_parking_record_by_id(record_id)
    except sqlite3.Error:
        app.logger.exception("Unable to load parking receipt")
        return render_template("500.html"), 500
    if record is None:
        abort(404)
    return render_template("receipt.html", record=record)


@app.route("/booking", methods=["GET", "POST"])
@user_required
def booking():
    try:
        available_ids = {slot["slot_id"] for slot in database.get_available_slots()}
    except sqlite3.Error:
        app.logger.exception("Unable to load available booking slots")
        return render_template("500.html"), 500
    available_slots = [
        slot
        for slot in parking_lot.slots
        if slot.status == "Available" and slot.slot_id in available_ids
    ]

    if request.method == "POST":
        if not valid_csrf_token(request.form.get("csrf_token", "")):
            return render_template("booking.html", slots=available_slots,
                                   error="This form has expired. Please try again.")
        vehicle_number = request.form.get("vehicle_number", "").strip()
        vehicle_type = request.form.get("vehicle_type", "")
        slot_id = request.form.get("slot_id", "")
        form_values = {
            "vehicle_number": vehicle_number,
            "vehicle_type": vehicle_type,
            "slot_id": slot_id,
        }

        error = None
        if not vehicle_number:
            error = "Please enter vehicle number."
        elif vehicle_number.upper() != (g.current_user.get("vehicle_number") or "").upper():
            error = "Bookings must use the vehicle saved in your profile. Update your profile first if needed."
        elif not vehicle_type:
            error = "Please select vehicle type."
        elif vehicle_type not in ["Car", "Bike"]:
            error = "Please select vehicle type."
        elif not slot_id:
            error = "Please select a parking slot."
        else:
            try:
                if database.check_active_booking(vehicle_number):
                    error = "Vehicle already has an active booking."
                elif database.check_slot_booking(slot_id):
                    error = "Selected slot is already booked."
            except sqlite3.Error:
                app.logger.exception("Unable to validate booking")
                error = "Unable to check booking availability. Please try again."

        if error:
            return render_template(
                "booking.html",
                slots=available_slots,
                error=error,
                form_values=form_values,
            )

        if slot_id not in available_ids or slot_id not in {
            slot.slot_id for slot in available_slots
        }:
            return render_template(
                "booking.html",
                slots=available_slots,
                error="Selected parking slot is no longer available.",
                form_values=form_values,
            )

        booking_time = datetime.now().isoformat()
        try:
            result = database.create_booking(
                vehicle_number, slot_id, booking_time, g.current_user["id"]
            )
        except sqlite3.Error:
            app.logger.exception("Unable to create booking")
            return render_template(
                "booking.html",
                slots=available_slots,
                form_values=form_values,
                error="Unable to save booking. Please try again.",
            ), 500
        if result == "created":
            booking_details = {
                **form_values,
                "booking_time": booking_time,
                "status": "Booked",
            }
            return render_template(
                "booking.html",
                slots=available_slots,
                booking=booking_details,
            )

        if result == "vehicle_booked":
            error = "Vehicle already has an active booking."
        else:
            try:
                if database.check_slot_booking(slot_id):
                    error = "Selected slot is already booked."
                else:
                    error = "Selected parking slot is no longer available."
            except sqlite3.Error:
                app.logger.exception("Unable to recheck booking slot")
                error = "Unable to check booking availability. Please try again."
        return render_template(
            "booking.html",
            slots=available_slots,
            error=error,
            form_values=form_values,
        )

    return render_template("booking.html", slots=available_slots,
                           form_values={"vehicle_number": g.current_user.get("vehicle_number") or "",
                                        "vehicle_type": g.current_user.get("vehicle_type") or ""})


@app.route("/bookings")
@admin_required
def bookings():
    try:
        all_bookings = database.get_all_bookings()
    except sqlite3.Error:
        app.logger.exception("Unable to load bookings")
        return render_template("500.html"), 500
    return render_template("bookings.html", bookings=all_bookings)


@app.route("/entry", methods=["GET", "POST"])
@user_required
def vehicle_entry():
    return redirect(url_for("user_entry"))


@app.route("/exit", methods=["GET", "POST"])
@user_required
def vehicle_exit():
    return redirect(url_for("user_exit"))


@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(error):
    return render_template("403.html"), 403


@app.errorhandler(500)
def internal_server_error(error):
    return render_template("500.html"), 500


if __name__ == "__main__":
    app.run(debug=True)
