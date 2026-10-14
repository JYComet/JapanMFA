"""One active alignment and one bounded lookahead preparation window."""
from concurrent.futures import ThreadPoolExecutor


class PreparationWindows:
    def __init__(self, prepare, align, commit):
        self.prepare, self.align, self.commit = prepare, align, commit
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.active = None

    def submit(self, work):
        preparation = self.pool.submit(self.prepare, work)
        self.finish()
        if preparation.result() != 0:
            raise RuntimeError("preparation window failed; original work retained")
        self.active = (work, self.pool.submit(self.align, work))

    def finish(self):
        if self.active is not None:
            work, future = self.active
            code = future.result()
            self.commit(work, code)
            self.active = None

    def __enter__(self):
        return self

    def __exit__(self, kind, value, tb):
        try:
            if kind is None:
                self.finish()
        finally:
            self.pool.shutdown(wait=True, cancel_futures=True)
