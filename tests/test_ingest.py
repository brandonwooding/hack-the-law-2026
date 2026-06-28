from pathlib import Path

import yaml

from legalgraph import ingest


def test_build_seed_uk():
    seed = ingest.build_seed("uk", "ukpga/2023/50", title="Online Safety Act 2023",
                             concepts=["eurovoc:online-safety"])
    assert seed == {"id": "ukpga/2023/50", "title": "Online Safety Act 2023",
                    "concepts": ["eurovoc:online-safety"]}


def test_build_seed_eu_uses_celex_key():
    seed = ingest.build_seed("eu", "32024R1689", title="AI Act")
    assert seed["celex"] == "32024R1689"
    assert "id" not in seed


def test_minimal_scope_eu_disables_cases():
    seed = ingest.build_seed("eu", "32024R1689")
    scope = ingest.minimal_scope("eu", seed)
    assert scope["eu"]["seeds"] == [seed]
    assert scope["eu"]["limits"]["cases_per_seed"] == 0


def test_minimal_scope_uk_has_single_seed():
    seed = ingest.build_seed("uk", "ukpga/2023/50")
    scope = ingest.minimal_scope("uk", seed)
    assert scope["uk"]["seeds"] == [seed]


def test_add_seed_to_scope_is_idempotent(tmp_path):
    scope_file = tmp_path / "scope.yaml"
    scope_file.write_text(yaml.safe_dump({
        "uk": {"seeds": [{"id": "ukpga/2003/21"}]},
        "eu": {"seeds": [{"celex": "32022R2065"}]},
    }))
    seed = ingest.build_seed("uk", "ukpga/2023/50", title="Online Safety Act 2023")

    added_first = ingest.add_seed_to_scope("uk", seed, scope_path=scope_file)
    added_again = ingest.add_seed_to_scope("uk", seed, scope_path=scope_file)

    data = yaml.safe_load(scope_file.read_text())
    ids = [s["id"] for s in data["uk"]["seeds"]]
    assert added_first is True
    assert added_again is False
    assert ids.count("ukpga/2023/50") == 1
    assert "ukpga/2003/21" in ids  # existing seeds preserved
