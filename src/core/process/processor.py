import numpy as np

from .parameter import Parameter


class Processor:

    Registry = {}

    @staticmethod
    def register(cls):

        label = getattr(cls, 'Label', cls.__name__)

        Processor.Registry[cls.__name__] = { "class": cls, "label": label }

        return cls

    @staticmethod
    def create(name: str):

        if name not in Processor.Registry:

            raise ValueError(f"Unknown processor: {name}")

        return Processor.Registry[name]["class"]()

    def __init__(self, name: str, label: str = ""):

        self._name  = f"{name}-{hex(id(self))[2:].upper()}"
        self._label = label

        self.enabled     = True
        self.parameters  = {}

    @property
    def name(self):

        return self._name

    @property
    def label(self):

        return self._label

    def add(self, param: Parameter):

        self.parameters[param.name] = param

    def set(self, name, value):

        if name in self.parameters:

            self.parameters[name].value = value

    def get(self, name):

        return self.parameters[name].value

    def process(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:

        return mask

    def to_dict(self):

        parameters = { name: parameter.to_dict() for name, parameter in self.parameters.items() }

        return \
            {
                "class":       self.__class__.__name__,
                "enabled":     self.enabled,
                "parameters":  parameters
            }

    @classmethod
    def from_dict(cls, data: dict):

        class_name = data["class"]

        if class_name not in Processor.Registry:

            raise ValueError(f"Unknown processor class: {class_name}")

        class_creator = Processor.Registry[class_name]["class"]

        processor = class_creator()

        processor.enabled = data.get("enabled", True)

        for name, parameter in data.get("parameters", {}).items():

            if name in processor.parameters:

                processor.parameters[name].value = parameter["value"]

            else:

                print(f"Warning: Processor {processor.name} has no parameter named {name}. Skipping.")

        return processor

