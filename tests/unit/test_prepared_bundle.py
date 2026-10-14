from pathlib import Path
import pytest
from japanmfa.mfa.prepared_bundle import save_prepared_bundle, load_prepared_bundle


def test_bundle_integrity_checked_before_loading(tmp_path):
    run = tmp_path / "run"; run.mkdir()
    path = save_prepared_bundle(run, {"items": "prepared"}, [{"stem":"a"}], "config-sha")
    assert load_prepared_bundle(run, "config-sha") == ({"items":"prepared"}, [{"stem":"a"}])
    with pytest.raises(ValueError, match="configuration"):
        load_prepared_bundle(run, "new-config")
    path.write_bytes(path.read_bytes()+b"changed")
    with pytest.raises(ValueError, match="integrity"):
        load_prepared_bundle(run, "config-sha")
