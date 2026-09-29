import os
import sqlite3
from contextlib import closing


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_FOLDER = os.path.join(PROJECT_ROOT, "database")
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(DATABASE_FOLDER, "parking.db"))


def get_connection():
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS vehicles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_number TEXT UNIQUE NOT NULL,
                    vehicle_type TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS parking_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_id TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Available'
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS parking_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_number TEXT NOT NULL,
                    slot_id TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    duration REAL,
                    fee REAL,
                    status TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_number TEXT NOT NULL,
                    slot_id TEXT NOT NULL,
                    booking_time TEXT NOT NULL,
                    status TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            _add_column_if_missing(connection, "users", "mobile", "TEXT")
            _add_column_if_missing(connection, "users", "vehicle_number", "TEXT")
            _add_column_if_missing(connection, "users", "vehicle_type", "TEXT")
            _add_column_if_missing(connection, "users", "is_active", "INTEGER NOT NULL DEFAULT 1")
            _add_column_if_missing(connection, "parking_records", "user_id", "INTEGER")
            _add_column_if_missing(connection, "parking_records", "vehicle_type", "TEXT")
            _add_column_if_missing(connection, "parking_records", "payment_status", "TEXT NOT NULL DEFAULT 'Pending'")
            _add_column_if_missing(connection, "parking_records", "payment_method", "TEXT")
            _add_column_if_missing(connection, "parking_records", "transaction_id", "TEXT")
            _add_column_if_missing(connection, "parking_records", "amount_paid", "REAL")
            _add_column_if_missing(connection, "bookings", "user_id", "INTEGER")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT UNIQUE NOT NULL,
                    user_id INTEGER,
                    parking_record_id INTEGER NOT NULL,
                    vehicle_number TEXT NOT NULL,
                    slot_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    payment_method TEXT NOT NULL,
                    payment_status TEXT NOT NULL,
                    payment_time TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT NOT NULL
                )"""
            )
            connection.execute(
                "INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)",
                ("car_session_rate", "40"),
            )
            connection.execute(
                "INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)",
                ("bike_session_rate", "20"),
            )

    if _get_count("SELECT COUNT(*) FROM parking_slots") == 0:
        add_parking_slots(["P" + str(number) for number in range(1, 11)])

    if _get_count("SELECT COUNT(*) FROM users WHERE role = 'admin'") == 0:
        from werkzeug.security import generate_password_hash

        admin_name = os.environ.get("ADMIN_NAME", "Admin")
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@smartparking.com").strip().lower()
        admin_pass = os.environ.get("ADMIN_PASSWORD", "Admin@123")
        create_user(admin_name, admin_email, generate_password_hash(admin_pass), role="admin")


def _add_column_if_missing(connection, table_name, column_name, definition):
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(" + table_name + ")")
    }
    if column_name not in columns:
        connection.execute(
            "ALTER TABLE " + table_name + " ADD COLUMN " + column_name + " " + definition
        )


def add_vehicle(vehicle_number, vehicle_type):
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """INSERT INTO vehicles (vehicle_number, vehicle_type)
                   VALUES (?, ?)
                   ON CONFLICT(vehicle_number) DO UPDATE SET
                   vehicle_type = excluded.vehicle_type""",
                (vehicle_number, vehicle_type),
            )


def get_user_by_email(email):
    users = _rows_as_dicts(
        "SELECT * FROM users WHERE email = ? LIMIT 1",
        (email,),
    )
    return users[0] if users else None


def get_user_by_id(user_id):
    users = _rows_as_dicts(
        "SELECT * FROM users WHERE id = ? LIMIT 1",
        (user_id,),
    )
    return users[0] if users else None


def get_admin_count():
    return _get_count("SELECT COUNT(*) FROM users WHERE role = ?", ("admin",))


def create_user(name, email, password_hash, role="user", mobile=None, vehicle_number=None, vehicle_type=None):
    if role not in ("user", "admin"):
        raise ValueError("User role must be 'user' or 'admin'.")

    with closing(get_connection()) as connection:
        try:
            with connection:
                connection.execute(
                    """INSERT INTO users
                       (name, email, password_hash, role, mobile, vehicle_number, vehicle_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, email, password_hash, role, mobile, vehicle_number, vehicle_type),
                )
                if vehicle_number and vehicle_type:
                    connection.execute(
                        """INSERT INTO vehicles (vehicle_number, vehicle_type) VALUES (?, ?)
                           ON CONFLICT(vehicle_number) DO UPDATE SET vehicle_type = excluded.vehicle_type""",
                        (vehicle_number, vehicle_type),
                    )
        except sqlite3.IntegrityError:
            return False
    return True


