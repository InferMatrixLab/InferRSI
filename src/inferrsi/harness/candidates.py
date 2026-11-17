"""Retain declared candidate inputs; never copy an undeclared project environment."""

import shutil
import stat
from pathlib import Path

from ..infra.artifacts import digest, sha256


def members(source: Path, includes: list[str] | None = None) -> dict[str, Path]:
    if source.is_symlink() or not source.exists():
        raise ValueError("Candidate input is missing or symbolic")
    if source.is_file():
        return {source.name: source}
    selected = {}
    for name in includes or ["."]:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Candidate includes must be relative paths inside the project")
        entry = source / relative
        if not entry.exists():
            raise ValueError(f"Declared candidate input is missing: {name}")
        if any(p.is_symlink() for p in (entry, *entry.parents) if p.is_relative_to(source)):
            raise ValueError("Candidate inputs cannot traverse symbolic links")
        paths = entry.rglob("*") if entry.is_dir() else [entry]
        for path in paths:
            if path.is_symlink():
                raise ValueError("Candidate inputs cannot contain symbolic links")
            rel = path.relative_to(source)
            if ".git" in rel.parts or "__pycache__" in rel.parts or path.suffix == ".pyc":
                continue
            if path.is_file():
                selected[rel.as_posix()] = path
    if not selected:
        raise ValueError("Candidate snapshot has no declared files")
    return dict(sorted(selected.items()))


def identity(source: Path, includes: list[str] | None = None) -> str:
    if source.is_file() and not source.is_symlink():
        return sha256(source)
    return digest({name: {"sha256": sha256(path), "mode": stat.S_IMODE(path.stat().st_mode)}
                   for name, path in members(source, includes).items()})


def retain(source: Path, destination: Path, includes: list[str] | None = None) -> str:
    """Copy bytes, then reject a changing input set or partial snapshot."""
    source = source.absolute()
    if destination.resolve().is_relative_to(source.resolve()):
        raise ValueError("Snapshot output must be outside the candidate inputs")
    before = identity(source, includes)
    if source.is_file():
        destination.write_bytes(source.read_bytes())
        shutil.copymode(source, destination)
    else:
        destination.mkdir()
        for name, path in members(source, includes).items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            shutil.copymode(path, target)
    if identity(source, includes) != before or identity(destination) != before:
        raise ValueError("Candidate changed while taking its snapshot")
    return before
