import os
import time
import threading
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)
from youtube import Download, get_available_qualities
import yt_dlp

TOKEN = "8008175129:AAEVbuLnaIpwOWu9CBq8NtXNrf6c19tCvwU"

WAITING_FOR_MODE, WAITING_FOR_RESOLUTION = range(2)
user_state = {}

def is_youtube_url(text):
    return any(part in text for part in [
        "youtube.com/watch",
        "youtu.be/",
        "youtube.com/shorts/",
        "youtube.com/live/",
        "youtube.com/embed/",
        "youtube.com/playlist"
    ])

def normalize_youtube_link(link):
    if "shorts/" in link:
        video_id = link.split("shorts/")[1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    if "youtu.be/" in link:
        video_id = link.split("youtu.be/")[1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return link

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    link = update.message.text.strip()

    if not is_youtube_url(link):
        await update.message.reply_text("❌ Please send a valid YouTube link.")
        return ConversationHandler.END

    link = normalize_youtube_link(link)
    user_state[user_id] = {'url': link}
    user_state[user_id]['type'] = 'playlist' if "playlist?" in link else 'video'

    keyboard = [
        [InlineKeyboardButton("🎬 Video", callback_data='video')],
        [InlineKeyboardButton("🎧 Audio", callback_data='audio')]
    ]
    await update.message.reply_text("What would you like to download?", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAITING_FOR_MODE

async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    mode = query.data
    user_state[user_id]['mode'] = mode

    url = user_state[user_id]['url']
    if user_state[user_id]['type'] == 'playlist' or mode == 'audio':
        await context.bot.send_message(chat_id=user_id, text="📥 Preparing download...")
        return await send_file(context, user_id)

    await context.bot.send_message(chat_id=user_id, text="🔍 Checking available video qualities...")
    qualities = get_available_qualities(url)
    if not qualities:
        await context.bot.send_message(chat_id=user_id, text="❌ Could not fetch video qualities.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(q, callback_data=q)] for q in qualities]
    await context.bot.send_message(
        chat_id=user_id,
        text="Choose resolution (height@fps):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_RESOLUTION

async def choose_resolution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    resolution = query.data
    user_state[user_id]['resolution'] = resolution

    await context.bot.send_message(chat_id=user_id, text=f"📥 Downloading {resolution}...")
    return await send_file(context, user_id)

def delete_file_delayed(file_path, delay=300):
    def _delete():
        time.sleep(delay)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[Auto-cleanup] Deleted: {file_path}")
    threading.Thread(target=_delete).start()

async def send_file(context: ContextTypes.DEFAULT_TYPE, user_id):
    data = user_state.get(user_id)
    if not data:
        await context.bot.send_message(chat_id=user_id, text="Session expired. Please send the link again.")
        return ConversationHandler.END

    url = data['url']
    mode = data['mode']
    resolution = data.get('resolution', '720p@30fps')
    link_type = data.get('type', 'video')

    if link_type == 'playlist':
        await context.bot.send_message(chat_id=user_id, text="🔁 Starting playlist download...")

        skipped = 0
        sent = 0

        try:
            ydl_opts = {
                'quiet': True,
                'outtmpl': f'Downloads/{user_id}/%(title)s.%(ext)s',
                'format': 'bestaudio/best' if mode == 'audio' else 'bestvideo+bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }] if mode == 'audio' else [],
                'noplaylist': False,
                'merge_output_format': 'mp4',
                'ignoreerrors': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                entries = info.get('entries', [])
                total = len(entries)

                progress_msg = await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏳ Downloading playlist: 0 of {total} (0%)"
                )

                for idx, entry in enumerate(entries, 1):
                    if entry is None:
                        skipped += 1
                        continue

                    title = entry.get('title') or f"Video {idx}"
                    file_path = ydl.prepare_filename(entry)
                    if mode == 'audio':
                        file_path = os.path.splitext(file_path)[0] + ".mp3"

                    percent = int((idx / total) * 100)
                    try:
                        await context.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=progress_msg.message_id,
                            text=f"⏳ {percent}% - {idx - skipped} of {total}\n🎞️ Now: {title}"
                        )
                    except:
                        pass

                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            filename = os.path.basename(file_path)
                            await context.bot.send_document(chat_id=user_id, document=f, filename=filename)
                        sent += 1
                        delete_file_delayed(file_path)
                        await asyncio.sleep(2)
                    else:
                        skipped += 1

                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=progress_msg.message_id,
                    text=f"✅ Playlist finished!\n📦 Sent: {sent}\n⛔ Skipped: {skipped} private/unavailable"
                )

        except Exception as e:
            print(f"Playlist error: {e}")
            await context.bot.send_message(chat_id=user_id, text="❌ Playlist download failed.")
        return ConversationHandler.END

    file_path, size_mb = Download(url, str(user_id), mode=mode, resolution=resolution)
    if not file_path:
        await context.bot.send_message(chat_id=user_id, text="❌ Download failed.")
        return ConversationHandler.END

    try:
        await context.bot.send_message(chat_id=user_id, text=f"📦 File size: {size_mb} MB. Sending now...")

        with open(file_path, 'rb') as f:
            filename = os.path.basename(file_path)
            caption = f"✅ Your {mode} file is ready."
            await context.bot.send_document(chat_id=user_id, document=f, filename=filename, caption=caption)

        await context.bot.send_message(chat_id=user_id, text="✅ Sent successfully.")
        delete_file_delayed(file_path)

    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text="❌ Failed to send file.")
        print(f"Sending error: {e}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & (~filters.COMMAND), handle_link)],
        states={
            WAITING_FOR_MODE: [CallbackQueryHandler(choose_mode)],
            WAITING_FOR_RESOLUTION: [CallbackQueryHandler(choose_resolution)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)

    print("✅ Bot is running without warnings...")
    app.run_polling()

if __name__ == '__main__':
    main()
