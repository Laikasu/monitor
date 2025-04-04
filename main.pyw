from PySide6.QtWidgets import QApplication

import imagingcontrol4 as ic4

from main_window import MainWindow

def main():
    ic4.Library.init()
    app = QApplication()
    app.setApplicationName("monitor")
    app.setApplicationDisplayName("Monitor")
    app.setStyle("fusion")

    w = MainWindow()
    w.show()

    app.exec()
    del(w) # Ensures cleanup while ic4 is still active
    ic4.Library.exit()

if __name__ == "__main__":
    main()