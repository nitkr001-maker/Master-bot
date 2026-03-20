import telebot
from telebot import types
import sqlite3
import datetime
import json
import html
import time
from contextlib import closing

# ==========================================
# CONFIGURATION - YOUR EXACT DETAILS
# ==========================================
BOT_TOKEN = "8575370561:AAH6OlLBYL1Uri_3Fg1KpGUvhDFdUriK_u4"
ADMIN_ID = 6915757343  
ADMIN_USERNAME = "@Mr_outlaw001" 
# ==========================================

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

# --- BULLETPROOF DATABASE SETUP & AUTO-MIGRATION ---
def init_db():
    with closing(sqlite3.connect('users.db', check_same_thread=False)) as conn:
        with conn:
            c = conn.cursor()
            # Create base table
            c.execute('''CREATE TABLE IF NOT EXISTS users
                         (user_id INTEGER PRIMARY KEY, plan_type TEXT, expiry_date TEXT, week_start TEXT, checks_used INTEGER)''')
            # Auto-Migrate: Add phone_number column if it doesn't exist from the old version
            try:
                c.execute("ALTER TABLE users ADD COLUMN phone_number TEXT")
            except sqlite3.OperationalError:
                pass # Column already exists, safe to proceed
init_db()

# --- HELPER FUNCTIONS ---
def safe_html(text):
    if not text: return "None"
    return html.escape(str(text))

def estimate_date(chat_id):
    try:
        chat_id_str = str(chat_id)
        if chat_id_str.startswith("-100"): real_id = int(chat_id_str[4:])
        elif chat_id_str.startswith("-"): real_id = int(chat_id_str[1:])
        else: real_id = int(chat_id)
    except: real_id = 99999999999

    if real_id < 100000000: return "2013 - 2014"
    elif real_id < 500000000: return "2015 - 2017"
    elif real_id < 1000000000: return "2018 - 2019"
    elif real_id < 2000000000: return "2020 - 2021"
    elif real_id < 5000000000: return "2022"
    elif real_id < 6000000000: return "Early 2023"
    elif real_id < 7000000000: return "Late 2023"
    elif real_id < 7500000000: return "2024"
    elif real_id < 8000000000: return "2025"
    else: return "2026 - Present"

def get_ad_text():
    return "🧠 <b>AI Help</b> → <a href='https://t.me/DeepSeek'>DeepSeek</a>\n🖼 <b>Images</b> → <a href='https://t.me/NanoBanana'>NanoBanana</a>"

def get_contact_admin_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👨‍💻 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME.replace('@', '')}"))
    return markup

# --- 100% CRASH-PROOF NATIVE KEYBOARDS ---
def get_registration_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton(text="📱 Share Phone Number to Start Trial", request_contact=True))
    return markup

def get_main_keyboard():
    """Bypasses library limitations by injecting pure JSON accepted directly by Telegram Servers"""
    class RawMenu:
        def to_json(self):
            return json.dumps({
                "keyboard": [[
                        {"text": "👤 User", "request_users": {"request_id": 1, "user_is_bot": False, "request_name": True, "request_username": True}},
                        {"text": "🤖 Bot", "request_users": {"request_id": 2, "user_is_bot": True, "request_name": True, "request_username": True}}
                    ],[
                        {"text": "📢 Channel", "request_chat": {"request_id": 3, "chat_is_channel": True, "request_title": True, "request_username": True}},
                        {"text": "👥 Group", "request_chat": {"request_id": 4, "chat_is_channel": False, "chat_is_forum": False, "request_title": True, "request_username": True}}
                    ]
                ],
                "resize_keyboard": True
            })
    return RawMenu()

