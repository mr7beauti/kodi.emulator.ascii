# SPDX-License-Identifier: GPL-3.0

import io
import json
import os
import signal
import threading
import time
from collections import namedtuple

from sakee.colors import Colors
from sakee.stub import KodiStub
from xbmcgui import ListItem

DRIVE_NOT_READY = 1
ENGLISH_NAME = 2
ISO_639_1 = 0
ISO_639_2 = 1
LOGDEBUG = 0
LOGERROR = 4
LOGFATAL = 6
LOGINFO = 1
LOGNONE = 7
LOGNOTICE = 2
LOGSEVERE = 5
LOGWARNING = 3
PLAYLIST_MUSIC = 0
PLAYLIST_VIDEO = 1
SERVER_AIRPLAYSERVER = 2
SERVER_EVENTSERVER = 6
SERVER_JSONRPCSERVER = 3
SERVER_UPNPRENDERER = 4
SERVER_UPNPSERVER = 5
SERVER_WEBSERVER = 1
SERVER_ZEROCONF = 7
TRAY_CLOSED_MEDIA_PRESENT = 96
TRAY_CLOSED_NO_MEDIA = 64
TRAY_OPEN = 16

# Custom AddonData type
AddonData = namedtuple('AddonData', [
    'kodi_home_path',  # data path (either portable of user path)
    'add_on_id',  # the add-on id
    'add_on_path',  # the full path to the add-on
    'kodi_profile_path'  # the full path to the add-on profile folder
])


# noinspection PyPep8Naming
class Monitor(KodiStub):
    def __init__(self):
        """ Creates a Dummy Kodi Monitor class """

        super(Monitor, self).__init__()
        self.__abort = False

        # noinspection PyUnusedLocal
        def stop_requested(signum, frame):
            self.__abort = True

        # Requires PyCharm to set the option of "Emulate terminal in output window" to work
        signal.signal(signal.SIGINT, stop_requested)

    def abortRequested(self):  # NOSONAR
        """ Returns True if abort has been requested.

        :return: True if abort has been requested.
        :rtype: bool

        """

        return self.__abort

    def waitForAbort(self, seconds=0.0):  # NOSONAR
        """ Block until abort is requested, or until timeout occurs. If an abort requested
        have already been made, return immediately.

        :param float seconds:  timeout in seconds. Default: no timeout.

        :return: True when abort have been requested, False if a timeout is given and
        the operation times out.
        :rtype: bool

        """

        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.__abort:
                return True
            time.sleep(0.1)  # Sleep 100ms

        return False


# noinspection PyPep8Naming
class Keyboard(KodiStub):
    def __init__(self, line="", heading="", hidden=False):
        """

        :param str line:        The default line to show?
        :param str heading:     The heading of the dialog
        :param bool hidden:     Hidden input?

        """

        super(Keyboard, self).__init__()

        self.log_method("xbmc.Keyboard", "__init__", line, heading, hidden)
        self.__confirmed = False
        self.__line = line
        self.__heading = heading
        self.__hidden = hidden
        self.__input = ""

    # noinspection PyUnusedLocal
    def doModal(self, autoclose=0):  # NOSONAR
        """ Show keyboard and wait for user action.

        :param int autoclose: milliseconds to autoclose dialog. (default=do not autoclose)

        """

        if not self.is_interactive:
            self.__confirmed = True
            return "1234"

        KodiStub.print_heading(self.__heading)
        try:
            answer = self.read_input(
                "Please provide keyboard input [{}]?".format(self.__line), color=Colors.Yellow)
            if not answer:
                answer = self.__line
            self.__confirmed = True
        except EOFError:
            answer = ""
            self.__confirmed = False

        self.__input = answer

    def getText(self):  # NOSONAR
        """ Returns the user input as a string.

        :return: Returns the user input as a string.
        :rtype: str

        This will always return the text entry even if you cancel the keyboard. Use
        the isConfirmed() method to check if user cancelled the keyboard.

        """

        return self.__input

    def isConfirmed(self):  # NOSONAR
        """ Returns False if the user cancelled the input.

        :return: Returns False if the user cancelled the input.
        :rtype: bool

        """

        return self.__confirmed

    def setDefault(self, line):  # NOSONAR
        """ Set the default text entry.

        :param str line:   The default line to show?

        """

        self.__line = line

    def setHeading(self, heading):  # NOSONAR
        """ Set the keyboard heading.

        :param str heading: Keyboard heading

        """

        self.__heading = heading

    def setHiddenInput(self, hidden):  # NOSONAR
        """ Allows hidden text entry.

        :param bool hidden:     True for hidden text entry.

        """

        self.__hidden = hidden


