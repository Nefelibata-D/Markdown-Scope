class MDScopeError(Exception):
    """Base domain exception."""


class IndexNotFoundError(MDScopeError):
    """Raised when index file cannot be found."""


class InvalidRangeError(MDScopeError):
    """Raised when start/end lines are invalid."""


class SectionNotFoundError(MDScopeError):
    """Raised when section id does not exist."""


class ScopePathError(MDScopeError):
    """Raised when path is outside root scope."""


class SummaryProviderError(MDScopeError):
    """Raised when summary generation fails."""

