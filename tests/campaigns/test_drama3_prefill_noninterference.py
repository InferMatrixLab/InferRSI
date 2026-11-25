"""CPU reference fixture for the Drama3 partial-prefill noninterference contract.

Reference abstraction of the historical repair in
david6666666/drama-3-single-b300-inference@a6e660cc3693c61e14f4ed5acf75e3ac249294f0
("Isolate padded prefill rows and their GDN suffix states from live requests").
It models the state-ownership invariant only. It does NOT execute Drama3, GDN,
a codec, CUDA/ACL graphs or any NPU kernel, so it carries no target-execution,
graph-safety, allocator or arithmetic validity. See
``docs/drama3-npu-readiness.md`` §3 for the contract this fixture encodes.

Mechanism being modelled
------------------------
A batched prefill graph processes a fixed number of rows. Each processed row
owns a *primary* state slot AND an independent *GDN suffix-scratch* slot derived
by a mirror offset. When a partial batch is padded, the padding (dummy) rows
also consume a primary slot and a suffix slot.

The original engine sized the arena at ``2 * primary`` and assigned padding
primaries from the *top* of that arena (the mirror region). A primary placed in
the mirror region has its suffix fold back into the primary region under the
fixed captured buffer, overwriting an unrelated live request's recurrent,
convolution and KV state. The repair reserves a dedicated band for padding
primaries plus separate mirror space for their suffixes, and rejects any overlap
between padding slots and live slots.
"""

from __future__ import annotations

import pytest

# State kinds a single slot owns; all must stay with their owning request.
STATE_KINDS = ("recurrent", "conv", "kv")

# One prefilled batch processes this many rows (real + padding), mirroring the
# ``BatchedPrefillGraph(model, 8, ...)`` batch width in the source regression.
BATCH = 8

# Live requests occupy the primary band [0, PRIMARY_ROWS).
PRIMARY_ROWS = 16


class PrefillArena:
    """A reference state arena with a primary band and a GDN suffix mirror band.

    ``mirror_offset`` maps a lawful primary slot to its suffix scratch slot. When
    ``wrap`` is set a slot assigned at or beyond ``mirror_offset`` has its suffix
    fold back below ``mirror_offset`` (the historical fixed-buffer bug); otherwise
    such an assignment is rejected. A nonzero ``padding_reserve`` adds a dedicated
    band above the primary rows for padding primaries, with its own mirror space.
    """

    def __init__(self, *, wrap: bool, padding_reserve: int = 0) -> None:
        self.wrap = wrap
        self.padding_reserve = padding_reserve
        self.mirror_offset = PRIMARY_ROWS + padding_reserve
        self.total_rows = 2 * self.mirror_offset
        self.state: dict[str, list[str | None]] = {
            kind: [None] * self.total_rows for kind in STATE_KINDS
        }

    def suffix(self, primary: int) -> int:
        if 0 <= primary < self.mirror_offset:
            return primary + self.mirror_offset
        if self.wrap:
            return primary - self.mirror_offset
        raise ValueError("Primary slot must lie below the mirror boundary")

    def place_live(self, row: int, owner: str) -> None:
        for kind in STATE_KINDS:
            self.state[kind][row] = owner
            self.state[kind][self.suffix(row)] = owner

    def write_row(self, primary: int, owner: str) -> None:
        for kind in STATE_KINDS:
            self.state[kind][primary] = owner
            self.state[kind][self.suffix(primary)] = owner


def buggy_padding_slots(arena: PrefillArena, live_slots: list[int], padding: int) -> list[int]:
    """Original assignment: the top ``padding`` rows of the 2*primary arena."""
    return list(range(arena.total_rows - padding, arena.total_rows))


def fixed_padding_slots(arena: PrefillArena, live_slots: list[int], padding: int) -> list[int]:
    """Repaired assignment: the top of a dedicated band above the primary rows.

    Both the padding primaries and their mirrored suffixes stay clear of every
    live request. Overlap with any live slot is rejected rather than used.
    """
    padding_end = PRIMARY_ROWS + arena.padding_reserve
    slots = list(range(padding_end - padding, padding_end))
    if set(live_slots) & set(slots):
        raise ValueError("Prefill padding requires reserved primary state slots")
    return slots


