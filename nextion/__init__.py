from .client import EventType, Nextion
from .exceptions import CommandFailed, CommandTimeout, ConnectionFailed

__version__ = "2.0.0"

__all__ = [
    "Nextion",
    "CommandFailed",
    "CommandTimeout",
    "ConnectionFailed",
    "EventType",
]
