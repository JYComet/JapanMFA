"""Per-key publication locks for this job's bounded preparation processes."""
from japanmfa.cache import StageCache


class PreparationCache(StageCache):
    def load_or_run(self, stage, fingerprint, producer, **kwargs):
        import fcntl
        locks = self.root / ".preparation-locks"
        locks.mkdir(parents=True, exist_ok=True)
        with (locks / (stage + "-" + fingerprint)).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return super().load_or_run(stage, fingerprint, producer, **kwargs)
