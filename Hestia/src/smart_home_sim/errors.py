"""Domain-specific errors with messages suitable for CLI users."""


class ScenarioError(ValueError):
    """Raised when a scenario is structurally valid but semantically inconsistent."""


class SimulationInvariantError(RuntimeError):
    """Raised when a runtime safety invariant is violated."""


class OutputValidationError(ValueError):
    """Raised when generated output violates its documented contract."""
