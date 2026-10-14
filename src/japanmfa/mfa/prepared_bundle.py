"""Integrity checked handoff generated only in a private job work directory."""
import hashlib
import json
import os
import pickle
from pathlib import Path


def save_prepared_bundle(run, preparation, rows, config_sha):
    path = Path(run) / "prepared-bundle.pkl"
    if path.is_symlink():
        raise ValueError("bundle cannot be a symlink")
    data = pickle.dumps((preparation, rows), protocol=5)
    temporary = path.with_suffix(".partial")
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(data)
    os.replace(temporary, path)
    (Path(run) / "prepared-bundle.json").write_text(json.dumps({
        "sha256": hashlib.sha256(data).hexdigest(), "config_sha256": config_sha,
        "sources": len(rows)}))
    return path


def load_prepared_bundle(run, config_sha):
    path = Path(run) / "prepared-bundle.pkl"
    marker = Path(run) / "prepared-bundle.json"
    if path.is_symlink() or marker.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("bundle must be private and regular")
    metadata = json.loads(marker.read_text())
    if metadata["config_sha256"] != config_sha:
        raise ValueError("prepared configuration changed")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != metadata["sha256"]:
        raise ValueError("prepared bundle integrity mismatch")
    # This is our own 0600 spool file, never a NAS/user-supplied pickle.
    preparation, rows = pickle.loads(data)
    if len(rows) != metadata["sources"]:
        raise ValueError("prepared source coverage differs")
    return preparation, rows
