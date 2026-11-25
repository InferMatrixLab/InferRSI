"""Verify per-object evidence references and standing-review interpretations."""

from __future__ import annotations

import re

if __package__:
    from .label_cutover import instant
else:
    from label_cutover import instant

REPO = "InferMatrixLab/InferRSI"
ISSUE_COMMENT = re.compile(rf"https://github\.com/{REPO}/issues/\d+#issuecomment-(\d+)")
STANDING = re.compile(
    r"^\s*<!-- always-on-bot:v1 -->\s*$|\bI am (?:an? |the )?"
    r"(?:unattended|standing) reviewer\b|我是常驻(?:自动)?评审",
    re.I | re.M,
)
REVIEW = re.compile(r"\breview\b|NO PASS|检视|评审|审阅|复核", re.I)
UNINVITED = re.compile(
    r"\bI (?:started|submitted|initiated) (?:this|the|my) review "
    r"(?:uninvited|without (?:an? )?invitation)\b|"
    r"我(?:在)?未(?:经|获)(?:点名|邀请)(?:时|便|就|的情况下)?(?:主动)?(?:发起|开始|提交)(?:了)?评审",
    re.I,
)
CAPACITY = {
    "owner": re.compile(
        r"\bI (?:am |act (?:here )?as )(?:the )?(?:issue |decision )?owner\b|"
        r"我(?:是|作为)(?:本单)?负责人",
        re.I,
    ),
    "delegate": re.compile(r"on behalf of|acting for|受托|代办|代表", re.I),
    "human": re.compile(r"\bI (?:am|reviewed as) (?:a )?human\b|人工评审|我本人", re.I),
}


def actor(record: dict) -> str:
    return (record.get("user") or record.get("actor") or {}).get("login", "").lower()


def record_time(record: dict):
    value = record.get("submitted_at") or record.get("created_at")
    return instant(value) if value else None


def text_version_time(record: dict):
    """Latest time the observed text could have been written."""
    created = record_time(record)
    if created and record.get("updated_at"):
        return max(created, instant(record["updated_at"]))
    return created


def own_text(body: str, *, keep_standing_marker: bool = False) -> str:
    """Discard quoted material, code examples and hidden instructions."""
    if keep_standing_marker:
        body = re.sub(
            r"(?m)^([ \t]*)<!-- always-on-bot:v1 -->[ \t]*$",
            r"\1I am a standing reviewer",
            body,
        )
    lines = []
    fence = None
    for line in re.sub(r"<!--.*?-->", "", body, flags=re.S).splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">"):
            continue
        marker = re.match(r"^(`{3,}|~{3,})", stripped)
        if marker:
            run = marker[1]
            if fence is None:
                fence = run
            elif run.startswith(fence) and not stripped[len(run) :].strip():
                fence = None
        elif fence is None and not line.startswith(("    ", "\t")):
            lines.append(line)
    return "\n".join(lines)


class Evidence:
    """Accept a curator's interpretation only with a traceable quotation."""

    def __init__(self, obj, events, supplied, linked):
        self.obj = obj
        self.supplied = supplied
        self.local = {e["html_url"]: e for e in events if e.get("html_url")}
        self.local[obj["html_url"]] = obj
        self.linked = linked

    def proof(self, value):
        if not isinstance(value, dict):
            return None
        url, quote = value.get("url"), value.get("quote")
        if not isinstance(url, str) or not isinstance(quote, str) or not quote.strip():
            return None
        record = self.local.get(url)
        if record is None:
            via = self.local.get(value.get("via"), {})
            if url not in (via.get("body") or ""):
                return None
            record = self.linked.get(url)
        if not record or quote not in (record.get("body") or ""):
            return None
        return url, record, quote

    def field(self, name):
        proof = self.proof(self.supplied.get(name))
        return proof[0] if proof else None

    def standing_reviews(self, pr: bool):
        """Return (code, detail, pending, sources) for positive or ambiguous cases."""
        activities = {
            v.get("activity"): v
            for v in self.supplied.get("standing_reviews", [])
            if isinstance(v, dict) and isinstance(v.get("activity"), str)
        }
        for url, record in self.local.items():
            body = own_text(record.get("body") or "", keep_standing_marker=True)
            if (
                record.get("event") in {"reviewed", "commented"}
                and STANDING.search(body)
                and (record.get("event") == "reviewed" or REVIEW.search(body))
            ):
                activities.setdefault(url, {})
        for url, item in activities.items():
            event = self.local.get(url) or {}
            account = actor(event)
            body = own_text(event.get("body") or "", keep_standing_marker=True)
            if event.get("event") not in {"reviewed", "commented"} or not account:
                yield (
                    "review-evidence",
                    "Verify the cited native review activity.",
                    True,
                    [self.obj["html_url"]],
                )
                continue
            role = self.proof(item.get("role"))
            mode = {"human": "human", "delegated": "delegate"}.get(item.get("mode"))
            role_text = (
                own_text((role[1].get("body") or ""), keep_standing_marker=True) if role else ""
            )
            if (
                role
                and mode
                and role[2] in role_text
                and CAPACITY[mode].search(role[2])
                and actor(role[1]) == account
            ):
                continue
            if not (
                STANDING.search(body)
                or (
                    role
                    and role[2] in role_text
                    and actor(role[1]) == account
                    and STANDING.search(role[2])
                )
            ):
                yield (
                    "review-role",
                    "The account's standing reviewer role needs evidence.",
                    True,
                    [url],
                )
                continue
            if event.get("event") != "reviewed" and not REVIEW.search(body):
                continue
            revision = event.get("commit_id") or item.get("revision")
            if not revision or (not event.get("commit_id") and revision not in body):
                yield "review-revision", "Identify the reviewed commit or Issue state.", True, [url]
                continue
            if pr and revision != self.obj.get("head_sha"):
                continue
            if not pr and revision != self.supplied.get("issue_revision"):
                yield "review-revision", "Verify the named current Issue state.", True, [url]
                continue
            invitation = self.proof(item.get("invitation"))
            if invitation:
                _, record, quote = invitation
                mentioned = re.search(rf"(?<![\w-])@{re.escape(account)}(?![\w-])", quote, re.I)
                invited_at = text_version_time(record)
                activity_at = record_time(event)
                if (
                    mentioned
                    and REVIEW.search(quote)
                    and quote in own_text(record.get("body") or "")
                    and revision in quote
                    and actor(record) != account
                    and activity_at
                    and invited_at
                    and invited_at < activity_at
                ):
                    continue
            if UNINVITED.search(body) and STANDING.search(body):
                yield (
                    "uninvited-standing-review",
                    "The standing reviewer explicitly reported starting "
                    "uninvited on this revision.",
                    False,
                    [url],
                )
            else:
                yield (
                    "review-invitation",
                    "Confirm a dated, revision-specific invitation or delegation.",
                    True,
                    [url],
                )