# noinspection PyArgumentList,PyPep8Naming
class PlayList(KodiStub):
    def __init__(self, playList):  # NOSONAR
        """ Playlist object

        :param int playList:    The type of playlist

        PLAYLIST_MUSIC = 13
        PLAYLIST_VIDEO = 14

        """

        self.__play_list_type = playList
        self.__items = []

        super(PlayList, self).__init__()

    def getPlayListId(self):
        """ Returns the type of playlist

        :return: The type of playlist
        :rtype: int

        """
        return self.__play_list_type

    def clear(self):
        """ Clear all items in the playlist. """
        self.__items = []

    def getposition(self):
        """ Returns the position of the current song in this playlist.

        :return: Position of the current song
        :rtype: int
        """
        self.log_method("xbmc.PlayList", "getposition")
        return 0

    def add(self, url, listitem=None, index=None):
        """`Adds a new file to the playlist.
        
        :param str url:                 Filename or url to add.
        :param ListItem|None listitem:  Used with setInfo() to set different infolabels.
        :param int|None index:          Position to add playlist item. (default=end)
        """

        if index is not None:
            self.__items.insert(index, (url, listitem))
        else:
            self.__items.append((url, listitem))

    def __len__(self):
        return len(self.__items)

    def __getitem__(self, i):
        return self.__items[i]


class KodiInteralPlayer(object):  # NOSONAR
    STATUS_INIT = 'init'
    STATUS_STOPPED = 'stopped'
    STATUS_PLAYING = 'playing'
    STATUS_PAUSED = 'paused'

    def __init__(self):
        self.status = KodiInteralPlayer.STATUS_STOPPED
        self.file = None
        self.current_time = 0
        self.total_time = 0

        self._stop_event = threading.Event()

        # Keep track of players
        self.__players = []

    # noinspection PyPep8Naming,PyUnusedLocal
    def playResolvedItem(self, path, item):  # NOSONAR
        """ Sets the resolved item to play

        :param str path:
        :param ListItem item:

        """

        self.file = path
        self.play(path)

    def play(self, path):
        self.file = path
        self.status = KodiInteralPlayer.STATUS_INIT
        self.total_time = 5  # 5 seconds
        self._stop_event.clear()

        # Start the playback simulation thread
        background_thread = threading.Thread(target=self.__loop)
        background_thread.start()

    def register_player(self, player):
        """ Register a xbmc.Player instance

        :param Player player: The player to register

        """

        self.__players.append(player)

    def unregister_player(self, player):
        """ Unregister a xbmc.Player instance

        :param Player player: The player to unregister

        """

        self.__players.remove(player)

    def set_events(self):
        self._stop_event.set()

    def __loop(self):
        """ Background playback loop. """
        from datetime import timedelta

        for player in self.__players:
            player.onPlayBackStarted()

        while not self._stop_event.wait(1):
            Player.print_line(
                'Player: [{status}] {pos}/{total}'.format(
                    status=self.status,
                    pos=timedelta(seconds=self.current_time),
                    total=timedelta(seconds=self.total_time)
                ), verbose=True)

            if self.status == KodiInteralPlayer.STATUS_INIT:
                self.status = KodiInteralPlayer.STATUS_PLAYING
                self.current_time = 0
                for player in self.__players:
                    player.onAVStarted()
                    player.onAVChange()
                continue

            if self.status == KodiInteralPlayer.STATUS_PLAYING:
                self.current_time += 1
                if self.current_time > self.total_time:
                    for player in self.__players:
                        player.stop()

            if self.status == KodiInteralPlayer.STATUS_STOPPED:
                break

        for player in self.__players:
            player.onPlayBackStopped()


