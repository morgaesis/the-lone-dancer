# pylint: disable=missing-function-docstring
# pylint: disable=missing-module-docstring

from unittest import mock
import warnings
import asyncio
import unittest
import bot  # pylint: disable=import-error


class MockVoiceClient:
    """The mock version of a Discord VoiceClient"""

    def __init__(self):
        self.after_callback = None
        self.current_audio_source = None
        self.guild = mock.AsyncMock()

    def is_playing(self):
        return self.current_audio_source is not None

    def play(self, audio_source, after=None):
        # Play should not be called something was already playing.
        assert not self.current_audio_source
        self.current_audio_source = audio_source
        self.after_callback = after

    def stop(self):
        self.current_audio_source = None
        if self.after_callback is not None:
            self.after_callback(None)
        self.after_callback = None

    def finish_audio_source(self, exception=None):
        """Call this to signal that the audio source has finished"""
        if self.after_callback is not None:
            self.after_callback(exception)
        self.current_audio_source = None


def create_mock_voice_channel():
    voice_client = MockVoiceClient()
    voice_channel = mock.Mock()
    voice_channel.connect = mock.AsyncMock(return_value=voice_client)

    return voice_channel


def create_mock_voice_state(channel=None):
    voice_state = mock.Mock()
    voice_state.channel = channel
    return voice_state


def create_mock_author(name="default_author", voice_state=None):
    author = mock.Mock()
    author.author_str = name

    def author_eq(self, other_author):
        return self.author_str == other_author.author_str

    author.__eq__ = author_eq

    def author_repr(self):
        return self.author_str

    author.__repr__ = author_repr

    author.voice = voice_state

    return author


def create_mock_message(
    contents="",
    author=create_mock_author(name="default_user"),
):
    message = mock.Mock()
    message.content = contents
    message.author = author
    message.channel.send = mock.AsyncMock()
    message.add_reaction = mock.AsyncMock()
    message.edit = mock.AsyncMock()

    return message


def async_assert_no_warnings_wrapper(func):
    """
    Add this wrapper to tests to make sure that warnings are also cought as errors
    """

    def inner(self):
        with warnings.catch_warnings(record=True) as cought_warnings:
            self.dispatcher_.loop.run_until_complete(func(self))

            if len(cought_warnings) != 0:
                MusicBotTest.total_warnings += cought_warnings
                raise Warning

    return inner


def create_mock_track(name="Mock Track", artists="Mock Artist"):
    if isinstance(artists, list):
        artists = [{"name": artist} for artist in artists]
    else:
        artists = [{"name": artists}]

    return {
        "name": name,
        "duration_ms": 1000,
        "artists": artists,
    }


def create_mock_spotify(_self):
    spotify = mock.Mock()
    spotify.album = mock.Mock(return_value={"tracks": {"items": [create_mock_track()]}})
    spotify.playlist = mock.Mock(
        return_value={
            "tracks": {
                "items": [
                    {"track": create_mock_track("track1")},
                    {"track": create_mock_track("track2")},
                    {"track": create_mock_track("track3")},
                ]
            }
        }
    )
    spotify.track = mock.Mock(return_value=create_mock_track())
    return spotify


def mock_pytube_playlist(_self, _url):
    return [
        "https://www.youtube.com/watch?v=xxxxxxxxxx1",
        "https://www.youtube.com/watch?v=xxxxxxxxxx2",
        "https://www.youtube.com/watch?v=xxxxxxxxxx3",
    ]


