class ArtifactError(RuntimeError):
    """Base error for artifact operations."""


class ArtifactValidationError(ArtifactError):
    """Artifact metadata or package contents are invalid."""


class ArtifactNotFoundError(ArtifactError):
    """Requested artifact does not exist."""


class ArtifactConflictError(ArtifactError):
    """An immutable artifact identity already exists with different content."""


class ArtifactIntegrityError(ArtifactError):
    """Artifact bytes do not match the recorded manifest."""
