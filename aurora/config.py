from abc import ABC
from dataclasses import asdict, dataclass, field, fields, make_dataclass
from typing import Any, Optional
from urllib.parse import ParseResult, urljoin, urlparse


@dataclass
class AbstractDataclass(ABC):
    def __new__(cls, *args, **kwargs):
        if cls == AbstractDataclass or cls.__bases__[0] == AbstractDataclass:
            raise TypeError("AbstractDataclass cannot be instantiated directly.")
        return super().__new__(cls)


@dataclass
class BaseConfig(AbstractDataclass):
    """Base configuration class for Aurora."""

    def to_dict(self) -> dict[str, Any]:
        """Convert the configuration to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseConfig":
        """Create a BaseConfig instance from a dictionary."""
        return cls(**data)


@dataclass
class GlobalConfig(BaseConfig):
    """Global configuration for Aurora."""

    letta_base_url: str = "https://api.letta.ai"
    """Base URL for the Letta API."""
    agent_id: Optional[str] = None
    """Agent ID to use for all guilds and channels by default. Can be overridden per guild."""
    respond_to_dms: bool = True
    """Whether Aurora should respond to direct messages."""
    respond_to_bots: bool = False
    """Whether Aurora should respond to messages from other bots."""
    surface_errors: bool = False
    """Whether to surface errors in the chat. Set to True to show errors in the chat,
    or False to just log them instead."""

    def __post_init__(self):
        """Post-initialization to validate the Letta base URL."""
        # Parse the URL to ensure it is valid
        parsed_url: ParseResult = urlparse(self.letta_base_url, scheme="https")
        # Validate the base URL
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid Letta base URL provided.")
        # Ensure the URL ends with a trailing slash
        if not parsed_url.path.endswith("/"):
            parsed_url = parsed_url._replace(path=urljoin(parsed_url.path, "/"))
        self.letta_base_url = parsed_url.geturl()

    def to_dict(self) -> dict[str, Any]:
        """Convert the configuration to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GlobalConfig":
        """Create a GlobalConfig instance from a dictionary."""
        return cls(**data)


@dataclass
class GuildConfig(BaseConfig):
    """Guild-specific configuration for Aurora."""

    enabled: bool = False
    """Whether Aurora is enabled in this guild."""
    channels: list[int] = field(default_factory=list)
    """List of channel IDs where Aurora is enabled."""
    agent_id: Optional[str] = None
    """The ID of the Letta agent to use in this guild."""
    respond_to_generic: bool = False
    """Whether to respond to generic messages."""
    respond_to_mentions: bool = True
    """Whether to respond to mentions."""
    respond_to_replies: bool = True
    """Whether to respond to replies."""
    enable_timer: bool = True
    """Whether to enable the timer feature (will randomly trigger an agent input/event)."""
    min_timer_interval_minutes: int = 5
    """Minimum interval in minutes between autonomous messages."""
    max_timer_interval_minutes: int = 15
    """Maximum interval in minutes between autonomous messages."""
    firing_probability: float = 0.1
    """Probability of the timer firing when enabled."""


# Create a dynamic dataclass for ChannelConfig that inherits from GuildConfig to allow channel-specific overrides
channel_config_fields = [
    (f.name, f.type, f)
    for f in fields(GuildConfig)
    if f.name not in ["agent_id", "channels"]
]
ChannelConfig = make_dataclass(
    "ChannelConfig",
    channel_config_fields,
    bases=(BaseConfig,),
)