def update_user_profile(user_id, name, mobile, vehicle_number, vehicle_type):
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """UPDATE users SET name = ?, mobile = ?, vehicle_number = ?, vehicle_type = ?
                   WHERE id = ? AND role = 'user'""",
                (name, mobile, vehicle_number, vehicle_type, user_id),
            )
            connection.execute(
                """INSERT INTO vehicles (vehicle_number, vehicle_type) VALUES (?, ?)
                   ON CONFLICT(vehicle_number) DO UPDATE SET vehicle_type = excluded.vehicle_type""",
                (vehicle_number, vehicle_type),
            )


def get_user_parking_records(user_id):
    return _rows_as_dicts(
        """SELECT id, vehicle_number, vehicle_type, slot_id, entry_time, exit_time,
                  duration, fee, amount_paid, status, payment_status, payment_method
           FROM parking_records WHERE user_id = ? ORDER BY id DESC""",
        (user_id,),
    )


def get_user_parking_record_by_id(record_id, user_id):
    records = _rows_as_dicts(
        """SELECT * FROM parking_records WHERE id = ? AND user_id = ? LIMIT 1""",
        (record_id, user_id),
    )
    return records[0] if records else None


def get_user_active_parking(user_id):
    records = _rows_as_dicts(
        """SELECT * FROM parking_records WHERE user_id = ? AND status = 'Parked'
           ORDER BY id DESC LIMIT 1""",
        (user_id,),
    )
    return records[0] if records else None


def get_setting(setting_key, default=None):
    rows = _rows_as_dicts(
        "SELECT setting_value FROM settings WHERE setting_key = ? LIMIT 1",
        (setting_key,),
    )
    return rows[0]["setting_value"] if rows else default


def set_setting(setting_key, setting_value):
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """INSERT INTO settings (setting_key, setting_value) VALUES (?, ?)
                   ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value""",
                (setting_key, str(setting_value)),
            )


def create_paid_parking_entry(user_id, vehicle_number, vehicle_type, slot_id,
                              entry_time, amount, payment_method, transaction_id):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        active = connection.execute(
            """SELECT 1 FROM parking_records WHERE UPPER(vehicle_number) = UPPER(?)
               AND status = 'Parked' LIMIT 1""",
            (vehicle_number,),
        ).fetchone()
        slot = connection.execute(
            "SELECT status FROM parking_slots WHERE slot_id = ?", (slot_id,)
        ).fetchone()
        active_booking = connection.execute(
            """SELECT 1 FROM bookings WHERE slot_id = ? AND status = 'Booked'
               AND (user_id IS NULL OR user_id != ?) LIMIT 1""",
            (slot_id, user_id),
        ).fetchone()
        if active:
            connection.rollback()
            return "vehicle_parked", None
        if slot is None or slot["status"] != "Available" or active_booking:
            connection.rollback()
            return "slot_unavailable", None

        connection.execute(
            """INSERT INTO vehicles (vehicle_number, vehicle_type) VALUES (?, ?)
               ON CONFLICT(vehicle_number) DO UPDATE SET vehicle_type = excluded.vehicle_type""",
            (vehicle_number, vehicle_type),
        )
        cursor = connection.execute(
            """INSERT INTO parking_records
               (vehicle_number, vehicle_type, slot_id, entry_time, status, user_id,
                payment_status, payment_method, transaction_id, amount_paid, fee)
               VALUES (?, ?, ?, ?, 'Parked', ?, 'Paid', ?, ?, ?, ?)""",
            (vehicle_number, vehicle_type, slot_id, entry_time, user_id,
             payment_method, transaction_id, amount, amount),
        )
        record_id = cursor.lastrowid
        connection.execute(
            "UPDATE parking_slots SET status = 'Occupied' WHERE slot_id = ?", (slot_id,)
        )
        connection.execute(
            """UPDATE bookings SET status = 'Completed' WHERE user_id = ?
               AND slot_id = ? AND status = 'Booked'""",
            (user_id, slot_id),
        )
        connection.execute(
            """INSERT INTO payments
               (transaction_id, user_id, parking_record_id, vehicle_number, slot_id,
                amount, payment_method, payment_status, payment_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'Paid', ?)""",
            (transaction_id, user_id, record_id, vehicle_number, slot_id,
             amount, payment_method, entry_time),
        )
        connection.commit()
        return "created", record_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def complete_user_parking(record_id, user_id, exit_time, duration):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        record = connection.execute(
            """SELECT slot_id FROM parking_records
               WHERE id = ? AND user_id = ? AND status = 'Parked'""",
            (record_id, user_id),
        ).fetchone()
        if record is None:
            connection.rollback()
            return False
        connection.execute(
            """UPDATE parking_records SET exit_time = ?, duration = ?, status = 'Completed'
               WHERE id = ? AND user_id = ? AND status = 'Parked'""",
            (exit_time, duration, record_id, user_id),
        )
        connection.execute(
            "UPDATE parking_slots SET status = 'Available' WHERE slot_id = ?",
            (record["slot_id"],),
        )
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_user_payment_records(user_id):
    return _rows_as_dicts(
        """SELECT * FROM payments WHERE user_id = ? ORDER BY id DESC""",
        (user_id,),
    )