# noinspection PyPep8Naming,PyArgumentList
class Player(KodiStub):
    __kodi_player = None

    @staticmethod
    def kodi_player():
        """ The Kodi player instance

        :return: The stub for the internal Kodi player
        :rtype: KodiInteralPlayer

        """

        if Player.__kodi_player is None:
            Player.__kodi_player = KodiInteralPlayer()

        return Player.__kodi_player

    def __init__(self):
        super(Player, self).__init__()

        # register this player with the main Kodi player
        Player.kodi_player().register_player(self)

    def __del__(self):
        # unregister
        Player.kodi_player().unregister_player(self)

    def getAvailableAudioStreams(self):  # NOSONAR
        """ Returns the available audio stream names.

        :return: The available audio streams.
        :rtype: List[str]

        """

        return []  # Not implemented

    def getAvailableSubtitleStreams(self):  # NOSONAR
        """ Returns the available subtitle stream names.

        :return: The available subtitle streams.
        :rtype: List[str]

        """

        return []  # Not implemented

    def getAvailableVideoStreams(self):  # NOSONAR
        """ Returns the available video stream names.

        :return: The available video streams.
        :rtype: List[str]

        """

        return []  # Not implemented

    def getMusicInfoTag(self):
        """ Return the music info tag.

        :return: Returns the MusicInfoTag of the current playing 'Song'.
        :rtype: MusicInfoTag|None

        """

        if Player.kodi_player().status == KodiInteralPlayer.STATUS_STOPPED:
            raise Exception('Player is not playing a file.')

        return None  # Not implemented

    def getPlayingFile(self):  # NOSONAR
        """ Returns the current playing file as a string.

        :return: The filename of the playing item.
        :rtype: str

        """

        return Player.kodi_player().file

    def getRadioRDSInfoTag(self):
        """ Return the Radio RDS info tag.

        :return: Returns the RadioRDSInfoTag of the current playing 'Radio Song if. present'.
        :rtype: RadioRDSInfoTag|None
        """

        if Player.kodi_player().status == KodiInteralPlayer.STATUS_STOPPED:
            raise Exception('Player is not playing a file.')

        return None  # Not implemented

    def getSubtitles(self):
        """ Return the subtitle stream name.

        :return: Stream name
        :rtype: str

        """

        return ''  # Not implemented

    def getTime(self):
        """ Return the current playing time.

        :return: Returns the current time of the current playing media as fractional seconds.
        :rtype: int
        """

        return Player.kodi_player().current_time

    def getTotalTime(self):
        """ Return the total playing time.

        :return: Returns the total time of the current playing media in seconds. This is only accurate to the full second.
        :rtype: int

        """

        if Player.kodi_player().status == KodiInteralPlayer.STATUS_STOPPED:
            raise Exception('Player is not playing a file.')

        return Player.kodi_player().total_time

    def getVideoInfoTag(self):
        """ Return the video info tag.

        :return: The VideoInfoTag of the current playing Movie.
        :rtype: VideoInfoTag|None

        """

        if Player.kodi_player().status == KodiInteralPlayer.STATUS_STOPPED:
            raise Exception('Player is not playing a file.')

        return None  # Not implemented

    def isExternalPlayer(self):
        """ Check for external player.

        :return: True if kodi is playing using an external player.
        :rtype: bool

        """

        return False

    def isPlaying(self):  # NOSONAR
        """ Check Kodi is playing something.

        :return: True if Kodi is playing a file.
        :rtype: bool

        """

        return Player.kodi_player().status == KodiInteralPlayer.STATUS_PLAYING

    def isPlayingAudio(self):  # NOSONAR
        """ Check for playing audio.

        :return: True if Kodi is playing an audio file.
        :rtype: bool

        """

        return Player.kodi_player().status == KodiInteralPlayer.STATUS_PLAYING

    def isPlayingRDS(self):  # NOSONAR
        """ Check for playing radio data system (RDS).

        :return: True if kodi is playing a radio data system (RDS).
        :rtype: bool

        """

        return Player.kodi_player().status == KodiInteralPlayer.STATUS_PLAYING

    def isPlayingVideo(self):  # NOSONAR
        """ Check for playing video.

        :return: True if Kodi is playing a video.
        :rtype: bool

        """

        return Player.kodi_player().status == KodiInteralPlayer.STATUS_PLAYING

    def pause(self):  # NOSONAR
        """ Pause or resume playing if already paused. """

        if Player.kodi_player().status == KodiInteralPlayer.STATUS_STOPPED:
            return

        if Player.kodi_player().status == KodiInteralPlayer.STATUS_PLAYING:
            Player.kodi_player().status = KodiInteralPlayer.STATUS_PAUSED
            self.onPlayBackPaused()
            return

        if Player.kodi_player().status == KodiInteralPlayer.STATUS_PAUSED:
            Player.kodi_player().status = KodiInteralPlayer.STATUS_PLAYING
            self.onPlayBackResumed()
            return

    # noinspection PyUnusedLocal
    def play(self, item=None, listitem=None, windowed=False, startpos=-1):
        """ Play an item.

        :param str|None item:            Filename, url or playlist
        :param ListItem|None listitem:   Used with setInfo() to set different infolabels.
        :param bool windowed:            True=play video windowed, False=play users preference.(default)
        :param int startpos:             Starting position when playing a playlist. Default = -1

        If item is not given then the Player will try to play the current item in the current playlist.

        You can use the above as keywords for arguments and skip certain optional arguments.
        Once you use a keyword, all following arguments require the keyword.

        """
        # Stop playing the current file (if any)
        self.stop()
        Player.kodi_player().play(item)

    def playnext(self):  # NOSONAR
        """ Play next item in playlist."""

        pass  # Not implemented

    def playprevious(self):  # NOSONAR
        """ Play previous item in playlist."""

        pass  # Not implemented

    def playselected(self, selected):  # NOSONAR
        """ Set Audio Stream.

        :param int selected:            Item to select

        """

        pass  # Not implemented

    def seekTime(self, seekTime):  # NOSONAR
        """ Seek time.

        Seeks the specified amount of time as fractional seconds.
        The time specified is relative to the beginning of the currently. playing media file.

        :param int seekTime:            Time to seek as fractional seconds

        """

        if Player.kodi_player().status == KodiInteralPlayer.STATUS_STOPPED:
            raise Exception('Player is not playing a file.')

        Player.kodi_player().current_time = seekTime
        self.onPlayBackSeek(seekTime, 0)

    def setAudioStream(self, stream):  # NOSONAR
        """ Set Audio Stream.

        :param int stream:              Audio stream to select for play

        """

        pass  # Not implemented

    def setSubtitles(self, subtitleFile):  # NOSONAR
        """ Set subtitle file and enable subtitles.

        :param str subtitleFile:        File to use as source of subtitles

        """

        pass  # Not implemented

    def setSubtitleStream(self, stream):  # NOSONAR
        """ Set Subtitle Stream.

        :param int stream:              Subtitle stream to select for play

        """

        pass  # Not implemented

    def setVideoStream(self, stream):  # NOSONAR
        """ Set Video Stream.

        :param int stream:              Video stream to select for play

        """

        pass  # Not implemented

    def showSubtitles(self, visible):  # NOSONAR
        """ Enable / disable subtitles.

        :param bool visible:            True for visible subtitles.

        """

        pass  # Not implemented

    def stop(self):  # NOSONAR
        """ Stop playing."""

        Player.kodi_player().status = KodiInteralPlayer.STATUS_STOPPED
        Player.kodi_player().current_time = 0
        Player.kodi_player().total_time = 0
        Player.kodi_player().file = None
        Player.kodi_player().set_events()

    # noinspection PyUnusedLocal
    def updateInfoTag(self, item):  # NOSONAR
        """ Update info labels for currently playing item.

        :param ListItem item:           ListItem with new info

        """

        if Player.kodi_player().status == KodiInteralPlayer.STATUS_STOPPED:
            raise Exception('Player is not playing a file.')

        # Not implemented

    def onAVChange(self):  # NOSONAR
        """ onAVChange method.
        Will be called when Kodi has a video, audio or subtitle stream. Also happens when the stream changes.

        """

        self.print_line('Invoked onAVChange()', verbose=True)

    def onAVStarted(self):  # NOSONAR
        """ onAVStarted method.

        Will be called when Kodi has a video or audiostream.

        """

        self.print_line('Invoked onAVStarted()', verbose=True)

    def onPlaybackEnded(self):  # NOSONAR
        """ onPlaybackEnded method.

        Will be called when Kodi stops playing a file.

        """
        self.print_line('Invoked onPlaybackEnded()', verbose=True)

    def onPlayBackError(self):  # NOSONAR
        """ onPlayBackError method.

        Will be called when playback stops due to an error.

        """

        self.print_line('Invoked onPlayBackError()', verbose=True)

    def onPlayBackPaused(self):  # NOSONAR
        """ onPlayBackPaused method.

        Will be called when user pauses a playing file.

        """

        self.print_line('Invoked onPlayBackPaused()', verbose=True)

    def onPlayBackResumed(self):  # NOSONAR
        """ onPlayBackResumed method.

        Will be called when user resumes a paused file.

        """

        self.print_line('Invoked onPlayBackResumed()', verbose=True)

    def onPlayBackSeek(self, time, seekOffset):  # NOSONAR
        """ onPlayBackSeek method.
        Will be called when user seeks to a time.

        :param int time:            Time to seek to
        :param int seekOffset:      ?

        """
        self.print_line('Invoked onPlayBackSeek(%d, %d)' % (time, seekOffset), verbose=True)

    def onPlayBackSeekChapter(self, chapter):  # NOSONAR
        """ onPlayBackSeekChapter method.

        Will be called when user performs a chapter seek.

        :param int chapter:         Chapter to seek to

        """

        self.print_line('Invoked onPlayBackSeekChapter(%d)' % chapter, verbose=True)

    def onPlayBackSpeedChanged(self, speed):  # NOSONAR
        """ onPlayBackSpeedChanged method.

        Will be called when players speed changes (eg. user FF/RW).

        Negative speed means player is rewinding, 1 is normal playback speed.

        :param int speed:           Current speed of player

        """

        self.print_line('Invoked onPlayBackSpeedChanged(%d)' % speed, verbose=True)

    def onPlayBackStarted(self):  # NOSONAR
        """ onPlayBackStarted method.

        Will be called when Kodi player starts. Video or audio might not be available at this point.

        Use onAVStarted() instead if you need to detect if Kodi is actually playing a media file
        (i.e, if a stream is available).

        """

        self.print_line('Invoked onPlayBackStarted()', verbose=True)

    def onPlayBackStopped(self):  # NOSONAR
        """ onPlayBackStopped method.

        Will be called when user stops Kodi playing a file.

        """

        self.print_line('Invoked onPlayBackStopped()', verbose=True)

    def onQueueNextItem(self):  # NOSONAR
        """ onQueueNextItem method.

        Will be called when user queues the next item.

        """

        self.print_line('Invoked onQueueNextItem()', verbose=True)


