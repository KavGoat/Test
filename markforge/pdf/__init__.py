"""MarkForge's PDF layer.

Two modules, and the split between them is the point.

:mod:`objects` is what a PDF is made of — a name, a reference, a stream —
as plain Python values. It is the vocabulary a markup's annotation is
described in, so the description is written once and does not belong to
whatever library happens to write it out.

:mod:`engine` is MuPDF. Opening files, measuring and drawing pages, reading
objects and line work, writing annotations, attachments, bookmarks and links,
and saving — full or as an incremental update that leaves every original byte
where it was. Nothing in here imports Qt: above this line a page is a
rectangle of points with markups on it, below it a page is objects and
streams, and the two do not need to know about each other.

MarkForge used to carry a PDF reader and writer of its own — a lexer, the
filters, a cross-reference reader that could fall back to scanning, an object
store. It was correct on the files it had been shown and it was never going to
be correct on the ones it had not: a drawing set is full of files written by
CAD packages that treat the specification as a suggestion, and every one of
them was a fix. MuPDF has had thirty years of those fixes. What is left here
is the part that is actually MarkForge's own — what a markup *is* in a PDF —
and that is worth owning.
"""
