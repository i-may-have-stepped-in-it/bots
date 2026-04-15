"""
Unit tests for bot/commands/handlers.py - Command handling logic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.commands.handlers import (
    active_users,
    extract_prefixed_command,
    handle_command,
    is_guild_admin_command,
    is_super_user_or_moderator,
)

# =============================================================================
# is_super_user_or_moderator Tests
# =============================================================================

class TestIsSuperUserOrModerator:
    """Tests for permission checking function."""

    def test_power_user_allowed(self, mock_discord_message, minimal_config_dict):
        """Test that power users are allowed."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.author.id = 987654321  # Power user from config

        assert is_super_user_or_moderator(mock_discord_message, config) is True

    def test_non_power_user_denied(self, mock_discord_message, minimal_config_dict):
        """Test that non-power users are denied."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.author.id = 999999999  # Not a power user
        mock_discord_message.author.guild_permissions = MagicMock()
        mock_discord_message.author.guild_permissions.administrator = False
        mock_discord_message.author.guild_permissions.manage_guild = False
        mock_discord_message.author.guild_permissions.manage_messages = False
        mock_discord_message.author.guild_permissions.moderate_members = False

        assert is_super_user_or_moderator(mock_discord_message, config) is False

    def test_admin_allowed(self, mock_discord_message, minimal_config_dict):
        """Test that Discord admins are allowed."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.author.id = 999999999  # Not a power user
        mock_discord_message.author.guild_permissions = MagicMock()
        mock_discord_message.author.guild_permissions.administrator = True

        assert is_super_user_or_moderator(mock_discord_message, config) is True

    def test_moderator_allowed(self, mock_discord_message, minimal_config_dict):
        """Test that Discord moderators are allowed."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.author.id = 999999999
        mock_discord_message.author.guild_permissions = MagicMock()
        mock_discord_message.author.guild_permissions.administrator = False
        mock_discord_message.author.guild_permissions.moderate_members = True

        assert is_super_user_or_moderator(mock_discord_message, config) is True


# =============================================================================
# is_guild_admin_command Tests
# =============================================================================

class TestIsGuildAdminCommand:
    """Tests for admin command detection."""

    def test_admin_commands(self):
        """Test that admin commands are detected."""
        assert is_guild_admin_command("!txt2vid test") is True
        assert is_guild_admin_command("!check models") is True
        assert is_guild_admin_command("!load model test") is True
        assert is_guild_admin_command("!change model test") is True
        assert is_guild_admin_command("!recreate agent") is True
        assert is_guild_admin_command("!teamviewer") is True

    def test_non_admin_commands(self):
        """Test that non-admin commands return False."""
        assert is_guild_admin_command("!draw test") is False
        assert is_guild_admin_command("!play url") is False
        assert is_guild_admin_command("!help") is False
        assert is_guild_admin_command("!status") is False

    def test_case_insensitive(self):
        """Test case-insensitive detection."""
        assert is_guild_admin_command("!TXT2VID test") is True
        assert is_guild_admin_command("!Check Models") is True
        assert is_guild_admin_command("!Load Model test") is True


# =============================================================================
# extract_prefixed_command Tests
# =============================================================================

class TestExtractPrefixedCommand:
    """Tests for command extraction."""

    def test_simple_exclamation_command(self):
        """Test simple !command extraction."""
        assert extract_prefixed_command("!draw a cat", "Jennifer", 123) == "!draw a cat"
        assert extract_prefixed_command("!help", "Jennifer", 123) == "!help"

    def test_mention_prefix(self):
        """Test @mention prefix extraction."""
        result = extract_prefixed_command("<@123> !draw a cat", "Jennifer", 123)
        assert result == "!draw a cat"

        result = extract_prefixed_command("<@!123> !help", "Jennifer", 123)
        assert result == "!help"

    def test_name_prefix(self):
        """Test bot name prefix extraction."""
        result = extract_prefixed_command("Jennifer !draw a cat", "Jennifer", 123)
        assert result == "!draw a cat"

        result = extract_prefixed_command("jennifer !help", "Jennifer", 123)
        assert result == "!help"

    def test_no_command(self):
        """Test non-command messages return None."""
        assert extract_prefixed_command("Hello Jennifer", "Jennifer", 123) is None
        assert extract_prefixed_command("How are you?", "Jennifer", 123) is None
        assert extract_prefixed_command("", "Jennifer", 123) is None

    def test_whitespace_handling(self):
        """Test whitespace is handled correctly."""
        result = extract_prefixed_command("  !draw a cat  ", "Jennifer", 123)
        assert result == "!draw a cat"

        result = extract_prefixed_command("Jennifer   !help", "Jennifer", 123)
        assert result == "!help"

    def test_name_with_punctuation(self):
        """Test bot name followed by punctuation."""
        result = extract_prefixed_command("Jennifer, !draw a cat", "Jennifer", 123)
        assert result == "!draw a cat"

        result = extract_prefixed_command("Jennifer! !help", "Jennifer", 123)
        assert result == "!help"

    def test_different_bot_id(self):
        """Test with different bot user ID."""
        result = extract_prefixed_command("<@999> !draw", "Jennifer", 123)
        assert result is None  # Different bot ID


# =============================================================================
# handle_command Tests
# =============================================================================

@pytest.mark.asyncio
class TestHandleCommand:
    """Tests for the main command handler."""

    async def test_help_command(self, mock_discord_message, minimal_config_dict):
        """Test !help command."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.content = "!help"

        with patch("bot.commands.handlers.handle_help_command") as mock_handler:
            mock_handler.return_value = AsyncMock()

            result = await handle_command(
                message=mock_discord_message,
                config=config,
                user_message_histories={},
                bot=MagicMock(),
                history_file_name="test.json",
            )

            assert result is True
            mock_handler.assert_called_once()

    async def test_status_command(self, mock_discord_message, minimal_config_dict):
        """Test !status command."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.content = "!status"

        with patch("bot.commands.handlers.handle_status_command") as mock_handler:
            mock_handler.return_value = AsyncMock()

            result = await handle_command(
                message=mock_discord_message,
                config=config,
                user_message_histories={},
                bot=MagicMock(),
                history_file_name="test.json",
            )

            assert result is True

    async def test_draw_command(self, mock_discord_message, minimal_config_dict):
        """Test !draw command."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.content = "!draw a cat"

        with patch("bot.commands.handlers.handle_draw_command") as mock_handler:
            mock_handler.return_value = AsyncMock()

            result = await handle_command(
                message=mock_discord_message,
                config=config,
                user_message_histories={},
                bot=MagicMock(),
                history_file_name="test.json",
            )

            assert result is True

    async def test_unknown_command(self, mock_discord_message, minimal_config_dict):
        """Test unknown command response."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.content = "!unknowncommand"

        result = await handle_command(
            message=mock_discord_message,
            config=config,
            user_message_histories={},
            bot=MagicMock(),
            history_file_name="test.json",
        )

        assert result is True
        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "Unknown command" in sent_message

    async def test_no_command_extracted(self, mock_discord_message, minimal_config_dict):
        """Test when no command is extracted."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.content = "Hello Jennifer"

        result = await handle_command(
            message=mock_discord_message,
            config=config,
            user_message_histories={},
            bot=MagicMock(),
            history_file_name="test.json",
        )

        assert result is False  # Not handled as command

    async def test_admin_command_denied_in_guild(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test admin command denied in guild without permissions."""
        from discord import ChannelType

        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.content = "!txt2vid test"
        mock_discord_message.channel.type = ChannelType.text
        mock_discord_message.author.id = 999999999  # Not power user
        mock_discord_message.author.guild_permissions = MagicMock()
        mock_discord_message.author.guild_permissions.administrator = False

        result = await handle_command(
            message=mock_discord_message,
            config=config,
            user_message_histories={},
            bot=MagicMock(),
            history_file_name="test.json",
        )

        assert result is True  # Handled (denied)
        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "admin-only" in sent_message

    async def test_admin_command_allowed_in_dm(
        self, mock_discord_dm, minimal_config_dict
    ):
        """Test admin command allowed in DM."""
        from discord import ChannelType

        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_dm.content = "!txt2vid test"
        mock_discord_dm.channel.type = ChannelType.private

        with patch("bot.commands.handlers.handle_txt2vid_command") as mock_handler:
            mock_handler.return_value = AsyncMock()

            result = await handle_command(
                message=mock_discord_dm,
                config=config,
                user_message_histories={},
                bot=MagicMock(),
                history_file_name="test.json",
            )

            # Should not be blocked - DM is allowed
            assert result is True

    async def test_active_user_tracking_updated(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test that active user tracking is updated."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        user_id = 987654321
        mock_discord_message.content = "!help"
        mock_discord_message.author.id = user_id

        # Pre-populate active_users
        active_users[user_id] = 0

        with patch("bot.commands.handlers.handle_help_command") as mock_handler:
            mock_handler.return_value = AsyncMock()

            await handle_command(
                message=mock_discord_message,
                config=config,
                user_message_histories={},
                bot=MagicMock(),
                history_file_name="test.json",
            )

            # Active user timestamp should be updated
            assert active_users[user_id] > 0

        # Cleanup
        if user_id in active_users:
            del active_users[user_id]

    async def test_handler_exception_caught(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test that handler exceptions are caught."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.content = "!draw test"

        with patch("bot.commands.handlers.handle_draw_command") as mock_handler:
            mock_handler.side_effect = Exception("Test error")

            # Should not raise, but send error message
            result = await handle_command(
                message=mock_discord_message,
                config=config,
                user_message_histories={},
                bot=MagicMock(),
                history_file_name="test.json",
            )

            assert result is True  # Still considered handled
            mock_discord_message.channel.send.assert_called_once()
            sent_message = mock_discord_message.channel.send.call_args[0][0]
            assert "Error" in sent_message


# =============================================================================
# Handler Function Tests
# =============================================================================

@pytest.mark.asyncio
class TestHandlerFunctions:
    """Tests for individual handler functions."""

    async def test_handle_draw_command(self, mock_discord_message, minimal_config_dict):
        """Test handle_draw_command."""
        from bot.commands.handlers import handle_draw_command
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        # Mock the global image_queue
        with patch("bot.commands.handlers.image_queue") as mock_queue:
            mock_queue.put = AsyncMock()

            await handle_draw_command(
                message=mock_discord_message,
                config=config,
                command="!draw a cat",
                command_lower="!draw a cat",
            )

            # Should send initial message
            mock_discord_message.channel.send.assert_called_once()

            # Should queue the task
            mock_queue.put.assert_called_once()
            task = mock_queue.put.call_args[0][0]
            assert task.type == "image"
            assert task.payload["message_content"] == "!draw a cat"

    async def test_handle_join_vc_no_voice(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test join_vc when user not in voice channel."""
        from bot.commands.handlers import handle_join_vc_command
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.author.voice = None

        # config must be passed as named param (bug fix: was a NameError inside lambda)
        await handle_join_vc_command(message=mock_discord_message, config=config)

        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "voice channel" in sent_message.lower()

    async def test_handle_leave_vc_not_in_vc(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test leave_vc when bot not in voice channel (guild context)."""
        from bot.commands.handlers import handle_leave_vc_command

        mock_discord_message.guild.voice_client = None

        await handle_leave_vc_command(message=mock_discord_message)

        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "not in a voice channel" in sent_message.lower()

    async def test_handle_leave_vc_dm_no_guild(self, mock_discord_dm):
        """Test leave_vc from a DM where guild is None — must not AttributeError."""
        from bot.commands.handlers import handle_leave_vc_command

        # DM fixture has guild=None — previously would crash with AttributeError
        assert mock_discord_dm.guild is None

        await handle_leave_vc_command(message=mock_discord_dm)

        mock_discord_dm.channel.send.assert_called_once()
        sent_message = mock_discord_dm.channel.send.call_args[0][0]
        assert "not in a voice channel" in sent_message.lower()

    async def test_handle_recreate_agent_clears_verified_cache(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test !recreate agent clears _verified_agents via dict.pop() not set.remove()."""
        from bot.commands.handlers import handle_recreate_agent_command
        from core.config import JenniferConfig
        from utils.openclaw import OpenClawClient
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        mock_discord_message.author.id = 987654321
        mock_discord_message.author.display_name = "TestUser"

        # Build a fake client with the agent pre-cached in the dict
        fake_client = OpenClawClient.__new__(OpenClawClient)
        fake_client.prefix = "jennifer"
        fake_client._verified_agents = {
            "jennifer-user-987654321": "localai/Qwen3-14B-Nexa-Uncensored"
        }
        fake_client.normalize_id = lambda uid: f"jennifer-user-{uid}"

        with patch("bot.commands.handlers.get_client", return_value=fake_client), \
             patch("bot.commands.handlers.delete_openclaw_agent", new=AsyncMock()), \
             patch("bot.commands.handlers.save_message_histories", new=AsyncMock()):

            await handle_recreate_agent_command(
                message=mock_discord_message,
                config=config,
                user_message_histories={},
                history_file_name="test.json",
                bot=MagicMock(),
            )

        # Cache entry must be removed (dict.pop — not set.remove which would AttributeError)
        assert "jennifer-user-987654321" not in fake_client._verified_agents

    async def test_handle_volume_invalid_value(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test volume command with invalid value."""
        from bot.commands.handlers import handle_volume_command
        from bot.commands.music import music_players

        # Setup mock player
        mock_player = MagicMock()
        music_players[mock_discord_message.guild.id] = mock_player

        await handle_volume_command(
            message=mock_discord_message,
            command="!volume abc",
        )

        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "number" in sent_message.lower()

        # Cleanup
        del music_players[mock_discord_message.guild.id]

    async def test_handle_volume_out_of_range(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test volume command with out of range value."""
        from bot.commands.handlers import handle_volume_command
        from bot.commands.music import music_players

        mock_player = MagicMock()
        music_players[mock_discord_message.guild.id] = mock_player

        await handle_volume_command(
            message=mock_discord_message,
            command="!volume 2.0",
        )

        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "between 0.0 and 1.0" in sent_message

        del music_players[mock_discord_message.guild.id]

    async def test_handle_play_no_guild(self, mock_discord_dm, minimal_config_dict):
        """Test play command without guild (DM)."""
        from bot.commands.handlers import handle_play_command

        mock_discord_dm.content = "!play url"
        mock_discord_dm.guild = None

        await handle_play_command(
            message=mock_discord_dm,
            bot=MagicMock(),
            command="!play url",
        )

        mock_discord_dm.channel.send.assert_called_once()
        sent_message = mock_discord_dm.channel.send.call_args[0][0]
        assert "only works in servers" in sent_message.lower()

    async def test_handle_play_no_voice(self, mock_discord_message, minimal_config_dict):
        """Test play command when user not in voice."""
        from bot.commands.handlers import handle_play_command

        mock_discord_message.content = "!play url"
        mock_discord_message.author.voice = None

        await handle_play_command(
            message=mock_discord_message,
            bot=MagicMock(),
            command="!play url",
        )

        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "voice channel" in sent_message.lower()


# =============================================================================
# Edge Cases
# =============================================================================

class TestHandlerEdgeCases:
    """Tests for edge cases in handlers."""

    def test_extract_command_empty_string(self):
        """Test extract with empty string."""
        assert extract_prefixed_command("", "Jennifer", 123) is None

    def test_extract_command_only_whitespace(self):
        """Test extract with only whitespace."""
        assert extract_prefixed_command("   ", "Jennifer", 123) is None

    def test_extract_command_special_characters(self):
        """Test extract with special characters in bot name."""
        result = extract_prefixed_command("!draw", "Bot[v2]", 123)
        assert result == "!draw"

    async def test_handle_command_with_parsed_command(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test handle_command with pre-parsed command."""
        from core.config import JenniferConfig
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        # Message doesn't have command, but we pass parsed_command
        mock_discord_message.content = "Hello"

        with patch("bot.commands.handlers.handle_help_command") as mock_handler:
            mock_handler.return_value = AsyncMock()

            result = await handle_command(
                message=mock_discord_message,
                config=config,
                user_message_histories={},
                bot=MagicMock(),
                history_file_name="test.json",
                parsed_command="!help",
            )

            assert result is True
            mock_handler.assert_called_once()


# =============================================================================
# Video Generation Tests
# =============================================================================

class TestVideoGenerationHandlers:
    """Tests for video generation command handlers."""

    async def test_handle_txt2vid_no_permission(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test txt2vid without power user permission."""
        from bot.commands.handlers import handle_txt2vid_command
        from core.config import JenniferConfig

        # Configure video backend
        minimal_config_dict["ZaiAPIKey"] = "test-key"
        # Use different user ID that's NOT in Power_Users
        mock_discord_message.author.id = 123456789
        config = JenniferConfig._migrate_legacy(minimal_config_dict)

        # Mock video_queue
        with patch("bot.commands.handlers.video_queue") as mock_queue:
            await handle_txt2vid_command(
                message=mock_discord_message,
                config=config,
                command="!txt2vid a cat",
            )

            # Should not queue anything for non-power users
            mock_queue.put.assert_not_called()

        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "admin-only" in sent_message.lower()

    async def test_handle_txt2vid_not_configured(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test txt2vid when video not configured."""
        from bot.commands.handlers import handle_txt2vid_command
        from core.config import JenniferConfig

        # Add user as power user but no API key
        minimal_config_dict["Power_Users"] = [mock_discord_message.author.id]
        config = JenniferConfig._migrate_legacy(minimal_config_dict)
        config.video.zai_api_key = ""  # No API key

        await handle_txt2vid_command(
            message=mock_discord_message,
            config=config,
            command="!txt2vid a cat",
        )

        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "not configured" in sent_message.lower()

    async def test_handle_txt2vid_no_prompt(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test txt2vid without prompt."""
        from bot.commands.handlers import handle_txt2vid_command
        from core.config import JenniferConfig

        # Add user as power user with API key
        minimal_config_dict["Power_Users"] = [mock_discord_message.author.id]
        config = JenniferConfig._migrate_legacy(minimal_config_dict)
        config.video.zai_api_key = "test-key"

        await handle_txt2vid_command(
            message=mock_discord_message,
            config=config,
            command="!txt2vid",  # No prompt
        )

        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][0]
        assert "provide a prompt" in sent_message.lower()

    async def test_handle_txt2vid_success(
        self, mock_discord_message, minimal_config_dict
    ):
        """Test txt2vid queues task successfully."""
        from bot.commands.handlers import handle_txt2vid_command
        from core.config import JenniferConfig

        # Add user as power user with API key
        minimal_config_dict["Power_Users"] = [mock_discord_message.author.id]
        config = JenniferConfig._migrate_legacy(minimal_config_dict)
        config.video.zai_api_key = "test-key"

        # Mock video queue
        with patch("bot.commands.handlers.video_queue") as mock_queue:
            mock_queue.put = AsyncMock()

            await handle_txt2vid_command(
                message=mock_discord_message,
                config=config,
                command="!txt2vid a cat playing piano",
            )

            # Should send initial message
            assert mock_discord_message.channel.send.called

            # Should queue the task
            mock_queue.put.assert_called_once()
            task = mock_queue.put.call_args[0][0]
            assert task.type == "video"
            assert task.payload["prompt"] == "a cat playing piano"

    async def test_parse_video_prompt_simple(self):
        """Test parsing simple video prompt."""
        from bot.commands.handlers import _parse_video_prompt

        prompt, image_path = await _parse_video_prompt("!txt2vid a cat dancing")
        assert prompt == "a cat dancing"
        assert image_path is None

    async def test_parse_video_prompt_with_image(self):
        """Test parsing video prompt with image."""
        from bot.commands.handlers import _parse_video_prompt

        prompt, image_path = await _parse_video_prompt(
            "!txt2vid a cat dancing --image /path/to/cat.jpg"
        )
        assert prompt == "a cat dancing"
        assert image_path == "/path/to/cat.jpg"

    async def test_parse_video_prompt_empty(self):
        """Test parsing empty video prompt."""
        from bot.commands.handlers import _parse_video_prompt

        prompt, image_path = await _parse_video_prompt("!txt2vid")
        assert prompt == ""
        assert image_path is None
