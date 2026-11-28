"""Model research uses the ordinary per-question Find and pinned Read workflow."""

import json
from importlib.resources import files

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.cli.arguments import parser
from inferrsi.knowledge.research import PROCEDURE

H3_QUESTION = "MiniMax-H3 component inventory on Apple Silicon"
MLX_QUESTION = "MLX lazy evaluation and buffer lifetime"
PROFILE = "references/minimax-h3-profile.json"
QUESTIONS = (
    (H3_QUESTION, "audit_h3_runtime_residency"),
    (MLX_QUESTION, "lazy_evaluation_stream_lifetimes"),
)
RETIRED = {
    "--model": "MiniMax-H3", "--framework": "mlx", "--task": "diffusion", "--modality": "video",
    "--mechanism": "memory", "--target-backend": "metal", "--target-device": "Apple Silicon",
    "--target-memory-gib": "64",
}


def _run(capsys, *argv):
    assert main(list(argv)) == 0
    return json.loads(capsys.readouterr().out)


def test_model_research_options_are_only_in_the_historical_parser(capsys):
    with pytest.raises(SystemExit) as help_exit:
        main(["find", "--help"])
    assert help_exit.value.code == 0
    help_text = capsys.readouterr().out
    for flag, value in RETIRED.items():
        assert flag not in help_text
        with pytest.raises(SystemExit) as error:
            main(["find", H3_QUESTION, flag, value])
        assert error.value.code == 2 and "unrecognized arguments" in capsys.readouterr().err

    old = parser(historical=True)
    dimensions = [word for flag, value in RETIRED.items() if flag != "--model"
                  for word in (flag, value)]
    for words in (["find", "--model"], ["knowledge", "research"]):
        archived = old.parse_args([*words, "MiniMax-H3", *dimensions])
        assert archived.model == "MiniMax-H3" and archived.framework == ["mlx"]
        assert archived.target_memory_gib == 64


def test_model_profile_opens_at_the_advertised_revision(capsys):
    found = _run(capsys, "find", H3_QUESTION, "--limit", "1", "--json")
    hit, = found["items"]
    read_args = hit["read_args"]
    body = _run(capsys, *read_args)
    assert PROFILE in body["content"]
    # A base install can use a package projection with an explicit SKILL.md resource.
    args = read_args[:]
    if "--resource" in args:
        del args[args.index("--resource"):args.index("--resource") + 2]
    opened = _run(capsys, *args, "--resource", PROFILE)
    assert opened["revision"] == body["revision"] == read_args[read_args.index("--revision") + 1]
    assert opened["ref"] == body["ref"] and opened["content_resource"].endswith("/" + PROFILE)
    profile = json.loads(opened["content"])
    assert profile["model"] == "MiniMax-H3" and "MiniMax-H3" in profile["aliases"]
    assert {row["role"] for row in profile["components"]} == {
        "denoiser", "text_encoder", "video_vae", "audio_vae",
    }
    assert profile["input_modalities"] == ["text", "image", "video", "audio"]
    assert profile["output_modalities"] == ["video", "audio"]
    assert all(source["commit"] in source["url"] for source in profile["sources"])
    assert not profile["verification"]["locally_verified"]
    resources = files("inferrsi.knowledge")
    for key in ("skill_resource", "inventory_resource", "worked_example_resource"):
        assert resources.joinpath(*profile[key].split("/")).is_file()
    assert resources.joinpath(*PROCEDURE.split("/")).is_file()
    missing = _run(capsys, "find", "zzcanaryunknownqx", "--json")
    assert missing["no_match"] and not missing["items"]


def test_session_keeps_each_research_question_and_selected_read(tmp_path, capsys):
    root = tmp_path / "campaign"
    _run(capsys, "campaign", "init", "--directory", str(root), "--id", "research")
    searches = []
    for query, skill in QUESTIONS:
        found = _run(capsys, "find", query, "--session", str(root), "--limit", "1")
        search = found["reference"]
        searches.append(search["path"])
        assert search["kind"] == "knowledge_search"
        capture = json.loads((root / search["path"]).read_bytes())
        assert capture["request"]["query"] == found["query"] == query
        assert capture["contexts"] == []
        hit, = found["items"]
        assert hit["material_ref"] == "package:inferrsi.common.skills." + skill
        opened = _run(capsys, *hit["read_args"])
        assert opened["search_ref"] == search["path"]
        assert opened["ref"] == hit["material_ref"] and opened["revision"] == hit["revision"]
        assert opened["reference"]["kind"] == "delivered_context" and opened["content"]
        if query == H3_QUESTION:
            resource = _run(capsys, *hit["read_args"], "--resource", PROFILE)
            assert resource["search_ref"] == search["path"]
            assert resource["revision"] == hit["revision"]
            assert json.loads(resource["content"])["model"] == "MiniMax-H3"
    assert len(set(searches)) == 2
