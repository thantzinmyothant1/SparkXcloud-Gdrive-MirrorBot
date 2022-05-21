import sys
from os import remove as osremove, path as ospath, mkdir, walk, listdir, rmdir, makedirs
from bot import aria2, LOGGER, DOWNLOAD_DIR, get_client
import shutil
import os
import pathlib
from magic import Magic
from subprocess import run as srun, check_output
from math import ceil
from sys import exit as sysexit
from json import loads as jsnloads
from shutil import rmtree, disk_usage
import tarfile
from .exceptions import NotSupportedExtractionArchive
from bot import aria2, LOGGER, DOWNLOAD_DIR, get_client, TG_SPLIT_SIZE, EQUAL_SPLITS, STORAGE_THRESHOLD

VIDEO_SUFFIXES = ("M4V", "MP4", "MOV", "FLV", "WMV", "3GP", "MPG", "WEBM", "MKV", "AVI")

def clean_download(path: str):
    if os.path.exists(path):
        LOGGER.info(f"Cleaning download: {path}")
        shutil.rmtree(path)


def start_cleanup():
    try:
        shutil.rmtree(DOWNLOAD_DIR)
    except FileNotFoundError:
        pass
    makedirs(DOWNLOAD_DIR)


def clean_all():
    aria2.remove_all(True)
    qbc = get_client()
    qbc.torrents_delete(torrent_hashes="all", delete_files=True)
    qbc.app_shutdown()
    try:
        shutil.rmtree(DOWNLOAD_DIR)
    except FileNotFoundError:
        pass


def exit_clean_up(signal, frame):
    try:
        LOGGER.info("Please wait, while we clean up the downloads and stop running downloads")
        clean_all()
        sys.exit(0)
    except KeyboardInterrupt:
        LOGGER.warning("Force Exiting before the cleanup finishes!")
        sys.exit(1)


def get_path_size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total_size = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            abs_path = os.path.join(root, f)
            total_size += os.path.getsize(abs_path)
    return total_size


def tar(org_path):
    tar_path = org_path + ".tar"
    #path = pathlib.PurePath(org_path)
    LOGGER.info(f'Tar: orig_path: {org_path}, tar_path: {tar_path}')
    tar = tarfile.open(tar_path, "w")
    tar.add(org_path, arcname=os.path.basename(org_path))
    tar.close()
    return tar_path


def zip(name, path):
    root_dir = os.path.dirname(path)
    base_dir = os.path.basename(path.strip(os.sep))
    zip_file = shutil.make_archive(name, "zip", root_dir, base_dir)
    zip_path = shutil.move(zip_file, root_dir)
    LOGGER.info(f"Zip: {zip_path}")
    return zip_path

def check_storage_threshold(size: int, arch=False, alloc=False):
    if not alloc:
        if not arch:
            if disk_usage(DOWNLOAD_DIR).free - size < STORAGE_THRESHOLD * 1024**3:
                return False
        elif disk_usage(DOWNLOAD_DIR).free - (size * 2) < STORAGE_THRESHOLD * 1024**3:
            return False
    elif not arch:
        if disk_usage(DOWNLOAD_DIR).free < STORAGE_THRESHOLD * 1024**3:
            return False
    elif disk_usage(DOWNLOAD_DIR).free - size < STORAGE_THRESHOLD * 1024**3:
        return False
    return True

