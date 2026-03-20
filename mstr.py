import os
import re
import csv
import io
import json
import asyncio
import logging
import uuid
import random
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

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# ⚙️ CONFIGURATION - YOUR CREDENTIALS
# ==========================================
TELEGRAM_BOT_TOKEN = "8689120822:AAHM4aCXJZ_y2hufeEOD03sZePu3LLXU_Kg"
ADMIN_CONTACT = "@Mr_outlaw001"
ADMIN_ID = 6915757343  

AUTH_FILE = "auth_users.json"
TRACKING_FILE = "sent_polls.json"  

# ==========================================
# 🔒 AUTHORIZATION SYSTEM
# ==========================================
def load_auth_users():
    if not os.path.exists(AUTH_FILE): return {}
    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                new_data = {}
                expiry = (datetime.now() + timedelta(days=2)).isoformat()
                for uid in data: new_data[str(uid)] = {"expiry": expiry}
                save_auth_users(new_data)
                return new_data
            return data
    except Exception: return {}

def save_auth_users(users):
    with open(AUTH_FILE, "w") as f: json.dump(users, f, indent=4)

def save_sent_poll(channel_id, message_id, session_id="default", session_label="Unnamed Quiz Session"):
    data = {}
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, "r") as f: data = json.load(f)
        except Exception: pass
            
    ch_id_str = str(channel_id)
    if ch_id_str not in data: data[ch_id_str] = {}
        
    if isinstance(data[ch_id_str], list):
        old_list = data[ch_id_str]
        data[ch_id_str] = {"legacy_session": {"label": "Older Quizzes (Legacy)", "msg_ids": old_list}}
        
    if session_id not in data[ch_id_str]:
        data[ch_id_str][session_id] = {"label": session_label, "msg_ids":[]}
        
    data[ch_id_str][session_id]["msg_ids"].append(message_id)
    with open(TRACKING_FILE, "w") as f: json.dump(data, f, indent=4)

def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id == ADMIN_ID: return await func(update, context, *args, **kwargs)
            
        users = load_auth_users()
        if str(user_id) in users:
            try:
                if datetime.now() <= datetime.fromisoformat(users[str(user_id)]["expiry"]):
                    return await func(update, context, *args, **kwargs)
                else: msg = "⛔ **Your subscription has expired.**\nPlease use /contact to reach the admin to renew."
            except Exception: msg = "⛔ **Subscription data error.**\nPlease contact admin."
        else: msg = "⛔ **Access Denied.**\nYou are not authorized. Use /start to get a 2-Day Free Trial!"
            
        if update.message: await update.message.reply_text(msg, parse_mode="Markdown")
        elif update.callback_query: await update.callback_query.answer("Access Denied or Expired.", show_alert=True)
        return
    return wrapped

# ==========================================
# 📝 HELPER FUNCTIONS & TASKS
# ==========================================
def get_all_poll_questions(context: ContextTypes.DEFAULT_TYPE):
    """Flattens all question batches into a single list."""
    batches = context.user_data.get('poll_batches', [])
    return [q for batch in batches for q in batch]

def parse_date_time(text: str):
    now = datetime.now()
    text = text.strip()
    try:
        dt = datetime.strptime(text, "%d/%m/%Y %H:%M")
        if dt < now: return None
        return dt
    except ValueError: pass
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        if dt < now: return None
        return dt
    except ValueError: pass
    try:
        t = datetime.strptime(text, "%H:%M").time()
        dt = datetime.combine(now.date(), t)
        if dt <= now: dt += timedelta(days=1)
        return dt
    except ValueError: pass
    return False 

def parse_csv_content(csv_content: str):
    if csv_content.startswith('\ufeff'): csv_content = csv_content[1:]
    reader = csv.reader(io.StringIO(csv_content.strip()))
    questions =[]
    ans_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3, '1': 0, '2': 1, '3': 2, '4': 3}
    for i, row in enumerate(reader):
        if not row or len(row) < 6: continue
        if i == 0 and ('Q' in row[0].upper() or 'QUESTION' in row[0].upper() or 'प्रश्न' in row[0]): continue
        try:
            raw_ans = row[5].strip().upper()
            clean_ans = raw_ans[-1] if raw_ans else 'A'
            explanation = row[6].strip()[:200] if len(row) >= 7 and row[6].strip() else None
            questions.append({
                'question': row[0].strip()[:300], 
                'options': [row[1].strip()[:100] or 'Opt A', row[2].strip()[:100] or 'Opt B', row[3].strip()[:100] or 'Opt C', row[4].strip()[:100] or 'Opt D'],
                'correct_index': ans_map.get(clean_ans, 0),
                'explanation': explanation
            })
        except Exception: continue
    return questions

def generate_html_quiz(questions: list, title: str, negative_marking: str) -> str:
    html = f"<html><head><title>{title}</title><style>body{{font-family: Arial; padding: 20px; background: #f4f4f9;}} .q{{margin-top: 20px; font-weight: bold; font-size: 18px;}} .opt{{margin-left: 15px; font-size: 16px; padding: 5px;}} .ans{{color: green; font-weight: bold; margin-left: 15px; margin-top: 10px;}} .exp{{color: #555; font-size: 14px; margin-left: 15px; font-style: italic;}}</style></head><body>"
    html += f"<h2>🔥 Test: {title}</h2><p><b>Negative Marking:</b> {negative_marking}</p><hr>"
    for i, q in enumerate(questions):
        html += f"<div class='q'>Q{i+1}. {q['question']}</div>"
        for j, opt in enumerate(q['options']): html += f"<div class='opt'>({chr(65+j)}) {opt}</div>"
        html += f"<div class='ans'>Answer: {chr(65 + q['correct_index'])}</div>"
        if q.get('explanation'):
            html += f"<div class='exp'>Explanation: {q['explanation']}</div>"
    html += "</body></html>"
    return html

async def get_channel_selection_markup(context: ContextTypes.DEFAULT_TYPE, next_action: str) -> InlineKeyboardMarkup:
    saved_channels = context.user_data.get('channels',[])
    selected = context.user_data.get('temp_target_channels',[])
    keyboard = [[InlineKeyboardButton(f"{'✅' if ch in selected else '❌'} {ch}", callback_data=f"togglech_{ch}_{next_action}")] for ch in saved_channels]
    keyboard.append([InlineKeyboardButton("🚀 CONFIRM CHANNELS", callback_data=f"confirmch_{next_action}")])
    return InlineKeyboardMarkup(keyboard)

