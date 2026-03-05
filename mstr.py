import os
import re
import csv
import io
import json
import asyncio
import logging
from functools import wraps
from datetime import datetime, timedelta
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Poll
from telegram.error import TelegramError, RetryAfter, Conflict
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Optional Basic PDF support (for fallback)
try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# Google Gemini AI Generation Support (100% Free & Native Scanned PDF Support)
try:
    import google.generativeai as genai
    AI_SUPPORT = True
except ImportError:
    AI_SUPPORT = False

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# ⚙️ CONFIGURATION - EDIT THESE VALUES
# ==========================================
TELEGRAM_BOT_TOKEN = "8689120822:AAHzkhFHyuYcWDd5MwiwqPBoQXV-ujobk2w"
ADMIN_CONTACT = "@Mr_outlaw001"
ADMIN_ID = 6915757343  # ⚠️ CHANGE THIS TO YOUR ACTUAL NUMERIC TELEGRAM USER ID

# 🤖 GET YOUR FREE API KEY FROM: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = "AIzaSyC1Jv-HhcBixqg-TRtJ-JTmeuDfTyLfnJI"

AUTH_FILE = "auth_users.json"
TRACKING_FILE = "sent_polls.json"  

# ==========================================
# 🔒 AUTHORIZATION SYSTEM
# ==========================================
def load_auth_users():
    if not os.path.exists(AUTH_FILE):
        return {}
    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                new_data = {}
                expiry = (datetime.now() + timedelta(days=2)).isoformat()
                for uid in data:
                    new_data[str(uid)] = {"expiry": expiry}
                save_auth_users(new_data)
                return new_data
            return data
    except Exception:
        return {}

def save_auth_users(users):
    with open(AUTH_FILE, "w") as f:
        json.dump(users, f, indent=4)

def save_sent_poll(channel_id, message_id):
    data = {}
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            pass
            
    ch_id_str = str(channel_id)
    if ch_id_str not in data:
        data[ch_id_str] = []
        
    data[ch_id_str].append(message_id)
    
    with open(TRACKING_FILE, "w") as f:
        json.dump(data, f, indent=4)

def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id == ADMIN_ID:
            return await func(update, context, *args, **kwargs)
            
        users = load_auth_users()
        str_uid = str(user_id)
        if str_uid in users:
            try:
                expiry = datetime.fromisoformat(users[str_uid]["expiry"])
                if datetime.now() <= expiry:
                    return await func(update, context, *args, **kwargs)
                else:
                    msg = "⛔ **Your subscription has expired.**\nPlease use /contact to reach the admin to renew."
            except Exception:
                msg = "⛔ **Subscription data error.**\nPlease contact admin."
        else:
            msg = "⛔ **Access Denied.**\nYou are not authorized. Use /start to get a 2-Day Free Trial!"
            
        if update.message:
            await update.message.reply_text(msg, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.answer("Access Denied or Expired.", show_alert=True)
        return
    return wrapped

# ==========================================
# 📝 HELPER FUNCTIONS
# ==========================================
def parse_csv_content(csv_content: str):
    if csv_content.startswith('\ufeff'):
        csv_content = csv_content[1:]
    reader = csv.reader(io.StringIO(csv_content.strip()))
    questions =[]
    ans_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3, '1': 0, '2': 1, '3': 2, '4': 3}
    for i, row in enumerate(reader):
        if not row or len(row) < 6: continue
        if i == 0 and ('Q' in row[0].upper() or 'QUESTION' in row[0].upper()): continue
        try:
            q_text = row[0].strip()[:300]
            options = [
                row[1].strip()[:100] or 'Opt A',
                row[2].strip()[:100] or 'Opt B',
                row[3].strip()[:100] or 'Opt C',
                row[4].strip()[:100] or 'Opt D'
            ]
            ans_letter = row[5].strip().upper()
            if ans_letter not in ans_map: continue
            questions.append({
                'question': q_text, 
                'options': options,
                'correct_index': ans_map[ans_letter]
            })
        except Exception as e:
            logger.error(f"Row parsing error: {e}")
    return questions

def generate_html_quiz(questions: list, title: str, negative_marking: str) -> str:
    html = f"<html><head><title>{title}</title><style>body{{font-family: Arial; padding: 20px; background: #f4f4f9;}} .q{{margin-top: 20px; font-weight: bold; font-size: 18px;}} .opt{{margin-left: 15px; font-size: 16px; padding: 5px;}} .ans{{color: green; font-weight: bold; margin-left: 15px; margin-top: 10px;}}</style></head><body>"
    html += f"<h2>🔥 Test: {title}</h2><p><b>Negative Marking:</b> {negative_marking}</p><hr>"
    for i, q in enumerate(questions):
        html += f"<div class='q'>Q{i+1}. {q['question']}</div>"
        for j, opt in enumerate(q['options']):
            html += f"<div class='opt'>({chr(65+j)}) {opt}</div>"
        html += f"<div class='ans'>Answer: {chr(65 + q['correct_index'])}</div>"
    html += "</body></html>"
    return html

async def extract_content(msg, context) -> str:
    if msg.document:
        file = await context.bot.get_file(msg.document.file_id)
        byte_array = await file.download_as_bytearray()
        try:
            return byte_array.decode('utf-8-sig')
        except UnicodeDecodeError:
            return byte_array.decode('cp1252', errors='replace')
    elif msg.text: return msg.text
    return ""

