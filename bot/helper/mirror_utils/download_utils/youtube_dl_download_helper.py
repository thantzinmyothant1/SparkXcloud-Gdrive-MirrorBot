import os
import random
import string
from .download_helper import DownloadHelper
import time
from yt_dlp import YoutubeDL, DownloadError
from bot import download_dict_lock, download_dict, STORAGE_THRESHOLD
from bot.helper.ext_utils.bot_utils import get_readable_file_size
from bot.helper.telegram_helper.message_utils import sendStatusMessage
from ..status_utils.youtube_dl_download_status import YoutubeDLDownloadStatus
from bot.helper.ext_utils.fs_utils import check_storage_threshold
import logging
import re
import threading

LOGGER = logging.getLogger(__name__)


class MyLogger:
    def __init__(self, obj):
        self.obj = obj

    def debug(self, msg):
        LOGGER.debug(msg)
        match = re.search(r'.ffmpeg..Merging formats into..(.*?).$', msg)
        if match and not self.obj.is_playlist:
            newname = match.group(1)
            newname = newname.split("/")
            newname = newname[-1]
            self.obj.name = newname

    @staticmethod
    def warning(msg):
        LOGGER.warning(msg)

    @staticmethod
    def error(msg):
        LOGGER.error(msg)


class YoutubeDLHelper(DownloadHelper):
    def __init__(self, listener):
        super().__init__()
        self.name = ""
        self.__start_time = time.time()
        self.__listener = listener
        self.__gid = ""
        self.opts = {
            'progress_hooks': [self.__onDownloadProgress],
            'logger': MyLogger(self),
            'usenetrc': True
        }
        self.__download_speed = 0
        self.downloaded_bytes = 0
        self.size = 0
        self.is_playlist = False
        self.last_downloaded = 0
        self.is_cancelled = False
        self.vid_id = ''
        self.__resource_lock = threading.RLock()

    @property
    def download_speed(self):
        with self.__resource_lock:
            return self.__download_speed

    @property
    def gid(self):
        with self.__resource_lock:
            return self.__gid

    def __onDownloadProgress(self, d):
        if self.is_cancelled:
            raise ValueError("Cancelling Download..")
        if d['status'] == "finished":
            if self.is_playlist:
                self.last_downloaded = 0
        elif d['status'] == "downloading":
            with self.__resource_lock:
                self.__download_speed = d['speed']
                try:
                    tbyte = d['total_bytes']
                except KeyError:
                    tbyte = d['total_bytes_estimate']
                if self.is_playlist:
                    progress = d['downloaded_bytes'] / tbyte
                    chunk_size = d['downloaded_bytes'] - self.last_downloaded
                    self.last_downloaded = tbyte * progress
                    self.downloaded_bytes += chunk_size
                else:
                    if d.get('total_bytes'):
                        self.size = d['total_bytes']
                    elif d.get('total_bytes_estimate'):
                        self.size = d['total_bytes_estimate']
                    self.downloaded_bytes = d['downloaded_bytes']
                try:
                    self.progress = (self.downloaded_bytes / self.size) * 100
                except ZeroDivisionError:
                    pass

    def __onDownloadStart(self):
        with download_dict_lock:
            download_dict[self.__listener.uid] = YoutubeDLDownloadStatus(self, self.__listener, self.__gid)
        sendStatusMessage(self.__listener.message, self.__listener.bot)

    def __onDownloadComplete(self):
        self.__listener.onDownloadComplete()

    def onDownloadError(self, error):
        self.__listener.onDownloadError(error)

    def extractMetaData(self, link, name, args, get_info=False):
        if args is not None:
            self.__set_args(args)
        if get_info:
            self.opts['playlist_items'] = '0'
        with YoutubeDL(self.opts) as ydl:
            try:
                result = ydl.extract_info(link, download=False)
                if get_info:
                    return result
                realName = ydl.prepare_filename(result)
            except Exception as e:
                if get_info:
                    raise e
                self.__onDownloadError(str(e))
                return
        if 'entries' in result:
            for v in result['entries']:
                try:
                    self.size += v['filesize_approx']
                except:
                    pass
            self.is_playlist = True
            if name == "":
                self.name = str(realName).split(f" [{result['id'].replace('*', '_')}]")[0]
            else:
                self.name = name
        else:
            ext = realName.split('.')[-1]
            if name == "":
                newname = str(realName).split(f" [{result['id'].replace('*', '_')}]")
                if len(newname) > 1:
                    self.name = newname[0] + '.' + ext
                else:
                    self.name = newname[0]
            else:
                self.name = f"{name}.{ext}"

    def __download(self, link):
        try:
            with YoutubeDL(self.opts) as ydl:
                try:
                    ydl.download([link])
                except DownloadError as e:
                    if not self.__is_cancelled:
                        self.__onDownloadError(str(e))
                    return
            if self.__is_cancelled:
                raise ValueError
            self.__onDownloadComplete()
        except ValueError:
            self.__onDownloadError("Download Stopped by User!")

    def add_download(self, link, path, name, qual, playlist, args):
        if playlist:
            self.opts['ignoreerrors'] = True
        self.__gid = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=10))
        self.__onDownloadStart()
        if qual.startswith('ba/b'):
            audio_info = qual.split('-')
            qual = audio_info[0]
            if len(audio_info) == 2:
                rate = audio_info[1]
            else:
                rate = 320
            self.opts['postprocessors'] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': f'{rate}'}]
        self.opts['format'] = qual
        LOGGER.info(f"Downloading with YT-DLP: {link}")
        self.extractMetaData(link, name, args)
        if self.__is_cancelled:
            return
        if STORAGE_THRESHOLD is not None:
            acpt = check_storage_threshold(self.size, self.__listener.isZip)
            if not acpt:
                msg = f'You must leave {STORAGE_THRESHOLD}GB free storage.'
                msg += f'\nYour File/Folder size is {get_readable_file_size(self.size)}'
                return self.__onDownloadError(msg)
        if not self.is_playlist:
            self.opts['outtmpl'] = f"{path}/{self.name}"
        else:
            self.opts['outtmpl'] = f"{path}/{self.name}/%(title)s.%(ext)s"
        self.__download(link)

    def cancel_download(self):
        self.__is_cancelled = True
        LOGGER.info(f"Cancelling Download: {self.name}")
        if not self.__downloading:
            self.__onDownloadError("Download Cancelled by User!")

    def __set_args(self, args):
        args = args.split('|')
        for arg in args:
            xy = arg.split(':')
            if xy[1].startswith('^'):
                xy[1] = int(xy[1].split('^')[1])
            elif xy[1].lower() == 'true':
                xy[1] = True
            elif xy[1].lower() == 'false':
                xy[1] = False
            self.opts[xy[0]] = xy[1]