async def send_polls_task(context: ContextTypes.DEFAULT_TYPE, admin_chat_id: int, questions: list, target_channels: list):
    timer = context.user_data.get('timer', 0)
    topic = context.user_data.get('quiz_topic', 'Unnamed Quiz Session')
    sess_id = str(uuid.uuid4())
    
    for i, q in enumerate(questions):
        while context.user_data.get('paused', False):
            await asyncio.sleep(1)
            
        for ch in target_channels:
            try:
                msg = await context.bot.send_poll(
                    chat_id=ch,
                    question=q['question'],
                    options=q['options'],
                    type=Poll.QUIZ,
                    correct_option_id=q['correct_index'],
                    explanation=q.get('explanation'),
                    open_period=timer if timer > 0 else None,
                    is_anonymous=True
                )
                save_sent_poll(ch, msg.message_id, sess_id, topic)
            except RetryAfter as e:
                logger.warning(f"Flood control: sleeping for {e.retry_after}s")
                await asyncio.sleep(e.retry_after)
                try:
                    msg = await context.bot.send_poll(chat_id=ch, question=q['question'], options=q['options'], type=Poll.QUIZ, correct_option_id=q['correct_index'], explanation=q.get('explanation'), open_period=timer if timer > 0 else None, is_anonymous=True)
                    save_sent_poll(ch, msg.message_id, sess_id, topic)
                except Exception: pass
            except TelegramError as e:
                logger.error(f"Failed to send poll to {ch}: {e}")
                
        await asyncio.sleep(2)

    await context.bot.send_message(chat_id=admin_chat_id, text="✅ **Quiz Posting Completed Successfully!**", parse_mode="Markdown")

async def post_init(application: Application) -> None:
    commands =[
        BotCommand("start", "Show welcome message & menu"),
        BotCommand("guide", "📖 Detailed Guide for all commands"),
        BotCommand("contact", "Contact the Admin"),
        BotCommand("myplan", "Check subscription validity"),
        BotCommand("channels", "View list of target channels"),
        BotCommand("setchannel", "Add target channels (Multiple allowed)"),
        BotCommand("removechannel", "Remove a saved channel"),
        BotCommand("uploadcsv", "Upload CSVs to generate MCQs"),
        BotCommand("shuffle", "🔀 Randomize the order of loaded questions"),
        BotCommand("clearcsv", "🗑 Clear currently loaded questions"),
        BotCommand("pdftocsv", "Convert PDF to CSV via Free AI"),
        BotCommand("settopic", "📚 Set Quiz Topic (For session memory)"),
        BotCommand("settimer", "Set the auto-close timer for polls"),
        BotCommand("getcsv", "Send quizzes immediately"),
        BotCommand("schedule", "Schedule Date/Time for Quiz posting"),
        BotCommand("schedulepost", "📨 Schedule any Custom Message / Photo"),
        BotCommand("cancelposts", "🚫 Cancel all Custom Scheduled Messages"),
        BotCommand("csv2html", "Live offline HTML test from CSV"),
        BotCommand("status", "Check ongoing processes & loaded data"),
        BotCommand("deletequizzes", "🗑 Delete past bot quizzes & memory"),
        BotCommand("pause", "⏸ Pause the ongoing quiz"),
        BotCommand("resume", "▶️ Resume the paused quiz"),
        BotCommand("stop", "🛑 Instantly stop sending ongoing polls"),
        BotCommand("cancel", "🚫 Cancel waiting for files/input"),
        BotCommand("startfresh", "🔄 Wipe all configurations & reset bot")
    ]
    await application.bot.set_my_commands(commands)
    
    # 🔔 Send Startup Notification to Admin
    try:
        await application.bot.send_message(
            chat_id=ADMIN_ID,
            text="✅ **Bot started successfully!**\nAll systems are online.",
            parse_mode="Markdown"
        )
        print("✅ Startup message successfully sent to Admin!")
    except Exception as e:
        print(f"⚠️ Could not send startup message to Admin (Did you /start the bot first?): {e}")

