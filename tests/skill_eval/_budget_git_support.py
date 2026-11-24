"""Git data objects shared by the PR and daily budget store fakes."""

import base64
import copy
import hashlib
import json


class GitObjects:
    def __init__(self):
        self.objects = {}

    def put(self, value):
        sha = hashlib.sha1(json.dumps(value, sort_keys=True).encode()).hexdigest()
        self.objects[sha] = {**value, "sha": sha}
        return sha

    def read_object(self, path):
        return copy.deepcopy(self.objects[path.rsplit("/", 1)[1]])

    def tree(self, content):
        raw = content.encode()
        blob = self.put({
            "encoding": "base64", "size": len(raw), "content": base64.b64encode(raw).decode(),
        })
        return self.put({
            "truncated": False,
            "tree": [{"path": "ledger.json", "mode": "100644", "type": "blob", "sha": blob}],
        })

    def commit(self, tree, parents, **fields):
        return self.put({"tree": {"sha": tree}, "parents": [{"sha": p} for p in parents], **fields})
