
import discord, asyncio, subprocess, os, json
from discord.ext import commands

class Server:
    def __init__(self, bot):
        self.bot = bot
        self.config = self.bot.config
        self.responses = self.config['responses']['server_stuff']

    def server_running(self):
        print('1')
        with open(os.devnull, 'wb') as hide_output:
            exit_code = subprocess.Popen(['service', 'minecraft-server', 'status'], stdout=hide_output, stderr=hide_output).wait()
            print('2')
            return exit_code == 0

    @commands.command()
    async def state(self, ctx):
        """I'll tell you if Server-chan is awake."""
        ctx.send('Test')
        if self.server_running():
            await ctx.send(self.responses['state_on'])
        else:
            await ctx.send(self.responses['state_off'])

    @commands.command()
    async def start(self, ctx):
        """I'll wake server-chan up if she's asleep"""
        if self.server_running():
            await ctx.send(self.responses['start_error_on'])
        else:
            await ctx.send(self.responses['start_begining'])
            p = subprocess.Popen(['service', 'minecraft-server', 'start'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            p.stdin.close()
            await ctx.send(self.responses['start_end'])

    @commands.command()
    async def stop(self, ctx):
        """I'll take Server-chan to bed if she's awake"""
        if self.server_running():
            await ctx.send(self.responses['stop_start'])
            p = subprocess.Popen(['service', 'minecraft-server', 'stop'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            p.stdin.close()
            await ctx.send(self.responses['stop_end'])

def setup(bot):
    bot.add_cog(Server(bot))
