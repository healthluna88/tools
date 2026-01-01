import numpy as np


class Parameter:

    def __init__(self, name: str, default = None, label: str = None):

        self.name  = name
        self.label = label or name
        self.value = default

    def to_dict(self):

        return \
            {
                "type":  self.__class__.__name__,
                "label": self.label,
                "value": self.value
            }


class ParameterEnum(Parameter):

    def __init__(self, name, choices, default = None, label = None):

        super().__init__(name, default or choices[0], label)

        self.choices = choices


class ParameterNumber(Parameter):

    def __init__(self, name, default, v_min, v_max, v_step, label = None):

        super().__init__(name, default, label)

        self.min  = v_min
        self.max  = v_max
        self.step = v_step


class ParameterInt(ParameterNumber):

    def __init__(self, name, default = 0, v_min = 0, v_max = 100, v_step = 1, label = None):

        super().__init__(name, default, v_min, v_max, v_step, label)


class ParameterFloat(ParameterNumber):

    def __init__(self, name, default = 0.0, v_min = 0.0, v_max = 1.0, v_step = 0.01, label = None):

        super().__init__(name, default, v_min, v_max, v_step, label)

