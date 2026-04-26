"""
api.py — HTTP REST endpoints for a fictional web service.

Routes:
  POST /auth/login         — authenticate and get tokens
  POST /auth/logout        — invalidate tokens
  POST /auth/refresh       — exchange refresh token for new access token
  GET  /users              — list users (admin only)
  GET  /users/{id}         — get user by ID
  POST /users              — create a new user
  GET  /items              — list items (paginated)
  GET  /items/{id}         — get item by ID
  POST /items              — create an item
"""

import json
import logging
from typing import Any, Callable

from auth import login, logout, validate_jwt_token, refresh_access_token, require_role
from database import fetch_all, fetch_one, execute_write
from retry import retry
from cache import get_cached, set_cached, invalidate

logger = logging.getLogger(__name__)


# ── Simple request / response stubs ──────────────────────────────────────────

class Request:
    def __init__(self, method: str, path: str, headers: dict, body: dict):
        self.method  = method
        self.path    = path
        self.headers = headers
        self.body    = body or {}

    def bearer_token(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return None


class Response:
    def __init__(self, status: int, body: Any):
        self.status = status
        self.body   = body

    def to_dict(self) -> dict:
        return {"status": self.status, "body": self.body}


def _ok(body)    -> Response: return Response(200, body)
def _created(body) -> Response: return Response(201, body)
def _bad(msg)    -> Response: return Response(400, {"error": msg})
def _unauth(msg) -> Response: return Response(401, {"error": msg})
def _forbid(msg) -> Response: return Response(403, {"error": msg})
def _not_found() -> Response: return Response(404, {"error": "Not found"})


# ── Auth endpoints ────────────────────────────────────────────────────────────

def handle_login(req: Request) -> Response:
    """
    POST /auth/login
    Body: { "email": str, "password": str }
    Returns access_token, refresh_token on success.
    """
    email    = req.body.get("email")
    password = req.body.get("password")

    if not email or not password:
        return _bad("email and password are required")

    try:
        tokens = login(email, password)
        logger.info("User %s logged in successfully", email)
        return _ok(tokens)
    except ValueError as e:
        return _unauth(str(e))


def handle_logout(req: Request) -> Response:
    """POST /auth/logout — revoke tokens."""
    token = req.bearer_token()
    if not token:
        return _unauth("Missing bearer token")

    refresh = req.body.get("refresh_token")
    logout(token, refresh or "")
    return _ok({"message": "Logged out"})


def handle_refresh(req: Request) -> Response:
    """POST /auth/refresh — exchange refresh_token for new access_token."""
    refresh = req.body.get("refresh_token")
    if not refresh:
        return _bad("refresh_token is required")
    try:
        access = refresh_access_token(refresh)
        return _ok({"access_token": access})
    except ValueError as e:
        return _unauth(str(e))


# ── User endpoints ────────────────────────────────────────────────────────────

def handle_list_users(req: Request) -> Response:
    """GET /users — admin only, returns all users."""
    token = req.bearer_token()
    if not token:
        return _unauth("Authentication required")

    try:
        require_role(token, "admin")
    except (ValueError, PermissionError) as e:
        return _forbid(str(e))

    cache_key = "users:all"
    cached    = get_cached(cache_key)
    if cached:
        return _ok({"users": cached, "source": "cache"})

    rows = fetch_all("SELECT id, email, role, created_at FROM users ORDER BY created_at DESC")
    set_cached(cache_key, rows, ttl=60)
    return _ok({"users": rows, "source": "db"})


def handle_get_user(req: Request, user_id: str) -> Response:
    """GET /users/{id} — get a single user by ID."""
    token = req.bearer_token()
    if not token:
        return _unauth("Authentication required")

    try:
        payload = validate_jwt_token(token)
    except ValueError as e:
        return _unauth(str(e))

    # Users can only view their own profile unless admin
    if payload.get("user_id") != user_id and payload.get("role") != "admin":
        return _forbid("Cannot access another user's profile")

    row = fetch_one("SELECT id, email, role, created_at FROM users WHERE id = %s", (user_id,))
    if not row:
        return _not_found()

    return _ok(row)


@retry(max_attempts=3, retryable_exceptions=(RuntimeError,))
def handle_create_user(req: Request) -> Response:
    """
    POST /users — create a new user.
    Retries on transient DB errors up to 3 times.
    """
    token = req.bearer_token()
    if not token:
        return _unauth("Authentication required")

    try:
        require_role(token, "admin")
    except (ValueError, PermissionError) as e:
        return _forbid(str(e))

    email = req.body.get("email")
    role  = req.body.get("role", "viewer")

    if not email:
        return _bad("email is required")

    execute_write(
        "INSERT INTO users (email, role) VALUES (%s, %s)",
        (email, role),
    )
    invalidate("users:all")
    return _created({"message": f"User {email} created"})


# ── Item endpoints ────────────────────────────────────────────────────────────

def handle_list_items(req: Request) -> Response:
    """GET /items — paginated item listing."""
    page  = int(req.body.get("page", 1))
    limit = min(int(req.body.get("limit", 20)), 100)
    offset = (page - 1) * limit

    cache_key = f"items:page:{page}:limit:{limit}"
    cached    = get_cached(cache_key)
    if cached:
        return _ok({"items": cached, "page": page, "source": "cache"})

    rows = fetch_all(
        "SELECT id, name, price, stock FROM items ORDER BY id LIMIT %s OFFSET %s",
        (limit, offset),
    )
    set_cached(cache_key, rows, ttl=30)
    return _ok({"items": rows, "page": page, "source": "db"})


def handle_get_item(req: Request, item_id: str) -> Response:
    """GET /items/{id}"""
    cache_key = f"item:{item_id}"
    cached    = get_cached(cache_key)
    if cached:
        return _ok({**cached, "source": "cache"})

    row = fetch_one("SELECT * FROM items WHERE id = %s", (item_id,))
    if not row:
        return _not_found()

    set_cached(cache_key, row, ttl=120)
    return _ok({**row, "source": "db"})


# ── Router ────────────────────────────────────────────────────────────────────

def dispatch(req: Request) -> Response:
    """
    Simple request router — maps method + path to handler function.
    """
    routes: dict[tuple[str, str], Callable] = {
        ("POST", "/auth/login"):    handle_login,
        ("POST", "/auth/logout"):   handle_logout,
        ("POST", "/auth/refresh"):  handle_refresh,
        ("GET",  "/users"):         handle_list_users,
        ("POST", "/users"):         handle_create_user,
        ("GET",  "/items"):         handle_list_items,
    }

    key = (req.method, req.path)
    if key in routes:
        return routes[key](req)

    # Dynamic routes
    parts = req.path.strip("/").split("/")
    if len(parts) == 2:
        if parts[0] == "users":
            return handle_get_user(req, parts[1])
        if parts[0] == "items":
            return handle_get_item(req, parts[1])

    return Response(404, {"error": "Route not found"})
