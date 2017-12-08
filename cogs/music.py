import asyncio
import uuid

import discord
import youtube_dl
from discord.ext import commands

from .utils.database_models import MPlaylistInfo, MGuild

youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0' # ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
        'before_options': '-nostdin',
        'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.uploader = data.get('uploader')

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, ytdl.extract_info, url)

        if 'entries' in data:
            data = data['entries'][0]

        filename = ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class NormalSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, filename, volume=0.5):
        super().__init__(source, volume)

        self.filename = filename

    @classmethod
    async def from_file(cls, filename):
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), filename=filename)


class VoiceEntry:
    def __init__(self, message, player):
        self.requester = message.author
        self.channel = message.channel
        self.player = player

    def __str__(self):
        if isinstance(self.player, YTDLSource):
            fmt = '*{0.title}* uploaded by {0.uploader} and requested by {1.display_name}'
            duration = self.player.duration
            if duration:
                fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
            return fmt.format(self.player, self.requester)
        else:
            # TODO: fix this.
            # fmt = '*{0.filename}* requested by {1.display_name}'
            # return fmt.format(self.player, self.requester)
            return 'WIP'


class VoiceState:
    def __init__(self, bot):
        self.current = None
        self.voice = None
        self.bot = bot
        self.play_next_song = asyncio.Event()
        self.songs = asyncio.Queue()
        self.skip_votes = set()
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    def is_playing(self):
        if self.voice is None or self.current is None:
            return False
        return self.voice.is_playing()

    @property
    def player(self):
        return self.current.player

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing():
            self.voice.stop()

    def toggle_next(self, e=None):
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)
        print(e)

    async def audio_player_task(self):
        while True:
            try:
                print('next')
                self.play_next_song.clear()
                self.current = await self.songs.get()
                await self.current.channel.send('Now playing' + str(self.current))
                print('1')
                self.voice.play(self.current.player, after=self.toggle_next)
                print('2')
                await self.play_next_song.wait()
            except Exception as e:
                print(e)


class Music:
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}
        self.config = self.bot.config

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state
        return state

    async def create_voice_client(self, channel: discord.VoiceChannel):
        voice = channel.connect()
        state = self.get_voice_state(channel.guild)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                state.audio_player.cancel()
                if state.voice:
                    self.bot.loop.create_task(state.voice.disconnect())
            except:
                pass

    def gen_id(self):
        return uuid.uuid4().int & (1 << 64) - 1

    @property
    def db(self):
        return self.bot.db

    @commands.group()
    async def music(self, ctx):
        pass

    @music.command(no_pm=True)
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Tells the bot to join a specific voice channel"""
        print('join')
        try:
            await self.create_voice_client(channel)
        except discord.ClientException:
            await ctx.send('Already in a voice channel...')
        else:
            await ctx.send('Ready to play audio in ' + channel.name)

    @music.command(no_pm=True)
    async def summon(self, ctx):
        """Makes the bot join your voice channel"""
        print('summon')
        summoned_channel = ctx.author.voice.channel
        if summoned_channel is None:
            await ctx.send('You are not in a voice channel.')
            return False
        state = self.get_voice_state(ctx.guild)
        if state.voice is None:
            state.voice = await summoned_channel.connect()
        else:
            await state.voice.move_to(summoned_channel)
        return True

    @music.command(no_pm=True)
    async def volume(self, ctx, value: int):
        """Sets the volume of the currently playing song."""

        state = self.get_voice_state(ctx.guild)
        if state.is_playing():
            player = state.voice
            player.volume = value / 100
            await ctx.send('Set the volume to {:.0%}'.format(player.volume))

    @music.command(no_pm=True)
    async def pause(self, ctx):
        print('pause')
        """Pauses the currently played song."""
        state = self.get_voice_state(ctx.guild)
        if state.is_playing():
            player = state.voice
            player.pause()

    @music.command(no_pm=True)
    async def resume(self, ctx):
        print('resume')
        """Resumes the currently played song."""
        state = self.get_voice_state(ctx.guild)
        if not state.is_playing():
            player = state.voice
            player.resume()

    @music.command(no_pm=True)
    async def stop(self, ctx):
        print('stop')
        """Stops playing audio and leaves the voice channel.
        This also clears the queue.
        """
        server = ctx.guild
        state = self.get_voice_state(server)

        if state.is_playing():
            player = state.voice
            player.stop()

        try:
            state.audio_player.cancel()
            del self.voice_states[server.id]
            await state.voice.disconnect()
        except:
            pass

    @music.command(no_pm=True)
    async def skip(self, ctx):
        print('skip')
        """Vote to skip a song. The song requester can automatically skip.
        2 skip votes are needed for the song to be skipped.
        """

        state = self.get_voice_state(ctx.guild)
        if not state.is_playing():
            await ctx.send('Not playing any music right now...')
            return

        voter = ctx.author
        if voter == state.current.requester:
            await ctx.send('Requester requested skipping song...')
            state.skip()
        elif voter.id not in state.skip_votes:
            state.skip_votes.add(voter.id)
            total_votes = len(state.skip_votes)
            if total_votes >= 2:
                await ctx.send('Skip vote passed, skipping song...')
                state.skip()
            else:
                await ctx.send('Skip vote added, currently at [{}/3]'.format(total_votes))
        else:
            await ctx.send('You have already voted to skip this song.')

    @music.group()
    async def playlist(self, ctx):
        pass

    @playlist.command(name='create', no_pm=True)
    async def playlist_create(self, ctx, name: str):
        async with self.db.get_session() as sess:
            pl_id = self.gen_id()
            query1 = await sess.insert.rows(MGuild(g_id=ctx.guild.id, p_id=pl_id))
            query1 = query1.on_conflict(MGuild.p_id).nothing()
            await query1.run()
            query2 = await sess.insert.rows(MPlaylistInfo(p_id=pl_id, p_name=name, p_creator=ctx.author.id))
            query2 = query2.on_conflict(MPlaylistInfo.p_id).nothing()
            await query2.run()
        await ctx.send('Playlist created!')


def setup(bot):
    bot.add_cog(Music(bot))
