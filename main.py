#!/home/yui/.pyenv/versions/Bot-tan/bin python
import discord
from discord.ext import commands
import asyncio
import subprocess, os
import json
import logging
import traceback
import sys
from logging.handlers import RotatingFileHandler

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(filename='Bot-tan.log', encoding='utf-8', backupCount=1, maxBytes=1024 * 1024 * 50)
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)


def embed_split(text: str) -> [str]:
    """split text to fit embed"""
    while text:
        yield text[:1024]
        text = text[1024:]


class Bot_tan(commands.AutoShardedBot):
    def __init__(self, config):
        self.config = json.loads(open(config).read())
        self.config['run_dir'] = sys.argv[0][:-7]

        super().__init__(
                command_prefix='!~',
                description=self.config['description'],
                max_messages = 500
                )
        self.key = open(self.config['key']).read().strip()
        self.responses = self.config['responses']['main']

    async def log(self, *args, **kwargs):
        chn = self.get_channel(self.config['log_channel'])
        if chn is not None:
            await chn.send(*args, **kwargs)
        else:
            print(*args, **kwargs)

    async def on_command_error(self, ctx, error):
        if ctx.command is not None:
            prepared_help = f'{ctx.prefix}{ctx.command.signature}'

        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(self.responses['private_message_error'])
            return
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(f'Command is missing required argument: {error}\nUsage: {prepared_help}', delete_after=10)
            return
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"{error}\nUsage: `{prepared_help}`", delete_after=10)
            return
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(error, delete_after=5)
            return
        elif isinstance(error, commands.CommandNotFound):
            return

        embed = discord.Embed(title="EXCEPTION on_command_error", colour=0xf74242)

        for i in embed_split('\n'.join(traceback.format_exception(type(error), error, error.__traceback__))):
            embed.add_field(name=str(error) or "No Event", value=i)

        await self.log(embed=embed)
        await super().on_command_error(ctx, error)

    async def on_ready(self):
        for i in self.shards:
            await self.change_presence(game=discord.Game(name='Taking care of Server-chan'), shard_id = i)

        cogs_s, cogs_f = await self.load_cogs()

        embed = discord.Embed(title='Import modules', colour=0xc67647)

        for i in embed_split(', '.join(cogs_s)):
            embed.add_field(name="Successful", value=i)
        for i in embed_split(', '.join(f'{k}: {j}' for k, j in cogs_f)):
            embed.add_field(name="Failed", value=i)
        await self.log(embed=embed)

    async def load_cogs(self):
        for extension in self.extensions.copy():
            self.unload_extension(extension)

        imported_modules = []
        failed_modules = []

        for i in self.config['extensions']:
            try:
                self.load_extension(i)
            except ImportError:
                failed_modules.append([i, traceback.format_exc()])
            else:
                imported_modules.append(i)

        return imported_modules, failed_modules

    def run(self):
        super().run(self.key)

    async def close(self):
        await super().close()


if __name__ == '__main__':
    bot = Bot_tan('bot.json')
    bot.run()
