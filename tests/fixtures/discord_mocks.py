"""
Mock objects for Discord.py classes to use in testing.
"""

from unittest.mock import MagicMock, AsyncMock, PropertyMock
from typing import Optional, List, Any
import discord
from discord import ChannelType


class MockDiscordUser:
    """Mock Discord User object."""
    
    def __init__(
        self,
        user_id: int = 987654321,
        name: str = "testuser",
        display_name: str = "TestUser",
        bot: bool = False,
    ):
        self.id = user_id
        self.name = name
        self.display_name = display_name
        self.bot = bot
        
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<MockDiscordUser id={self.id} name={self.name}>"


class MockDiscordChannel:
    """Mock Discord Channel object."""
    
    def __init__(
        self,
        channel_id: int = 111111111,
        name: str = "general",
        channel_type: ChannelType = ChannelType.text,
        guild: Optional[Any] = None,
    ):
        self.id = channel_id
        self.name = name
        self.type = channel_type
        self.guild = guild
        self.send = AsyncMock()
        
    async def typing(self):
        """Mock typing context manager."""
        class TypingContext:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
        return TypingContext()
    
    async def fetch_message(self, message_id: int):
        """Mock fetch_message."""
        return MockDiscordMessage(message_id=message_id)


class MockDMChannel(MockDiscordChannel):
    """Mock DM Channel object."""
    
    def __init__(self, recipient: Optional[MockDiscordUser] = None):
        super().__init__(
            channel_id=recipient.id if recipient else 987654321,
            name="Direct Message",
            channel_type=ChannelType.private,
        )
        self.recipient = recipient or MockDiscordUser()


class MockDiscordGuild:
    """Mock Discord Guild object."""
    
    def __init__(
        self,
        guild_id: int = 555555555,
        name: str = "Test Server",
    ):
        self.id = guild_id
        self.name = name
        self.voice_client = None
        self.me = MockDiscordUser(user_id=111111111, name="Jennifer", bot=True)
        
    def get_member(self, user_id: int):
        """Mock get_member."""
        return MockDiscordUser(user_id=user_id)


class MockVoiceChannel:
    """Mock Voice Channel object."""
    
    def __init__(
        self,
        channel_id: int = 777777777,
        name: str = "General Voice",
        guild: Optional[MockDiscordGuild] = None,
    ):
        self.id = channel_id
        self.name = name
        self.guild = guild or MockDiscordGuild()
        self.connect = AsyncMock()
        self.disconnect = AsyncMock()


class MockVoiceState:
    """Mock Voice State object."""
    
    def __init__(
        self,
        channel: Optional[MockVoiceChannel] = None,
        self_mute: bool = False,
        self_deaf: bool = False,
    ):
        self.channel = channel
        self.self_mute = self_mute
        self.self_deaf = self_deaf


class MockMember(MockDiscordUser):
    """Mock Discord Member object."""
    
    def __init__(
        self,
        user_id: int = 987654321,
        name: str = "testuser",
        display_name: str = "TestUser",
        guild: Optional[MockDiscordGuild] = None,
        voice_channel: Optional[MockVoiceChannel] = None,
        administrator: bool = False,
        manage_guild: bool = False,
        manage_messages: bool = False,
        moderate_members: bool = False,
    ):
        super().__init__(user_id, name, display_name, bot=False)
        self.guild = guild or MockDiscordGuild()
        
        # Voice state
        self.voice = MockVoiceState(channel=voice_channel) if voice_channel else MockVoiceState()
        
        # Permissions
        self.guild_permissions = MagicMock()
        self.guild_permissions.administrator = administrator
        self.guild_permissions.manage_guild = manage_guild
        self.guild_permissions.manage_messages = manage_messages
        self.guild_permissions.moderate_members = moderate_members


class MockDiscordMessage:
    """Mock Discord Message object."""
    
    def __init__(
        self,
        message_id: int = 123456789,
        content: str = "Hello!",
        author: Optional[MockDiscordUser] = None,
        channel: Optional[MockDiscordChannel] = None,
        guild: Optional[MockDiscordGuild] = None,
        mentions: Optional[List[MockDiscordUser]] = None,
        reference: Optional[Any] = None,
    ):
        self.id = message_id
        self.content = content
        self.author = author or MockDiscordUser()
        self.channel = channel or MockDiscordChannel(guild=guild)
        self.guild = guild
        self.mentions = mentions or []
        self.reference = reference
        
        # Mock methods
        self.add_reaction = AsyncMock()
        self.reply = AsyncMock()
        self.edit = AsyncMock()
        self.delete = AsyncMock()
        
    @property
    def jump_url(self):
        """Mock jump_url property."""
        guild_id = self.guild.id if self.guild else "@me"
        return f"https://discord.com/channels/{guild_id}/{self.channel.id}/{self.id}"


def create_mock_message(
    content: str = "Hello!",
    user_id: int = 987654321,
    channel_id: int = 111111111,
    guild_id: int = 555555555,
    is_dm: bool = False,
    is_bot: bool = False,
) -> MockDiscordMessage:
    """
    Factory function to create a mock message with common configurations.
    
    Args:
        content: Message content
        user_id: Author's user ID
        channel_id: Channel ID
        guild_id: Guild ID
        is_dm: Whether this is a DM message
        is_bot: Whether the author is a bot
        
    Returns:
        Configured MockDiscordMessage
    """
    author = MockDiscordUser(
        user_id=user_id,
        name=f"user_{user_id}",
        display_name=f"User{user_id}",
        bot=is_bot,
    )
    
    if is_dm:
        channel = MockDMChannel(recipient=author)
        guild = None
    else:
        guild = MockDiscordGuild(guild_id=guild_id)
        channel = MockDiscordChannel(
            channel_id=channel_id,
            name="general",
            guild=guild,
        )
    
    return MockDiscordMessage(
        content=content,
        author=author,
        channel=channel,
        guild=guild,
    )


def create_mock_member(
    user_id: int = 987654321,
    in_voice: bool = False,
    admin: bool = False,
) -> MockMember:
    """
    Factory function to create a mock member.
    
    Args:
        user_id: User's ID
        in_voice: Whether the member is in a voice channel
        admin: Whether the member has admin permissions
        
    Returns:
        Configured MockMember
    """
    voice_channel = MockVoiceChannel() if in_voice else None
    
    return MockMember(
        user_id=user_id,
        voice_channel=voice_channel,
        administrator=admin,
    )


class MockBot:
    """Mock Discord Bot/Client object."""
    
    def __init__(self):
        self.user = MockDiscordUser(user_id=111111111, name="Jennifer", bot=True)
        self.guilds = [MockDiscordGuild()]
        self.latency = 0.050
        self.voice_clients = []
        
    def get_channel(self, channel_id: int):
        """Mock get_channel."""
        return MockDiscordChannel(channel_id=channel_id)
    
    def get_guild(self, guild_id: int):
        """Mock get_guild."""
        return MockDiscordGuild(guild_id=guild_id)
    
    async def fetch_user(self, user_id: int):
        """Mock fetch_user."""
        return MockDiscordUser(user_id=user_id)
    
    async def fetch_channel(self, channel_id: int):
        """Mock fetch_channel."""
        return MockDiscordChannel(channel_id=channel_id)
