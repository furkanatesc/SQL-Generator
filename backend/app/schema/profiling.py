"""Sprint 28.1 — deterministic profiling probe (pure, stdlib only).

An optional counter threaded into schema hot paths. When a function receives
probe=None (every production caller), no increments happen -> zero behavior
change. Only the benchmark passes a probe to capture internal-explosion counts.
"""


class ProfileProbe:
    __slots__ = ("counts",)

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def incr(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n