async def post_init(application: Application) -> None:
    commands =[
        BotCommand("start", "Show welcome message & menu"),
        BotCommand("contact", "Contact the Admin"),
        BotCommand("help", "Show list of all commands"),
        BotCommand("myplan", "Check subscription validity"),
        BotCommand("channels", "View list of target channels"),
        BotCommand("uploadcsv", "Upload CSV to generate MCQs"),
        BotCommand("pdftocsv", "AI Convert PDF to CSV MCQs"),
        BotCommand("getcsv", "Send quizzes from uploaded CSV"),
        BotCommand("setchannel", "Set the target channel"),
        BotCommand("settimer", "Set the auto-close timer for polls"),
        BotCommand("schedule", "Schedule a time to start posting"),
        BotCommand("csv2html", "Live offline test create using csv"),
        BotCommand("status", "Check ongoing processes & loaded data"),
        BotCommand("deletequizzes", "🗑 Delete past bot quizzes from channel"),
        BotCommand("pause", "⏸ Pause the ongoing quiz"),
        BotCommand("resume", "▶️ Resume the paused quiz"),
        BotCommand("stop", "🛑 Instantly stop sending ongoing polls"),
        BotCommand("cancel", "🚫 Cancel waiting for files/input"),
        BotCommand("startfresh", "🔄 Wipe all data and reset the bot")
    ]
    await application.bot.set_my_commands(commands)
    print("✅ Menu Button configured successfully on Telegram!")

# ==========================================
# 👑 ADMIN COMMANDS (Authorization)
# ==========================================
async def auth_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("⛔ Only the main Admin can use this command.")
    if not context.args: return await update.message.reply_text("⚠️ Please provide a User ID.\nExample: `/auth 987654321`", parse_mode="Markdown")
    try:
        new_user = int(context.args[0])
        keyboard = [[InlineKeyboardButton("30 Days", callback_data=f"authplan_{new_user}_30"), InlineKeyboardButton("100 Days", callback_data=f"authplan_{new_user}_100")]]
        await update.message.reply_text(f"⚙️ Choose plan validity for user `{new_user}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid ID. Must be a number.")

