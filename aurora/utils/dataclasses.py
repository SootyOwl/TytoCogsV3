from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from discord import Member, Message, User

if TYPE_CHECKING:
    from discord.abc import MessageableChannel


@dataclass
class MessageRecord:
    message_id: int
    author: str
    author_id: int
    content: str
    clean_content: str
    timestamp: str
    is_bot: bool
    has_attachments: bool
    has_embeds: bool

    @classmethod
    def from_message(cls, message: Message) -> "MessageRecord":
        return cls(
            message_id=message.id,
            author=message.author.display_name,
            author_id=message.author.id,
            content=message.content or "[No text content]",
            clean_content=message.clean_content or "[No text content]",
            timestamp=message.created_at.isoformat(),
            is_bot=message.author.bot,
            has_attachments=len(message.attachments) > 0,
            has_embeds=len(message.embeds) > 0,
        )

    def format(self) -> str:
        """Format message record into human-readable text."""
        # format timestamp
        try:
            dt = datetime.fromisoformat(self.timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, KeyError):
            time_str = self.timestamp

        indicators = []
        if self.has_attachments:
            indicators.append("[Has attachments]")
        if self.has_embeds:
            indicators.append("[Has embeds]")
        indicator_str = " ".join(indicators)

        line = (
            f"[{time_str}] {self.author} [ID: {self.author_id}]: {self.clean_content}"
        )
        if indicator_str:
            line += f" {indicator_str}"
        line += f" [MessageID: {self.message_id}]"
        return line

    def format_yaml(self) -> str:
        """Format message record into YAML-like text."""
        yaml_str = (
            f"- message_id: {self.message_id}\n"
            f"  author: {self.author}\n"
            f"  author_id: {self.author_id}\n"
            f"  content: |\n"
            f"    {self.clean_content.replace(chr(10), chr(10) + '    ')}\n"
            f"  timestamp: {self.timestamp}\n"
            f"  is_bot: {self.is_bot}\n"
            f"  has_attachments: {self.has_attachments}\n"
            f"  has_embeds: {self.has_embeds}\n"
        )
        return yaml_str


@dataclass
class ReplyChain:
    messages: list[MessageRecord] = field(default_factory=list)

    def insert(self, message: Message):
        # Insert at beginning for chronological order
        self.messages.insert(0, MessageRecord.from_message(message))

    def to_list(self) -> list[dict]:
        return [vars(msg) for msg in self.messages]

    def __len__(self) -> int:
        return len(self.messages)

    def __getitem__(self, index: int) -> MessageRecord:
        return self.messages[index]

    def format(self) -> str:
        """Format reply chain into human-readable text."""
        if not self.messages:
            return "No reply chain."

        lines = []
        for msg in self.messages:
            lines.append(msg.format())

        return "\n".join(lines)

    def format_yaml(self) -> str:
        """Format reply chain into YAML-like text."""
        if not self.messages:
            return "No reply chain."

        lines = []
        for msg in self.messages:
            lines.append(msg.format_yaml())

        return "\n".join(lines)


@dataclass
class AuthorMetadata:
    id: int
    username: str
    display_name: str
    global_name: str
    is_bot: bool
    roles: list[str] = field(default_factory=list)

    @classmethod
    def from_author(cls, author_data: User | Member) -> "AuthorMetadata":
        return cls(
            id=author_data.id,
            username=author_data.name,
            display_name=getattr(author_data, "display_name", author_data.name),
            global_name=getattr(author_data, "global_name", author_data.name),
            is_bot=author_data.bot,
            roles=[role.name for role in author_data.roles if role.name != "@everyone"]
            if isinstance(author_data, Member)
            else [],
        )

    def format(self) -> str:
        """Format author metadata into human-readable text."""
        return f"- From: {self.display_name}{' | ' + self.global_name if self.global_name != self.display_name else ''} (ID: {self.id})"


@dataclass
class ChannelMetadata:
    id: int
    name: str
    type: str

    @classmethod
    def from_channel(cls, channel_data) -> "ChannelMetadata":
        if TYPE_CHECKING:
            channel_data: MessageableChannel = channel_data  # type: ignore
        return cls(
            id=channel_data.id,
            name=getattr(channel_data, "name", "DM"),
            type=str(channel_data.type if hasattr(channel_data, "type") else "DM"),
        )

    def format(self) -> str:
        """Format channel metadata into human-readable text."""
        return f"- Channel: {self.name} (ID: {self.id}, Type: {self.type})"


@dataclass
class GuildMetadata:
    id: int
    name: str

    @classmethod
    def from_guild(cls, guild_data) -> "GuildMetadata":
        return cls(
            id=guild_data.id,
            name=guild_data.name,
        )

    def format(self) -> str:
        """Format guild metadata into human-readable text."""
        return f"- Server: {self.name} (ID: {self.id})"


@dataclass
class MessageMetadata:
    message_id: int
    timestamp: str
    author: AuthorMetadata
    channel: ChannelMetadata
    guild: GuildMetadata | None = None

    @classmethod
    def from_message(cls, message: Message) -> "MessageMetadata":
        guild_meta = GuildMetadata.from_guild(message.guild) if message.guild else None
        channel_meta = ChannelMetadata.from_channel(message.channel)
        author_meta = AuthorMetadata.from_author(message.author)

        return cls(
            message_id=message.id,
            timestamp=message.created_at.isoformat(),
            author=author_meta,
            channel=channel_meta,
            guild=guild_meta,
        )

    @classmethod
    def empty(cls) -> "MessageMetadata":
        return cls(
            message_id=0,
            timestamp="",
            author=AuthorMetadata(0, "", "", False, []),
            channel=ChannelMetadata(0, "", ""),
            guild=None,
        )

    def format(self) -> str:
        """Format metadata into human-readable text."""
        lines = []

        # Author information
        lines.append(self.author.format())
        # Guild and channel information
        if self.guild:
            lines.append(self.guild.format())
        lines.append(self.channel.format())
        # Timestamp
        try:
            dt = datetime.fromisoformat(self.timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            lines.append(f"- Time: {time_str}")
        except (ValueError, KeyError):
            lines.append(f"- Time: {self.timestamp}")
        # Message ID
        lines.append(f"- Message ID: {self.message_id}")
        return "\n".join(lines)
