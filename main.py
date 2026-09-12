#!/usr/bin/env python3
"""Launch MarkForge."""
import sys

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    from markforge.app import main
    sys.exit(main())