def get_admin_users(search=None):
    query = """SELECT id, name, email, mobile, vehicle_number, vehicle_type, role,
                  is_active, created_at FROM users"""
    parameters = []
    if search:
        query += " WHERE name LIKE ? OR email LIKE ? OR mobile LIKE ?"
        pattern = "%" + search + "%"
        parameters.extend((pattern, pattern, pattern))
    query += " ORDER BY id DESC"
    return _rows_as_dicts(
        query, parameters
    )


def get_admin_vehicles(vehicle_number=None, status=None):
    query = """SELECT v.vehicle_number, v.vehicle_type, u.name AS owner,
                  r.slot_id, r.entry_time, r.exit_time,
                  COALESCE(r.status, 'Not parked') AS status
           FROM vehicles v
           LEFT JOIN users u ON UPPER(u.vehicle_number) = UPPER(v.vehicle_number)
           LEFT JOIN parking_records r ON r.id = (
               SELECT MAX(r2.id) FROM parking_records r2
               WHERE UPPER(r2.vehicle_number) = UPPER(v.vehicle_number)
           )"""
    conditions = []
    parameters = []
    if vehicle_number:
        conditions.append("UPPER(v.vehicle_number) LIKE UPPER(?)")
        parameters.append("%" + vehicle_number + "%")
    if status == "Active":
        conditions.append("r.status = 'Parked'")
    elif status == "Completed":
        conditions.append("r.status = 'Completed'")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY v.id DESC"
    return _rows_as_dicts(
        query, parameters,
    )


def get_all_payment_records(search=None, status=None):
    query = """SELECT p.*, u.name AS owner FROM payments p
           LEFT JOIN users u ON u.id = p.user_id"""
    conditions = []
    parameters = []
    if search:
        conditions.append("(UPPER(p.vehicle_number) LIKE UPPER(?) OR UPPER(p.transaction_id) LIKE UPPER(?))")
        pattern = "%" + search + "%"
        parameters.extend((pattern, pattern))
    if status in ("Paid", "Pending", "Failed"):
        conditions.append("p.payment_status = ?")
        parameters.append(status)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY p.id DESC"
    return _rows_as_dicts(
        query, parameters
    )


def toggle_user_active(user_id):
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """UPDATE users SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END
                   WHERE id = ? AND role = 'user'""",
                (user_id,),
            )


def update_admin_account(user_id, name, email, password_hash=None):
    with closing(get_connection()) as connection:
        try:
            with connection:
                if password_hash:
                    connection.execute(
                        """UPDATE users SET name = ?, email = ?, password_hash = ?
                           WHERE id = ? AND role = 'admin'""",
                        (name, email, password_hash, user_id),
                    )
                else:
                    connection.execute(
                        """UPDATE users SET name = ?, email = ?
                           WHERE id = ? AND role = 'admin'""",
                        (name, email, user_id),
                    )
        except sqlite3.IntegrityError:
            return False
    return True


