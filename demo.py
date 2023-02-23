import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView


if __name__ == "__main__":
    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.load(QUrl("http://localhost:5173"))
    view.show()
    sys.exit(app.exec_())