# noinspection PyPep8Naming
def executeJSONRPC(jsonrpccommand):  # NOSONAR
    """ Execute an JSONRPC command.

    :param str jsonrpccommand:   jsonrpc command to execute.

    :return: jsonrpc return string
    :rtype: str

    See https://codedocs.xyz/xbmc/xbmc/namespace_j_s_o_n_r_p_c.html
    """
    from sakee.sakejsonrpc import JsonRpcApi

    json_data = json.loads(jsonrpccommand)
    try:
        # Implement some methods for real
        return json.dumps(JsonRpcApi().handle(json_data))

    except NotImplementedError:
        # Fallback to stubs
        pass

    json_responses = os.environ.get("KODI_STUB_RPC_RESPONSES")
    if not json_responses:
        raise ValueError(
            "Could not find JSON Response folder. Use the environment variable KODI_STUB_RPC_RESPONSES to set one")

    path = "{}.json".format(os.path.join(json_responses, json_data["method"].lower()))
    if os.path.isfile(path):
        with io.open(path, mode='r', encoding='utf-8') as fd:
            stub_content = json.loads(fd.read())
            if isinstance(stub_content, dict):
                return json.dumps(stub_content)
            try:
                return json.dumps(next(stub.get('response')
                                       for stub in stub_content
                                       if json_data.get('params')
                                       and stub.get('request', {}).get('method') == json_data.get('method')
                                       and stub.get('request', {}).get('params') == json_data.get('params')))
            except StopIteration:
                pass

    return '{"id":1,"jsonrpc":"2.0","result":"OK"}'


