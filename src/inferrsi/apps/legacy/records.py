"""Read the two retained Apps record types written under their former Python names."""

import pickle
from pathlib import PosixPath, WindowsPath
from typing import BinaryIO

from ..handoff.context_provider import DeliveredContextDraft
from ..storage.archive import RunOutput

_RECORDS = {
    ("inferrsi.apps.archive", "RunOutput"): RunOutput,
    ("inferrsi.apps.context_provider", "DeliveredContextDraft"): DeliveredContextDraft,
    (RunOutput.__module__, RunOutput.__name__): RunOutput,
    (DeliveredContextDraft.__module__, DeliveredContextDraft.__name__): DeliveredContextDraft,
}


def _new_record(cls, base, state):
    if cls not in (RunOutput, DeliveredContextDraft) or base is not object or state is not None:
        raise pickle.UnpicklingError("unexpected retained record constructor")
    return object.__new__(cls)


def _legacy_bytes(text, encoding):
    if type(text) is not str or encoding != "latin1":
        raise pickle.UnpicklingError("unexpected retained bytes representation")
    return text.encode("latin1")


# Protocols 0/1 use Python 2 names for record reconstruction and bytes.
_GLOBALS = {
    **_RECORDS,
    ("copy_reg", "_reconstructor"): _new_record,
    ("copyreg", "_reconstructor"): _new_record,
    ("__builtin__", "object"): object,
    ("builtins", "object"): object,
    ("_codecs", "encode"): _legacy_bytes,
    ("pathlib", "PosixPath"): PosixPath,
    ("pathlib", "WindowsPath"): WindowsPath,
    ("pathlib._local", "PosixPath"): PosixPath,
    ("pathlib._local", "WindowsPath"): WindowsPath,
}


class _RecordReader(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        try:
            return _GLOBALS[module, name]
        except KeyError:
            raise pickle.UnpicklingError("unsupported global in retained Apps record") from None


def load_record(stream: BinaryIO) -> RunOutput | DeliveredContextDraft:
    """Read a trusted local record for offline migration on its original platform."""
    record = _RecordReader(stream).load()
    if type(record) not in (RunOutput, DeliveredContextDraft):
        raise pickle.UnpicklingError("expected a retained Apps record")
    return record
