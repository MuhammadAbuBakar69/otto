"""`python -m otto ...` works without installing anything."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
