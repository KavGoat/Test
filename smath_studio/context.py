"""Evaluation context -- symbol table, scope management, worksheet evaluation."""

from __future__ import annotations

from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .expression import ASTNode

from .units import UnitRegistry, get_default_registry
from .constants import ConstantsRegistry, get_default_constants


class EvalContext:
    """Evaluation context holding variables, functions, and evaluation state."""

    def __init__(
        self,
        unit_registry: Optional[UnitRegistry] = None,
        constants: Optional[ConstantsRegistry] = None,
        precision: int = 4,
    ):
        self._variables: dict[str, Any] = {}
        self._functions: dict[str, tuple[list[str], "ASTNode"]] = {}
        # key is (name, arity) -> (param_names, body_expression)

        self._unit_registry = unit_registry
        self._constants = constants
        self._precision = precision

        # Load constants as variables
        if constants is not None:
            for name, qty in constants.all_constants().items():
                self._variables[name] = qty

    @property
    def precision(self) -> int:
        return self._precision

    def get_unit_registry(self) -> Optional[UnitRegistry]:
        return self._unit_registry

    def get_variable(self, name: str) -> Any:
        """Look up a variable by name. Returns None if not found."""
        val = self._variables.get(name)
        if val is not None:
            return val
        # Check constants
        if self._constants is not None:
            cval = self._constants.get(name)
            if cval is not None:
                return cval
        return None

    def set_variable(self, name: str, value: Any):
        """Set a variable."""
        self._variables[name] = value

    def get_function(self, name: str, arity: int) -> Optional[Callable]:
        """Look up a user-defined function. Returns a callable or None."""
        # Try exact arity match first
        key = (name, arity)
        entry = self._functions.get(key)
        if entry is None:
            # Try any arity
            for (fn, ar), v in self._functions.items():
                if fn == name:
                    entry = v
                    break

        if entry is None:
            return None

        param_names, body_expr = entry

        def _call(args: list["ASTNode"], ctx: "EvalContext") -> Any:
            # Create a new scope with parameters bound
            old_values = {}
            for i, pname in enumerate(param_names):
                old_values[pname] = ctx.get_variable(pname)
                if i < len(args):
                    ctx.set_variable(pname, args[i].evaluate(ctx))

            try:
                result = body_expr.evaluate(ctx)
            finally:
                # Restore old scope
                for pname, old_val in old_values.items():
                    if old_val is None:
                        self._variables.pop(pname, None)
                    else:
                        ctx.set_variable(pname, old_val)

            return result

        return _call

    def define_function(self, name: str, param_names: list[str], body: "ASTNode"):
        """Define a user function."""
        key = (name, len(param_names))
        self._functions[key] = (param_names, body)

    def all_variables(self) -> dict[str, Any]:
        return dict(self._variables)


def create_default_context() -> EvalContext:
    """Create an evaluation context with default units and constants loaded."""
    try:
        registry = get_default_registry()
    except Exception:
        registry = UnitRegistry()

    try:
        constants = get_default_constants(registry)
    except Exception:
        constants = ConstantsRegistry()

    ctx = EvalContext(
        unit_registry=registry,
        constants=constants,
    )

    # Add some mathematical constants
    import math
    ctx.set_variable("pi", math.pi)
    ctx.set_variable("π", math.pi)
    ctx.set_variable("e_const", math.e)

    return ctx
