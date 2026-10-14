"""Diagnostic script to find why the window doesn't appear."""
import sys
import traceback

print("Step 1: Testing basic PySide6...")
try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
    from PySide6.QtGui import QFont
    print("  OK: PySide6 imports work")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

print("Step 2: Creating QApplication...")
try:
    app = QApplication(sys.argv)
    print("  OK: QApplication created")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

print("Step 3: Testing basic window...")
try:
    w = QMainWindow()
    w.setWindowTitle("Test Window")
    w.resize(400, 300)
    label = QLabel("If you can see this, PySide6 works!", w)
    w.setCentralWidget(label)
    w.show()
    w.raise_()
    w.activateWindow()
    print(f"  Window visible: {w.isVisible()}")
    print(f"  Window size: {w.width()}x{w.height()}")
    print("  OK: Basic window shown")
    print()
    print(">>> A small test window should be visible now.")
    print(">>> If you can see it, close it and we'll test CalcForge next.")
    print(">>> If you can NOT see it, PySide6 itself is broken on your system.")
    print()
    app.exec()
    w = None
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
    sys.exit(1)

print()
print("Step 4: Testing CalcForge window...")
try:
    app2 = QApplication.instance() or QApplication(sys.argv)
    from calcforge.ui.mainwindow import MainWindow
    print("  Imports OK, creating MainWindow...")
    window = MainWindow()
    print(f"  MainWindow created: {window.width()}x{window.height()}")
    window.show()
    window.raise_()
    window.activateWindow()
    print(f"  Window visible: {window.isVisible()}")
    print()
    print(">>> CalcForge window should be visible now.")
    print(">>> Close it when done.")
    app2.exec()
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
