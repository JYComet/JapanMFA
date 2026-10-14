from pathlib import Path
import pytest
from japanmfa.asr.precomputed_ctc import PrecomputedCTCClient
from japanmfa.errors import StageFailure


def test_identity_is_per_source_and_rejects_changed_ctc(tmp_path):
    a=tmp_path/"a.TextGrid"; a.write_text("original-a")
    b=tmp_path/"b.TextGrid"; b.write_text("original-b")
    small=PrecomputedCTCClient({"a":a},{"a":"文"})
    large=PrecomputedCTCClient({"a":a,"b":b},{"a":"文","b":"別"})
    assert small.cache_identity("a")==large.cache_identity("a")
    a.write_text("changed")
    with pytest.raises(StageFailure,match="changed"):
        small.cache_identity("a")