def get_today_revenue():
    return _get_count(
        """SELECT
             (SELECT COALESCE(SUM(amount), 0) FROM payments
              WHERE payment_status = 'Paid' AND date(payment_time) = date('now', 'localtime')) +
             (SELECT COALESCE(SUM(fee), 0) FROM parking_records
              WHERE status = 'Completed' AND payment_status = 'Pending'
                AND date(exit_time) = date('now', 'localtime'))"""
    )


def get_period_revenue(date_modifier):
    return _get_count(
        """SELECT
             (SELECT COALESCE(SUM(amount), 0) FROM payments
              WHERE payment_status = 'Paid'
                AND date(payment_time) >= date('now', 'localtime', ?)) +
             (SELECT COALESCE(SUM(fee), 0) FROM parking_records
              WHERE status = 'Completed' AND payment_status = 'Pending'
                AND date(exit_time) >= date('now', 'localtime', ?))""",
        (date_modifier, date_modifier),
    )


def get_week_revenue():
    return get_period_revenue("-6 days")


def get_month_revenue():
    return get_period_revenue("start of month")


def get_total_users():
    return _get_count("SELECT COUNT(*) FROM users WHERE role = ?", ("user",))


def get_completed_payment_revenue():
    return get_total_revenue()


def get_today_entry_count():
    return _get_count(
        "SELECT COUNT(*) FROM parking_records WHERE date(entry_time) = date('now', 'localtime')"
    )


def get_today_exit_count():
    return _get_count(
        "SELECT COUNT(*) FROM parking_records WHERE exit_time IS NOT NULL AND date(exit_time) = date('now', 'localtime')"
    )


def add_parking_slots(slot_ids):
    with closing(get_connection()) as connection:
        with connection:
            for slot_id in slot_ids:
                connection.execute(
                    "INSERT OR IGNORE INTO parking_slots (slot_id) VALUES (?)",
                    (slot_id,),
                )


def add_parking_slot(slot_id):
    with closing(get_connection()) as connection:
        try:
            with connection:
                connection.execute("INSERT INTO parking_slots (slot_id) VALUES (?)", (slot_id,))
        except sqlite3.IntegrityError:
            return False
    return True


def remove_available_parking_slot(slot_id):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """DELETE FROM parking_slots WHERE slot_id = ? AND status = 'Available'
               AND NOT EXISTS (SELECT 1 FROM bookings WHERE bookings.slot_id = ? AND bookings.status = 'Booked')""",
            (slot_id, slot_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_parking_slot_status(slot_id, status):
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                "UPDATE parking_slots SET status = ? WHERE slot_id = ?",
                (status, slot_id),
            )


def save_parking_entry(vehicle_number, slot_id, entry_time, vehicle_type=None):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        active_record = connection.execute(
            """SELECT 1 FROM parking_records
               WHERE UPPER(vehicle_number) = UPPER(?) AND status = ?
               LIMIT 1""",
            (vehicle_number, "Parked"),
        ).fetchone()
        if active_record:
            connection.rollback()
            return None

        if vehicle_type:
            connection.execute(
                """INSERT INTO vehicles (vehicle_number, vehicle_type)
                   VALUES (?, ?)
                   ON CONFLICT(vehicle_number) DO UPDATE SET
                   vehicle_type = excluded.vehicle_type""",
                (vehicle_number, vehicle_type),
            )
        connection.execute(
            """UPDATE bookings SET status = ?
               WHERE UPPER(vehicle_number) = UPPER(?)
                 AND slot_id = ? AND status = ?""",
            ("Completed", vehicle_number, slot_id, "Booked"),
        )
        connection.execute(
            "UPDATE parking_slots SET status = ? WHERE slot_id = ?",
            ("Occupied", slot_id),
        )

        cursor = connection.execute(
            """INSERT INTO parking_records
               (vehicle_number, slot_id, entry_time, status)
               VALUES (?, ?, ?, ?)""",
            (vehicle_number, slot_id, entry_time, "Parked"),
        )
        connection.commit()
        return cursor.lastrowid
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def is_vehicle_currently_parked(vehicle_number):
    return bool(
        _get_count(
            """SELECT COUNT(*) FROM parking_records
               WHERE UPPER(vehicle_number) = UPPER(?) AND status = ?""",
            (vehicle_number, "Parked"),
        )
    )