# ==========================================
# 👑 ADMIN COMMANDS
# ==========================================
async def auth_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("⛔ Only the main Admin can use this command.")
    if not context.args: return await update.message.reply_text("⚠️ Please provide a User ID.\nExample: `/auth 987654321`", parse_mode="Markdown")
    try:
        new_user = int(context.args[0])
        keyboard = [[InlineKeyboardButton("30 Days", callback_data=f"authplan_{new_user}_30"), InlineKeyboardButton("100 Days", callback_data=f"authplan_{new_user}_100")]]
        await update.message.reply_text(f"⚙️ Choose plan validity for user `{new_user}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except ValueError: await update.message.reply_text("❌ Invalid ID. Must be a number.")

async def unauth_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("⛔ Only the main Admin can use this command.")
    if not context.args: return await update.message.reply_text("⚠️ Please provide a User ID.")
    del_user = str(context.args[0])
    users = load_auth_users()
    if del_user in users:
        users[del_user]["expiry"] = "2000-01-01T00:00:00"
        save_auth_users(users)
        await update.message.reply_text(f"✅ User `{del_user}` access revoked forever (Expired).", parse_mode="Markdown")
    else: 
        await update.message.reply_text("⚠️ User is not in the authorized list.")

async def auth_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("⛔ Only the main Admin can use this command.")
    users = load_auth_users()
    if not users: return await update.message.reply_text("📋 No users are currently authorized.")
    user_str =[]
    now = datetime.now()
    for uid, data in users.items():
        try:
            exp = datetime.fromisoformat(data["expiry"])
            status = "✅" if exp > now else "❌ Expired"
            user_str.append(f"• `{uid}` - Exp: {exp.strftime('%Y-%m-%d')} ({status})")
        except Exception: user_str.append(f"• `{uid}` - Error parsing date")
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

    keyboard = [[InlineKeyboardButton("📖 Open Setup Guide", callback_data="help_main_menu")],[InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_CONTACT.replace('@', '')}")]]
    text = "🤖 **WELCOME TO MCQ MASTER BOT!**\n\n"
    if trial_given: text += "🎉 **You have been granted a 2-Day Free Trial!**\n\n"
    elif expired: text += "⚠️ **Your subscription has EXPIRED.**\nYou can view menus, but cannot execute commands. Use /contact to renew.\n\n"
    else: text += "✨ **Welcome back! Your subscription is ACTIVE.**\n\n"
            
    text += (
        "✦ I automatically convert your CSV files into Telegram Quiz Polls.\n"
        "✦ **Multi-Channel:** Connect multiple channels and post to them simultaneously.\n"
        "✦ **Schedule Magic:** Setup Custom Messages & Quizzes with Date/Time scheduling.\n\n"
        "🔰 **Need Help?** Click the Guide button below!\n\n"
        f"• MAINTAINER: `{ADMIN_CONTACT}`"
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"📞 **Contact Administration**\n\n👤 **Username:** `{ADMIN_CONTACT}`\n🔗 **Link:** [Click here](https://t.me/{ADMIN_CONTACT.replace('@', '')})", parse_mode="Markdown", disable_web_page_preview=True)

@restricted
async def myplan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id == ADMIN_ID: return await update.message.reply_text("👑 **Admin Account**\nYou have unlimited lifetime access.", parse_mode="Markdown")
    users = load_auth_users()
    str_uid = str(update.effective_user.id)
    if str_uid in users:
        expiry = datetime.fromisoformat(users[str_uid]["expiry"])
        now = datetime.now()
        if expiry > now:
            delta = expiry - now
            await update.message.reply_text(f"✅ **Active Plan**\n\n⏳ Remaining: `{delta.days} days, {delta.seconds // 3600} hours`\n📅 Expiry: `{expiry.strftime('%Y-%m-%d %H:%M:%S')}`", parse_mode="Markdown")
        else: await update.message.reply_text("⛔ **Your plan has expired.**", parse_mode="Markdown")
    else: await update.message.reply_text("❓ You don't have an active plan.")

@restricted
async def setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    saved_channels = context.user_data.setdefault('channels',[])
    if context.args:
        added =[]
        for ch_id in context.args:
            if ch_id not in saved_channels:
                saved_channels.append(ch_id)
                added.append(ch_id)
        if added: 
            await update.message.reply_text(f"✅ Saved target channels:\n`{'`, `'.join(added)}`", parse_mode="Markdown")
        else: 
            await update.message.reply_text("⚠️ Channel(s) already exist in your list.")
        return
    context.user_data['state'] = 'wait_channel_id'
    await update.message.reply_text("✏️ **Add Channels Interactively**\n\nPlease enter the Channel / Group / Chat ID(s).\nYou can send one or multiple separated by space or commas.\n*(Example: @MyChannel, -100123456789)*\n\n*(Send /cancel to abort)*", parse_mode="Markdown")

@restricted
async def removechannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    saved_channels = context.user_data.get('channels',[])
    if not context.args: return await update.message.reply_text("⚠️ Usage: `/removechannel <channel_id>`\nUse `/channels` to see your list.", parse_mode="Markdown")
    ch_id = context.args[0]
    if ch_id in saved_channels:
        saved_channels.remove(ch_id)
        await update.message.reply_text(f"✅ Removed `{ch_id}` from saved channels.", parse_mode="Markdown")
    else: await update.message.reply_text("❌ Channel not found in your list.")

@restricted
async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    saved_channels = context.user_data.get('channels',[])
    if not saved_channels: return await update.message.reply_text("❌ No target channels saved yet. Use /setchannel to add.")
    text = "📢 **Your Saved Target Channels:**\n\n" + "\n".join([f"{idx}. `{ch}`" for idx, ch in enumerate(saved_channels, 1)])
    text += "\n\n*(Use /removechannel <id> to delete a channel)*"
    await update.message.reply_text(text, parse_mode="Markdown")

@restricted
async def settopic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        topic = " ".join(context.args)
        context.user_data['quiz_topic'] = topic
        await update.message.reply_text(f"✅ Quiz topic set to: `{topic}`\nIt will group your next quiz in /deletequizzes memory.", parse_mode="Markdown")
    else:
        context.user_data['state'] = 'wait_quiz_topic'
        await update.message.reply_text("📝 **Set Quiz Topic**\n\nPlease send the topic/title for your upcoming quiz.\n*(Send /cancel to abort)*", parse_mode="Markdown")

@restricted
async def schedulepost_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get('channels',[]): return await update.message.reply_text("❌ No target channels saved. Use /setchannel first.")
    context.user_data['state'] = 'wait_schedule_post_text'
    await update.message.reply_text("📝 **Schedule a Custom Message**\n\nPlease send the text, photo, or document you want to schedule.\n*(I will clone and send exactly what you provide)*\n\n*(Send /cancel to abort)*", parse_mode="Markdown")

@restricted
async def cancelposts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    posts = context.user_data.get('scheduled_custom_posts',[])
    if not posts: return await update.message.reply_text("⚠️ No custom scheduled posts to cancel.")
    count = sum(1 for p in posts if not p['task'].done() and p['task'].cancel())
    context.user_data['scheduled_custom_posts'] =[]
    await update.message.reply_text(f"✅ `{count}` scheduled custom messages have been safely cancelled.", parse_mode="Markdown")

@restricted
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    batches = context.user_data.get('poll_batches', [])
    if not batches: 
        return await update.message.reply_text("❌ No questions loaded. Use /uploadcsv first.")
    if not context.user_data.get('channels',[]): 
        return await update.message.reply_text("❌ No target channels saved. Use /setchannel first.")
    
    if len(batches) > 1:
        keyboard = [
            [InlineKeyboardButton(f"Last Session ({len(batches[-1])} Qs)", callback_data="selb_sched_1")],
            [InlineKeyboardButton(f"Last 2 Sessions ({sum(len(b) for b in batches[-2:])} Qs)", callback_data="selb_sched_2")],
        ]
        if len(batches) >= 3:
            keyboard.append([InlineKeyboardButton(f"Last 3 Sessions ({sum(len(b) for b in batches[-3:])} Qs)", callback_data="selb_sched_3")])
        keyboard.append([InlineKeyboardButton(f"All Sessions ({sum(len(b) for b in batches)} Qs)", callback_data="selb_sched_all")])
        
        await update.message.reply_text("📚 **Multiple Quiz Sessions Detected!**\n\nWhich sessions do you want to schedule?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        context.user_data['temp_active_questions'] = batches[0]
        context.user_data['temp_target_channels'] = context.user_data.get('channels',[]).copy()
        await update.message.reply_text("📢 **Select target channels to Schedule this Quiz:**", reply_markup=await get_channel_selection_markup(context, "sched_quiz"), parse_mode="Markdown")

@restricted
async def getcsv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("Send to Target Channels 📢", callback_data="send_channel")],[InlineKeyboardButton("Test Here in Bot 🤖", callback_data="send_bot")]]
    await update.message.reply_text("📦 Where do you want to post the loaded quizzes?", reply_markup=InlineKeyboardMarkup(keyboard))

@restricted
async def uploadcsv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("📎 Upload CSV File", callback_data="up_file")],[InlineKeyboardButton("✍️ Paste Text Instead", callback_data="up_text")]]
    await update.message.reply_text("📂 **Upload your file or paste MCQs in text format**\n\n📌 **Format:** `Question, Opt A, Opt B, Opt C, Opt D, Correct Ans, [Optional Explanation]`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

@restricted
async def shuffle_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    qs = get_all_poll_questions(context)
    if not qs:
        return await update.message.reply_text("❌ No questions loaded to shuffle. Use /uploadcsv first.")
    random.shuffle(qs)
    context.user_data['poll_batches'] = [qs] 
    await update.message.reply_text("🔀 **Questions Shuffled Successfully!**\nThe order of the loaded quizzes has been fully randomized.", parse_mode="Markdown")

@restricted
async def clearcsv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['poll_batches'] = []
    await update.message.reply_text("🗑 **Loaded Questions Cleared!**\nAll CSV data currently in memory has been successfully erased.", parse_mode="Markdown")

@restricted
async def pdftocsv_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['state'] = 'wait_pdf_quiz_count'
    await update.message.reply_text("🔢 **How many unique questions (MCQs) do you want to create from your PDF/Book?**\n\n👉 Please type a number (e.g., `20`, `50`).\n\n*(Send /cancel to abort)*", parse_mode="Markdown")

@restricted
async def csv2html(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("0", callback_data="neg_0"), InlineKeyboardButton("0.25", callback_data="neg_0.25")],[InlineKeyboardButton("0.33", callback_data="neg_0.33"), InlineKeyboardButton("0.50", callback_data="neg_0.50")]]
    await update.message.reply_text("🧮 Select Negative Marking for offline HTML Quiz:", reply_markup=InlineKeyboardMarkup(keyboard))

