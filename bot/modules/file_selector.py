import contextlib

from aiofiles.os import path as aiopath
from aiofiles.os import remove
from pyrogram.filters import command, regex
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

from bot import (
    LOGGER,
    OWNER_ID,
    aria2,
    bot,
    config_dict,
    qbittorrent_client,
    sabnzbd_client,
    task_dict,
    task_dict_lock,
    user_data,
)
from bot.helper.ext_utils.bot_utils import (
    bt_selection_buttons,
    new_task,
    sync_to_async,
)
from bot.helper.ext_utils.status_utils import MirrorStatus, getTaskByGid
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    deleteMessage,
    sendMessage,
    sendStatusMessage,
)


@new_task
async def select(_, message):
    if not config_dict["BASE_URL"]:
        await sendMessage(message, "Base URL not defined!")
        return
    user_id = message.from_user.id
    msg = message.text.split()
    if len(msg) > 1:
        gid = msg[1]
        task = await getTaskByGid(gid)
        if task is None:
            await sendMessage(message, f"GID: <code>{gid}</code> Not Found.")
            return
    elif reply_to_id := message.reply_to_message_id:
        async with task_dict_lock:
            task = task_dict.get(reply_to_id)
        if task is None:
            await sendMessage(message, "This is not an active task!")
            return
    elif len(msg) == 1:
        msg = (
            "Reply to an active /cmd which was used to start the download or add gid along with cmd\n\n"
            + "This command mainly for selection incase you decided to select files from already added torrent/nzb. "
            + "But you can always use /cmd with arg `s` to select files before download start."
        )
        await sendMessage(message, msg)
        return

    if user_id not in (OWNER_ID, task.listener.userId) and (
        user_id not in user_data or not user_data[user_id].get("is_sudo")
    ):
        await sendMessage(message, "This task is not for you!")
        return
    if await sync_to_async(task.status) not in [
        MirrorStatus.STATUS_DOWNLOADING,
        MirrorStatus.STATUS_PAUSED,
        MirrorStatus.STATUS_QUEUEDL,
    ]:
        await sendMessage(
            message,
            "Task should be in download or pause (incase message deleted by wrong) or queued status (incase you have used torrent or nzb file)!",
        )
        return
    if task.name().startswith("[METADATA]") or task.name().startswith("Trying"):
        await sendMessage(message, "Try after downloading metadata finished!")
        return

    try:
        id_ = task.gid()
        if not task.queued:
            if task.listener.isNzb:
                await sabnzbd_client.pause_job(id_)
            elif task.listener.isQbit:
                await sync_to_async(task.update)
                id_ = task.hash()
                await sync_to_async(
                    qbittorrent_client.torrents_pause,
                    torrent_hashes=id_,
                )
            else:
                await sync_to_async(task.update)
                try:
                    await sync_to_async(aria2.client.force_pause, id_)
                except Exception as e:
                    LOGGER.error(
                        f"{e} Error in pause, this mostly happens after abuse aria2",
                    )
        task.listener.select = True
    except:
        await sendMessage(message, "This is not a bittorrent or sabnzbd task!")
        return

    SBUTTONS = bt_selection_buttons(id_)
    msg = "Your download paused. Choose files then press Done Selecting button to resume downloading."
    await sendMessage(message, msg, SBUTTONS)


@new_task
async def get_confirm(_, query):
    user_id = query.from_user.id
    data = query.data.split()
    message = query.message
    task = await getTaskByGid(data[2])
    if task is None:
        await query.answer("This task has been cancelled!", show_alert=True)
        await deleteMessage(message)
        return
    if user_id != task.listener.userId:
        await query.answer("This task is not for you!", show_alert=True)
    elif data[1] == "pin":
        await query.answer(data[3], show_alert=True)
    elif data[1] == "done":
        await query.answer()
        id_ = data[3]
        if hasattr(task, "seeding"):
            if task.listener.isQbit:
                tor_info = (
                    await sync_to_async(
                        qbittorrent_client.torrents_info,
                        torrent_hash=id_,
                    )
                )[0]
                path = tor_info.content_path.rsplit("/", 1)[0]
                res = await sync_to_async(
                    qbittorrent_client.torrents_files,
                    torrent_hash=id_,
                )
                for f in res:
                    if f.priority == 0:
                        f_paths = [f"{path}/{f.name}", f"{path}/{f.name}.!qB"]
                        for f_path in f_paths:
                            if await aiopath.exists(f_path):
                                with contextlib.suppress(Exception):
                                    await remove(f_path)
                if not task.queued:
                    await sync_to_async(
                        qbittorrent_client.torrents_resume,
                        torrent_hashes=id_,
                    )
            else:
                res = await sync_to_async(aria2.client.get_files, id_)
                for f in res:
                    if f["selected"] == "false" and await aiopath.exists(f["path"]):
                        with contextlib.suppress(Exception):
                            await remove(f["path"])
                if not task.queued:
                    try:
                        await sync_to_async(aria2.client.unpause, id_)
                    except Exception as e:
                        LOGGER.error(
                            f"{e} Error in resume, this mostly happens after abuse aria2. Try to use select cmd again!",
                        )
        elif task.listener.isNzb:
            await sabnzbd_client.resume_job(id_)
        await sendStatusMessage(message)
        await deleteMessage(message)
    else:
        await deleteMessage(message)
        await task.cancel_task()


bot.add_handler(
    MessageHandler(
        select,
        filters=command(BotCommands.SelectCommand, case_sensitive=True)
        & CustomFilters.authorized,
    ),
)
bot.add_handler(CallbackQueryHandler(get_confirm, filters=regex("^sel")))
