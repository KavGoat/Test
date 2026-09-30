#!/usr/bin/env python3
"""Launch CalcForge."""
import sys

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    from calcforge.app import main
    sys.exit(main())
