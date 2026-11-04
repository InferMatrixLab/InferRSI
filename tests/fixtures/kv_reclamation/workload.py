"""Protected deterministic input construction, independent of submitted code."""


def workload(count):
    if type(count) is not int or count < 1:
        raise ValueError("count must be a positive integer")
    events = [{"op": "allocate", "request_id": str(index), "generation": 0,
               "blocks": [2 * index, 2 * index + 1], "write_step": index % 257,
               "save_required": index % 3 != 0} for index in range(count)]
    events += [{"op": "finish", "request_id": str(index), "generation": 0}
               for index in reversed(range(count))]
    events += [{"op": "save_complete", "request_id": str(index), "generation": 0}
               for index in range(count)]
    events += [{"op": "advance", "processed_step": frontier} for frontier in range(257)]
    return events