# --- SUBSCRIPTION LOGIC ---
def check_access(user_id):
    if user_id == ADMIN_ID: return True, ""

    with closing(sqlite3.connect('users.db', check_same_thread=False)) as conn:
        with conn:
            c = conn.cursor()
            user = c.execute("SELECT plan_type, expiry_date, week_start, checks_used FROM users WHERE user_id=?", (user_id,)).fetchone()

            if not user: return False, "REGISTRATION_REQUIRED"

            plan_type, expiry_str, week_start_str, checks_used = user
            now = datetime.datetime.now()
            expiry_date = datetime.datetime.fromisoformat(expiry_str)
            week_start = datetime.datetime.fromisoformat(week_start_str)

            if now > expiry_date:
                return False, f"❌ Your <b>{plan_type.upper()}</b> subscription has expired. Contact the admin."

            if now > week_start + datetime.timedelta(days=7):
                week_start = now
                checks_used = 0
                c.execute("UPDATE users SET week_start=?, checks_used=? WHERE user_id=?", (week_start.isoformat(), checks_used, user_id))

            limit = 50 if plan_type == 'plan1' else 200 if plan_type == 'plan2' else 999999
            if checks_used >= limit and plan_type != 'unlimited':
                return False, f"⚠️ Weekly limit reached (<b>{limit}</b> checks).\n\nPlease wait until next week or upgrade your plan."

            c.execute("UPDATE users SET checks_used=? WHERE user_id=?", (checks_used + 1, user_id))
            return True, ""


# ==========================================
# 1. GENERAL COMMAND HANDLERS 
# ==========================================

