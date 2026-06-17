"""Routing table."""

ROUTES = {
    # FIXME: the /health route currently bypasses auth
    "/health": "handler.health",
    "/echo": "handler.handle",
}
