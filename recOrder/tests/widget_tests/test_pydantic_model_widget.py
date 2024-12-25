import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QStyle
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QByteArray

from recOrder.plugin import tab_recon

PLUGIN_NAME = "recOrder: Computational Toolkit for Label-Free Imaging"
PLUGIN_ICON = "🔬"

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        recon_tab = tab_recon.Ui_ReconTab_Form(stand_alone=True)
        layout = QVBoxLayout()        
        self.setLayout(layout)
        layout.addWidget(recon_tab.recon_tab_widget)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Other options: "Fusion", "Windows", "macOS", "WindowsVista"
    
    window = MainWindow()
    window.setWindowTitle(PLUGIN_ICON + " " + PLUGIN_NAME + " " + PLUGIN_ICON)

    pixmapi = getattr(QStyle.StandardPixmap, "SP_TitleBarMenuButton")
    icon = app.style().standardIcon(pixmapi)        
    window.setWindowIcon(icon)

    window.show()
    sys.exit(app.exec_())