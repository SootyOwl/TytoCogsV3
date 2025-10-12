"""Initialize the tools module."""

# Avoid importing submodules here to prevent circular imports when those
# submodules import register_tool from this package. Call load_tools()
# to import submodules lazily (for side-effects such as registering tools).

ALL_TOOLS = {}

__all__ = ["ALL_TOOLS", "register_tool", "load_tools"]

# function decorator to register a tool
def register_tool(func):
    """Decorator to register a tool by function name."""
    # don't include this decorator, just the inner function
    ALL_TOOLS[func.__name__] = func
    return func

def load_tools():
    """Lazily import submodules that register tools to avoid circular imports.

    Import this explicitly after importing the package, e.g.:
        import aurora.tools.tools as tools
        tools.load_tools()
    """
    # Import submodules for their side-effects (they should call @register_tool).
    # noqa comments silence unused-import warnings.
    from . import blocks  # noqa: F401
    from . import discord  # noqa: F401