def update_parking_exit(vehicle_number, slot_id, exit_time, duration, fee):
    with closing(get_connection()) as connection:
        with connection:
            cursor = connection.execute(
                """UPDATE parking_records
                   SET exit_time = ?, duration = ?, fee = ?, status = ?
                   WHERE id = (
                       SELECT id FROM parking_records
                       WHERE vehicle_number = ? AND slot_id = ? AND status = 'Parked'
                       ORDER BY id DESC LIMIT 1
                   )""",
                (exit_time, duration, fee, "Completed", vehicle_number, slot_id),
            )
            if cursor.rowcount > 0:
                connection.execute(
                    "UPDATE parking_slots SET status = ? WHERE slot_id = ?",
                    ("Available", slot_id),
                )
            return cursor.rowcount > 0


def _rows_as_dicts(query, parameters=()):
    with closing(get_connection()) as connection:
        rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]


def get_parking_records():
    return _rows_as_dicts("SELECT * FROM parking_records ORDER BY id")


def search_parking_records(vehicle_number=None, status=None):
    query = "SELECT * FROM parking_records"
    conditions = []
    parameters = []

    if vehicle_number:
        conditions.append("UPPER(vehicle_number) LIKE UPPER(?)")
        parameters.append("%" + vehicle_number + "%")

    if status:
        conditions.append("status = ?")
        parameters.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id DESC"
    return _rows_as_dicts(query, parameters)


def get_vehicles():
    return _rows_as_dicts("SELECT * FROM vehicles ORDER BY id")


def get_parking_slots():
    return _rows_as_dicts("SELECT * FROM parking_slots ORDER BY id")


def get_available_slots():
    return _rows_as_dicts(
        """SELECT parking_slots.slot_id
           FROM parking_slots
           WHERE parking_slots.status = 'Available'
             AND NOT EXISTS (
                 SELECT 1 FROM bookings
                 WHERE bookings.slot_id = parking_slots.slot_id
                   AND bookings.status = 'Booked'
             )
           ORDER BY parking_slots.id"""
    )


def check_active_booking(vehicle_number):
    bookings = _rows_as_dicts(
        """SELECT * FROM bookings
           WHERE UPPER(vehicle_number) = UPPER(?) AND status = 'Booked'
           ORDER BY id LIMIT 1""",
        (vehicle_number,),
    )
    return bookings[0] if bookings else None


def check_slot_booking(slot_id):
    bookings = _rows_as_dicts(
        """SELECT * FROM bookings
           WHERE slot_id = ? AND status = 'Booked'
           ORDER BY id LIMIT 1""",
        (slot_id,),
    )
    return bookings[0] if bookings else None


def create_booking(vehicle_number, slot_id, booking_time, user_id=None):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")

        active_vehicle_booking = connection.execute(
            """SELECT 1 FROM bookings
               WHERE UPPER(vehicle_number) = UPPER(?) AND status = 'Booked'
               LIMIT 1""",
            (vehicle_number,),
        ).fetchone()
        if active_vehicle_booking:
            connection.rollback()
            return "vehicle_booked"

        slot = connection.execute(
            "SELECT status FROM parking_slots WHERE slot_id = ?",
            (slot_id,),
        ).fetchone()
        if slot is None or slot["status"] != "Available":
            connection.rollback()
            return "unavailable"

        active_slot_booking = connection.execute(
            """SELECT 1 FROM bookings
               WHERE slot_id = ? AND status = 'Booked'
               LIMIT 1""",
            (slot_id,),
        ).fetchone()
        if active_slot_booking:
            connection.rollback()
            return "unavailable"

        connection.execute(
            """INSERT INTO bookings
               (vehicle_number, slot_id, booking_time, status, user_id)
               VALUES (?, ?, ?, ?, ?)""",
            (vehicle_number, slot_id, booking_time, "Booked", user_id),
        )
        connection.commit()
        return "created"
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_all_bookings():
    return _rows_as_dicts("SELECT * FROM bookings ORDER BY id DESC")


