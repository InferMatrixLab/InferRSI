"""Synthetic CPU task starter: a deliberately repeated linear scan, not vLLM."""


class Reclaimer:
    def __init__(self):
        self._frontier = -1
        self._leases = []
        self._generations = {}
        self._blocks = set()

    def apply(self, event):
        if type(event) is not dict or type(event.get("op")) is not str:
            raise ValueError("event must have an operation")
        op = event["op"]
        fields = {
            "allocate": {"op", "request_id", "generation", "blocks", "write_step",
                         "save_required"},
            "finish": {"op", "request_id", "generation"},
            "save_complete": {"op", "request_id", "generation"},
            "advance": {"op", "processed_step"},
        }
        if op not in fields or set(event) != fields[op]:
            raise ValueError("unexpected operation or fields")
        integers = ("processed_step",) if op == "advance" else ("generation",)
        if op == "allocate":
            integers += ("write_step",)
        if any(type(event[key]) is not int or event[key] < 0 for key in integers):
            raise ValueError("integer fields must be nonnegative integers, excluding bool")
        if op != "advance" and type(event["request_id"]) is not str:
            raise ValueError("request_id must be a string")
        if op == "allocate":
            request, generation, blocks = event["request_id"], event["generation"], event["blocks"]
            if (type(blocks) is not list or not blocks
                    or any(type(block) is not int or block < 0 for block in blocks)
                    or len(set(blocks)) != len(blocks)
                    or type(event["save_required"]) is not bool):
                raise ValueError("invalid allocation fields")
            if (generation <= self._generations.get(request, -1)
                    or any(lease["request_id"] == request for lease in self._leases)
                    or self._blocks.intersection(blocks)):
                raise ValueError("allocation conflicts with lifetime history")
            self._leases.append({**event, "blocks": tuple(blocks), "finished": False,
                                 "saved": False})
            self._generations[request] = generation
            self._blocks.update(blocks)
        elif op == "advance":
            if event["processed_step"] < self._frontier:
                raise ValueError("processed frontier cannot decrease")
            self._frontier = event["processed_step"]
        else:
            for lease in self._leases:
                if (lease["request_id"], lease["generation"]) == (
                        event["request_id"], event["generation"]):
                    lease["finished" if op == "finish" else "saved"] = True
                    break
        reclaimed, remaining = [], []
        for lease in self._leases:
            if (lease["finished"] and (not lease["save_required"] or lease["saved"])
                    and lease["write_step"] <= self._frontier):
                reclaimed.extend(lease["blocks"])
                self._blocks.difference_update(lease["blocks"])
            else:
                remaining.append(lease)
        self._leases = remaining
        return reclaimed

    def pending(self):
        return [(lease["request_id"], lease["generation"], lease["blocks"])
                for lease in self._leases]
