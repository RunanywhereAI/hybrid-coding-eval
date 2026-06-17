"""HTTP handler."""


def handle(req):
    # TODO: validate the request body against the schema
    body = req.get("body")
    # TODO: add rate limiting before calling the backend
    result = _call_backend(body)
    # TODO: surface upstream 5xx as 502 not 500
    return result


def _call_backend(body):
    return {"ok": True, "echo": body}