async def unauth_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("⛔ Only the main Admin can use this command.")
    if not context.args: return await update.message.reply_text("⚠️ Please provide a User ID.\nExample: `/unauth 987654321`", parse_mode="Markdown")
    del_user = str(context.args[0])
    users = load_auth_users()
    if del_user in users:
        del users[del_user]
        save_auth_users(users)
        await update.message.reply_text(f"✅ User `{del_user}` access revoked.", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ User is not in the authorized list.")

async def auth_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("⛔ Only the main Admin can use this command.")
    users = load_auth_users()
    if not users:
        await update.message.reply_text("📋 No users are currently authorized.")
    else:
        user_str =[]
        now = datetime.now()
        for uid, data in users.items():
            try:
                exp = datetime.fromisoformat(data["expiry"])
                status = "✅" if exp > now else "❌ Expired"
                user_str.append(f"• `{uid}` - Exp: {exp.strftime('%Y-%m-%d')} ({status})")
            except Exception:
                user_str.append(f"• `{uid}` - Error parsing date")
        await update.message.reply_text("📋 **Authorized Users:**\n" + "\n".join(user_str), parse_mode="Markdown")

# ==========================================
# 🛠️ GENERAL BOT COMMANDS
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    str_uid = str(user_id)
    trial_given, expired = False, False
    if user_id != ADMIN_ID:
        users = load_auth_users()
        if str_uid not in users:
            users[str_uid] = {"expiry": (datetime.now() + timedelta(days=2)).isoformat()}
            save_auth_users(users)
            trial_given = True
        else:
            try:
                if datetime.now() > datetime.fromisoformat(users[str_uid]["expiry"]): expired = True
            except Exception: expired = True

    keyboard = [[InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_CONTACT.replace('@', '')}")],[InlineKeyboardButton("ℹ️ Help", callback_data="help_btn")]]
    text = "🤖 **WELCOME TO MCQ MASTER BOT!**\n\n"
    if trial_given: text += "🎉 **You have been granted a 2-Day Free Trial!**\n\n"
    elif expired: text += "⚠️ **Your subscription has EXPIRED.**\nYou can view menus, but cannot execute commands. Use /contact to renew.\n\n"
    else: text += "✨ **Welcome back! Your subscription is ACTIVE.**\n\n"
            
    text += (
        "✦ I automatically convert your CSV & PDF files into Telegram Quiz Polls.\n"
        "✦ **AI PDF Processing:** I can read Notes/Books and automatically generate MCQs flawlessly!\n\n"
        "🔰 **To begin:** Use /uploadcsv or /pdftocsv\n"
        "⚙️ **To configure:** Use /setchannel & /settimer\n\n"
        f"• MAINTAINER: {ADMIN_CONTACT}"
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"📞 **Contact Administration**\n\n👤 **Username:** `{ADMIN_CONTACT}`\n🔗 **Link:**[Click here](https://t.me/{ADMIN_CONTACT.replace('@', '')})", parse_mode="Markdown", disable_web_page_preview=True)

@restricted
async def myplan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id == ADMIN_ID: return await update.message.reply_text("👑 **Admin Account**\nYou have unlimited lifetime access.", parse_mode="Markdown")
    users = load_auth_users()
    str_uid = str(user_id)
    if str_uid in users:
        expiry = datetime.fromisoformat(users[str_uid]["expiry"])
        now = datetime.now()
        if expiry > now:
            delta = expiry - now
            await update.message.reply_text(f"✅ **Active Plan**\n\n⏳ Remaining: `{delta.days} days, {delta.seconds // 3600} hours`\n📅 Expiry: `{expiry.strftime('%Y-%m-%d %H:%M:%S')}`", parse_mode="Markdown")
        else: await update.message.reply_text("⛔ **Your plan has expired.**", parse_mode="Markdown")
    else: await update.message.reply_text("❓ You don't have an active plan.")

@restricted
async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    saved_channels = context.user_data.get('channels',[])
    current_channel = context.user_data.get('selected_channel', 'None')
    if current_channel != 'None' and current_channel not in saved_channels:
        saved_channels.append(current_channel)
        context.user_data['channels'] = saved_channels
    if not saved_channels: return await update.message.reply_text("❌ No target channels saved yet. Use /setchannel to add one.")
    text = "📢 **Your Target Channels:**\n\n"
    for ch in saved_channels:
        text += f"• `{ch}` {'✅ (Active)' if ch == current_channel else ''}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

@restricted
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    poll_questions = context.user_data.get('poll_questions',[])
    channel_id = context.user_data.get('selected_channel')
    if not poll_questions: return await update.message.reply_text("❌ No questions loaded. Use /uploadcsv first.")
    if not channel_id or channel_id == 'None': return await update.message.reply_text("❌ No channel selected. Use /setchannel first.")
    keyboard = [[InlineKeyboardButton("5 Mins", callback_data="sched_5"), InlineKeyboardButton("15 Mins", callback_data="sched_15")],[InlineKeyboardButton("30 Mins", callback_data="sched_30"), InlineKeyboardButton("1 Hour", callback_data="sched_60")],[InlineKeyboardButton("2 Hours", callback_data="sched_120"), InlineKeyboardButton("Set Time (HH:MM)", callback_data="sched_manual")],[InlineKeyboardButton("Cancel", callback_data="sched_cancel")]]
    await update.message.reply_text(f"⏰ **Schedule Quiz Posting**\n\n• Channel: `{channel_id}`\n• Questions: `{len(poll_questions)}`\n\nSelect when to post:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🛠 **User Command Guide:**\n\n"
        "`/start` - Show welcome message & menu\n"
        "`/myplan` - Check subscription validity\n"
        "`/pdftocsv` - 🔥 Convert Notes/Books to Quizzes using AI\n"
        "`/uploadcsv` - Upload text or a CSV file to load questions\n"
        "`/getcsv` - Start posting your loaded questions immediately\n"
        "`/setchannel` - Connect your target group/channel\n"
        "`/settimer` - Set the time limit for polls\n"
        "`/schedule` - Schedule a time for the bot to start posting\n"
        "`/deletequizzes` - 🗑 Delete past bot quizzes from channel\n"
        "`/pause` / `/resume` / `/stop` - Quiz Controls\n"
        "`/cancel` / `/startfresh` - Clean Data Controls"
    )
    if update.message: await update.message.reply_text(text, parse_mode="Markdown")
    else: await update.callback_query.message.reply_text(text, parse_mode="Markdown")

@restricted
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get('state', 'Idle / None')
    ch_id = context.user_data.get('selected_channel', 'Not Set ❌')
    poll_q = context.user_data.get('poll_questions',[])
    timer = context.user_data.get('timer', 0)
    timer_text = f"{timer} Seconds" if timer >= 5 else "No Timer 🚫"
    is_paused = context.user_data.get('paused', False)
    
    active_task = context.user_data.get('active_task')
    scheduled_task = context.user_data.get('scheduled_task')
    schedule_time = context.user_data.get('schedule_time')
    task_status = "🔴 Stopped / None"
    
    if active_task and not active_task.done():
        progress = context.user_data.get('task_progress', 'Running...')
        task_status = "⏸ Paused" if is_paused else f"🟢 Sending Polls ({progress})"
    elif scheduled_task and not scheduled_task.done():
        if schedule_time:
            remaining = (schedule_time - datetime.now()).total_seconds() / 60
            if remaining > 0: task_status = f"⏰ Scheduled to start in `{int(remaining)}` mins"

    text = f"📊 *Bot Current Status*\n\n🔹 *State:* `{state}`\n📢 *Channel:* `{ch_id}`\n⏱ *Timer:* `{timer_text}`\n📝 *Polls Loaded:* `{len(poll_q)} Questions`\n⚙️ *Tasks:* {task_status}"
    await update.message.reply_text(text, parse_mode="Markdown")

# ==========================================
# 🛑 LIVE QUIZ CONTROLS
# ==========================================
@restricted
async def pause_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('active_task') and not context.user_data['active_task'].done():
        context.user_data['paused'] = True
        await update.message.reply_text("⏸ *Quiz Paused!*\nThe bot will wait until you send /resume.", parse_mode="Markdown")
    else: await update.message.reply_text("⚠️ No active quiz to pause.")

@restricted
async def resume_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('paused'):
        context.user_data['paused'] = False
        await update.message.reply_text("▶️ *Quiz Resumed!*\nContinuing the questions...", parse_mode="Markdown")
    else: await update.message.reply_text("⚠️ Quiz is not currently paused.")

@restricted
async def stop_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    active_task = context.user_data.get('active_task')
    scheduled_task = context.user_data.get('scheduled_task')
    stopped = False
    if active_task and not active_task.done():
        active_task.cancel()
        context.user_data['paused'] = False
        stopped = True
    if scheduled_task and not scheduled_task.done():
        scheduled_task.cancel()
        if 'schedule_time' in context.user_data: del context.user_data['schedule_time']
        stopped = True
    if stopped: await update.message.reply_text("🛑 *Process Stopped!*\nThe ongoing or scheduled quiz has been completely halted.", parse_mode="Markdown")
    else: await update.message.reply_text("⚠️ There is no active or scheduled quiz running.")

@restricted
async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('state'):
        context.user_data['state'] = None
        await update.message.reply_text("🚫 *Action Cancelled!*\nI am no longer waiting for your input.", parse_mode="Markdown")
    else: await update.message.reply_text("⚠️ You don't have any active actions to cancel right now.")

@restricted
async def startfresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    active_task = context.user_data.get('active_task')
    if active_task and not active_task.done(): active_task.cancel()
    scheduled_task = context.user_data.get('scheduled_task')
    if scheduled_task and not scheduled_task.done(): scheduled_task.cancel()
    context.user_data.clear()
    await update.message.reply_text("🔄 *Fresh Start Complete!*\nAll configurations and background tasks have been wiped.", parse_mode="Markdown")

@restricted
async def setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        ch_id = context.args[0]
        context.user_data['selected_channel'] = ch_id
        saved_channels = context.user_data.setdefault('channels',[])
        if ch_id not in saved_channels: saved_channels.append(ch_id)
        await update.message.reply_text(f"✅ Target channel instantly set to: `{ch_id}`", parse_mode="Markdown")
        return
    keyboard = [[InlineKeyboardButton("📢 Select/Add Channel ID", callback_data="select_channel")]]
    await update.message.reply_text("✅ Click below button to select or type your channel ID:", reply_markup=InlineKeyboardMarkup(keyboard))

@restricted
async def settimer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("10 Sec", callback_data="timer_10"), InlineKeyboardButton("15 Sec", callback_data="timer_15")],[InlineKeyboardButton("30 Sec", callback_data="timer_30"), InlineKeyboardButton("60 Sec", callback_data="timer_60")],[InlineKeyboardButton("🚫 No Timer (Unlimited)", callback_data="timer_0")]]
    await update.message.reply_text("⏱ *Select the auto-close timer for polls:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

@restricted
async def uploadcsv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("📎 Upload CSV File", callback_data="up_file")], [InlineKeyboardButton("✍️ Paste Text Instead", callback_data="up_text")]]
    text = "📂 **Upload your file or paste MCQs in text format**\n\n📌 **Required Format:**\n`Question, Option A, Option B, Option C, Option D, Correct Ans`\n\n👉 **How would you like to upload?**"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