@restricted
async def deletequizzes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("📢 Delete Posted Quizzes (Channels)", callback_data="delq_type_ch")],
        [InlineKeyboardButton("🧠 Delete Loaded Quizzes (Bot Memory)", callback_data="delq_type_mem")]
    ]
    await update.message.reply_text("🗑 **Where do you want to delete quizzes from?**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

@restricted
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get('state', 'Idle / None')
    ch_text = ", ".join(context.user_data.get('channels',[])) or "Not Set ❌"
    timer = context.user_data.get('timer', 0)
    
    active_task = context.user_data.get('active_task')
    scheduled_task = context.user_data.get('scheduled_task')
    schedule_time = context.user_data.get('schedule_time')
    
    task_status = "🔴 Stopped / None"
    if active_task and not active_task.done():
        task_status = "⏸ Paused" if context.user_data.get('paused', False) else "🟢 Sending Polls Actively"
    elif scheduled_task and not scheduled_task.done():
        if schedule_time:
            remaining = (schedule_time - datetime.now()).total_seconds() / 60
            if remaining > 0: task_status = f"⏰ Scheduled to start in `{int(remaining)}` mins"
    
    qs_count = sum(len(b) for b in context.user_data.get('poll_batches', []))
    
    text = f"📊 *Bot Current Status*\n\n🔹 *State:* `{state}`\n📢 *Channels:* `{ch_text}`\n⏱ *Timer:* `{timer} Sec`\n📚 *Topic:* `{context.user_data.get('quiz_topic', 'Not Set ❌')}`\n📝 *Polls Loaded:* `{qs_count} Qs`\n📨 *Custom Msgs Sched:* `{len(context.user_data.get('scheduled_custom_posts',[]))}`\n⚙️ *Quiz Process:* {task_status}"
    await update.message.reply_text(text, parse_mode="Markdown")

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
    stopped = False
    for task_name in ['active_task', 'scheduled_task']:
        t = context.user_data.get(task_name)
        if t and not t.done():
            t.cancel()
            stopped = True
    context.user_data['paused'] = False
    if stopped: await update.message.reply_text("🛑 *Quiz Process Stopped!*\n*(Note: Custom normal posts are unaffected. Use /cancelposts to stop them.)*", parse_mode="Markdown")
    else: await update.message.reply_text("⚠️ There is no active quiz running.")

@restricted
async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('state'):
        context.user_data['state'] = None
        await update.message.reply_text("🚫 *Action Cancelled!*\nI am no longer waiting for your input.", parse_mode="Markdown")
    else: await update.message.reply_text("⚠️ You don't have any active actions to cancel right now.")

@restricted
async def startfresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    active = context.user_data.get('active_task')
    if active and not active.done(): active.cancel()
    sched = context.user_data.get('scheduled_task')
    if sched and not sched.done(): sched.cancel()
    for p in context.user_data.get('scheduled_custom_posts',[]):
        if not p['task'].done(): p['task'].cancel()
        
    context.user_data.clear()
    await update.message.reply_text("🔄 *Fresh Start Complete!*\nAll configurations, loaded questions, and active tasks have been safely wiped.", parse_mode="Markdown")

@restricted
async def settimer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("10 Sec", callback_data="timer_10"), InlineKeyboardButton("15 Sec", callback_data="timer_15")],[InlineKeyboardButton("30 Sec", callback_data="timer_30"), InlineKeyboardButton("60 Sec", callback_data="timer_60")],[InlineKeyboardButton("🚫 No Timer (Unlimited)", callback_data="timer_0")]]
    await update.message.reply_text("⏱ *Select the auto-close timer for polls:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

@restricted
async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("📂 Upload CSV / Text", callback_data="help_uploadcsv"), InlineKeyboardButton("📢 Set Channels", callback_data="help_setchannel")],[InlineKeyboardButton("🚀 Multi-Posting Quizzes", callback_data="help_getcsv"), InlineKeyboardButton("🗑 Delete Quiz Session", callback_data="help_deletequizzes")],[InlineKeyboardButton("🔙 Close Guide", callback_data="close_guide")]]
    text = "📖 **Interactive Quick Guide!**\n\nChoose an option below to learn about the bot features:"
    if update.message: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ==========================================
