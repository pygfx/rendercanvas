"""
Qt app
------

An example demonstrating a qt app with a wgpu viz inside.
If needed, change the PySide6 import to e.g. PyQt6, PyQt5, or PySide2.

"""

# ruff: noqa: N802, E402

import time
import importlib


# For the sake of making this example Just Work, we try multiple QT libs
for lib in ("PySide6", "PyQt6", "PySide2", "PyQt5"):
    try:
        QtWidgets = importlib.import_module(".QtWidgets", lib)
        break
    except ModuleNotFoundError:
        pass

from rendercanvas.qt import QRenderWidget
from rendercanvas.utils.cube import setup_drawing_sync


class ExampleWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.resize(640, 480)
        self.setWindowTitle("Rendering to a canvas embedded in a qt app")

        splitter = QtWidgets.QSplitter()

        self.button = QtWidgets.QPushButton("Hello world", self)
        self.canvas = QRenderWidget(splitter, update_mode="continuous")
        self.output = QtWidgets.QTextEdit(splitter)

        self.button.clicked.connect(self.whenButtonClicked)

        splitter.addWidget(self.canvas)
        splitter.addWidget(self.output)
        splitter.setSizes([400, 300])

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.button, 0)
        layout.addWidget(splitter, 1)
        self.setLayout(layout)

        self.show()

    def addLine(self, line):
        t = self.output.toPlainText()
        t += "\n" + line
        self.output.setPlainText(t)

    def whenButtonClicked(self):
        self.addLine(f"Clicked at {time.time():0.1f}")


app = QtWidgets.QApplication([])
example = ExampleWidget()

draw_frame = setup_drawing_sync(example.canvas)
example.canvas.request_draw(draw_frame)

# Enter Qt event loop (compatible with qt5/qt6)
app.exec() if hasattr(app, "exec") else app.exec_()
