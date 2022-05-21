import logging
import threading
import random
import time
from bot import LOGGER, download_dict, download_dict_lock, app, STOP_DUPLICATE, STORAGE_THRESHOLD
from bot.helper.ext_utils.bot_utils import get_readable_file_size
from .download_helper import DownloadHelper
from ..status_utils.telegram_download_status import TelegramDownloadStatus
from bot.helper.telegram_helper.message_utils import sendMarkup, sendMessage, sendStatusMessage
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.ext_utils.fs_utils import check_storage_threshold

global_lock = threading.Lock()
GLOBAL_GID = set()
logging.getLogger("pyrogram").setLevel(logging.WARNING)


class TelegramDownloadHelper(DownloadHelper):
    def __init__(self, listener):
        super().__init__()
        self.__listener = listener
        self.__resource_lock = threading.RLock()
        self.__name = ""
        self.__start_time = time.time()
        self.__id = ""
        self.__is_cancelled = False

    @property
    def gid(self):
        with self.__resource_lock:
            return self.__gid

    @property
    def download_speed(self):
        with self.__resource_lock:
            return self.downloaded_bytes / (time.time() - self.__start_time)

    def __onDownloadStart(self, name, size, file_id):
        with download_dict_lock:
            download_dict[self.__listener.uid] = TelegramDownloadStatus(self, self.__listener)
        with global_lock:
            GLOBAL_GID.add(file_id)
        with self.__resource_lock:
            self.name = name
            self.size = size
            self.__id = file_id
        gid = ''.join(random.choices(file_id, k=12))
        with download_dict_lock:
            download_dict[self.__listener.uid] = TelegramDownloadStatus(self, self.__listener, gid)
        sendStatusMessage(self.__listener.message, self.__listener.bot)

    def __onDownloadProgress(self, current, total):
        if self.__is_cancelled:
            self.__onDownloadError('Cancelled by user!')
            app.stop_transmission()
            return
        with self.__resource_lock:
            self.downloaded_bytes = current
            try:
                self.progress = current / self.size * 100
            except ZeroDivisionError:
                pass
            
    def __onDownloadError(self, error):
        with global_lock:
            try:
                GLOBAL_GID.remove(self.__id)
            except KeyError:
                pass
        self.__listener.onDownloadError(error)

    def __onDownloadComplete(self):
        with global_lock:
            GLOBAL_GID.remove(self.__id)
        self.__listener.onDownloadComplete()

    def __download(self, message, path):
        download = app.download_media(
            message,
            progress = self.__onDownloadProgress,
            file_name = path
        )
        if download is not None:
            self.__onDownloadComplete()
        else:
            if not self.__is_cancelled:
                self.__onDownloadError('Internal error occurred')

    def add_download(self, message, path, filename):
        _dmsg = app.get_messages(message.chat.id, reply_to_message_ids=message.message_id)
        media = None
        media_array = [_dmsg.document, _dmsg.video, _dmsg.audio]
        for i in media_array:
            if i is not None:
                media = i
                break
        if media is not None:
            with global_lock:
                # For avoiding locking the thread lock for long time unnecessarily
                download = media.file_id not in GLOBAL_GID
            if filename == "":
                name = media.file_name
            else:
                name = filename
                path = path + name
            
            if download:
                size = media.file_size
                if STOP_DUPLICATE and not self.__listener.isLeech:
                    LOGGER.info(f"Checking File/Folder if already in Drive...")
                    if self.__listener.isTar:
                        name = name + ".tar"
                    if self.__listener.extract:           
                        smsg = None
                    else:
                        gd = GoogleDriveHelper()
                        smsg, button = gd.drive_list(name)
                    if smsg:
                        msg = "File/Folder is already available in Drive.\nHere are the search results:"
                        return sendMarkup(msg, self.__listener.bot, self.__listener.message, button)
                if STORAGE_THRESHOLD is not None:
                    arch = any([self.__listener.isZip, self.__listener.extract])
                    acpt = check_storage_threshold(size, arch)
                    if not acpt:
                        msg = f'You must leave {STORAGE_THRESHOLD}GB free storage.'
                        msg += f'\nYour File/Folder size is {get_readable_file_size(size)}'
                        return sendMessage(msg, self.__listener.bot, self.__listener.message)
                self.__onDownloadStart(name, size, media.file_id)
                
                LOGGER.info(f'Downloading Telegram file with id: {media.file_id}')
                threading.Thread(target=self.__download, args=(_dmsg, path)).start()
            else:
                self.__onDownloadError('File already being downloaded!')
        else:
            self.__onDownloadError('No document in the replied message')

    def cancel_download(self):
        LOGGER.info(f'Cancelling download on user request: {self.__id}')
        self.__is_cancelled = True
