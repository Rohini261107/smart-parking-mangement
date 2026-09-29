from functools import wraps
import hmac
import secrets

from flask import abort, g, redirect, session, url_for

from . import database


def csrf_token():
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def valid_csrf_token(token):
    expected_token = session.get("csrf_token", "")
    return bool(expected_token and token and hmac.compare_digest(expected_token, token))


def _session_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None

    user = database.get_user_by_id(user_id)
    if user is None or not user.get("is_active", 1):
        session.clear()
        return None
    return user


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        user = _session_user()
        if user is None:
            return redirect(url_for("login"))
        g.current_user = user
        return view_function(*args, **kwargs)

    return wrapped_view


def admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        user = _session_user()
        if user is None:
            return redirect(url_for("login", portal="admin"))
        if user["role"] != "admin":
            abort(403)
        g.current_user = user
        return view_function(*args, **kwargs)

    return wrapped_view


def user_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        user = _session_user()
        if user is None:
            return redirect(url_for("login", portal="user"))
        if user["role"] != "user":
            abort(403)
        g.current_user = user
        return view_function(*args, **kwargs)

    return wrapped_view