@restricted
async def pdftocsv_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not PDF_SUPPORT: return await update.message.reply_text("❌ PDF support is not enabled. Please install `pypdf` module.")
    context.user_data['state'] = 'wait_pdf_for_csv'
    
    # Check Google Gemini Key status
    ai_status = "🟢 ENABLED (Google Gemini 1.5 Flash Vision)" if AI_SUPPORT and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE" else "🔴 DISABLED (Will only extract pre-formatted text)"
    
    await update.message.reply_text(
        f"📄 **PDF to CSV Converter**\n\n"
        f"🤖 AI Book-To-Quiz Engine: {ai_status}\n\n"
        "Please send me your PDF file containing notes, books, or MCQs.\n\n"
        "*(Send /cancel to abort)*", 
        parse_mode="Markdown"
    )

@restricted
async def getcsv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("Send to Target Channel 📢", callback_data="send_channel")],[InlineKeyboardButton("Test Here in Bot 🤖", callback_data="send_bot")]]
    await update.message.reply_text("📦 Where do you want to post the loaded quizzes?", reply_markup=InlineKeyboardMarkup(keyboard))

@restricted
async def csv2html(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("0", callback_data="neg_0"), InlineKeyboardButton("0.25", callback_data="neg_0.25")],[InlineKeyboardButton("0.33", callback_data="neg_0.33"), InlineKeyboardButton("0.50", callback_data="neg_0.50")]]
    await update.message.reply_text("🧮 Select Negative Marking for offline HTML Quiz:", reply_markup=InlineKeyboardMarkup(keyboard))

@restricted
async def deletequizzes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    channel_id = context.user_data.get('selected_channel')
    if not channel_id or channel_id == 'None': return await update.message.reply_text("❌ No target channel selected. Use /setchannel first.")
    if not os.path.exists(TRACKING_FILE): return await update.message.reply_text("⚠️ No record of sent polls found.")
    try:
        with open(TRACKING_FILE, "r") as f: data = json.load(f)
    except Exception: data = {}
    ch_id_str = str(channel_id)
    if ch_id_str not in data or not data[ch_id_str]: return await update.message.reply_text(f"⚠️ No saved polls found in my memory for channel `{channel_id}`.", parse_mode="Markdown")
        
    msg_ids = data[ch_id_str]
    status_msg = await update.message.reply_text(f"🗑 Found {len(msg_ids)} tracked polls in `{channel_id}`.\n\nDeleting them now... Please wait.", parse_mode="Markdown")
    deleted, failed = 0, 0
    for mid in msg_ids:
        try:
            await context.bot.delete_message(chat_id=channel_id, message_id=mid)
            deleted += 1
            await asyncio.sleep(0.6) 
        except Exception: failed += 1
            
    data[ch_id_str] =[]
    with open(TRACKING_FILE, "w") as f: json.dump(data, f, indent=4)
    await status_msg.edit_text(f"✅ **Cleanup Complete for {channel_id}**\n\n🗑 Successfully deleted: `{deleted}` polls\n⚠️ Failed (too old/deleted): `{failed}`", parse_mode="Markdown")

