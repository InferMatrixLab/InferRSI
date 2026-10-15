"""External techniques remain attributed candidates, never implicit target support."""

import json
import re
from pathlib import Path

import pytest

from omnirsi import catalog
from omnirsi.arguments import parser
from omnirsi.catalog import get_knowledge, repository_pack, search_knowledge
from omnirsi.cli import main

ROOT = Path(__file__).resolve().parents[1] / "src/omnirsi/data/knowledge_packs"


def test_external_snapshot_has_complete_navigation_and_pinned_sources():
    paths = set(ROOT.glob("*/*/*/*/*.json"))
    links = re.findall(r"\]\(([^)]+\.json)\)", (ROOT / "README.md").read_text())
    assert {ROOT / link for link in links} == paths
    for tier in ("dependency", "peer"):
        records = search_knowledge(tier=tier, limit=100)
        assert {r["repo"] for r in records} == set(catalog.KNOWLEDGE_SCOPES[tier])
        for record in records:
            assert record["status"] == "imported"
            assert record["verification"]["locally_verified"] is False
            assert record["downstream_impact"] and record["limitations"]
            assert "/pull/" not in json.dumps(record)
            for source in record["sources"]:
                assert f"/blob/{source['commit']}/" in source["url"]
                assert re.fullmatch(r"[0-9a-f]{64}", source["content_sha256"])


def test_filters_intersect_before_limit_without_downstream_inheritance():
    records = search_knowledge(
        tier="dependency", repo="flashinfer", backend="cuda", scenario="llm.serving", limit=1
    )
    assert len(records) == 1 and records[0]["repo"] == "flashinfer"
    assert search_knowledge(tier="peer", repo="flashinfer") == []
    assert search_knowledge(repo="flashinfer", backend="ascend") == []
    assert search_knowledge(repo="flashinfer", scenario="diffusion.t2i") == []
    assert search_knowledge(tier="dependency", repo="vllm_omni") == []
    assert all(r["repo"] == "vllm_omni" for r in search_knowledge(repo="vllm_omni"))
    # Common guidance is available within its source repo, without inheriting validation.
    common = search_knowledge(repo="triton", backend="rocm")
    assert common and all(r["backend"] == "common" for r in common)
    assert all(not r["verification"]["locally_verified"] for r in common)
    assert search_knowledge(tier="contribution", repo="vllm_ascend") == []
    with pytest.raises(ValueError, match="Unknown knowledge tier"):
        search_knowledge(tier="validated")


def test_cli_preserves_tier_scope_and_transfer_cautions(capsys):
    assert main(["knowledge", "search", "--tier", "peer", "--json", "--limit", "100"]) == 0
    assert all(r["tier"] == "peer" for r in json.loads(capsys.readouterr().out))
    assert main(["context", "--repo-type", "xdit", "--backend", "cuda", "--tier", "peer"]) == 0
    output = capsys.readouterr().out
    assert "Tier: `peer`" in output
    assert "Downstream Impact:" in output
    assert "quality-sensitive experiment" in output
    assert '"locally_verified": false' in output
    assert "not tool instructions" in output
    assert main(["knowledge", "show", "triton.common.kernel.bandwidth_fusion_resource_limits"]) == 0
    assert json.loads(capsys.readouterr().out) == get_knowledge(
        "triton.common.kernel.bandwidth_fusion_resource_limits"
    )
    with pytest.raises(ValueError, match="Unknown repository type"):
        repository_pack("xdit")
    with pytest.raises(SystemExit):
        parser().parse_args(["doctor", "--repo-type", "xdit"])
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize("bad_tier", ["contribution", "peer", None])
def test_misclassified_external_card_is_rejected_before_retrieval(
    tmp_path, monkeypatch, bad_tier
):
    record = get_knowledge("flashinfer.cuda.llm.paged_decode_dispatch")
    if bad_tier is None:
        del record["tier"]
    else:
        record["tier"] = bad_tier
    target = (
        tmp_path / "data/knowledge_packs/dependency/flashinfer/cuda/llm/paged-decode-dispatch.json"
    )
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(record))
    monkeypatch.setattr(catalog, "files", lambda _: tmp_path)
    with pytest.raises(ValueError, match="tier disagrees"):
        search_knowledge(tier="contribution")
