from typing import Dict, List

import numpy as np

from .processor import Processor


class Pipeline:

    def __init__(self):

        self._sequence: List[     Processor] = []
        self._map:      Dict[str, Processor] = {}

    def processors(self):

        return self._sequence.copy()

    def add(self, p: Processor):

        self._sequence.append(p)

        self._map[p.name] = p

    def remove(self, name: str):

        p = self._map.pop(name, None)

        if p is not None:

            self._sequence.remove(p)

    def get_at(self, index: int):

        return self._sequence[index]

    def get_by(self, name: str) -> Processor | None:

        return self._map.get(name)

    def reorder_by(self, names: List[str]):

        existing = list(self._map.keys())

        missing = [n for n in existing if n not in names]

        if missing:

            raise ValueError(f"Missing processors in reorder: {missing}")

        extra = [n for n in names if n not in self._map]

        if extra:

            raise ValueError(f"Unknown processors in reorder: {extra}")

        if len(names) != len(existing):

            raise ValueError("Processor count mismatch or duplicate names in reorder")

        self._sequence = [self._map[name] for name in names]

    def process(self, image: np.ndarray, mask: np.ndarray):

        for p in self._sequence:

            if p.enabled:

                mask = p.process(image, mask)

        return mask

    def to_dict(self):

        return { "sequence": [p.to_dict() for p in self._sequence]}

    @classmethod
    def from_dict(cls, data: dict):

        pipeline = cls()

        for processor in data.get("sequence", []):

            pipeline.add(Processor.from_dict(processor))

        return pipeline

