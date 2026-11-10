import json
import subprocess

import pytest

from tools import check_vllm_ascend_source_anchors as check

SOURCE_PATH = "vllm_ascend/ascend_config.py"


@pytest.fixture
def source_repo(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    git("init", "-q")
    source = repo / SOURCE_PATH
    source.parent.mkdir()
    source.write_text(
        "class AscendConfig:\n"
        "    unrelated: int = 1\n"
        "\n"
        "    mega_moe_max_tokens: int = 65536\n"
        "    enable_fused_mc2: int = 0\n",
        encoding="utf-8",
    )
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "Source fixture")
    return repo, git("rev-parse", "HEAD"), git


def document(pin, defaults="L5", capacity="L4"):
    base = f"{check.SOURCE_URL}/blob/{pin}/{SOURCE_PATH}"
    return (f"[unselected link]({base}#L1)\n"
            f"[current defaults]({base}#{defaults})\n"
            f"[Capacity field]({base}#{capacity})\n")


def metadata(path, pin):
    path.write_text(json.dumps({"sources": [
        {"type": "git", "url": check.SOURCE_URL, "commit": pin},
    ]}), encoding="utf-8")


def test_reads_immutable_objects_without_touching_dirty_checkout(source_repo):
    repo, pin, git = source_repo
    (repo / SOURCE_PATH).write_text("uncommitted content\n", encoding="utf-8")
    before = git("status", "--porcelain")
    verified = check.verify_anchors(repo, document(pin), pin)
    assert len(verified) == 2
    assert "enable_fused_mc2: int = 0" in verified[0]
    assert "mega_moe_max_tokens: int = 65536" in verified[1]
    assert git("status", "--porcelain") == before
    assert (repo / SOURCE_PATH).read_text() == "uncommitted content\n"


def test_accepts_a_tight_span_containing_the_definition(source_repo):
    repo, pin, _ = source_repo
    assert len(check.verify_anchors(repo, document(pin, defaults="L4-L5"), pin)) == 2


def test_rejects_wrong_pinned_source_even_when_replaced_with_matching_definitions(source_repo):
    repo, pin, git = source_repo
    source = repo / SOURCE_PATH
    source.write_text(source.read_text().replace("= 65536", "= 1").replace("= 0", "= 999"),
                      encoding="utf-8")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "Different definitions")
    bad_pin = git("rev-parse", "HEAD")
    git("replace", bad_pin, pin)
    assert "enable_fused_mc2: int = 0" in git("show", f"{bad_pin}:{SOURCE_PATH}")
    with pytest.raises(ValueError, match="anchored source does not contain"):
        check.verify_anchors(repo, document(bad_pin), bad_pin)


@pytest.mark.parametrize("anchor", ["L2", "L3"])
def test_rejects_in_bounds_unrelated_or_blank_source_lines(source_repo, anchor):
    repo, pin, _ = source_repo
    with pytest.raises(ValueError, match="current defaults: anchored source does not contain"):
        check.verify_anchors(repo, document(pin, defaults=anchor), pin)


def test_checks_each_selected_definition(source_repo):
    repo, pin, _ = source_repo
    with pytest.raises(ValueError, match="Capacity field: anchored source does not contain"):
        check.verify_anchors(repo, document(pin, capacity="L5"), pin)


@pytest.mark.parametrize(("anchor", "error"), [
    ("L1-L6", "anchor span must contain"),
    ("L5-L4", "anchor span must contain"),
    ("L6", "anchor exceeds source length"),
    ("L0", "immutable source blob link"),
])
def test_rejects_invalid_or_broad_spans(source_repo, anchor, error):
    repo, pin, _ = source_repo
    with pytest.raises(ValueError, match=error):
        check.verify_anchors(repo, document(pin, defaults=anchor), pin)


def test_rejects_link_from_a_different_existing_commit(source_repo):
    repo, pin, git = source_repo
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--allow-empty", "-qm", "Same content, different revision")
    other_pin = git("rev-parse", "HEAD")
    with pytest.raises(ValueError, match="differs from source pin"):
        check.verify_anchors(repo, document(other_pin), pin)


@pytest.mark.parametrize("revision", ["main", "HEAD", "1234567"])
def test_rejects_mutable_or_abbreviated_link_revisions(source_repo, revision):
    repo, pin, _ = source_repo
    with pytest.raises(ValueError, match="immutable source blob link"):
        check.verify_anchors(repo, document(revision), pin)


def test_rejects_noncommit_source_pin(source_repo):
    repo, _, git = source_repo
    blob = git("hash-object", SOURCE_PATH)
    with pytest.raises(ValueError, match="must identify a commit object"):
        check.verify_anchors(repo, document(blob), blob)


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong path"])
def test_requires_unique_label_and_expected_source_path(source_repo, change):
    repo, pin, _ = source_repo
    text = document(pin)
    if change == "missing":
        text = text.replace("current defaults", "other defaults")
    elif change == "duplicate":
        text += text
    else:
        text = text.replace(SOURCE_PATH, "vllm_ascend/unrelated.py")
    with pytest.raises(ValueError, match="exactly one Markdown link|expected source path"):
        check.verify_anchors(repo, text, pin)


def test_metadata_requires_full_source_commit(tmp_path):
    path = tmp_path / "metadata.json"
    metadata(path, "main")
    with pytest.raises(ValueError, match="full 40-character commit SHA"):
        check.metadata_pin(path)


def test_cli_defaults_read_and_enforce_metadata_pin(source_repo, tmp_path, monkeypatch, capsys):
    repo, pin, git = source_repo
    doc = tmp_path / "reference.md"
    doc.write_text(document(pin), encoding="utf-8")
    info = tmp_path / "metadata.json"
    metadata(info, pin)
    monkeypatch.setattr(check, "DEFAULT_DOC", doc)
    monkeypatch.setattr(check, "DEFAULT_METADATA", info)
    assert check.main(["--repo", str(repo)]) == 0
    assert f"Verified 2 source anchors at {pin}" in capsys.readouterr().out

    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--allow-empty", "-qm", "Changed metadata revision")
    metadata(info, git("rev-parse", "HEAD"))
    assert check.main(["--repo", str(repo)]) == 1
    assert "differs from source pin" in capsys.readouterr().err
