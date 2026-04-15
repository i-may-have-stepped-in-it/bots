"""
Register slash commands for the bot.
"""

import discord
from discord import app_commands

def register_slash_commands(bot: discord.AutoShardedClient):
    """Register all slash commands to the bot's CommandTree."""
    
    @bot.tree.command(name="status", description="Check the system status of the bot and its AI backends.")
    async def status_slash(interaction: discord.Interaction):
        from bot.commands.handlers import handle_status_command
        # Defer response since health checks might take a few seconds
        await interaction.response.defer()
        
        # Create a mock message to satisfy the legacy handler signature
        class MockMessage:
            def __init__(self, interaction):
                self.channel = interaction.channel
                self.author = interaction.user
            
            async def send(self, **kwargs):
                await interaction.followup.send(**kwargs)
                
        mock_msg = MockMessage(interaction)
        await handle_status_command(mock_msg, bot.config, bot=bot)

    @bot.tree.command(name="draw", description="Generate an image using the current Stable Diffusion model.")
    @app_commands.describe(prompt="What do you want to see?")
    async def draw_slash(interaction: discord.Interaction, prompt: str):
        from bot.commands.handlers import handle_draw_command
        # Create a mock message for the queue system
        class MockMessage:
            def __init__(self, interaction, content):
                self.channel = interaction.channel
                self.author = interaction.user
                self.content = content
                self.id = interaction.id
                
            async def send(self, content):
                return await interaction.followup.send(content, wait=True)

        await interaction.response.defer()
        mock_msg = MockMessage(interaction, f"!draw {prompt}")
        
        await handle_draw_command(
            message=mock_msg,
            config=bot.config,
            command=f"!draw {prompt}",
            command_lower=f"!draw {prompt}".lower()
        )