@bot.message_handler(commands=['start', 'startfresh'])
def send_welcome(message):
    try:
        bot.clear_step_handler_by_chat_id(message.chat.id)
        user_id = message.from_user.id
        has_access, msg = check_access(user_id)
        
        if msg == "REGISTRATION_REQUIRED":
            bot.send_message(message.chat.id, "👋 <b>Welcome to ID Bot!</b>\n\nTo prevent spam, please verify your account by sharing your phone number to activate your <b>2-Day Free Trial</b>.", parse_mode="HTML", reply_markup=get_registration_keyboard())
            return
        elif not has_access:
            bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=get_contact_admin_markup())
            return

        bot.send_message(message.chat.id, "👋 <b>ID Bot Menu</b>\nTap a button below, or forward a message/file to me!\n\n<i>Need help? Send /guide</i>", parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e: 
        bot.send_message(message.chat.id, f"⚠️ Start Error: {e}")

@bot.message_handler(commands=['myplan'])
def check_my_plan(message):
    try:
        if message.from_user.id == ADMIN_ID:
            bot.send_message(message.chat.id, "👑 <b>Admin Status Active (Unlimited Check Bypass)</b>", parse_mode="HTML")
            return
            
        with closing(sqlite3.connect('users.db', check_same_thread=False)) as conn:
            user = conn.cursor().execute("SELECT plan_type, expiry_date, checks_used FROM users WHERE user_id=?", (message.from_user.id,)).fetchone()
        
        if not user: return
        exp_date = datetime.datetime.fromisoformat(user[1]).strftime("%Y-%m-%d %H:%M")
        bot.send_message(message.chat.id, f"📋 <b>Plan:</b> {user[0].upper()}\n📈 <b>Used:</b> {user[2]} checks\n⏳ <b>Expires:</b> <code>{exp_date}</code>", parse_mode="HTML", reply_markup=get_contact_admin_markup())
    except Exception as e: 
        bot.send_message(message.chat.id, f"⚠️ Plan Error: {e}")

@bot.message_handler(commands=['help', 'guide'])
def send_guide(message):
    guide_text = (
        "📖 <b>ULTIMATE ID BOT GUIDE</b>\n\n"
        "Welcome to the most advanced ID extraction bot! Here is exactly how to use all features:\n\n"
        "<b>1️⃣ Extracting Account/Chat IDs</b>\n"
        "• Look at the <b>bottom of your screen</b> for the custom keyboard (👤 User, 📢 Channel, etc.).\n"
        "• Tap any button and select a target. The bot will instantly pull their hidden ID, Name, and Creation Date!\n\n"
        "<b>2️⃣ Forwarded Messages Extraction</b>\n"
        "• Forward <b>ANY</b> message from a user, channel, or group to this bot.\n"
        "• We will reveal the original sender's ID, even if they have privacy settings enabled (shows as Hidden).\n\n"
        "<b>3️⃣ Media & File Server IDs</b>\n"
        "• Send any Photo, Video, Sticker, Audio, Document, Voice Note, or GIF directly to the bot.\n"
        "• It will instantly return the unique Telegram Server <code>file_id</code> for that specific media.\n\n"
        "<b>4️⃣ Subscriptions & Limits</b>\n"
        "• <b>Trial:</b> 2 Days Free\n"
        "• <b>Plan 1:</b> 50 Checks per Week\n"
        "• <b>Plan 2:</b> 200 Checks per Week\n"
        "• <i>Limits reset every 7 days automatically. Contact Admin to upgrade.</i>\n\n"
        "<i>Tap buttons below for specific topics:</i>"
    )
    bot.send_message(message.chat.id, guide_text, parse_mode="HTML", reply_markup=guide_markup(True))


# ==========================================
# 2. POWERFUL ADMIN DASHBOARD COMMANDS
# ==========================================

@bot.message_handler(commands=['authlist'])
def admin_authlist(message):
    try:
        if message.from_user.id != ADMIN_ID: 
            bot.reply_to(message, "⚠️ <b>Access Denied:</b> You are not the bot owner.", parse_mode="HTML")
            return
            
        with closing(sqlite3.connect('users.db', check_same_thread=False)) as conn:
            users = conn.cursor().execute("SELECT user_id, phone_number, plan_type, expiry_date FROM users ORDER BY expiry_date DESC").fetchall()
        
        if not users: 
            bot.send_message(message.chat.id, "⚠️ No users found in database.", parse_mode="HTML")
            return

        now = datetime.datetime.now()
        active_users =[]
        expired_users =[]

        for u in users:
            exp_date = datetime.datetime.fromisoformat(u[3])
            phone = u[1] if u[1] else "No Phone"
            exp_str = exp_date.strftime("%Y-%m-%d")
            line = f"👤 <code>{u[0]}</code> | 📱 {phone} | <b>{u[2].upper()}</b> | Exp: {exp_str}\n"
            
            if exp_date > now: active_users.append(line)
            else: expired_users.append(line)

        full_lines =[]
        full_lines.append(f"📋 <b>Total Database ({len(users)} users):</b>\n\n")
        full_lines.append(f"🟢 <b>ACTIVE USERS ({len(active_users)}):</b>\n")
        if active_users: full_lines.extend(active_users)
        else: full_lines.append("<i>None</i>\n")
        
        full_lines.append(f"\n🔴 <b>EXPIRED USERS ({len(expired_users)}):</b>\n")
        if expired_users: full_lines.extend(expired_users)
        else: full_lines.append("<i>None</i>\n")

        chunk = ""
        for line in full_lines:
            if len(chunk) + len(line) > 3900:
                bot.send_message(message.chat.id, chunk, parse_mode="HTML")
                chunk = ""
            chunk += line
        if chunk: 
            bot.send_message(message.chat.id, chunk, parse_mode="HTML")
            
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error in /authlist:</b> {e}", parse_mode="HTML")


@bot.message_handler(commands=['userinfo'])
def admin_userinfo(message):
    try:
        if message.from_user.id != ADMIN_ID: 
            bot.reply_to(message, "⚠️ <b>Access Denied.</b>", parse_mode="HTML")
            return
            
        args = message.text.split()
        if len(args) == 2:
            target_id = int(args[1])
            with closing(sqlite3.connect('users.db', check_same_thread=False)) as conn:
                user = conn.cursor().execute("SELECT phone_number, plan_type, expiry_date, checks_used FROM users WHERE user_id=?", (target_id,)).fetchone()
            if user:
                phone, plan, exp, checks = user
                phone_str = phone if phone else "No Phone"
                exp_date = datetime.datetime.fromisoformat(exp).strftime('%Y-%m-%d %H:%M')
                bot.send_message(message.chat.id, f"👤 <b>User Info:</b> <code>{target_id}</code>\n📱 <b>Phone:</b> {phone_str}\n💳 <b>Plan:</b> {plan.upper()}\n📈 <b>Checks Used:</b> {checks}\n⏳ <b>Expires:</b> {exp_date}", parse_mode="HTML")
            else:
                bot.send_message(message.chat.id, "⚠️ User not found in database.", parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, "Usage: <code>/userinfo <user_id></code>", parse_mode="HTML")
            
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error in /userinfo:</b> {e}", parse_mode="HTML")


@bot.message_handler(commands=['addtime'])
def admin_addtime(message):
    try:
        if message.from_user.id != ADMIN_ID: 
            bot.reply_to(message, "⚠️ <b>Access Denied.</b>", parse_mode="HTML")
            return
            
        args = message.text.split()
        if len(args) != 3:
            bot.send_message(message.chat.id, "Usage: <code>/addtime <user_id> <days></code>\nExample: <code>/addtime 123456789 10</code>", parse_mode="HTML")
            return
            
        target_id = int(args[1])
        days = int(args[2])
        
        with closing(sqlite3.connect('users.db', check_same_thread=False)) as conn:
            with conn:
                c = conn.cursor()
                user = c.execute("SELECT expiry_date FROM users WHERE user_id=?", (target_id,)).fetchone()
                if not user:
                    bot.send_message(message.chat.id, "⚠️ User not found in DB.")
                    return
                
                current_exp = datetime.datetime.fromisoformat(user[0])
                if current_exp < datetime.datetime.now(): current_exp = datetime.datetime.now()
                new_exp = current_exp + datetime.timedelta(days=days)
                c.execute("UPDATE users SET expiry_date=? WHERE user_id=?", (new_exp.isoformat(), target_id))
                
        bot.send_message(message.chat.id, f"✅ Added {days} days to <code>{target_id}</code>.\nNew Expiry: {new_exp.strftime('%Y-%m-%d %H:%M')}", parse_mode="HTML")
        try: bot.send_message(target_id, f"🎁 <b>Bonus Time!</b>\nAdmin has added {days} days to your subscription!\nNew Expiry: {new_exp.strftime('%Y-%m-%d %H:%M')}", parse_mode="HTML")
        except: pass
        
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ ID and Days must be numbers.", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error in /addtime:</b> {e}", parse_mode="HTML")


