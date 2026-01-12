from PySide6.QtCore import QRect, QMargins, Qt, QPoint, Signal, QRegularExpression
from PySide6.QtGui import QPixmap, QImage, QPen, QBrush, QRegularExpressionValidator
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem, QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QVBoxLayout, QHBoxLayout, QPushButton, QDialogButtonBox, QDockWidget, QWidget, QCheckBox, QLineEdit

import numpy as np

class PropertiesDialog(QDialog):
    def __init__(self, magnification, pxsize):
        super().__init__()
        self.setWindowTitle("Properties")

        self.magnification = QSpinBox(minimum=1, maximum=80, singleStep=10)
        self.magnification.setValue(magnification)
        self.pxsize = QDoubleSpinBox(minimum=0, maximum=100, singleStep=10, decimals=2, suffix=f" micron")
        self.pxsize.setValue(pxsize)
        layout = QFormLayout()
        layout.addRow("Magnification", self.magnification)
        layout.addRow("Pixel size", self.pxsize)


        self.button_box = QDialogButtonBox( QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        dialog_layout = QVBoxLayout()
        dialog_layout.addLayout(layout)
        dialog_layout.addWidget(self.button_box)
        self.setLayout(dialog_layout)
    
    def get_values(self):
        return self.magnification.value(), self.pxsize.value()

class SweepDialog(QDialog):
    def __init__(self, title: str, limits, defaults, unit):
        super().__init__()
        self.setWindowTitle(title)

        self.start = QDoubleSpinBox(minimum=limits[0], maximum=limits[1], singleStep=10, decimals=1, suffix=f" {unit}")
        self.start.setValue(defaults[0])
        self.end = QDoubleSpinBox(minimum=limits[2], maximum=limits[3], singleStep=10, decimals=1, suffix=f" {unit}")
        self.end.setValue(defaults[1])
        self.number = QSpinBox(minimum=10, maximum=200, singleStep=10)
        self.number.setValue(defaults[2])
        layout = QFormLayout()
        layout.addRow("Start", self.start)
        layout.addRow("End", self.end)
        layout.addRow("Number", self.number)


        self.button_box = QDialogButtonBox( QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        dialog_layout = QVBoxLayout()
        dialog_layout.addLayout(layout)
        dialog_layout.addWidget(self.button_box)
        self.setLayout(dialog_layout)
    
    def get_values(self):
        return self.start.value(), self.end.value(), self.number.value()
    
class MediaSweepDialog(QDialog):
    def __init__(self, title: str):
        super().__init__()
        self.setWindowTitle(title)

        # Media
        self.media = QLineEdit()
        validator = QRegularExpressionValidator(QRegularExpression(r"^\d*$"))
        self.media.setValidator(validator)

        layout = QFormLayout()
        layout.addRow("Media", self.media)


        self.button_box = QDialogButtonBox( QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        dialog_layout = QVBoxLayout()
        dialog_layout.addLayout(layout)
        dialog_layout.addWidget(self.button_box)
        self.setLayout(dialog_layout)
    
    def get_values(self):
        return [int(char) for char in self.media.text()]

class LaserWindow(QDockWidget):
    centerChanged = Signal(float)
    bandwidthChanged = Signal(float)
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setWindowTitle("Laser Parameters")
        self.widget = QWidget(self)

        self.center = QDoubleSpinBox(singleStep=10, decimals=1, suffix=f" nm")
        self.center.valueChanged.connect(self.centerChanged)
        self.bandwidth = QDoubleSpinBox(minimum=10, singleStep=10, decimals=1, suffix=f" nm")
        self.bandwidth.valueChanged.connect(self.bandwidthChanged)

        self.center.valueChanged.connect(self.update_wavelen)
        self.bandwidth.valueChanged.connect(self.update_bandwidth)

        layout = QFormLayout()
        layout.addRow("Center", self.center)
        layout.addRow("Bandwidth", self.bandwidth)

        self.widget.setLayout(layout)
        self.setWidget(self.widget)
    
    def update_bandwidth(self, bandwidth):
        self.center.setMinimum(390 + bandwidth/2)
        self.center.setMaximum(850 - bandwidth/2)

    def update_wavelen(self, wavelen):
        self.bandwidth.setMaximum(min((wavelen-390)*2, (850-wavelen)*2, 100))
    
    def set_values(self, wavelen, bandwidth):
        self.update_wavelen(wavelen)
        self.update_bandwidth(bandwidth)
        self.center.setValue(wavelen)
        self.bandwidth.setValue(bandwidth)

    
    # def get_values(self):
    #     return self.center.value(), self.bandwidth.value()

