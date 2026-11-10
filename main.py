import sys

from PySide6.QtWidgets import QApplication
from diskvision.ui import Window

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("DiskVision")
    app.setOrganizationName("DiskVision")
    window = Window()
    window.show()
    sys.exit(app.exec())