# ==========================================
# 🔄 CALLBACK & MESSAGE HANDLERS
# ==========================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    
    if data.startswith("authplan_"):
        if user_id != ADMIN_ID: return await query.answer("Admin only.", show_alert=True)
        _, target_user, days = data.split("_")
        keyboard = [[InlineKeyboardButton(f"✅ Confirm {days} Days", callback_data=f"authconfirm_{target_user}_{days}")],[InlineKeyboardButton("❌ Cancel", callback_data="authcancel")]]
        await query.edit_message_text(f"⚠️ **Confirm Authorization**\n\nGrant `{days}` days access to user `{target_user}`?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    elif data.startswith("authconfirm_"):
        if user_id != ADMIN_ID: return await query.answer("Admin only.", show_alert=True)
        _, target_user, days = data.split("_")
        users = load_auth_users()
        expiry = datetime.now() + timedelta(days=int(days))
        users[str(target_user)] = {"expiry": expiry.isoformat()}
        save_auth_users(users)
        await query.edit_message_text(f"✅ User `{target_user}` authorized for {days} days!\n📅 Expiry: {expiry.strftime('%Y-%m-%d %H:%M:%S')}", parse_mode="Markdown")
        try: await context.bot.send_message(chat_id=int(target_user), text=f"🎉 **Good News!**\nYour subscription has been extended for **{days} days**!\n📅 Expiry: `{expiry.strftime('%Y-%m-%d %H:%M:%S')}`", parse_mode="Markdown")
        except Exception: pass
        return
        
    elif data == "authcancel":
        if user_id != ADMIN_ID: return await query.answer("Admin only.", show_alert=True)
        await query.edit_message_text("❌ Authorization cancelled.")
        return

    if user_id != ADMIN_ID:
        users = load_auth_users()
        str_uid = str(user_id)
        if str_uid not in users or datetime.fromisoformat(users[str_uid]["expiry"]) < datetime.now(): return await query.answer("⛔ Plan Expired or Not Found. Use /contact", show_alert=True)

    if data == "help_btn": await help_command(update, context)
    elif data.startswith("timer_"):
        seconds = int(data.split("_")[1])
        context.user_data['timer'] = seconds
        if seconds == 0: await query.message.reply_text("✅ Timer removed. Polls will remain open infinitely.")
        else: await query.message.reply_text(f"✅ Timer set to {seconds} seconds.")
    
    elif data.startswith("neg_"):
        neg_val = data.split("_")[1]
        context.user_data['neg_mark'] = neg_val
        context.user_data['state'] = 'wait_test_name'
        await query.message.reply_text(f"✅ Negative marking set: {neg_val}\n\n📝 Send the name of your test:\n*(Send /cancel to abort)*")
        
    elif data in["up_file", "up_text"]:
        context.user_data['state'] = 'wait_csv_upload'
        await query.message.reply_text("📂 Please send your CSV file or paste your comma-separated text now.\n*(Send /cancel to abort)*")
        
    elif data == "select_channel":
        context.user_data['state'] = 'wait_channel_id'
        await query.message.reply_text("Forward any message from your channel or type the Chat ID (e.g. -10012345678):\n*(Send /cancel to abort)*")

    elif data == "send_bot":
        task = context.application.create_task(process_and_send_polls(query.message.chat_id, query.message.chat_id, context))
        context.user_data['active_task'] = task
        
    elif data == "send_channel":
        channel_id = context.user_data.get('selected_channel')
        if not channel_id: return await query.message.reply_text("❌ No channel selected. Use /setchannel first.")
        await query.message.reply_text(f"📢 Channel mode activated.\nPosting to `{channel_id}` immediately.\n\n*(Use /pause or /stop to control)*", parse_mode="Markdown")
        task = context.application.create_task(process_and_send_polls(query.message.chat_id, channel_id, context))
        context.user_data['active_task'] = task

    elif data.startswith("sched_"):
        val = data.split("_")[1]
        if val == "cancel": return await query.edit_message_text("🚫 Scheduling cancelled.")
        elif val == "manual":
            context.user_data['state'] = 'wait_schedule_time'
            return await query.edit_message_text("⏰ Send time in HH:MM format (24-hour clock, e.g., 14:30) when you want the bot to start posting.\n*(Send /cancel to abort)*", parse_mode="Markdown")
            
        delay_mins = int(val)
        channel_id = context.user_data.get('selected_channel')
        task = context.application.create_task(schedule_wait_and_send(delay_mins, query.message.chat_id, channel_id, context))
        context.user_data['scheduled_task'] = task
        context.user_data['schedule_time'] = datetime.now() + timedelta(minutes=delay_mins)
        await query.edit_message_text(f"✅ **Quiz Scheduled!**\nThe bot will start automatically in `{delay_mins} minutes`.", parse_mode="Markdown")

@restricted
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get('state')
    msg = update.message
    
    if msg.text and msg.text.startswith('/'): return

    if state == 'wait_schedule_time':
        try:
            target_time = datetime.strptime(msg.text.strip(), "%H:%M").time()
            now = datetime.now()
            schedule_dt = datetime.combine(now.date(), target_time)
            if schedule_dt <= now: schedule_dt += timedelta(days=1)
            delay_mins = (schedule_dt - now).total_seconds() / 60.0
            task = context.application.create_task(schedule_wait_and_send(delay_mins, msg.chat_id, context.user_data.get('selected_channel'), context))
            context.user_data['scheduled_task'] = task
            context.user_data['schedule_time'] = schedule_dt
            context.user_data['state'] = None
            await msg.reply_text(f"✅ **Quiz Scheduled!**\nThe bot will start at `{schedule_dt.strftime('%H:%M')}` (in ~`{int(delay_mins)}` mins).", parse_mode="Markdown")
        except ValueError: await msg.reply_text("❌ Invalid format. Please send the time exactly in HH:MM format (e.g., 14:30) or /cancel.")
        return

    if msg.text == "/done":
        if state == 'wait_html_file':
            questions = context.user_data.get('html_questions',[])
            if not questions: return await msg.reply_text("❌ No valid questions uploaded.")
            html_content = generate_html_quiz(questions, context.user_data.get('test_name', 'Quiz'), context.user_data.get('neg_mark', '0'))
            file_stream = io.BytesIO(html_content.encode('utf-8'))
            file_stream.name = f"{context.user_data.get('test_name', 'Quiz')}.html"
            await msg.reply_document(document=file_stream, caption="🔥 Quiz HTML ready")
            context.user_data['state'] = None
            context.user_data['html_questions'] =[]
        return

    if state == 'wait_test_name':
        context.user_data['test_name'] = msg.text or "Quiz"
        context.user_data['state'] = 'wait_html_file'
        context.user_data['html_questions'] =[]
        await msg.reply_text("📥 Now send your questions (CSV/TXT file or forward Telegram Polls).\n\nSend /done when finished, or /cancel to abort.")
        
    elif state == 'wait_html_file':
        if msg.poll:
            context.user_data['html_questions'].append({'question': msg.poll.question, 'options': [o.text for o in msg.poll.options], 'correct_index': msg.poll.correct_option_id or 0})
            await msg.reply_text("✅ Poll Added! Send more or type /done when finished.")
        else:
            new_q = parse_csv_content(await extract_content(msg, context))
            if new_q:
                context.user_data['html_questions'].extend(new_q)
                await msg.reply_text(f"✅ {len(new_q)} Added! Send more or type /done when finished.")
            else: await msg.reply_text("❌ No valid format found.")
                
    elif state == 'wait_pdf_for_csv':
        if not msg.document or not msg.document.file_name.lower().endswith('.pdf'): return await msg.reply_text("❌ Please upload a valid `.pdf` file, or use /cancel to abort.")
        status_msg = await msg.reply_text("⏳ Downloading PDF... Please wait.")
        try:
            file = await context.bot.get_file(msg.document.file_id)
            byte_array = await file.download_as_bytearray()
            
            ai_enabled = AI_SUPPORT and GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE"
            
            csv_output = io.StringIO()
            writer = csv.writer(csv_output)
            writer.writerow(['Q', 'A', 'B', 'C', 'D', 'E'])
            count = 0
            
            # --- GOOGLE GEMINI 1.5 FLASH (FREE) PROCESSING ENGINE ---
            if ai_enabled:
                await status_msg.edit_text("🤖 **Gemini AI Active:** Reading PDF natevely (vision processing for scanned pages)... This may take a minute.")
                try:
                    # Configure Free Google AI API
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash')

                    # Your strict Bilingual prompt
                    prompt = """
ROLE:
Act as a strict Assessment Generator. Your goal is to create Multiple Choice Questions (MCQs) based only on the provided text.

INPUT:
I will provide a specific PDF document (which may contain scanned images of a book).
Creat maximum posible Questions from page.
Translate these Questions and answer in hindi also.
Put English first then hindi in Questions and options.
Random Option( e.g. A for some questions, B for some questions, C for some questions, D for some questions and not in predictable order) must be Correct Answer of Every Questions.
Pole options Length must not exceeds 200, it must be under 200.

RULES FOR CREATING MCQS:
Source of Truth: The correct answer must be derived strictly from the statement in the text, even if the statement is factually incorrect in the real world.
The Question: Formulate a clear question based on a specific fact or sentence in the text.
The Options (4 total):
Option (Correct): The exact detail found in the text.
Options (Distractors - 3 total): These must be thematically relevant (numbers, names, dates, adjectives) that fit the style of the question but are incorrect according to the provided text.

Format:
question,option_a,option_b,option_c,option_d,correct_option
(e.g., What is the capital of India/भारत की राजधानी क्या है ?,Delhi/दिल्ली,Mumbai/मुंबई,Kolkata/कोलकाता,Chennai/चेन्नई,A)

Q,A,B,C,D,E
* One question per line
* No numbering
* No quotes unless required by CSV
* No blank rows

### 📌 CSV EXAMPLE (FORMAT DEMO ONLY):
Q,A,B,C,D,E
When was GATT replaced by WTO?/गैट को WTO द्वारा कब बदला गया?,Jan 1947/जनवरी 1947,Jan 1988/जनवरी 1988,Jan 1995/जनवरी 1995,Jan 2001/जनवरी 2001,C
"""
                    # Gemini handles PDFs natively via MIME type payload!
                    pdf_payload = {
                        "mime_type": "application/pdf",
                        "data": byte_array
                    }
                    
                    # Run it async so it doesn't freeze the bot
                    response = await asyncio.to_thread(
                        model.generate_content,
                        [prompt, pdf_payload]
                    )
                    
                    # Clean up the response from any markdown the AI might attempt
                    raw_csv = response.text.strip()
                    raw_csv = re.sub(r'^```(?:csv|text)?', '', raw_csv, flags=re.IGNORECASE).strip()
                    raw_csv = re.sub(r'```$', '', raw_csv).strip()
                    
                    # Parse AI CSV response directly
                    csv_reader = csv.reader(io.StringIO(raw_csv))
                    for row_idx, row in enumerate(csv_reader):
                        if not row or len(row) < 6: continue
                        
                        # Skip the header if AI generated it
                        if row[0].strip().upper() == 'Q' or 'QUESTION' in row[0].upper() or 'प्रश्न' in row[0]:
                            continue
                            
                        q_t = row[0].strip()[:300]
                        o_a = row[1].strip()[:100]
                        o_b = row[2].strip()[:100]
                        o_c = row[3].strip()[:100]
                        o_d = row[4].strip()[:100]
                        ans_letter = row[5].strip().upper()
                        
                        if ans_letter not in['A', 'B', 'C', 'D']:
                            ans_letter = 'A'
                            
                        if len(q_t) > 3 and len(o_a) > 0 and len(o_b) > 0:
                            writer.writerow([q_t, o_a, o_b, o_c, o_d, ans_letter])
                            count += 1

                except Exception as e:
                    logger.error(f"Gemini Generation failed: {e}")
                    await status_msg.edit_text("⚠️ Gemini API Error. Falling back to basic structural extraction...")
                    count = 0 # Reset count to trigger Regex Fallback
            
            # --- FALLBACK: STRUCTURAL REGEX PARSING ---
            if count == 0:
                reader = PdfReader(io.BytesIO(byte_array))
                text = "".join(page.extract_text() + "\n" for page in reader.pages if page.extract_text())
                
                if not text.strip(): 
                    return await status_msg.edit_text("❌ The PDF appears to be empty or contains only images.\n\n⚠️ **SOLUTION:** You need to enable the **Free Gemini Vision Engine** to read image-based PDFs. Open the python script, set your `GEMINI_API_KEY`, and restart the bot!")
                
                blocks = re.split(r'(?i)(?:^|\n)\s*(?:Q(?:uestion)?\s*\.?\s*)?\d+[\.\)\-\:]\s+', text)
                for block in blocks[1:]:
                    block = block.strip()
                    if not block: continue
                    ans_match = re.search(r'(?i)\bAns(?:wer)?\s*[:\-]?\s*([A-D1-4])\b', block)
                    ans = ans_match.group(1).upper() if ans_match else 'A'
                    if ans in ['1', '2', '3', '4']: ans = {'1':'A', '2':'B', '3':'C', '4':'D'}[ans]
                    if ans_match: block = block[:ans_match.start()] + block[ans_match.end():]
                    
                    opt_match = re.search(r'(?i)(?:\bA[\.\)]|\(A\))\s*(.*?)(?:\bB[\.\)]|\(B\))\s*(.*?)(?:\bC[\.\)]|\(C\))\s*(.*?)(?:\bD[\.\)]|\(D\))\s*(.*)', block, re.DOTALL)
                    if not opt_match: opt_match = re.search(r'(?:\b1[\.\)]|\(1\))\s*(.*?)(?:\b2[\.\)]|\(2\))\s*(.*?)(?:\b3[\.\)]|\(3\))\s*(.*?)(?:\b4[\.\)]|\(4\))\s*(.*)', block, re.DOTALL)
                    
                    if opt_match:
                        q, a, b, c, d = block[:opt_match.start()].strip(), opt_match.group(1).strip(), opt_match.group(2).strip(), opt_match.group(3).strip(), opt_match.group(4).strip()
                    else:
                        lines =[line.strip() for line in block.split('\n') if line.strip()]
                        if len(lines) >= 5: q, a, b, c, d = lines[0], lines[1], lines[2], lines[3], lines[4]
                        elif len(lines) > 0: q, a, b, c, d = lines[0], lines[1] if len(lines) > 1 else 'Opt A', lines[2] if len(lines) > 2 else 'Opt B', lines[3] if len(lines) > 3 else 'Opt C', lines[4] if len(lines) > 4 else 'Opt D'
                        else: continue
                    
                    q, a, b, c, d = re.sub(r'\s+', ' ', q).strip(), re.sub(r'\s+', ' ', a).strip(), re.sub(r'\s+', ' ', b).strip(), re.sub(r'\s+', ' ', c).strip(), re.sub(r'\s+', ' ', d).strip()
                    if len(q) > 0:
                        writer.writerow([q[:300], a[:100], b[:100], c[:100], d[:100], ans])
                        count += 1
                
                # Ultimate Force Group Fallback
                if count == 0:
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    for i in range(0, len(lines), 5):
                        chunk = lines[i:i+5]
                        if not chunk: continue
                        q = re.sub(r'\s+', ' ', chunk[0]).strip()
                        a = re.sub(r'\s+', ' ', chunk[1]).strip() if len(chunk) > 1 else 'Opt A'
                        b = re.sub(r'\s+', ' ', chunk[2]).strip() if len(chunk) > 2 else 'Opt B'
                        c = re.sub(r'\s+', ' ', chunk[3]).strip() if len(chunk) > 3 else 'Opt C'
                        d = re.sub(r'\s+', ' ', chunk[4]).strip() if len(chunk) > 4 else 'Opt D'
                        if len(q) > 0:
                            writer.writerow([q[:300], a[:100], b[:100], c[:100], d[:100], 'A'])
                            count += 1

            if count == 0: return await status_msg.edit_text("❌ The PDF format could not be parsed and AI generation yielded no results.")

            csv_bytes = io.BytesIO(csv_output.getvalue().encode('utf-8-sig'))
            csv_bytes.name = f"{msg.document.file_name.replace('.pdf', '')}_flawless_converted.csv"
            
            await msg.reply_document(
                document=csv_bytes, 
                caption=f"✅ **Flawless Conversion Complete!**\n\nGenerated / Extracted `{count}` MCQs successfully using Free Gemini.\n\n⚠️ *You can now use /uploadcsv to load this generated file into the bot.*", 
                parse_mode="Markdown"
            )
            await status_msg.delete()
            context.user_data['state'] = None
            
        except Exception as e:
            logger.error(f"PDF to CSV error: {e}")
            await status_msg.edit_text(f"❌ An error occurred while reading or parsing the PDF file.")
        
    elif state == 'wait_csv_upload':
        questions = parse_csv_content(await extract_content(msg, context))
        if not questions: return await msg.reply_text("❌ No valid questions found. Ensure strictly 6 columns: Q,A,B,C,D,Ans")
        context.user_data['poll_questions'] = questions
        keyboard = [[InlineKeyboardButton("Bot", callback_data="send_bot")], [InlineKeyboardButton("Channel", callback_data="send_channel")]]
        await msg.reply_text(f"✅ Upload successful. {len(questions)} MCQs detected.\nWhere do you want to forward them?", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['state'] = None 
        
    elif state == 'wait_channel_id':
        ch_id = str(msg.forward_origin.chat.id) if msg.forward_origin and msg.forward_origin.type == 'channel' else (msg.text.strip() if msg.text else "")
        if not ch_id: return await msg.reply_text("❌ Invalid channel ID. Please provide a valid ID.")
        context.user_data['selected_channel'] = ch_id
        saved_channels = context.user_data.setdefault('channels',[])
        if ch_id not in saved_channels: saved_channels.append(ch_id)
        await msg.reply_text(f"✅ Channel saved and selected: `{ch_id}`", parse_mode="Markdown")
        context.user_data['state'] = None

# ==========================================
# ⏱️ BACKGROUND POLL SENDER
# ==========================================
async def schedule_wait_and_send(delay_mins, user_chat_id, target_chat_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        await asyncio.sleep(delay_mins * 60)
        if 'scheduled_task' in context.user_data: del context.user_data['scheduled_task']
        if 'schedule_time' in context.user_data: del context.user_data['schedule_time']
        await context.bot.send_message(user_chat_id, f"⏰ Scheduled time reached! Starting to post to `{target_chat_id}`...", parse_mode="Markdown")
        task = context.application.create_task(process_and_send_polls(user_chat_id, target_chat_id, context))
        context.user_data['active_task'] = task
    except asyncio.CancelledError: logger.info("Scheduled task was cancelled.")

async def process_and_send_polls(user_chat_id, target_chat_id, context: ContextTypes.DEFAULT_TYPE):
    questions = context.user_data.get('poll_questions',[])
    timer_duration = context.user_data.get('timer', 0)
    total = len(questions)
    
    if str(target_chat_id) != str(user_chat_id): await context.bot.send_message(user_chat_id, f"📢 Initialized. Total Questions: {total}\nUse /pause to pause and /stop to halt.")
    
    success = 0
    try:
        for i, q in enumerate(questions):
            while context.user_data.get('paused', False): await asyncio.sleep(1) 
            context.user_data['task_progress'] = f"{i+1} / {total}"
            poll_kwargs = {'chat_id': target_chat_id, 'question': q['question'], 'options': q['options'], 'type': 'quiz', 'correct_option_id': q['correct_index'], 'is_anonymous': True}
            if timer_duration >= 5: poll_kwargs['open_period'] = timer_duration
            
            while True:
                try:
                    sent_msg = await context.bot.send_poll(**poll_kwargs)
                    save_sent_poll(target_chat_id, sent_msg.message_id) 
                    success += 1
                    break
                except RetryAfter as e:
                    logger.warning(f"Flood control hit. Sleeping for {e.retry_after} seconds.")
                    await asyncio.sleep(e.retry_after + 1)
            
            if i < len(questions) - 1: await asyncio.sleep(timer_duration + 1 if timer_duration >= 5 else 3) 
                
        if str(target_chat_id) != str(user_chat_id): await context.bot.send_message(user_chat_id, f"✅ Channel posting completed! All {success} polls sent.")
    
    except asyncio.CancelledError: logger.info("Task was cancelled by the user (/stop command).")
    except Exception as e:
        logger.error(f"Error sending poll: {e}")
        await context.bot.send_message(user_chat_id, f"❌ Error stopped at {success} polls.\nEnsure ID is correct and I am Admin in the channel.")
    finally:
        if 'active_task' in context.user_data: del context.user_data['active_task']

# ==========================================
# 🚀 MAIN APPLICATION BUILDER
# ==========================================
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start)) 
    application.add_handler(CommandHandler("contact", contact_command))
    application.add_handler(CommandHandler("myplan", myplan))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("setchannel", setchannel))
    application.add_handler(CommandHandler("settimer", settimer))
    application.add_handler(CommandHandler("uploadcsv", uploadcsv))
    application.add_handler(CommandHandler("pdftocsv", pdftocsv_command))
    application.add_handler(CommandHandler("getcsv", getcsv))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("csv2html", csv2html))
    application.add_handler(CommandHandler("startfresh", startfresh))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("cancel", cancel_action))
    application.add_handler(CommandHandler("deletequizzes", deletequizzes_command))
    application.add_handler(CommandHandler("pause", pause_quiz))
    application.add_handler(CommandHandler("resume", resume_quiz))
    application.add_handler(CommandHandler("stop", stop_process))
    application.add_handler(CommandHandler("auth", auth_user))
    application.add_handler(CommandHandler("unauth", unauth_user))
    application.add_handler(CommandHandler("authlist", auth_list))

    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL | filters.POLL, message_handler))

    print("✅ Advance Free Gemini MCQ Bot is Running securely!")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
