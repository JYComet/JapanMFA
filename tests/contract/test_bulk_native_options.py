import json
import sys
from pathlib import Path
import pytest
from japanmfa.mfa.g2p import MfaG2pClient, TerminalSokuonG2p

FAKE = Path(__file__).parents[1] / "fixtures/bin/fake_mfa.py"

def test_bulk_native_workers_preserve_pronunciations_and_forward_exact_flag(tmp_path, monkeypatch):
    argv = tmp_path / "argv.json"; monkeypatch.setenv("FAKE_MFA_ARGV", str(argv))
    command = tmp_path / "native.py"
    command.write_text("import sys,json,os\nfrom pathlib import Path\nPath(os.environ['FAKE_MFA_ARGV']).write_text(json.dumps(sys.argv))\nPath(sys.argv[4]).write_text('キョウ k jo N\\nハレ h a r e\\n')\n")
    client = TerminalSokuonG2p(MfaG2pClient((sys.executable, str(command))))
    before = client.pronounce(("キョウ", "ハレ"), tmp_path / "serial")
    after = client.pronounce(("キョウ", "ハレ"), tmp_path / "parallel", num_jobs=16)
    assert after == before
    assert json.loads(argv.read_text())[-2:] == ["--num_jobs", "16"]

@pytest.mark.parametrize("jobs", [0, -1])
def test_invalid_worker_count_never_starts_command(tmp_path, jobs):
    with pytest.raises(ValueError, match="positive"):
        MfaG2pClient(("must-not-run",)).pronounce(("キョウ",), tmp_path, num_jobs=jobs)
