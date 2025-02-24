from time import time

from bot.helper.ext_utils.status_utils import MirrorStatus, get_readable_time


class RcloneStatus:
    def __init__(self, listener, obj, gid, status):
        self._obj = obj
        self._gid = gid
        self._status = status
        self._elapsed = time()
        self.listener = listener

    @staticmethod
    def engine():
        return "RClone"

    def elapsed(self):
        return get_readable_time(time() - self._elapsed)

    def gid(self):
        return self._gid

    def progress(self):
        return self._obj.percentage

    def speed(self):
        return self._obj.speed

    def name(self):
        return self.listener.name

    def size(self):
        return self._obj.size

    def eta(self):
        return self._obj.eta

    def status(self):
        match self._status:
            case "dl":
                return MirrorStatus.STATUS_DOWNLOADING
            case "up":
                return MirrorStatus.STATUS_UPLOADING
            case _:
                return MirrorStatus.STATUS_CLONING

    def processed_bytes(self):
        return self._obj.transferred_size

    def task(self):
        return self._obj
