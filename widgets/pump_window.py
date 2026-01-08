from PySide6.QtCore import Signal, QRegularExpression
from PySide6.QtWidgets import QFormLayout, QSpinBox, QDockWidget, QWidget, QPushButton, QCheckBox, QGroupBox, QVBoxLayout, QLineEdit, QComboBox, QButtonGroup, QHBoxLayout
from PySide6.QtGui import QRegularExpressionValidator

class PumpWindow(QDockWidget):
    start_dispense = Signal(int, int)
    start_pickup = Signal(int, int)
    start_clean = Signal(list)
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setWindowTitle("Pump")
        self._widget = QWidget(self)


        
        self.port = QComboBox()
        self.port.addItems(['1: Water', '2', '3', '4', '5', '6', '7', '8: Flowcell', '9', '10: Waste'])
        self.port.currentTextChanged.connect(self.update_controls)

        self.volume = QSpinBox(minimum=0, maximum=250, singleStep=10, suffix = 'uL')
        self.volume.setValue(100)


        self.pickup_button = QPushButton('Pickup')
        self.pickup_button.released.connect(self.pickup)
        
        self.dispense_button = QPushButton('Dispense')
        self.dispense_button.released.connect(self.dispense)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.pickup_button)
        button_layout.addWidget(self.dispense_button)
        


        self.clean_ports = QLineEdit()
        validator = QRegularExpressionValidator(QRegularExpression(r"^\d*$"))
        self.clean_ports.setValidator(validator)
        self.clean_button = QPushButton("Clean")
        self.clean_button.released.connect(self.clean)
        clean_layout = QVBoxLayout()
        clean_layout.addWidget(self.clean_ports)
        clean_layout.addWidget(self.clean_button)

        main_layout = QVBoxLayout()
        layout = QFormLayout()
        layout.addRow("Port", self.port)
        layout.addRow("Volume", self.volume)

        main_layout.addLayout(layout)
        main_layout.addLayout(button_layout)
        main_layout.addLayout(clean_layout)
        main_layout.addStretch(-1)

        self._widget.setLayout(main_layout)

        self.setWidget(self._widget)
    
    def update_controls(self, port):
        self.dispense_button.setEnabled(True)
        self.pickup_button.setEnabled(True)
        if 'Water' in port:
            self.dispense_button.setEnabled(False)
        
        if 'Waste' in port or 'Flowcell' in port:
            self.pickup_button.setEnabled(False)
    
    def dispense(self):
        self.start_dispense.emit(self.port.currentIndex() + 1, self.volume.value())
    
    def pickup(self):
        self.start_pickup.emit(self.port.currentIndex() + 1, self.volume.value())
    
    def clean(self):
        ports = set(int(i) for i in self.clean_ports.text())
        ports.discard(1)
        ports.discard(8)
        ports.discard(0)
        self.start_clean.emit(list(ports))