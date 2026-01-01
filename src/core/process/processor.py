from __future__ import annotations

import logging
from typing import Any, ClassVar

import numpy as np

from .parameter import Parameter

logger = logging.getLogger(__name__)


class Processor:

    Registry: ClassVar[dict[str, dict[str, Any]]] = { }

    @staticmethod
    def register(cls):

        label = getattr(cls, "Label", cls.__name__)

        Processor.Registry[cls.__name__] = { "class": cls, "label": label }

        return cls

    @staticmethod
    def create(name: str) -> "Processor":

        if name not in Processor.Registry:

            raise ValueError(f"Unknown processor: {name}")

        return Processor.Registry[name]["class"]()

    def __init__(self, name: str, label: str = ""):

        self._name  = f"{name}-{hex(id(self))[2:].upper()}"
        self._label = label

        self.enabled = True

        self.parameters: dict[str, Parameter] = { }

    @property
    def name(self) -> str:

        return self._name

    @property
    def label(self) -> str:

        return self._label

    def add(self, param: Parameter) -> None:

        self.parameters[param.name] = param

    def set(self, name: str, value) -> None:

        if name in self.parameters:

            self.parameters[name].value = value

    def get(self, name: str):

        return self.parameters[name].value

    def process(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:

        return mask

    def to_dict(self) -> dict:

        parameters = { name: parameter.to_dict() for name, parameter in self.parameters.items() }

        return \
            {
                "class":      self.__class__.__name__,
                "enabled":    self.enabled,
                "parameters": parameters,
            }

    @classmethod
    def from_dict(cls, data: dict) -> "Processor":

        class_name = data["class"]

        if class_name not in Processor.Registry:

            raise ValueError(f"Unknown processor class: {class_name}")

        class_creator = Processor.Registry[class_name]["class"]

        processor: Processor = class_creator()
        processor.enabled = data.get("enabled", True)

        for name, parameter in data.get("parameters", { }).items():

            if name in processor.parameters:

                processor.parameters[name].value = parameter["value"]

            else:

                logger.warning \
                    (
                        "Processor %s has no parameter named %s. Skipping.",
                        processor.name,
                        name,
                    )

        return processor
