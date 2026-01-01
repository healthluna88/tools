from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSlider, QSpinBox, QDoubleSpinBox, QComboBox
)
from PySide6.QtCore import Qt, Signal

from core.process.parameter import Parameter, ParameterInt, ParameterEnum, ParameterFloat


class ProcessorEditor(QWidget):

    param_changed    = Signal(str, object)
    enabled_changed  = Signal(bool)
    remove_requested = Signal()

    def __init__(self, processor):

        super().__init__()

        self.processor = processor

        check = QCheckBox()
        check.setChecked(processor.enabled)
        check.stateChanged.connect(self._on_enabled_changed)

        label = QLabel(processor.label)

        button = QPushButton("×")
        button.setFixedWidth(22)
        button.setFlat(True)
        button.clicked.connect(self.remove_requested.emit)

        caption = QWidget()

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(10)
        bar.addWidget(check)
        bar.addWidget(label)
        bar.addStretch()
        bar.addWidget(button)

        caption.setLayout(bar)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(caption)

        for p in processor.parameters.values():

            layout.addLayout(self._make_param_row(p))

        self.setLayout(layout)

    def _make_param_row(self, p: Parameter):

        layout = QHBoxLayout()
        layout.setSpacing(10)

        label = QLabel(p.label)
        label.setFixedWidth(80)

        layout.addWidget(label)

        if isinstance(p, ParameterEnum):

            combo = QComboBox()
            combo.addItems(p.choices)
            combo.setCurrentText(p.value)

            def on_combo(val):

                self._emit_param_changed(p.name, val)

            combo.currentTextChanged.connect(on_combo)

            layout.addWidget(combo)

            return layout

        elif isinstance(p, ParameterInt):

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 1000)
            slider.setValue(int(1000 * (p.value - p.min) / (p.max - p.min)))

            spin = QSpinBox()
            spin.setRange(p.min, p.max)
            spin.setSingleStep(p.step)
            spin.setValue(p.value)

            def slider_to_spin():
                ratio = slider.value() / 1000.0
                val = p.min + ratio * (p.max - p.min)
                spin.blockSignals(True)
                spin.setValue(int(val))
                spin.blockSignals(False)
                self._emit_param_changed(p.name, int(val))

            def spin_to_slider(val):
                ratio = (val - p.min) / (p.max - p.min)
                slider.blockSignals(True)
                slider.setValue(int(ratio * 1000))
                slider.blockSignals(False)
                self._emit_param_changed(p.name, val)

            slider.valueChanged.connect(slider_to_spin)
            spin.valueChanged.connect(spin_to_slider)

            layout.addWidget(slider)
            layout.addWidget(spin)

            return layout

        elif isinstance(p, ParameterFloat):

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 1000)
            slider.setValue(int(1000 * (p.value - p.min) / (p.max - p.min)))

            spin = QDoubleSpinBox()
            spin.setRange(p.min, p.max)
            spin.setSingleStep(p.step)
            spin.setValue(p.value)

            def slider_to_spin():

                ratio = slider.value() / 1000.0

                val = p.min + ratio * (p.max - p.min)

                spin.blockSignals(True)
                spin.setValue(int(val))
                spin.blockSignals(False)

                self._emit_param_changed(p.name, int(val))

            def spin_to_slider(val):

                ratio = (val - p.min) / (p.max - p.min)

                slider.blockSignals(True)
                slider.setValue(int(ratio * 1000))
                slider.blockSignals(False)

                self._emit_param_changed(p.name, val)

            slider.valueChanged.connect(slider_to_spin)
            spin.valueChanged.connect(spin_to_slider)

            layout.addWidget(slider)
            layout.addWidget(spin)
            return layout

    def _emit_param_changed(self, name, value):

        self.processor.set(name, value)

        self.param_changed.emit(name, value)

    def _on_enabled_changed(self, state):

        enabled = (state == Qt.CheckState.Checked.value)

        self.processor.enabled = enabled

        self.enabled_changed.emit(enabled)
