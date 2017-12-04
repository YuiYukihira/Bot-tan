import asyncio
import discord
import youtube_dl
import json

from os import listdir, path, makedirs

from discord.ext import commands

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
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), filename)


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
            fmt = '*{0.filename}* requested by {1.display_name}'
            return fmt.format(self.player, self.requester)


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

    async def audio_player_task(self):
        while True:
            print('next')
            self.play_next_song.clear()
            self.current = await self.songs.get()
            await self.current.channel.send('Now playing' + str(self.current))
            self.voice.play(self.current.player, after=self.toggle_next)
            await self.play_next_song.wait()


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
    async def play(self, ctx, song: str):
        """Plays a song.
        If there is a song currently in the queue, then it is
        queued until the next song is done playing.
        This command automatically searches as well from YouTube.
        The list of supported sites can be found here:
        https://rg3.github.io/youtube-dl/supportedsites.html
        """
        print('start')
        state = self.get_voice_state(ctx.guild)
        songs_to_add = []
        if song.find('playlist?list=') >= 0:
            ytdl_opts = {
                'flat-playlist': True,
                'dump-single-json': True,
                'skip-download': True
            }
            urls = {}

            with youtube_dl.YoutubeDL(ytdl_opts) as ydl:
                urls = ydl.extract_info(song)
            print(urls)
            for song in urls['entries']:
                try:
                    player = await YTDLSource.from_url('https://www.youtube.com/watch?v='+song['id'], loop=self.bot.loop)
                except Exception as e:
                    fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
                    await ctx.send(fmt.format(type(e).__name__, e))
                else:
                    player.volume = 0.6
                    entry = VoiceEntry(ctx.message, player)
                    await ctx.send('Enqueued ' + str(entry))
                    songs_to_add.append(entry)
        else:
            try:
                player = await YTDLSource.from_url(song, loop=self.bot.loop)
            except Exception as e:
                fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
                await ctx.send(fmt.format(type(e).__name__, e))
            else:
                player.volume = 0.6
                entry = VoiceEntry(ctx.message, player)
                await ctx.send('Enqueued ' + str(entry))
                songs_to_add.append(entry)

        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return
        for song in songs_to_add:
            await state.songs.put(song)
        print('stop')

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

    @music.command(no_pm=True)
    async def playing(self, ctx):
        """Shows info about the currently played song."""

        state = self.get_voice_state(ctx.guild)
        if state.current is None:
            await ctx.send('Not playing anything.')
        else:
            skip_count = len(state.skip_votes)
            await ctx.send('Now playing {} [skips: {}/3]'.format(state.current, skip_count))

    @music.group(no_pm=True)
    async def playlist(self, ctx):
        pass

    @playlist.command(no_pm=True)
    async def add(self, ctx, playlist, song):
        await ctx.send('adding songs to playlist')
        ytdl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': '{}/{}/{}/{}/%(title)s.%(ext)s'.format(self.config['run_dir'], self.config['music']['music_dir'], str(ctx.guild.id), playlist),
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            #'quiet': True,
            'no_warnings': True,
            #'default_search': 'auto'
        }
        with youtube_dl.YoutubeDL(ytdl_opts) as ydl:
            ydl.download([song])
        await ctx.send('songs added, you can play them now.')

    @playlist.command(no_pm=True)
    async def play(self, ctx, playlist):
        state = self.get_voice_state(ctx.guild)
        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return

        songs = listdir('{}/{}/{}/{}/'.format(self.config['run_dir'], self.config['music']['music_dir'], str(ctx.guild.id), playlist))
        for song in songs:
            print(song)
            player = discord.FFmpegPCMAudio('{}/{}/{}/{}/{}'.format(self.config['run_dir'], self.config['music']['music_dir'], str(ctx.guild.id), playlist, song), **ffmpeg_options)
            entry = VoiceEntry(ctx.message, player)
            await state.songs.put(entry)
        await ctx.send(f'Enqueued playlist: {playlist}')

    @playlist.command(no_pm=True)
    async def create(self, ctx, *, playlist):
        if not path.exists('{}/{}/{}/{}'.format(self.config['run_dir'], self.config['music']['music_dir'], str(ctx.guild.id), playlist)):
            makedirs('{}/{}/{}/{}'.format(self.config['run_dir'], self.config['music']['music_dir'], str(ctx.guild.id), playlist))


def setup(bot):
    bot.add_cog(Music(bot))
