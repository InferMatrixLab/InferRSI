"""Project collected knowledge contexts into the text and item fields a caller keeps."""

from __future__ import annotations

_IDENTITY_FIELDS = ("ref", "revision", "title", "kind", "backend", "scenario")
PROVENANCE_FIELDS = ("authority", "sources", "entrypoint", "skill_documents")


def assemble_context_text(contexts: list[dict]) -> str:
    """Render context views exactly as ``inferrsi collect`` prints them."""
    lines = []
    for context in contexts:
        for resource in context["resources"]:
            content = resource["content"]
            lines.append(
                f"--- begin context {context['ref']} @ {context['revision']} "
                f"{resource['path']} ---\n"
            )
            lines.append(content if content.endswith("\n") else content + "\n")
            lines.append(f"--- end context {resource['path']} ---\n")
        for omission in context["omissions"]:
            lines.append(f"{omission['path']}\tcontext_omitted\t{omission['reason']}\n")
    return "".join(lines)


def context_item(view: dict, *, provenance: bool = False) -> dict:
    """Keep the identity fields of one collected item.

    ``provenance`` also keeps the item's authority, sources, entrypoint and
    skill documents. It is off by default: an item projected without it has
    exactly the six identity fields, so a caller that supplies no provenance
    stores no empty provenance fields.
    """
    fields = _IDENTITY_FIELDS + PROVENANCE_FIELDS if provenance else _IDENTITY_FIELDS
    return {key: view.get(key) for key in fields}