def run_partial_prefill(*, wrap: bool, padding_reserve: int, assign, count: int):
    """Process ``count`` real rows padded up to ``BATCH`` and report live rows.

    Real requests occupy ``[0, count)``. Other in-flight requests occupy the low
    rows ``[count, BATCH)`` that the source regression protects, plus a high-slot
    request in ``[PRIMARY_ROWS - padding, PRIMARY_ROWS)`` — the slots the historical
    mirror-wrap lands on. Returns the arena, the live rows that must remain owned
    by their original requests, every live slot and the padding slots used.
    """
    arena = PrefillArena(wrap=wrap, padding_reserve=padding_reserve)
    padding = BATCH - count

    real_slots = list(range(count))
    other_low = list(range(count, BATCH))
    other_high = list(range(PRIMARY_ROWS - padding, PRIMARY_ROWS))
    protected = other_low + other_high
    for row in protected:
        arena.place_live(row, f"live-{row}")

    live_slots = real_slots + protected
    for slot in real_slots:
        arena.write_row(slot, f"real-{slot}")
    padding_slots = assign(arena, live_slots, padding)
    for slot in padding_slots:
        arena.write_row(slot, "padding")

    return arena, protected, live_slots, padding_slots


def footprint(arena: PrefillArena, slots: list[int]) -> set[int]:
    """Every primary and suffix slot touched by ``slots``."""
    return set(slots) | {arena.suffix(slot) for slot in slots}


@pytest.mark.parametrize("count", [5, 6, 7])
def test_buggy_layout_overwrites_a_live_request(count: int) -> None:
    """The original top-of-arena padding corrupts an unrelated live request."""
    arena, protected, live_slots, padding_slots = run_partial_prefill(
        wrap=True, padding_reserve=0, assign=buggy_padding_slots, count=count
    )
    assert footprint(arena, padding_slots) & footprint(arena, live_slots)
    corrupted = [
        row
        for row in protected
        if any(arena.state[kind][row] == "padding" for kind in STATE_KINDS)
    ]
    assert corrupted, (
        "Expected the historical collision: a padding suffix slot should fold back "
        "onto a live request's primary state"
    )


@pytest.mark.parametrize("count", [5, 6, 7])
def test_fixed_layout_preserves_every_live_request(count: int) -> None:
    """The repaired layout leaves all live primary and suffix state untouched.

    ``wrap=True`` keeps the real modulo suffix mapping active; the repair holds
    because every assigned slot stays below the mirror boundary.
    """
    arena, protected, live_slots, padding_slots = run_partial_prefill(
        wrap=True, padding_reserve=BATCH, assign=fixed_padding_slots, count=count
    )
    assert not footprint(arena, padding_slots) & footprint(arena, live_slots)
    for row in protected:
        for slot in (row, arena.suffix(row)):
            for kind in STATE_KINDS:
                assert arena.state[kind][slot] == f"live-{row}", (count, row, slot, kind)
    for row in range(count):
        for slot in (row, arena.suffix(row)):
            for kind in STATE_KINDS:
                assert arena.state[kind][slot] == f"real-{row}", (count, row, slot, kind)


@pytest.mark.parametrize("count", [5, 6, 7])
def test_fixed_assignment_without_reserved_band_is_rejected(count: int) -> None:
    """Without the reserved band the repaired assignment refuses live slots."""
    with pytest.raises(ValueError, match="reserved primary state slots"):
        run_partial_prefill(
            wrap=True, padding_reserve=0, assign=fixed_padding_slots, count=count
        )


def test_fixed_assignment_rejects_live_slot_overlap() -> None:
    """Requesting padding slots that collide with live slots is an explicit error."""
    arena = PrefillArena(wrap=True, padding_reserve=BATCH)
    overlapping = [PRIMARY_ROWS + BATCH - 2, PRIMARY_ROWS + BATCH - 1]
    with pytest.raises(ValueError, match="reserved primary state slots"):
        fixed_padding_slots(arena, overlapping, padding=2)
