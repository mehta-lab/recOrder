import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout

from recOrder.plugin import tab_recon

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        recon_tab = tab_recon.Ui_Form()
        layout = QVBoxLayout()        
        self.setLayout(layout)
        layout.addWidget(recon_tab.recon_tab_widget)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())