# noinspection PyPep8Naming
def translatePath(path):  # NOSONAR
    """ Returns the translated path.

    :param str path:    Path to format

    :return: Translated path
    :rtype: str

    See http://kodi.wiki/view/Special_protocol

    E.g:
        special://home/ is mapped to: kodi/
        special://profile/ is mapped to: kodi/userdata

    Or in portable:
        special://home/ is mapped to: kodi/portable_data/
        special://profile/ is mapped to: kodi/portable_data/userdata

    """

    def get_return_path(base_path, name, *segments):
        if not base_path:
            raise ValueError("Missing __kodi_{}_path data".format(name))
        new_path = os.path.join(base_path, *[i.replace("/", os.sep) for i in segments if i and i != ''])

        if not os.path.exists(new_path):
            raise ValueError("Invalid path specified: {}".format(path, ))

        return new_path

    if path.startswith("special://profile/"):
        return_path = get_return_path(__add_on_info.kodi_profile_path,
                                      "profile",
                                      path.replace("special://profile/", ""))

    elif path.startswith("special://home/"):
        return_path = get_return_path(__add_on_info.kodi_home_path,
                                      "home",
                                      path.replace("special://home/", ""))

    elif path.startswith("special://xbmcbin/"):
        return_path = get_return_path(__add_on_info.kodi_home_path,
                                      "home",
                                      "system",
                                      path.replace("special://xbmcbin/", ""))

    elif os.path.isabs(path):
        return path

    else:
        raise ValueError("Invalid special path: %s" % (path,))

    actual_path = os.path.abspath(return_path)
    KodiStub.print_line("Mapped '{0}' -> '{1}'".format(path, actual_path), color=Colors.Blue)
    return actual_path


