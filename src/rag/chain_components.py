class ChainComponent:
    """Base class for collaborators that operate on an ExecutiveAgentChain."""

    def __init__(self, chain) -> None:
        object.__setattr__(self, "_chain", chain)

    def __getattr__(self, name):
        return getattr(self._chain, name)

    def __setattr__(self, name, value) -> None:
        if name == "_chain":
            object.__setattr__(self, name, value)
            return
        setattr(self._chain, name, value)