def get_user_bookings(user_id):
    return _rows_as_dicts(
        "SELECT * FROM bookings WHERE user_id = ? ORDER BY id DESC", (user_id,)
    )


def _get_count(query, parameters=()):
    with closing(get_connection()) as connection:
        row = connection.execute(query, parameters).fetchone()
        return row[0]


def get_total_slots():
    return _get_count("SELECT COUNT(*) FROM parking_slots")


def get_available_slots_count():
    return _get_count(
        "SELECT COUNT(*) FROM parking_slots WHERE status = ?",
        ("Available",),
    )


def get_occupied_slots_count():
    return _get_count(
        "SELECT COUNT(*) FROM parking_slots WHERE status = ?",
        ("Occupied",),
    )


def get_currently_parked_count():
    return _get_count(
        "SELECT COUNT(*) FROM parking_records WHERE status = ?",
        ("Parked",),
    )


def get_completed_records_count():
    return _get_count(
        "SELECT COUNT(*) FROM parking_records WHERE status = ?",
        ("Completed",),
    )


def get_total_revenue():
    return _get_count(
        """SELECT
             (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE payment_status = 'Paid') +
             (SELECT COALESCE(SUM(fee), 0) FROM parking_records
              WHERE status = 'Completed' AND payment_status = 'Pending')"""
    )


def get_recent_parking_records(limit=5):
    return _rows_as_dicts(
        "SELECT * FROM parking_records ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def get_slot_overview():
    return _rows_as_dicts(
        """SELECT parking_slots.slot_id,
                  parking_slots.status AS physical_status,
                  CASE
                      WHEN parking_slots.status = ? THEN 'occupied'
                      WHEN EXISTS (
                          SELECT 1 FROM bookings
                          WHERE bookings.slot_id = parking_slots.slot_id
                            AND bookings.status = ?
                      ) THEN 'booked'
                      ELSE 'available'
                  END AS display_status,
                  (SELECT parking_records.vehicle_number
                   FROM parking_records
                   WHERE parking_records.slot_id = parking_slots.slot_id
                   AND parking_records.status = ?
                   ORDER BY parking_records.id DESC LIMIT 1) AS vehicle_number,
                  (SELECT parking_records.vehicle_type FROM parking_records
                   WHERE parking_records.slot_id = parking_slots.slot_id AND parking_records.status = ?
                   ORDER BY parking_records.id DESC LIMIT 1) AS vehicle_type,
                  (SELECT parking_records.entry_time FROM parking_records
                   WHERE parking_records.slot_id = parking_slots.slot_id AND parking_records.status = ?
                   ORDER BY parking_records.id DESC LIMIT 1) AS entry_time,
                  (SELECT bookings.vehicle_number
                   FROM bookings
                   WHERE bookings.slot_id = parking_slots.slot_id
                     AND bookings.status = ?
                   ORDER BY bookings.id DESC LIMIT 1) AS booking_vehicle_number,
                  (SELECT bookings.booking_time
                   FROM bookings
                   WHERE bookings.slot_id = parking_slots.slot_id
                     AND bookings.status = ?
                   ORDER BY bookings.id DESC LIMIT 1) AS booking_time
           FROM parking_slots
           ORDER BY parking_slots.id""",
        ("Occupied", "Booked", "Parked", "Parked", "Parked", "Booked", "Booked"),
    )


def get_active_parking_record(vehicle_number, slot_id):
    records = _rows_as_dicts(
        """SELECT * FROM parking_records
           WHERE vehicle_number = ? AND slot_id = ? AND status = ?
           ORDER BY id DESC LIMIT 1""",
        (vehicle_number, slot_id, "Parked"),
    )
    return records[0] if records else None


def get_parking_record_by_id(record_id):
    records = _rows_as_dicts(
        """SELECT parking_records.*, vehicles.vehicle_type
           FROM parking_records
           LEFT JOIN vehicles
             ON vehicles.vehicle_number = parking_records.vehicle_number
           WHERE parking_records.id = ?""",
        (record_id,),
    )
    return records[0] if records else None
