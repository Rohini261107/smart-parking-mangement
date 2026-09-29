# Smart Parking Management System

A college project built with Python, Flask, SQLite, HTML, CSS, and JavaScript.
The application keeps its Flask code in `backend/` and its templates and static
files in `frontend/`.

## Setup and run locally

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open the local address printed by Flask. The first start creates
`database/parking.db`, its tables, and ten parking slots (`P1` through `P10`).

## Admin account

Run `python setup_admin.py` and enter the account details when prompted. The
first run creates an admin. Later runs can update that account by entering its
email address again. Passwords are stored as Werkzeug password hashes.

For automated environments, you can also pass parameters:
```bash
python setup_admin.py --name "Admin" --email "admin@smartparking.com" --password "YourPassword123"
```
Or set `ADMIN_NAME`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` environment variables.

## Deployment on Render

This project is fully configured for continuous deployment on [Render](https://render.com).

### Method 1: Render Blueprints (Automatic)
1. Push this repository to your GitHub account.
2. Go to the [Render Dashboard](https://dashboard.render.com).
3. Click **New +** -> **Blueprint**.
4. Select your `Smart_Parking_Management` repository.
5. Render will detect `render.yaml`, set up the build command (`pip install -r requirements.txt`), and start the web service with `gunicorn app:app`.

### Method 2: Web Service (Manual)
1. In Render Dashboard, click **New +** -> **Web Service**.
2. Connect your GitHub repository.
3. Configure:
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Environment variables:
   - `SMART_PARKING_SECRET_KEY`: Set to any long random string or let Render generate it.
   - `PYTHON_VERSION`: `3.11.9`
   - `ADMIN_EMAIL` / `ADMIN_PASSWORD` (Optional): To customize the default administrator credentials on initialization.

## Features

- User registration, login, profile, parking history, and private receipts.
- Server-side role checks and CSRF checks for form submissions.
- Simulated user payment at entry. The payment is recorded once, and exit
  completes the session without charging again.
- Admin facility dashboard, slot management, bookings, users, records, and
  revenue views.
- Admin managed entry and exit use the OOP fee calculator: cars cost ₹20 per
  started hour and bikes cost ₹10 per started hour.
- User entry uses configurable one-time demo session rates managed in Admin
  Settings. This keeps the entry-payment workflow from needing to predict an
  exit time.
- Production-ready WSGI server configuration (`gunicorn`) with Render Blueprint support.