class MusicBotTest(unittest.IsolatedAsyncioTestCase):
    """MusicBot test suite"""

    async def asyncSetUp(self):
        # pylint: disable=attribute-defined-outside-init

        self.dispatcher_ = mock.Mock()
        self.dispatcher_.user = create_mock_author(name="test_bot")
        self.dispatcher_.loop = asyncio.get_running_loop()

        self.guild_ = mock.Mock()

        bot.MusicBot.get_spotify_client = create_mock_spotify
        bot.MusicBot.pytube_playlist = mock_pytube_playlist

        self.music_bot_ = bot.MusicBot(
            self.guild_, self.dispatcher_.loop, self.dispatcher_.user
        )
        self.music_bot_.pafy_search = mock.Mock()
        self.music_bot_.youtube_search = mock.MagicMock()
        self.mock_audio_source_ = mock.Mock()
        self.music_bot_.create_audio_source = mock.Mock(
            return_value=self.mock_audio_source_
        )

    @classmethod
    def setUpClass(cls):
        cls.total_warnings = []

    @classmethod
    def tearDownClass(cls):
        if len(cls.total_warnings) == 0:
            return

        warnings_report = "\n\n======== WARNINGS ========="
        for warning in cls.total_warnings:
            warnings_report += "\n\n" + str(warning.message)
        warnings_report += "\n\n==========================="

        print(warnings_report)

    @async_assert_no_warnings_wrapper
    async def test_ignores_own_message(self):
        message = create_mock_message(
            contents="-Some bot message", author=self.dispatcher_.user
        )

        await self.music_bot_.handle_message(message)

        # Bot didn't respond with anything.
        message.channel.send.assert_not_awaited()

    @async_assert_no_warnings_wrapper
    async def test_ignores_message_without_command_prefix(self):
        ignore_message = create_mock_message(contents="Some non-command message")

        await self.music_bot_.handle_message(ignore_message)

        # Bot didn't respond with anything.
        ignore_message.channel.send.assert_not_awaited()

    @async_assert_no_warnings_wrapper
    async def test_hello_command_sends_message(self):
        hello_message = create_mock_message(contents="-hello")

        await self.music_bot_.handle_message(hello_message)

        hello_message.channel.send.assert_awaited_with(":wave: Hello! default_user")

    @async_assert_no_warnings_wrapper
    async def test_play_fails_when_user_not_in_voice_channel(self):
        play_message = create_mock_message(
            contents="-play song", author=create_mock_author()
        )

        await self.music_bot_.handle_message(play_message)

        play_message.channel.send.assert_awaited_with(
            ":studio_microphone: default_author, please join a voice channel to start "
            "the :robot:"
        )

    @async_assert_no_warnings_wrapper
    async def test_play_connects_deafaned(self):
        play_message = create_mock_message(
            contents="-play song",
            author=create_mock_author(
                voice_state=create_mock_voice_state(channel=create_mock_voice_channel())
            ),
        )

        mock_media = mock.Mock()
        mock_media.title.__repr__ = lambda self: "song"

        self.music_bot_.pafy_search = mock.Mock(return_value=mock_media)

        await self.music_bot_.handle_message(play_message)

        self.music_bot_.voice_client.guild.change_voice_state.assert_awaited_with(
            channel=play_message.author.voice.channel, self_deaf=True
        )

        self.assertEqual(
            self.music_bot_.voice_client.current_audio_source, self.mock_audio_source_
        )
        self.assertEqual(
            self.music_bot_.voice_client.after_callback, self.music_bot_.after_callback
        )

        play_message.channel.send.assert_called_once_with(
            ":notes: Now Playing :notes:\n```\nsong\n```"
        )

    @async_assert_no_warnings_wrapper
    async def test_second_play_command_queues_media(self):
        author = create_mock_author(
            voice_state=create_mock_voice_state(channel=create_mock_voice_channel())
        )
        play_message1 = create_mock_message(contents="-play song1", author=author)
        play_message2 = create_mock_message(contents="-play song2", author=author)

        mock_media = mock.Mock()
        self.music_bot_.pafy_search = mock.Mock(return_value=mock_media)
        mock_media.title.__repr__ = lambda _: "song1"

        await self.music_bot_.handle_message(play_message1)

        play_message1.channel.send.assert_called_once_with(
            ":notes: Now Playing :notes:\n```\nsong1\n```"
        )

        mock_media.title.__repr__ = lambda _: "song2"
        await self.music_bot_.handle_message(play_message2)

        play_message2.channel.send.assert_awaited_with(
            ":clipboard: Added to Queue\n```\nsong2\n```"
        )

        self.music_bot_.voice_client.finish_audio_source()

        await asyncio.sleep(0.1)

        play_message2.channel.send.assert_called_with(
            ":notes: Now Playing :notes:\n```\nsong2\n```"
        )

    @async_assert_no_warnings_wrapper
    async def test_play_livestream_informs_user_unable_to_play(self):
        mock_author = create_mock_author(
            voice_state=create_mock_voice_state(channel=create_mock_voice_channel())
        )
        play_message = create_mock_message(
            contents="-play livestream", author=mock_author
        )
        mock_media = mock.Mock()
        mock_media.title.__repr__ = lambda self: "livestream"
        mock_media.duration = "00:00:00"
        self.music_bot_.pafy_search = mock.Mock(return_value=mock_media)

        await self.music_bot_.handle_message(play_message)

        await asyncio.sleep(0.1)

        play_message.channel.send.assert_awaited_with(
            "Sorry, I can't play livestreams :sob:"
        )
        self.music_bot_.voice_client.finish_audio_source()

    async def test_playlist_youtube(self):
        url = "https://www.youtube.com/playlist?list=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        mock_author = create_mock_author(
            voice_state=create_mock_voice_state(channel=create_mock_voice_channel())
        )
        play_message = create_mock_message(contents=f"-play {url}", author=mock_author)
        mock_media = mock.Mock()
        mock_media.title = "playlist item"
        mock_media.duration = "00:01:00"
        self.music_bot_.pafy_search = mock.Mock(return_value=mock_media)

        await self.music_bot_.handle_message(play_message)

        await asyncio.sleep(0.1)

        assert len(self.music_bot_.media_deque) > 0
        play_message.channel.send.has_awaits(
            (
                "Fetching playlist... ",
                ":notes: Now Playing :notes:\n```\nplaylist item\n```",
            )
        )

    async def test_playlist_spotify(self):
        url = "https://open.spotify.com/playlist/xxxxxxxxxxxxxxxxxxxxxx"
        mock_author = create_mock_author(
            voice_state=create_mock_voice_state(channel=create_mock_voice_channel())
        )
        play_message = create_mock_message(contents=f"-play {url}", author=mock_author)
        mock_media = mock.Mock()
        mock_media.title = "playlist item"
        mock_media.duration = "00:01:00"
        self.music_bot_.pafy_search = mock.Mock(return_value=mock_media)

        await self.music_bot_.handle_message(play_message)

        await asyncio.sleep(0.1)

        assert len(self.music_bot_.media_deque) > 0
        play_message.channel.send.has_awaits(
            (
                "Fetching playlist... ",
                ":notes: Now Playing :notes:\n```\nplaylist item\n```",
            )
        )

    async def test_disconnect(self):
        old_timer = bot.MusicBot.ALONE_SLEEP_TIMER
        bot.MusicBot.ALONE_SLEEP_TIMER = 0.1

        voice_channel = create_mock_voice_channel()
        self.music_bot_.voice_connect(None, voice_channel)

        bot.MusicBot.ALONE_SLEEP_TIMER = old_timer


if __name__ == "__main__":
    unittest.main()
