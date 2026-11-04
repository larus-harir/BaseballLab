"""Streaming event CSV, so large experiments need not keep every pitch in memory."""

import csv
from dataclasses import fields
from pathlib import Path

from baseball_lab.data.schema import PitchEvent


class EventWriter:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.file = self.path.open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=[field.name for field in fields(PitchEvent)])
        self.writer.writeheader()
        return self

    def __call__(self, event: PitchEvent):
        self.writer.writerow(event.to_dict())

    def __exit__(self, *args):
        self.file.close()