# 🔄 CALLBACK & MESSAGE HANDLERS
# ==========================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "close_guide" or data == "cancel_action":
        context.user_data['state'] = None
        return await query.edit_message_text("✅ Action closed.")

    if data.startswith("authplan_"):
        parts = data.split("_")
        user_id_to_auth = parts[1]
        days = int(parts[2])
        users = load_auth_users()
        
        new_expiry = datetime.now() + timedelta(days=days)
        if user_id_to_auth not in users:
            users[user_id_to_auth] = {}
            
        users[user_id_to_auth]["expiry"] = new_expiry.isoformat()
        save_auth_users(users)
        
        await query.edit_message_text(f"✅ User `{user_id_to_auth}` granted access for `{days}` days.\n📅 Expires: `{new_expiry.strftime('%Y-%m-%d %H:%M:%S')}`", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=int(user_id_to_auth),
                text=f"🎉 **Good News!**\nYour subscription has been upgraded by the Admin.\n\n⏳ **Validity:** `{days} Days`\n📅 **Expires on:** `{new_expiry.strftime('%Y-%m-%d')}`\n\nUse /start to begin using all features!",
                parse_mode="Markdown"
            )
        except Exception: pass
        return

    if data.startswith("csv_act_"):
        temp_qs = context.user_data.get('temp_uploaded_questions', [])
        if not temp_qs:
            return await query.edit_message_text("❌ No temporary questions found. Please upload again.")
            
        batches = context.user_data.setdefault('poll_batches', [])
        
        if data == "csv_act_post":
            batches.append(temp_qs)
            context.user_data['temp_active_questions'] = temp_qs
            del context.user_data['temp_uploaded_questions']
            if not context.user_data.get('channels'):
                return await query.edit_message_text("❌ No target channels saved. Use /setchannel first.")
            context.user_data['temp_target_channels'] = context.user_data.get('channels', []).copy()
            return await query.edit_message_text("📢 **Select target channels for Immediate Posting:**", reply_markup=await get_channel_selection_markup(context, "start_quiz"), parse_mode="Markdown")
            
        elif data == "csv_act_save":
            batches.append(temp_qs)
            del context.user_data['temp_uploaded_questions']
            return await query.edit_message_text(f"✅ **Saved as a new independent session!**\n\nTotal sessions loaded: `{len(batches)}`\nUse /getcsv or /schedule when ready.", parse_mode="Markdown")
            
        elif data == "csv_act_stack":
            if batches: batches[-1].extend(temp_qs)
            else: batches.append(temp_qs)
            del context.user_data['temp_uploaded_questions']
            return await query.edit_message_text(f"✅ **Stacked with previous session!**\n\nTotal questions in current session: `{len(batches[-1])}`", parse_mode="Markdown")

    if data.startswith("selb_"):
        parts = data.split("_")
        action = parts[1] 
        num = parts[2] 
        
        batches = context.user_data.get('poll_batches', [])
        if num == "all":
            selected_qs = [q for b in batches for q in b]
        else:
            count = int(num)
            selected_qs = [q for b in batches[-count:] for q in b]
            
        context.user_data['temp_active_questions'] = selected_qs
        context.user_data['temp_target_channels'] = context.user_data.get('channels', []).copy()
        
        next_action = "start_quiz" if action == "get" else "sched_quiz"
        msg = "📢 **Select target channels for the Live Quiz:**" if action == "get" else "📢 **Select target channels to Schedule this Quiz:**"
        return await query.edit_message_text(msg, reply_markup=await get_channel_selection_markup(context, next_action), parse_mode="Markdown")

    if data.startswith("up_"):
        if data == "up_file":
            context.user_data['state'] = 'wait_csv_file'
            return await query.edit_message_text("📎 **Please send the CSV or Text file now.**\n*(Send /cancel to abort)*", parse_mode="Markdown")
        elif data == "up_text":
            context.user_data['state'] = 'wait_csv_text'
            return await query.edit_message_text("✍️ **Please paste your CSV text now.**\n*(Send /cancel to abort)*", parse_mode="Markdown")

    if data.startswith("timer_"):
        val = int(data.split("_")[1])
        context.user_data['timer'] = val
        return await query.edit_message_text(f"✅ Timer set to `{val}` seconds.", parse_mode="Markdown")
        
    if data.startswith("neg_"):
        neg_val = data.split("_")[1]
        questions = get_all_poll_questions(context)
        if not questions: return await query.edit_message_text("❌ No questions loaded. Use /uploadcsv first.")
        title = context.user_data.get('quiz_topic', 'Offline_Test')
        html_content = generate_html_quiz(questions, title, neg_val)
        bio = io.BytesIO(html_content.encode('utf-8'))
        bio.name = f"{title}.html"
        await query.edit_message_text("✅ Generating HTML file...")
        await context.bot.send_document(chat_id=update.effective_chat.id, document=bio)
        return

    if data == "send_bot":
        questions = get_all_poll_questions(context)
        if not questions: return await query.edit_message_text("❌ No questions loaded. Use /uploadcsv first.")
        await query.edit_message_text("🤖 **Sending polls here for testing...**", parse_mode="Markdown")
        context.user_data['active_task'] = asyncio.create_task(send_polls_task(context, update.effective_chat.id, questions,[update.effective_chat.id]))
        return

    if data == "send_channel":
        batches = context.user_data.get('poll_batches', [])
        if not batches: return await query.edit_message_text("❌ No questions loaded. Use /uploadcsv first.")
        if not context.user_data.get('channels'): return await query.edit_message_text("❌ No target channels saved. Use /setchannel first.")
        
        if len(batches) > 1:
            keyboard = [
                [InlineKeyboardButton(f"Last Session ({len(batches[-1])} Qs)", callback_data="selb_get_1")],
                [InlineKeyboardButton(f"Last 2 Sessions ({sum(len(b) for b in batches[-2:])} Qs)", callback_data="selb_get_2")],
            ]
            if len(batches) >= 3:
                keyboard.append([InlineKeyboardButton(f"Last 3 Sessions ({sum(len(b) for b in batches[-3:])} Qs)", callback_data="selb_get_3")])
            keyboard.append([InlineKeyboardButton(f"All Sessions ({sum(len(b) for b in batches)} Qs)", callback_data="selb_get_all")])
            return await query.edit_message_text("📚 **Multiple Quiz Sessions Detected!**\n\nWhich sessions do you want to post?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            context.user_data['temp_active_questions'] = batches[0]
            context.user_data['temp_target_channels'] = context.user_data.get('channels',[]).copy()
            return await query.edit_message_text("📢 **Select target channels for the Live Quiz:**", reply_markup=await get_channel_selection_markup(context, "start_quiz"), parse_mode="Markdown")

    if data.startswith("help_"):
        if data == "help_main_menu": return await guide_command(update, context)
        elif data == "help_uploadcsv": guide_info = "📂 **Upload CSV / Text**\nUse `/uploadcsv`, choose file or text upload. You can stack multiple files to combine them or save them independently! The bot remembers them by Sessions."
        elif data == "help_setchannel": guide_info = "📢 **Multi-Channel Guide**\nYou can post to multiple groups at once!\n\nUse `/setchannel` to add multiple channels. Then type `/channels` to see them."
        elif data == "help_deletequizzes": guide_info = "🗑 **Delete Session Guide**\nUse `/deletequizzes` to either delete polls previously sent to channels, OR to clear quiz sessions temporarily loaded in bot memory."
        elif data == "help_getcsv": guide_info = "🚀 **Multi-Posting Quizzes**\nAfter loading questions, hit `/getcsv`. A checklist of your saved channels will appear. Click to `✅` or `❌` specific channels, then hit Confirm to blast the quiz to all selected groups at once!"
        else: guide_info = "📖 Guide section coming soon."
        return await query.edit_message_text(guide_info, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help_main_menu")]]), parse_mode="Markdown")

    if data.startswith("togglech_"):
        ch_id, next_action = data.split("_", 2)[1:]
        selected = context.user_data.get('temp_target_channels',[])
        if ch_id in selected: selected.remove(ch_id)
        else: selected.append(ch_id)
        context.user_data['temp_target_channels'] = selected
        return await query.edit_message_reply_markup(reply_markup=await get_channel_selection_markup(context, next_action))

    elif data.startswith("confirmch_"):
        next_action = data.split("_", 1)[1]
        selected = context.user_data.get('temp_target_channels',[])
        if not selected: return await query.answer("⚠️ You must select at least one channel!", show_alert=True)
        context.user_data['final_target_channels'] = selected
        
        if next_action == "start_quiz":
            questions = context.user_data.get('temp_active_questions')
            if not questions: questions = get_all_poll_questions(context)
            if not questions: return await query.edit_message_text("❌ No questions loaded.")
            await query.edit_message_text(f"✅ Starting live Quiz posting across `{len(selected)}` selected channels...", parse_mode="Markdown")
            context.user_data['active_task'] = asyncio.create_task(send_polls_task(context, update.effective_chat.id, questions, selected))
        
        elif next_action == "sched_quiz":
            keyboard = [[InlineKeyboardButton("🚀 Immediately", callback_data="sched_0")],[InlineKeyboardButton("5 Mins", callback_data="sched_5"), InlineKeyboardButton("15 Mins", callback_data="sched_15")],[InlineKeyboardButton("30 Mins", callback_data="sched_30"), InlineKeyboardButton("1 Hour", callback_data="sched_60")],[InlineKeyboardButton("Set Date/Time", callback_data="sched_manual")]]
            await query.edit_message_text(f"⏰ **Schedule Quiz Posting**\n\n• Channels Selected: `{len(selected)}`\n\nSelect when to start:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        elif next_action == "sched_post":
            keyboard = [[InlineKeyboardButton("🚀 Immediately", callback_data="schedp_0")],[InlineKeyboardButton("5 Mins", callback_data="schedp_5"), InlineKeyboardButton("15 Mins", callback_data="schedp_15")]]
            await query.edit_message_text(f"⏰ **Schedule Custom Post**\n\n• Channels Selected: `{len(selected)}`\n\nSelect when to post:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data.startswith("sched_") and data != "sched_manual":
        mins = int(data.split("_")[1])
        context.user_data['schedule_time'] = datetime.now() + timedelta(minutes=mins)
        selected = context.user_data.get('final_target_channels',[])
        questions = context.user_data.get('temp_active_questions')
        if not questions: questions = get_all_poll_questions(context)
        
        async def scheduled_quiz(ctx, admin_chat, qs, channels, delay):
            if delay > 0: await asyncio.sleep(delay)
            await send_polls_task(ctx, admin_chat, qs, channels)
            
        context.user_data['scheduled_task'] = asyncio.create_task(scheduled_quiz(context, update.effective_chat.id, questions, selected, mins * 60))
        if mins == 0: return await query.edit_message_text(f"🚀 Quiz posting started IMMEDIATELY across `{len(selected)}` channels.", parse_mode="Markdown")
        return await query.edit_message_text(f"✅ Quiz scheduled to run in `{mins}` minutes across `{len(selected)}` channels.", parse_mode="Markdown")

    if data == "sched_manual":
        context.user_data['state'] = 'wait_schedule_datetime'
        return await query.edit_message_text("⏰ **Enter Date & Time**\nFormat: `DD/MM/YYYY HH:MM` or `HH:MM`\n*(Send /cancel to abort)*", parse_mode="Markdown")

    if data.startswith("schedp_"):
        mins = int(data.split("_")[1])
        selected = context.user_data.get('final_target_channels',[])
        content = context.user_data.get('pending_post_content')
        
        async def scheduled_post(ctx, admin_chat, msg, channels, delay):
            if delay > 0: await asyncio.sleep(delay)
            for ch in channels:
                try: await msg.copy(chat_id=ch)
                except Exception: pass
            await ctx.bot.send_message(chat_id=admin_chat, text="✅ **Scheduled Custom Post Sent!**", parse_mode="Markdown")

        task = asyncio.create_task(scheduled_post(context, update.effective_chat.id, content, selected, mins * 60))
        posts = context.user_data.setdefault('scheduled_custom_posts',[])
        posts.append({'task': task})
        if mins == 0: return await query.edit_message_text(f"🚀 Custom post sent IMMEDIATELY to `{len(selected)}` channels.", parse_mode="Markdown")
        return await query.edit_message_text(f"✅ Custom post scheduled in `{mins}` minutes.", parse_mode="Markdown")

    if data == "delq_type_ch":
        try:
            with open(TRACKING_FILE, "r") as f: tracking_data = json.load(f)
            tracked_channels = list(tracking_data.keys())
        except Exception: tracked_channels = []

        if not tracked_channels: return await query.edit_message_text("❌ No target channels found with saved quizzes in my memory.")
        keyboard = [[InlineKeyboardButton(f"🗑 {ch}", callback_data=f"delq_ch_{ch}")] for ch in tracked_channels]
        return await query.edit_message_text("🗑 **Select which channel you want to clean up:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif data == "delq_type_mem":
        batches = context.user_data.get('poll_batches', [])
        if not batches: return await query.edit_message_text("⚠️ No quizzes currently loaded in bot memory.")
        
        keyboard = [
            [InlineKeyboardButton("🧹 Clear Last Upload Session Only", callback_data="delq_mem_last")],
            [InlineKeyboardButton("🗑 Clear ALL Loaded Sessions", callback_data="delq_mem_all")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="cancel_action")]
        ]
        return await query.edit_message_text(f"🧠 **Bot Memory Management**\n\nTotal Sessions Loaded: `{len(batches)}`\nTotal Questions: `{sum(len(b) for b in batches)}`\n\nSelect what to clear:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif data == "delq_mem_last":
        batches = context.user_data.get('poll_batches', [])
        if batches:
            removed = batches.pop()
            return await query.edit_message_text(f"✅ Successfully cleared the last uploaded session (`{len(removed)}` Qs).\nRemaining sessions: `{len(batches)}`.", parse_mode="Markdown")
        return await query.edit_message_text("⚠️ No quizzes to clear.")
            
    elif data == "delq_mem_all":
        context.user_data['poll_batches'] = []
        return await query.edit_message_text("✅ All loaded quiz sessions have been safely wiped from bot memory.", parse_mode="Markdown")

    if data.startswith("delq_ch_"):
        ch_id = data.split("_", 2)[2]
        try:
            with open(TRACKING_FILE, "r") as f: tracking_data = json.load(f)
        except Exception: return await query.edit_message_text("⚠️ No tracking data found.")
            
        ch_data = tracking_data.get(str(ch_id), {})
        if not ch_data: return await query.edit_message_text(f"⚠️ No saved quiz records found in my memory for `{ch_id}`.", parse_mode="Markdown")
        
        keyboard = [[InlineKeyboardButton(f"📄 {sess_info.get('label', 'Unknown')} ({len(sess_info.get('msg_ids', []))} Qs)", callback_data=f"delqs_{ch_id}_{sess_id[:15]}")] for sess_id, sess_info in ch_data.items()]
        keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data="cancel_action")])
        return await query.edit_message_text(f"🗑 **Select a Quiz Session to delete from `{ch_id}`:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif data.startswith("delqs_"):
        parts = data.split("_", 2)
        ch_id, sess_id = parts[1], parts[2]
        await query.edit_message_text(f"⏳ **Deleting selected quiz session from `{ch_id}`...**\nPlease wait.")
        try:
            with open(TRACKING_FILE, "r") as f: tracking_data = json.load(f)
        except Exception: return
            
        ch_data = tracking_data.get(str(ch_id), {})
        actual_sess_id = next((k for k in ch_data.keys() if k.startswith(sess_id)), None)
        
        if actual_sess_id and actual_sess_id in ch_data:
            msg_ids = ch_data[actual_sess_id].get("msg_ids", [])
            del tracking_data[str(ch_id)][actual_sess_id]
            if not tracking_data[str(ch_id)]: del tracking_data[str(ch_id)]
            
            deleted, failed = 0, 0
            for mid in msg_ids:
                try:
                    await context.bot.delete_message(chat_id=ch_id, message_id=mid)
                    deleted += 1
                    await asyncio.sleep(0.4) 
                except Exception: failed += 1
                    
            with open(TRACKING_FILE, "w") as f: json.dump(tracking_data, f, indent=4)
            return await query.edit_message_text(f"✅ **Session Cleanup Complete for {ch_id}**\n\n🗑 Successfully deleted: `{deleted}`\n⚠️ Failed (deleted already or too old): `{failed}`", parse_mode="Markdown")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get('state')
    
    if state == 'wait_channel_id':
        if update.message.text:
            raw_text = update.message.text.strip()
            new_chs = [ch for ch in re.split(r'[\s,]+', raw_text) if ch]
            saved_channels = context.user_data.setdefault('channels',[])
            added =[]
            for ch_id in new_chs:
                if ch_id not in saved_channels:
                    saved_channels.append(ch_id)
                    added.append(ch_id)
            if added:
                await update.message.reply_text(f"✅ Saved target channels:\n`{'`, `'.join(added)}`", parse_mode="Markdown")
            else:
                await update.message.reply_text("⚠️ Channel(s) already exist in your list or invalid input.")
            context.user_data['state'] = None
        else:
            await update.message.reply_text("❌ Please send valid text containing the IDs.")

    elif state == 'wait_quiz_topic':
        topic = update.message.text
        context.user_data['quiz_topic'] = topic
        context.user_data['state'] = None
        await update.message.reply_text(f"✅ Quiz topic successfully set to: `{topic}`\nIt will group your next quiz in /deletequizzes memory.", parse_mode="Markdown")
        
    elif state == 'wait_schedule_post_text':
        context.user_data['pending_post_content'] = update.message
        context.user_data['state'] = None
        context.user_data['temp_target_channels'] = context.user_data.get('channels',[]).copy()
        await update.message.reply_text("✅ Content safely received!\n\n📢 **Now, select target channels to schedule this on:**", reply_markup=await get_channel_selection_markup(context, "sched_post"), parse_mode="Markdown")
        
    elif state == 'wait_pdf_quiz_count':
        if update.message.text and update.message.text.isdigit():
            context.user_data['state'] = None
            prompt = f"Please read the attached PDF and generate {update.message.text} Multiple Choice Questions in CSV format. Format MUST be: Question, Option A, Option B, Option C, Option D, Correct Option (A/B/C/D), [Optional Explanation]."
            await update.message.reply_text(f"✅ Great! Copy the prompt below and paste it into ChatGPT with your PDF:\n\n`{prompt}`\n\nOnce you get the CSV back, use /uploadcsv here!", parse_mode="Markdown")
        else: await update.message.reply_text("❌ Please enter a valid number.")

    elif state == 'wait_csv_text':
        if update.message.text:
            questions = parse_csv_content(update.message.text)
            if not questions:
                await update.message.reply_text("❌ Failed to parse any questions. Make sure the format is correct:\n`Question, Opt A, Opt B, Opt C, Opt D, Correct Option`")
            else:
                context.user_data['temp_uploaded_questions'] = questions
                keyboard = [
                    [InlineKeyboardButton("🚀 Post Now", callback_data="csv_act_post"), InlineKeyboardButton("💾 Save for Later", callback_data="csv_act_save")],
                    [InlineKeyboardButton("📚 Stack with Previous", callback_data="csv_act_stack")],
                    [InlineKeyboardButton("🚫 Cancel", callback_data="cancel_action")]
                ]
                await update.message.reply_text(f"✅ Successfully parsed `{len(questions)}` questions!\n\nWhat would you like to do with these quizzes?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else: await update.message.reply_text("❌ Please send valid text.")

    elif state == 'wait_csv_file':
        if update.message.document:
            try:
                file = await context.bot.get_file(update.message.document.file_id)
                byte_array = await file.download_as_bytearray()
                
                try: text = byte_array.decode('utf-8')
                except UnicodeDecodeError: text = byte_array.decode('latin-1')
                
                questions = parse_csv_content(text)
                if not questions:
                    await update.message.reply_text("❌ Failed to parse any questions from the file. Please check the format.")
                else:
                    context.user_data['temp_uploaded_questions'] = questions
                    keyboard = [
                        [InlineKeyboardButton("🚀 Post Now", callback_data="csv_act_post"), InlineKeyboardButton("💾 Save for Later", callback_data="csv_act_save")],
                        [InlineKeyboardButton("📚 Stack with Previous", callback_data="csv_act_stack")],
                        [InlineKeyboardButton("🚫 Cancel", callback_data="cancel_action")]
                    ]
                    await update.message.reply_text(f"✅ Successfully parsed `{len(questions)}` questions from file!\n\nWhat would you like to do with these quizzes?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error processing file: {e}")
                await update.message.reply_text("❌ Error processing the file. Make sure it's a valid CSV or TXT file.")
        else:
            await update.message.reply_text("❌ Please send a valid document/file.")

    elif state == 'wait_schedule_datetime':
        if update.message.text:
            dt = parse_date_time(update.message.text)
            if not dt:
                await update.message.reply_text("❌ Invalid format or time is in the past. Try again (e.g. `15/05/2026 14:30`) or send /cancel:")
            else:
                delay_sec = (dt - datetime.now()).total_seconds()
                context.user_data['schedule_time'] = dt
                selected = context.user_data.get('final_target_channels',[])
                questions = context.user_data.get('temp_active_questions')
                if not questions: questions = get_all_poll_questions(context)
                
                async def scheduled_quiz(ctx, admin_chat, qs, channels, delay):
                    if delay > 0: await asyncio.sleep(delay)
                    await send_polls_task(ctx, admin_chat, qs, channels)
                    
                context.user_data['scheduled_task'] = asyncio.create_task(scheduled_quiz(context, update.effective_chat.id, questions, selected, delay_sec))
                context.user_data['state'] = None
                await update.message.reply_text(f"✅ Quiz scheduled for `{dt.strftime('%d/%m/%Y %H:%M')}`.", parse_mode="Markdown")
            
    else:
        if update.message.text and not update.message.text.startswith('/'):
            await update.message.reply_text("I'm not currently waiting for any input. Use the menu commands to start an action.")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("auth", auth_user))
    application.add_handler(CommandHandler("unauth", unauth_user))
    application.add_handler(CommandHandler("authlist", auth_list))

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("contact", contact_command))
    application.add_handler(CommandHandler("guide", guide_command))
    application.add_handler(CommandHandler("myplan", myplan))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("setchannel", setchannel))
    application.add_handler(CommandHandler("removechannel", removechannel_command))
    application.add_handler(CommandHandler("settopic", settopic_command))
    application.add_handler(CommandHandler("uploadcsv", uploadcsv))
    application.add_handler(CommandHandler("shuffle", shuffle_quizzes))
    application.add_handler(CommandHandler("clearcsv", clearcsv))
    application.add_handler(CommandHandler("pdftocsv", pdftocsv_command))
    application.add_handler(CommandHandler("getcsv", getcsv))
    application.add_handler(CommandHandler("csv2html", csv2html))
    application.add_handler(CommandHandler("settimer", settimer))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("schedulepost", schedulepost_command))
    application.add_handler(CommandHandler("cancelposts", cancelposts_command))
    application.add_handler(CommandHandler("deletequizzes", deletequizzes_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("pause", pause_quiz))
    application.add_handler(CommandHandler("resume", resume_quiz))
    application.add_handler(CommandHandler("stop", stop_process))
    application.add_handler(CommandHandler("cancel", cancel_action))
    application.add_handler(CommandHandler("startfresh", startfresh))

    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    print("🤖 MCQ Master Bot is starting up... Flawlessly configured.")
    application.run_polling()

if __name__ == "__main__":
    main()