@bot.message_handler(commands=['search'])
def admin_search(message):
    try:
        if message.from_user.id != ADMIN_ID: 
            bot.reply_to(message, "⚠️ <b>Access Denied.</b>", parse_mode="HTML")
            return
            
        args = message.text.split()
        if len(args) > 1:
            phone_query = args[1]
            with closing(sqlite3.connect('users.db', check_same_thread=False)) as conn:
                users = conn.cursor().execute("SELECT user_id, phone_number, plan_type FROM users WHERE phone_number LIKE ?", (f"%{phone_query}%",)).fetchall()
            if users:
                text = f"🔍 <b>Search Results for '{phone_query}':</b>\n\n"
                for u in users:
                    phone_str = u[1] if u[1] else "No Phone"
                    text += f"👤 ID: <code>{u[0]}</code> | 📱 {phone_str} | 💳 {u[2].upper()}\n"
                bot.send_message(message.chat.id, text, parse_mode="HTML")
            else:
                bot.send_message(message.chat.id, "⚠️ No users found matching that phone number.", parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, "Usage: <code>/search <phone_number></code>", parse_mode="HTML")
            
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error in /search:</b> {e}", parse_mode="HTML")


@bot.message_handler(commands=['auth'])
def admin_auth(message):
    try:
        if message.from_user.id != ADMIN_ID: 
            bot.reply_to(message, "⚠️ Access Denied.")
            return
        args = message.text.split()
        if len(args) > 1:
            try:
                target_id = int(args[1])
                send_plan_selection(message.chat.id, target_id)
            except ValueError:
                bot.send_message(message.chat.id, "⚠️ Invalid ID format. Must be numbers.", parse_mode="HTML")
        else:
            msg = bot.send_message(message.chat.id, "✍️ <b>Please send the User ID you want to authorize:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_auth_id)
    except Exception as e: bot.reply_to(message, f"Error: {e}")

def process_auth_id(message):
    if not message.text or message.text.startswith('/'):
        bot.send_message(message.chat.id, "⚠️ Authorization cancelled.", parse_mode="HTML")
        return
    try:
        target_id = int(message.text.strip())
        send_plan_selection(message.chat.id, target_id)
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Invalid ID format. Authorization cancelled.", parse_mode="HTML")

def send_plan_selection(chat_id, target_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🥉 Plan 1 (50 checks/wk) - 30 Days", callback_data=f"ask_plan1_{target_id}"),
        types.InlineKeyboardButton("🥈 Plan 2 (200 checks/wk) - 30 Days", callback_data=f"ask_plan2_{target_id}"),
        types.InlineKeyboardButton("👑 Unlimited (Unlimited) - 100 Days", callback_data=f"ask_unlimited_{target_id}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_auth")
    )
    bot.send_message(chat_id, f"⚙️ <b>Select a subscription plan for user:</b> <code>{target_id}</code>", parse_mode="HTML", reply_markup=markup)


# ==========================================
# 3. REGISTRATION HANDLER
# ==========================================
@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    try:
        user_id = message.from_user.id
        if message.contact is not None:
            if message.contact.user_id and message.contact.user_id != user_id:
                bot.send_message(message.chat.id, "⚠️ <b>Fraud Detected:</b> You must use the button below to share YOUR OWN contact.", parse_mode="HTML")
                return

            phone = message.contact.phone_number
            now = datetime.datetime.now()
            expiry = now + datetime.timedelta(days=2)
            
            with closing(sqlite3.connect('users.db', check_same_thread=False)) as conn:
                with conn:
                    c = conn.cursor()
                    # Safe insert
                    c.execute("INSERT OR IGNORE INTO users (user_id, phone_number, plan_type, expiry_date, week_start, checks_used) VALUES (?, ?, ?, ?, ?, ?)",
                              (user_id, phone, 'trial', expiry.isoformat(), now.isoformat(), 0))
            
            bot.send_message(message.chat.id, "✅ <b>Registration Successful!</b>\nYour 2-Day Free Trial is active. Menu unlocked below 👇", parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e: print(f"Contact Error: {e}")


# ==========================================
# 4. UNIVERSAL EXTRACTION CATCH-ALL
# ==========================================
@bot.message_handler(func=lambda message: True, content_types=['text', 'user_shared', 'users_shared', 'chat_shared', 'audio', 'photo', 'voice', 'video', 'document', 'sticker', 'animation', 'video_note', 'location', 'venue', 'dice', 'poll'])
def handle_all_requests(message):
    try:
        msg_data = message.json 

        # Handle User Extractions
        if 'users_shared' in msg_data or 'user_shared' in msg_data:
            user_id = message.from_user.id
            has_access, msg = check_access(user_id)
            if msg == "REGISTRATION_REQUIRED": return
            if not has_access:
                bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=get_contact_admin_markup())
                return

            users = msg_data.get('users_shared', {}).get('users',[]) if 'users_shared' in msg_data else [msg_data.get('user_shared')]
            req_id = msg_data.get('users_shared', {}).get('request_id') or msg_data.get('user_shared', {}).get('request_id')
            for u in users:
                target_id = u.get('user_id')
                name = safe_html(f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or "Unknown")
                username = safe_html(f"@{u['username']}" if 'username' in u else "None")
                icon = "🤖 Bot" if req_id == 2 else "👤 User"
                bot.send_message(message.chat.id, f"{icon}\n\n🆔 <b>ID:</b> <code>{target_id}</code>\n🔗 <b>Username:</b> {username}\n📝 <b>Name:</b> {name}\n📆 <b>Registered:</b> {estimate_date(target_id)}\n\n{get_ad_text()}", parse_mode="HTML")
            return

        # Handle Chat/Channel Extractions
        elif 'chat_shared' in msg_data:
            user_id = message.from_user.id
            has_access, msg = check_access(user_id)
            if msg == "REGISTRATION_REQUIRED": return
            if not has_access:
                bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=get_contact_admin_markup())
                return

            chat = msg_data['chat_shared']
            chat_id = chat.get('chat_id')
            title = safe_html(chat.get('title', 'Unknown'))
            username = safe_html(f"@{chat['username']}" if 'username' in chat else "None")
            icon = "📢 Channel" if chat.get('request_id') in[3, 5] else "👥 Group/Forum"
            bot.send_message(message.chat.id, f"{icon}\n\n🆔 <b>ID:</b> <code>{chat_id}</code>\n🔗 <b>Username:</b> {username}\n📝 <b>Title:</b> {title}\n📆 <b>Created:</b> {estimate_date(chat_id)}\n\n{get_ad_text()}", parse_mode="HTML")
            return

        # Handle Message Forwards
        if message.forward_from or message.forward_from_chat or message.forward_sender_name:
            user_id = message.from_user.id
            has_access, msg = check_access(user_id)
            if msg == "REGISTRATION_REQUIRED": return
            if not has_access:
                bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=get_contact_admin_markup())
                return

            if message.forward_from: target_id, name, t = message.forward_from.id, safe_html(message.forward_from.first_name), "👤 Forwarded User"
            elif message.forward_from_chat: target_id, name, t = message.forward_from_chat.id, safe_html(message.forward_from_chat.title), "📢 Forwarded Chat"
            elif message.forward_sender_name:
                bot.send_message(message.chat.id, f"👻 <b>Hidden Account</b>\n\nTelegram hides this ID due to their privacy settings.\n📝 <b>Name:</b> {safe_html(message.forward_sender_name)}", parse_mode="HTML")
                return
            bot.send_message(message.chat.id, f"↪️ <b>{t}</b>\n\n🆔 <b>Original ID:</b> <code>{target_id}</code>\n📝 <b>Name/Title:</b> {name}\n📆 <b>Est. Date:</b> {estimate_date(target_id)}", parse_mode="HTML")
            return

        # Handle Media Extractions
        meta, t_type = None, None
        if message.photo: meta, t_type = message.photo[-1].file_id, "🖼 Photo ID"
        elif message.sticker: meta, t_type = message.sticker.file_id, "🎃 Sticker ID"
        elif message.video: meta, t_type = message.video.file_id, "🎬 Video ID"
        elif message.document: meta, t_type = message.document.file_id, "📁 Document ID"
        elif message.audio: meta, t_type = message.audio.file_id, "🎵 Audio ID"
        elif message.voice: meta, t_type = message.voice.file_id, "🎤 Voice Note ID"
        elif message.animation: meta, t_type = message.animation.file_id, "🎞 GIF ID"
        elif message.video_note: meta, t_type = message.video_note.file_id, "📹 Video Note ID"
        elif message.poll: meta, t_type = message.poll.id, "📊 Poll ID"
        elif message.location: meta, t_type = f"Lat: {message.location.latitude}\nLong: {message.location.longitude}", "📍 Location Data"
        elif message.dice: meta, t_type = f"Emoji: {message.dice.emoji}\nValue: {message.dice.value}", "🎲 Dice Data"

        if meta:
            user_id = message.from_user.id
            has_access, msg = check_access(user_id)
            if msg == "REGISTRATION_REQUIRED": return
            if not has_access:
                bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=get_contact_admin_markup())
                return
                
            bot.reply_to(message, f"<b>{t_type}:</b>\n<code>{meta}</code>\n\n<i>(Tap to copy)</i>", parse_mode="HTML")
            return

        # Text Fallback to force Keyboard Menu
        if message.text and not message.text.startswith('/'):
            bot.send_message(message.chat.id, "🤖 <b>ID Extractor Ready!</b>\n\nTap the buttons below to extract an ID, or forward any message/file to me!", parse_mode="HTML", reply_markup=get_main_keyboard())

    except Exception as e: print(f"Extraction Guard Caught: {e}")