def executebuiltin(function):
    """ Execute a built in Kodi function.

    :param str function:    builtin function to execute.

    See: http://kodi.wiki/view/List_of_Built_In_Functions

    """

    KodiStub.print_line("Executebuiltin: {0}".format(function), color=Colors.Blue)


# noinspection PyPep8Naming
def getCondVisibility(condition):  # NOSONAR
    """ Get visibility conditions

    :param str condition:   condition to check

    :return: True (1) or False (0) as a bool
    :rtype: bool

    List of Conditions - http://kodi.wiki/view/List_of_Boolean_Conditions

    """
    result = False
    if condition.startswith('System.HasAddon('):
        add_on_id = condition.replace('System.HasAddon(', '').replace(')', '').strip('"')
        add_ons = os.listdir(os.path.join(__add_on_info.kodi_home_path, "addons"))

        parent_path = os.path.join(__add_on_info.kodi_home_path, "..", "addons")
        if os.path.isdir(parent_path):
            add_ons += os.listdir(parent_path)

        result = add_on_id in add_ons

    elif condition == 'system.platform.windows':
        result = os.name == "nt"

    elif condition == 'system.platform.linux':
        result = os.name == "posix"

    elif condition == 'system.platform.xbox' or condition == 'system.platform.uwp':
        result = False

    else:
        KodiStub.print_line("Missing condition: {}".format(condition), color=Colors.Yellow)

    KodiStub.print_line("Condition: {0}={1}".format(condition, result), color=Colors.Blue, verbose=True)
    return result


# noinspection PyPep8Naming
def getInfoLabel(infoTag):  # NOSONAR
    """ Get a info label

    :param str infoTag:  infoTag for value you want returned.

    :return: InfoLabel as a string
    :rtype: str

    List of InfoTags - http://kodi.wiki/view/InfoLabels
    """

    if infoTag.lower() == "system.buildversion":
        return "19.0 Git:20200626-xxxxxxxxxx"

    return "InfoLabel:{}".format(infoTag)


# noinspection PyPep8Naming,PyShadowingBuiltins,PyUnusedLocal
def getLanguage(format=ISO_639_1, region=None):  # NOSONAR
    """ Get the active language.

    :param int format:          Format of the returned language string (see table)
    :param str|None region:     append the region delimited by "-" of the language
                                (setting) to the returned language string

    :return: The active language as a string
    :rtype: str|unicode

    ==================  ========================================================
    Value               Description
    ==================  ========================================================
    xbmc.ISO_639_1      Two letter code as defined in ISO 639-1
    xbmc.ISO_639_2      Three letter code as defined in ISO 639-2/T
                        or ISO 639-2/B
    xbmc.ENGLISH_NAME   Full language name in English (default)
    ==================  ========================================================

    """

    if format == ISO_639_1:
        return "en"
    if format == ISO_639_2:
        return "eng"

    return "English"


