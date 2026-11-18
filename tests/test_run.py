"""run.py: --pack, --all, the call-count line printed before the run, and config errors."""
import pytest

import run
from engine import config
from tests.helpers import FAKE_PACKS, MockBackend, make_cfg, standard_rules


def call_main(argv, tmp_path, **kw):
    kw.setdefault("cfg", make_cfg())
    kw.setdefault("backend", MockBackend(standard_rules()))
    return run.main(argv, packs_dir=FAKE_PACKS, out_root=tmp_path / "outputs", **kw)


def test_pack_run_prints_the_call_count_first_then_the_summary(tmp_path, capsys):
    backend = MockBackend(standard_rules())
    assert call_main(["--pack", "engine_pack"], tmp_path, backend=backend) == 0
    out = capsys.readouterr().out
    assert out.index("Claude calls for this run") < out.index("Running engine_pack")
    assert "engine_pack: 6 extract calls, up to 6 draft calls" in out
    assert "total: 6 extract calls and up to 6 draft calls" in out
    assert "6 items, 3 auto, 2 need a person, 1 skipped" in out and "sum_mismatch (1)" in out
    assert (tmp_path / "outputs" / "engine_pack" / "dashboard.html").exists()
    assert not (tmp_path / "outputs" / "index.html").exists()          # only --all writes the index


def test_all_writes_the_index(tmp_path, capsys):
    assert call_main(["--all"], tmp_path) == 0
    index = (tmp_path / "outputs" / "index.html").read_text(encoding="utf-8")
    assert "engine_pack/dashboard.html" in index and "Engine test pack" in index
    assert "Index:" in capsys.readouterr().out


def test_the_run_makes_no_calls_before_the_count_is_printed(tmp_path, capsys):
    class Spy(MockBackend):
        printed_before_first_call = None

        def generate(self, *a, **kw):
            if self.printed_before_first_call is None:        # what had been printed when call 1 happened
                self.printed_before_first_call = capsys.readouterr().out
            return super().generate(*a, **kw)
    backend = Spy(standard_rules())
    call_main(["--pack", "engine_pack"], tmp_path, backend=backend)
    assert len(backend.extract_calls()) == 6
    assert "total: 6 extract calls" in backend.printed_before_first_call


def test_unknown_pack_and_missing_choice(tmp_path, capsys):
    assert call_main(["--pack", "nope"], tmp_path) == 2
    err = capsys.readouterr().err
    assert "Unknown pack 'nope'" in err and "engine_pack" in err
    with pytest.raises(SystemExit):
        call_main([], tmp_path)                                         # --pack or --all is required
    with pytest.raises(SystemExit):
        call_main(["--pack", "engine_pack", "--all"], tmp_path)         # but not both


def test_no_packs_found(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert run.main(["--all"], cfg=make_cfg(), backend=MockBackend(), packs_dir=empty, out_root=tmp_path / "o") == 2
    assert "No packs found" in capsys.readouterr().err


def test_config_error_is_reported_and_nothing_runs(tmp_path, capsys, monkeypatch):
    for var in ("BACKEND", "ANTHROPIC_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)                          # default backend is api, which needs both
    assert run.main(["--pack", "engine_pack"], packs_dir=FAKE_PACKS, out_root=tmp_path / "o") == 2
    assert "ANTHROPIC_MODEL" in capsys.readouterr().err and not (tmp_path / "o").exists()


def test_make_backend_picks_the_right_class():
    from engine.backends.api import ApiBackend
    from engine.backends.claude_code import ClaudeCodeBackend
    cli = run.make_backend(config.load({"BACKEND": "claude-code", "CLAUDE_CODE_TIMEOUT": "7"}))
    assert isinstance(cli, ClaudeCodeBackend) and cli.timeout == 7.0
    api = run.make_backend(config.load({"ANTHROPIC_MODEL": "m", "ANTHROPIC_API_KEY": "k"}))
    assert isinstance(api, ApiBackend) and api.model == "m"
