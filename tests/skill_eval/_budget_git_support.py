"""In-memory Git data API shared by the PR and daily budget store fakes."""

import base64
import copy
import hashlib
import json


class GitDataAPI:
    def __init__(self, repository_id, ref_name):
        self.repository_id = repository_id
        self.ref_name = ref_name
        self.objects = {}
        self.tip = None
        self.before_patch = None

    def put(self, value):
        sha = hashlib.sha1(json.dumps(value, sort_keys=True).encode()).hexdigest()
        self.objects[sha] = {**value, "sha": sha}
        return sha

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

    def ref(self):
        if self.tip is None:
            raise OSError("404")
        return {"ref": self.ref_name, "object": {"type": "commit", "sha": self.tip}}

    def request(self, method, path, data=None):
        if method == "GET":
            if path == "":
                return {"id": self.repository_id}
            if path.startswith("/git/ref/"):
                return self.ref()
            return copy.deepcopy(self.objects[path.rsplit("/", 1)[1]])
        if path == "/git/trees":
            return {"sha": self.tree(data["tree"][0]["content"])}
        if path == "/git/commits":
            return {"sha": self.commit(data["tree"], data["parents"], message=data["message"])}
        assert method == "PATCH" and path == f"/git/{self.ref_name}"
        assert data["force"] is False
        if self.before_patch:
            callback, self.before_patch = self.before_patch, None
            callback()
        self.update_ref(data["sha"])
        return self.ref()
