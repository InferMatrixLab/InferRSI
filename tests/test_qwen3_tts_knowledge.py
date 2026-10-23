"""Standalone TTS knowledge is discoverable without implying runtime support."""

import pytest

from inferrsi.catalog import get_knowledge, repository_pack, search_knowledge
from inferrsi.cli import main


def test_qwen_tts_peer_scope_and_runtime_boundary():
    records = search_knowledge(
        "Qwen3-TTS", tier="peer", repo="qwen3_tts_engine",
        backend="ascend", scenario="audio.tts", limit=10,
    )
    assert len(records) == 3
    for record in records:
        assert get_knowledge(record["id"]) == record
        assert record["status"] == "imported"
        assert record["verification"]["locally_verified"] is False
    assert search_knowledge(repo="qwen3_tts_engine", backend="cuda") == []
    assert search_knowledge(repo="qwen3_tts_engine", scenario="diffusion.image_generation") == []
    assert search_knowledge(repo="qwen3_tts_engine", tier="contribution") == []
    with pytest.raises(ValueError):
        repository_pack("qwen3_tts_engine")


def test_qwen_tts_cli_retains_source_and_unverified_status(capsys):
    assert main([
        "knowledge", "search", "Qwen3-TTS", "--tier", "peer",
        "--repo-type", "qwen3_tts_engine", "--backend", "ascend",
        "--scenario", "audio.tts", "--limit", "10", "--json",
    ]) == 0
    output = capsys.readouterr().out
    assert "qwen3_tts_engine.ascend.audio.codec_constants_and_state" in output
    assert '"locally_verified": false' in output
    assert "github.com/InferMatrixLab/qwen3-tts-engine/blob/" in output
