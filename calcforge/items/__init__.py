"""The markups that go on a page.

Importing this package registers every kind of markup, so
:func:`calcforge.items.base.build_item` can rebuild anything that has been
saved, copied or imported. Without that, whether a markup could be rebuilt
would depend on which modules happened to have been imported first — which is
the kind of bug that only shows up in the one place nobody looked.
"""
from . import base           # noqa: F401  the registry itself
from . import contents       # noqa: F401
from . import mathitem       # noqa: F401
from . import measure        # noqa: F401
from . import media          # noqa: F401
from . import plotitem       # noqa: F401
from . import shapes         # noqa: F401
from . import tableitem      # noqa: F401
from . import text           # noqa: F401

from .base import MarkupItem, Style, build_item   # noqa: F401
