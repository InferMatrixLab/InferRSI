"""Errors shared by knowledge readers and their optional dependencies."""


class MissingSkillsExtra(ValueError):
    """Reading a checkout skill requires the optional metadata parser.

    A ValueError subclass, so callers that already treat a bad skill as a
    ValueError keep working, but distinct so per-item handlers can let it
    through. A missing optional dependency is a property of the install, not
    of the item being read: folding it into a per-item omission reports
    "nothing found" where the truth is "install the skills extra".

    Kept in its own module so that raising or catching it never imports the
    skill catalog, and with it the parser this error is about.
    """