# ==========================================
# 5. BUTTON CALLBACK HANDLERS
# ==========================================
def guide_markup(main=True):
    m = types.InlineKeyboardMarkup(row_width=1)
    if main:
        m.add(types.InlineKeyboardButton("🔍 How to Extract IDs", callback_data="g_extract"),
              types.InlineKeyboardButton("📁 Getting Media/File IDs", callback_data="g_media"),
              types.InlineKeyboardButton("💳 Subscriptions & Limits", callback_data="g_subs"),
              types.InlineKeyboardButton("🔒 Privacy Policy", callback_data="g_privacy"))
    else: m.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="g_main"))
    return m

@bot.callback_query_handler(func=lambda call: True)
def master_callback(call):
    try:
        # --- GUIDE INTERFACE ---
        if call.data.startswith("g_"):
            if call.data == "g_main": text, m = "📖 <b>Ultimate Guide</b>\n\nChoose a topic below:", guide_markup(True)
            elif call.data == "g_extract": text, m = "🔍 <b>How to Extract IDs</b>\n\n<b>1:</b> Look at the bottom keyboard. Tap '👤 User', '📢 Channel', or '👥 Group' and select a chat.\n<b>2:</b> Forward ANY message to this bot to instantly reveal the original sender's ID!", guide_markup(False)
            elif call.data == "g_media": text, m = "📁 <b>Getting File IDs</b>\n\nSend any media file directly to this bot to get its Server File ID.\n\n<i>Supported: Photos, Videos, Stickers, Audio, Voice Notes, Documents, GIFs, Polls, and Locations!</i>", guide_markup(False)
            elif call.data == "g_subs": text, m = "💳 <b>Subscriptions</b>\n\nNew users get a 2-Day Free Trial. Limits reset automatically every 7 days.\n\nContact the Admin via the /start menu to purchase Plan 1 (50 checks/wk) or Plan 2 (200 checks/wk).", guide_markup(False)
            elif call.data == "g_privacy": text, m = "🔒 <b>Privacy</b>\n\nWe require your phone number upon registration strictly to prevent abuse and spam. It is stored securely and never shared.", guide_markup(False)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=m)
            return

        # --- ADMIN AUTHENTICATION INTERFACE ---
        if call.from_user.id != ADMIN_ID: 
            bot.answer_callback_query(call.id, "⚠️ Restricted Admin action.", show_alert=True)
            return

        if call.data.startswith("ask_"):
            parts = call.data.split('_')
            plan, target_id = parts[1], parts[2]
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("✅ CONFIRM YES", callback_data=f"confirm_{plan}_{target_id}"), 
                types.InlineKeyboardButton("❌ NO", callback_data="cancel_auth")
            )
            bot.edit_message_text(f"❓ <b>Confirm Action:</b>\nAre you sure you want to grant <b>{plan.upper()}</b> to <code>{target_id}</code>?", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)

        elif call.data == "cancel_auth":
            bot.edit_message_text("❌ <b>Action Cancelled.</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")

        elif call.data.startswith("confirm_"):
            bot.edit_message_text("⏳ <i>Processing authorization...</i>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
            
            parts = call.data.split('_')
            plan = parts[1]
            target_id = int(parts[2])
            
            now = datetime.datetime.now()
            days = 100 if plan == 'unlimited' else 30
            expiry = now + datetime.timedelta(days=days)

            with closing(sqlite3.connect('users.db', check_same_thread=False)) as conn:
                with conn:
                    c = conn.cursor()
                    # Look up phone safely
                    try:
                        existing = c.execute("SELECT phone_number FROM users WHERE user_id=?", (target_id,)).fetchone()
                        phone = existing[0] if existing else "Admin_Added"
                    except: phone = "Admin_Added"
                    
                    c.execute("REPLACE INTO users (user_id, phone_number, plan_type, expiry_date, week_start, checks_used) VALUES (?, ?, ?, ?, ?, ?)",
                              (target_id, phone, plan, expiry.isoformat(), now.isoformat(), 0))

            bot.edit_message_text(f"✅ <b>Success!</b>\nGranted <b>{plan.upper()}</b> to <code>{target_id}</code> for {days} days.", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
            try: bot.send_message(target_id, f"🎉 <b>Good News!</b>\nAdmin has granted you the <b>{plan.upper()}</b> subscription!\nEnjoy your premium access.", parse_mode="HTML")
            except: pass
            
    except Exception as e: print(f"Callback Guard Caught: {e}")

# ==========================================
# UI COMMAND MENU SETUP
# ==========================================
def setup_bot_commands():
    try:
        user_commands =[
            types.BotCommand("start", "🚀 Start the bot & menu"),
            types.BotCommand("myplan", "📋 Check active plan & limits"),
            types.BotCommand("guide", "📖 Detailed bot tutorial")
        ]
        bot.set_my_commands(user_commands, scope=types.BotCommandScopeDefault())
        
        admin_commands =[
            types.BotCommand("start", "🚀 Start the bot"),
            types.BotCommand("myplan", "📋 Check your admin plan"),
            types.BotCommand("guide", "📖 Detailed bot tutorial"),
            types.BotCommand("auth", "⚙️ Authorize a user ID"),
            types.BotCommand("authlist", "📋 View active & expired users"),
            types.BotCommand("userinfo", "👤 Check specific user info"),
            types.BotCommand("addtime", "⏳ Add bonus days to a user"),
            types.BotCommand("search", "🔍 Search user by phone")
        ]
        bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(ADMIN_ID))
        print("✅ Command Menus successfully set up in Telegram UI!")
    except Exception as e:
        print(f"⚠️ Could not set command menus: {e}")

# ==========================================
# INFINITE RESURRECTION LOOP
# ==========================================
print("🛡️ Mr_outlaw001's Ultimate Bot is now ONLINE!")
setup_bot_commands()

while True:
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"Network Interruption Caught: {e}. Resurrecting in 3 seconds...")
        time.sleep(3)
