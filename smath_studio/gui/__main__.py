"""Launch the SMath Studio GUI application.

Usage:
    python -m smath_studio.gui [file.sm]
"""

import sys

from .app import SMathApp


def main():
    file_path = None
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    app = SMathApp(file_path=file_path)
    app.run()


if __name__ == "__main__":
    main()
