class PerformanceClassifier:
    FAST_THRESHOLD_MS = 100.0
    NORMAL_THRESHOLD_MS = 500.0

    @classmethod
    def classify(cls, duration_ms: float) -> str:
        if duration_ms < cls.FAST_THRESHOLD_MS:
            return "fast"
        elif duration_ms <= cls.NORMAL_THRESHOLD_MS:
            return "normal"
        else:
            return "slow"