def get_base_name(orig_path: str):
    if orig_path.endswith(".tar.bz2"):
        return orig_path.replace(".tar.bz2", "")
    elif orig_path.endswith(".tar.gz"):
        return orig_path.replace(".tar.gz", "")
    elif orig_path.endswith(".bz2"):
        return orig_path.replace(".bz2", "")
    elif orig_path.endswith(".gz"):
        return orig_path.replace(".gz", "")
    elif orig_path.endswith(".tar.xz"):
        return orig_path.replace(".tar.xz", "")
    elif orig_path.endswith(".tar"):
        return orig_path.replace(".tar", "")
    elif orig_path.endswith(".tbz2"):
        return orig_path.replace("tbz2", "")
    elif orig_path.endswith(".tgz"):
        return orig_path.replace(".tgz", "")
    elif orig_path.endswith(".zip"):
        return orig_path.replace(".zip", "")
    elif orig_path.endswith(".7z"):
        return orig_path.replace(".7z", "")
    elif orig_path.endswith(".Z"):
        return orig_path.replace(".Z", "")
    elif orig_path.endswith(".rar"):
        return orig_path.replace(".rar", "")
    elif orig_path.endswith(".iso"):
        return orig_path.replace(".iso", "")
    elif orig_path.endswith(".wim"):
        return orig_path.replace(".wim", "")
    elif orig_path.endswith(".cab"):
        return orig_path.replace(".cab", "")
    elif orig_path.endswith(".apm"):
        return orig_path.replace(".apm", "")
    elif orig_path.endswith(".arj"):
        return orig_path.replace(".arj", "")
    elif orig_path.endswith(".chm"):
        return orig_path.replace(".chm", "")
    elif orig_path.endswith(".cpio"):
        return orig_path.replace(".cpio", "")
    elif orig_path.endswith(".cramfs"):
        return orig_path.replace(".cramfs", "")
    elif orig_path.endswith(".deb"):
        return orig_path.replace(".deb", "")
    elif orig_path.endswith(".dmg"):
        return orig_path.replace(".dmg", "")
    elif orig_path.endswith(".fat"):
        return orig_path.replace(".fat", "")
    elif orig_path.endswith(".hfs"):
        return orig_path.replace(".hfs", "")
    elif orig_path.endswith(".lzh"):
        return orig_path.replace(".lzh", "")
    elif orig_path.endswith(".lzma"):
        return orig_path.replace(".lzma", "")
    elif orig_path.endswith(".lzma2"):
        return orig_path.replace(".lzma2", "")
    elif orig_path.endswith(".mbr"):
        return orig_path.replace(".mbr", "")
    elif orig_path.endswith(".msi"):
        return orig_path.replace(".msi", "")
    elif orig_path.endswith(".mslz"):
        return orig_path.replace(".mslz", "")
    elif orig_path.endswith(".nsis"):
        return orig_path.replace(".nsis", "")
    elif orig_path.endswith(".ntfs"):
        return orig_path.replace(".ntfs", "")
    elif orig_path.endswith(".rpm"):
        return orig_path.replace(".rpm", "")
    elif orig_path.endswith(".squashfs"):
        return orig_path.replace(".squashfs", "")
    elif orig_path.endswith(".udf"):
        return orig_path.replace(".udf", "")
    elif orig_path.endswith(".vhd"):
        return orig_path.replace(".vhd", "")
    elif orig_path.endswith(".xar"):
        return orig_path.replace(".xar", "")
    else:
        raise NotSupportedExtractionArchive('File format not supported for extraction')


def get_mime_type(file_path):
    mime = magic.Magic(mime=True)
    mime_type = mime.from_file(file_path)
    mime_type = mime_type if mime_type else "text/plain"
    return mime_type

def split(path, size, file_, dirpath, split_size, start_time=0, i=1, inLoop=False):
    parts = ceil(size/TG_SPLIT_SIZE)
    if EQUAL_SPLITS and not inLoop:
        split_size = ceil(size/parts) + 1000
    if file_.upper().endswith(VIDEO_SUFFIXES):
        base_name, extension = ospath.splitext(file_)
        split_size = split_size - 2500000
        while i <= parts :
            parted_name = "{}.part{}{}".format(str(base_name), str(i).zfill(3), str(extension))
            out_path = ospath.join(dirpath, parted_name)
            srun(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i",
                            path, "-ss", str(start_time), "-fs", str(split_size),
                            "-async", "1", "-strict", "-2", "-c", "copy", out_path])
            out_size = get_path_size(out_path)
            if out_size > 2097152000:
                dif = out_size - 2097152000
                split_size = split_size - dif + 2500000
                osremove(out_path)
                return split(path, size, file_, dirpath, split_size, start_time, i, inLoop=True)
            lpd = get_media_info(out_path)[0]
            if lpd <= 4 or out_size < 1000000:
                osremove(out_path)
                break
            start_time += lpd - 3
            i = i + 1
    else:
        out_path = ospath.join(dirpath, file_ + ".")
        srun(["split", "--numeric-suffixes=1", "--suffix-length=3", f"--bytes={split_size}", path, out_path])

def get_media_info(path):
    try:
        result = check_output(["ffprobe", "-hide_banner", "-loglevel", "error", "-print_format",
                                          "json", "-show_format", path]).decode('utf-8')
        fields = jsnloads(result)['format']
    except Exception as e:
        LOGGER.error(f"get_media_info: {e}")
        return 0, None, None
    try:
        duration = round(float(fields['duration']))
    except:
        duration = 0
    try:
        artist = str(fields['tags']['artist'])
    except:
        artist = None
    try:
        title = str(fields['tags']['title'])
    except:
        title = None
    return duration, artist, title
def get_video_resolution(path):
    try:
        result = check_output(["ffprobe", "-hide_banner", "-loglevel", "error", "-select_streams", "v:0",
                                          "-show_entries", "stream=width,height", "-of", "json", path]).decode('utf-8')
        fields = jsnloads(result)['streams'][0]
        width = int(fields['width'])
        height = int(fields['height'])
        return width, height
    except Exception as e:
        LOGGER.error(f"get_video_resolution: {e}")
        return 480, 320