from amfTools import AMF, Device
import amfTools
import logging
from PySide6.QtCore import QObject, Signal, QCoreApplication


def requires_open(method):
    def wrapper(self, *args, **kwargs):
        if self.open and self.amf is not None:
            if not self.amf.getHomeStatus():
                    self.amf.home(block=True)
            return method(self, *args, **kwargs)
        else:
            raise RuntimeError("Device is not open, cannot call this method.")
    return wrapper
            

class PumpController(QObject):
    changedState = Signal(bool)
    open = False
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.amf = None
        self.water = 1
        self.flowcell = 8
        self.waste = 10
        self.setup(warning=False)

    def setup(self, warning=True):
        logging.debug('Opening pump')
        device_list = amfTools.util.getProductList(connection_mode="USB/RS232")
        if len(device_list) > 0:
            amf = AMF(product=device_list[0])
            if not amf.getHomeStatus():
                amf.home(block=False)
            amf.setSyringeSize(250)

            self.amf = amf
            self.open = True
            logging.debug('Pump connected')
        else:
            if warning:
                logging.warning('No pump available')
            logging.debug('No pump available')
            return None

    def toggle(self):
        if self.amf is not None:
            #  Reconnect
            if not self.open:
                self.amf.connect()
                if not self.amf.getHomeStatus():
                    self.amf.home(block=False)
                self.open = True
                logging.debug('Pump connected')
            else:
                self.amf.disconnect()
                self.open = False
                logging.debug('Pump disconnected')
        else:
            self.setup()
            
        self.changedState.emit(self.open)
    
    def cleanup(self):
        if self.open and self.amf is not None:
            self.amf.disconnect()
            logging.debug('Pump disconnected')
    
    @requires_open
    def pickup(self, port, volume=200):
        logging.debug(f'Picking up {volume}uL from port {port}')
        if port != self.waste and port != self.flowcell:
            self.amf.valveMove(port)
            self.amf.setFlowRate(1500,2)
            self.amf.pumpPickupVolume(volume, block=False)
        else:
            raise RuntimeError('Cannot pickup waste or flowcell!')
    
    @requires_open
    def dispense(self, port, volume=200):
        logging.debug(f'Dispensing {volume}uL to port {port}')
        if port != self.water:
            self.amf.valveMove(port)
            if port == self.flowcell:
                self.amf.setFlowRate(100,2)
            else:
                self.amf.setFlowRate(1500,2)
            self.amf.pumpDispenseVolume(volume, block=False)
        else:
            raise RuntimeError('Cannot dispense in water!')
    
    def wait_till_ready(self):
        if self.open and self.amf is not None:
            self.amf.pullAndWait()
    
    @requires_open
    def clean_pump(self, ports, volume=200):
        print(ports)
        if self.waste not in ports and self.flowcell not in ports:
            self.amf.pullAndWait()
            self.amf.setFlowRate(1500,2)
            for i in range(3):
                for output in ports:
                    print(output)
                    self.amf.valveMove(self.water)
                    self.amf.pumpPickupVolume(volume)
                    self.amf.valveMove(output)
                    self.amf.pumpDispenseVolume(volume)
                    self.amf.pumpPickupVolume(volume)
                    self.amf.valveMove(self.waste)
                    self.amf.pumpDispenseVolume(volume)
        else:
            raise RuntimeError('Cannot pickup waste or flowcell!')