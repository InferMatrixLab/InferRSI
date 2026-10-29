def evaluate(status, frames, requested_tokens):
    return {"success": status == 200, "reason": "length" if status == 200 else "http_error"}
