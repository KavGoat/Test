import sys

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    from .app import main
    sys.exit(main())
