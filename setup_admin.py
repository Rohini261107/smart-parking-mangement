"""Create the first admin account or update an existing admin account."""

import argparse
from getpass import getpass
import os
import sys

from werkzeug.security import generate_password_hash

from backend import database


def parse_args():
    parser = argparse.ArgumentParser(description="Create or update admin account.")
    parser.add_argument("--name", help="Admin name", default=os.environ.get("ADMIN_NAME"))
    parser.add_argument("--email", help="Admin email", default=os.environ.get("ADMIN_EMAIL"))
    parser.add_argument("--password", help="Admin password", default=os.environ.get("ADMIN_PASSWORD"))
    return parser.parse_args()


def main():
    database.init_db()
    args = parse_args()

    name = args.name.strip() if args.name else ""
    email = args.email.strip().lower() if args.email else ""
    password = args.password if args.password else ""

    if not (name and email and password):
        if not sys.stdin.isatty():
            print("Non-interactive environment: Provide --name, --email, --password or ADMIN_* env vars.")
            return
        if not name:
            name = input("Admin name: ").strip()
        if not email:
            email = input("Admin email: ").strip().lower()
        if not password:
            password = getpass("Admin password (at least 8 characters): ")

    if not name or "@" not in email or len(password) < 8:
        print("Enter a name, valid email, and password of at least 8 characters.")
        return

    password_hash = generate_password_hash(password)
    existing_admin = next(
        (user for user in database.get_admin_users() if user["role"] == "admin"),
        None,
    )

    if existing_admin:
        if email != existing_admin["email"].lower():
            print(f"An admin already exists ({existing_admin['email']}). Enter that admin's email to update it.")
            return
        if database.update_admin_account(existing_admin["id"], name, email, password_hash):
            print("Admin account updated.")
        else:
            print("Unable to update the admin account.")
        return

    if database.create_user(name, email, password_hash, role="admin"):
        print("Admin account created. You can now sign in.")
    else:
        print("An account with that email already exists.")


if __name__ == "__main__":
    main()
