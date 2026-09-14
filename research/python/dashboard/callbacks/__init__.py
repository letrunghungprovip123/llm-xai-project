"""Central callback registration."""
from .global_state import register_global_callbacks
from .effectiveness import register_effectiveness_callbacks
from .decision import register_decision_callbacks
from .mechanisms import register_mechanisms_callbacks
from .overview import register_overview_callbacks
from .robustness import register_robustness_callbacks
from .cases import register_case_callbacks
from .methods import register_methods_callbacks

def register_callbacks(app, release) -> None:
    register_global_callbacks(app, release)
    register_overview_callbacks(app)
    register_effectiveness_callbacks(app)
    register_decision_callbacks(app)
    register_mechanisms_callbacks(app)
    register_robustness_callbacks(app)
    register_case_callbacks(app)
    register_methods_callbacks(app)
