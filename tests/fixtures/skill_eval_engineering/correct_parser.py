def evaluate(status, frames, requested_tokens):
    def result(reason):
        return {"success": reason in ("length", "stop"), "reason": reason}
    if status != 200:
        return result("http_error")
    terminal = None
    done = False
    for index, frame in enumerate(frames):
        if frame == "[DONE]":
            if done or index != len(frames) - 1:
                return result("malformed_frame")
            done = True
            continue
        if isinstance(frame, dict) and "error" in frame:
            return result("stream_error")
        if done or terminal is not None or not isinstance(frame, dict):
            return result("malformed_frame")
        if set(frame) == {"content"} and type(frame["content"]) is str:
            continue
        if (set(frame) != {"finish_reason", "completion_tokens"}
                or frame["finish_reason"] not in ("length", "stop")
                or type(frame["completion_tokens"]) is not int
                or frame["completion_tokens"] < 0):
            return result("malformed_frame")
        terminal = frame
    if terminal is None:
        return result("missing_terminal")
    count = terminal["completion_tokens"]
    finish = terminal["finish_reason"]
    if count > requested_tokens or (finish == "length" and count != requested_tokens):
        return result("token_mismatch")
    return result(finish)