def log(msg, level=0):
    """ Write a string to Kodi's log file and the debug window.

    :param str msg:      Text to output.
    :param int level:    Log level to output at. (default=LOGDEBUG)

    ==================  ========================================================
    Value               Description
    ==================  ========================================================
    xbmc.LOGDEBUG       In depth information about the status of Kodi. This information can pretty much only be deciphered by a developer or long time Kodi power user.
    xbmc.LOGINFO        Something has happened. It's not a problem, we just thought you might want to know. Fairly excessive output that most people won't care about.
    xbmc.LOGNOTICE      Similar to INFO but the average Joe might want to know about these events. This level and above are logged by default.
    xbmc.LOGWARNING     Something potentially bad has happened. If Kodi did something you didn't expect, this is probably why. Watch for errors to follow.
    xbmc.LOGERROR       This event is bad. Something has failed. You likely noticed problems with the application be it skin artifacts, failure of playback a crash, etc.
    xbmc.LOGFATAL       We're screwed. Kodi is about to crash.
    ==================  ========================================================

    Note: You can use the above as keywords for arguments and skip certain optional arguments.
    Once you use a keyword, all following arguments require the keyword.

    """

    if level == LOGERROR:
        print(Colors.Red + msg + Colors.EndColor)
    elif level == LOGWARNING:
        print(Colors.Yellow + msg + Colors.EndColor)
    else:
        print(msg)


def get_add_on_info_from_calling_script(add_on_id=None, print_info=False):
    if add_on_id is not None:
        # Always print details for specific add-ons
        print_info = True

    # What is the Kodi Home path?
    assert os.path.isfile("addon.xml"), "Working directory outside add-on path: {}".format(os.getcwd())
    calling_add_on_path = os.getcwd()

    # Get the generic Kodi paths
    kodi_home_path = os.environ.get("KODI_HOME")
    if kodi_home_path:
        # We only need the ID from the path.
        _, path_add_on_id = calling_add_on_path.rsplit(os.sep, 1)
    else:
        # determine it based on the running path
        kodi_home_path, addon_name, path_add_on_id = os.getcwd().rsplit(os.sep, 2)

    kodi_home_path = os.path.abspath(kodi_home_path)
    assert os.path.isdir(kodi_home_path), \
        "Kodi home path (special://home) does not exist: '{}'".format(kodi_home_path)

    # Find the very first script called to determine the add-on ID if it was not specified
    add_on_id = add_on_id or path_add_on_id

    # Active add-on path
    if add_on_id is None or add_on_id == path_add_on_id:
        # We should use the data from the current calling add-on
        add_on_path = calling_add_on_path
    else:
        # We should set it to the requested add-on based on the given add-on ID
        add_on_path = os.path.join(kodi_home_path, "addons", add_on_id)
        if not os.path.isdir(add_on_path) and "portable_data" in calling_add_on_path:
            add_on_path = os.path.abspath(os.path.join(kodi_home_path, "..", "addons", add_on_id))
    assert os.path.isdir(add_on_path), \
        "Invalid add-on dir for add-on '{}': {}".format(add_on_id, add_on_path)

    # The active profile path
    if "KODI_PROFILE" in os.environ:
        add_on_profile_path = os.path.abspath(os.environ["KODI_PROFILE"])
    else:
        add_on_profile_path = os.path.join(kodi_home_path, "userdata")

    add_on_profile_path = os.path.abspath(add_on_profile_path)
    assert os.path.isdir(add_on_profile_path), \
        "Invalid Kodi master profile dir (special://masterprofile): {}".format(add_on_profile_path)

    if "KODI_ACTIVE_PROFILE" in os.environ:
        add_on_profile_path = os.path.join(
            add_on_profile_path, "profiles", os.environ["KODI_ACTIVE_PROFILE"])

        assert os.path.isdir(add_on_profile_path), \
            "Invalid Kodi profile dir (special://profile): {}".format(add_on_profile_path)

    a = AddonData(
        kodi_home_path=kodi_home_path,
        add_on_id=add_on_id,
        add_on_path=add_on_path,
        kodi_profile_path=add_on_profile_path
    )

    if not print_info:
        return a

    KodiStub.print_line(
        "Found Add-on info: \n"
        "- Kodi Home (special://home):       {} \n"
        "- Add-on ID:                        {} \n"
        "- Add-on Path:                      {} \n"
        "- Kodi Profile (special://profile): {} \n"
            .format(a.kodi_home_path, a.add_on_id, a.add_on_path, a.kodi_profile_path),
        color=Colors.Blue
    )
    return a


__add_on_info = get_add_on_info_from_calling_script(print_info=True)
