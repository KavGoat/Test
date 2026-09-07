"""A PDF engine of MarkForge's own.

Reading, writing and annotating PDF files without going through anybody
else's library: the object model (:mod:`objects`), the syntax
(:mod:`lexer`), the stream filters (:mod:`filters`), the object store
(:mod:`storage`), the file reader (:mod:`reader`), the writer with its
incremental update (:mod:`writer`) and the annotation model
(:mod:`annotations`).

It is here because a markup editor's file *is* a PDF. Saving has to leave
the drawing that came in exactly as it was — byte for byte, so a signature
still verifies and nothing is re-encoded — while adding the markups on top
as real annotations. That is an incremental update, and it needs a reader
that can be trusted with whatever somebody's CAD package wrote.
"""
