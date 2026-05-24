from typing import List
from app.trace.models import NL2SQLTrace

class RecordingTraceStore:
    def __init__(self):
        self.saved: List[NL2SQLTrace] = []

    def save(self, trace: NL2SQLTrace) -> None:
        self.saved.append(trace)
