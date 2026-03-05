import telebot
from telebot import types
import sqlite3
import datetime
import json

# ==========================================
# CONFIGURATION - CHANGE THESE!
# ==========================================
BOT_TOKEN = "8575370561:AAGpOu1R0zSRsaqBaPLI8klr_C4EXt0Tb1k" # <-- Put your token here
ADMIN_ID = 6915757343  # Your Admin ID
ADMIN_USERNAME = "@Mr_outlaw001" # Replace with your Telegram Username
# ==========================================

bot = telebot.TeleBot(BOT_TOKEN)

# --- DATABASE SETUP ---
def init_db():
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY, plan_type TEXT, expiry_date TEXT, week_start TEXT, checks_used INTEGER)''')
        conn.commit()

init_db()

# --- HELPER FUNCTIONS ---
def escape_md(text):
    """Prevents the bot from crashing when a username has an underscore '_' or special character"""
    if not text: return ""
    return str(text).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")

def estimate_date(chat_id):
    """Estimates date for Users AND Channels/Groups (handling negative IDs)"""
    try:
        chat_id_str = str(chat_id)
        if chat_id_str.startswith("-100"): real_id = int(chat_id_str[4:])
        elif chat_id_str.startswith("-"): real_id = int(chat_id_str[1:])
        else: real_id = int(chat_id)
    except:
        real_id = 9999999999

    if real_id < 100000000: return "2013 - 2014"
    elif real_id < 500000000: return "2015 - 2017"
    elif real_id < 1000000000: return "2018 - 2019"
    elif real_id < 2000000000: return "2020 - 2021"
    elif real_id < 5000000000: return "2022"
    elif real_id < 6000000000: return "January 2023"
    elif real_id < 7000000000: return "Late 2023"
    else: return "2024 - Present"

def get_ad_text():
    return (
        "🧠 **Explanations and answers**\n"
        "Free AI →[DeepSeek](https://t.me/DeepSeek) & [ChatGPT](https://t.me/ChatGPT)\n\n"
        "🖼 **Visualize your ideas**\n"
        "Make Image → [NanoBanana](https://t.me/NanoBanana)"
    )

def get_contact_admin_markup():
    markup = types.InlineKeyboardMarkup()
    admin_url = f"https://t.me/{ADMIN_USERNAME.replace('@', '')}"
    markup.add(types.InlineKeyboardButton("👨‍💻 Contact Admin", url=admin_url))
    return markup

# --- RAW JSON KEYBOARD INJECTION ---
def get_main_keyboard():
    admin_rights = {
        "is_anonymous": False, "can_manage_chat": True, "can_delete_messages": False,
        "can_manage_video_chats": False, "can_restrict_members": False, "can_promote_members": False,
        "can_change_info": False, "can_invite_users": False, "can_post_messages": False,
        "can_edit_messages": False, "can_pin_messages": False, "can_manage_topics": False
    }

    raw_keyboard = {
        "keyboard": [[
                {"text": "👤 User", "request_users": {"request_id": 1, "user_is_bot": False, "request_name": True, "request_username": True}},
                {"text": "🤖 Bot", "request_users": {"request_id": 2, "user_is_bot": True, "request_name": True, "request_username": True}}
            ],[
                {"text": "📢 Channel", "request_chat": {"request_id": 3, "chat_is_channel": True, "request_title": True, "request_username": True}},
                {"text": "👥 Group", "request_chat": {"request_id": 4, "chat_is_channel": False, "chat_is_forum": False, "request_title": True, "request_username": True}}
            ],[
                {"text": "🏠 My Channel", "request_chat": {"request_id": 5, "chat_is_channel": True, "user_administrator_rights": admin_rights, "request_title": True, "request_username": True}},
                {"text": "🏠 My Group", "request_chat": {"request_id": 6, "chat_is_channel": False, "chat_is_forum": False, "user_administrator_rights": admin_rights, "request_title": True, "request_username": True}}
            ],[
                {"text": "💬 Forum", "request_chat": {"request_id": 7, "chat_is_channel": False, "chat_is_forum": True, "request_title": True, "request_username": True}},
                {"text": "💬 My Forum", "request_chat": {"request_id": 8, "chat_is_channel": False, "chat_is_forum": True, "user_administrator_rights": admin_rights, "request_title": True, "request_username": True}}
            ]
        ],
        "resize_keyboard": True
    }
    return json.dumps(raw_keyboard)


# --- SUBSCRIPTION LOGIC ---
def check_or_create_user(user_id):
    if user_id == ADMIN_ID:
        return True, ""

    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("SELECT plan_type, expiry_date, week_start, checks_used FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()
        now = datetime.datetime.now()

        if not user:
            expiry = now + datetime.timedelta(days=2)
            c.execute("INSERT INTO users (user_id, plan_type, expiry_date, week_start, checks_used) VALUES (?, ?, ?, ?, ?)",
                      (user_id, 'trial', expiry.isoformat(), now.isoformat(), 0))
            conn.commit()
            return True, "🎉 **Welcome!** You've been granted a **2-Day Free Trial**.\nEnjoy unlimited checks for 48 hours!"

        plan_type, expiry_str, week_start_str, checks_used = user
        expiry_date = datetime.datetime.fromisoformat(expiry_str)
        week_start = datetime.datetime.fromisoformat(week_start_str)

        if now > expiry_date:
            return False, f"❌ Your **{plan_type.upper()}** subscription has expired. Please contact the admin to renew."

        if now > week_start + datetime.timedelta(days=7):
            week_start = now
            checks_used = 0
            c.execute("UPDATE users SET week_start=?, checks_used=? WHERE user_id=?", (week_start.isoformat(), checks_used, user_id))
            conn.commit()

        limit = None
        if plan_type == 'plan1': limit = 50
        elif plan_type == 'plan2': limit = 200
        
        if limit and checks_used >= limit:
            return False, f"⚠️ You have reached your weekly limit of **{limit} checks**. Please wait for the next week or upgrade your plan."

        c.execute("UPDATE users SET checks_used=? WHERE user_id=?", (checks_used + 1, user_id))
        conn.commit()
        return True, ""


# ==========================================
# USER COMMANDS
# ==========================================

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "📖 **ID Bot User Guide**\n\n"
        "This bot allows you to easily extract Telegram IDs and Registration Dates. "
        "Simply use our interactive menu at the bottom of your screen, or **Forward a message** to me!\n\n"
        "**How to use:**\n"
        "1. Tap any button on the custom keyboard (e.g., '👤 User', '📢 Channel').\n"
        "2. Or, forward any message/photo/video from a user or channel to me.\n"
        "3. The bot will instantly reply with their full details!\n\n"
        "**Available Commands:**\n"
        "👉 `/start` - Open the main menu & keyboard\n"
        "👉 `/myplan` - Check your subscription limits and expiry\n"
        "👉 `/help` - Show this guide\n"
        "👉 `/contact` - Message the admin for support/upgrades"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['myplan', 'plan'])
def check_my_plan(message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        bot.send_message(message.chat.id, "👑 **Admin Status**\nYou are the Admin. You have unlimited lifetime access to all features.", parse_mode="Markdown")
        return

    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("SELECT plan_type, expiry_date, week_start, checks_used FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()

    if not user:
        bot.send_message(message.chat.id, "You don't have an active plan yet. Send /start to activate your 2-Day Free Trial!", parse_mode="Markdown")
        return

    plan_type, expiry_str, week_start_str, checks_used = user
    expiry_date = datetime.datetime.fromisoformat(expiry_str)
    now = datetime.datetime.now()

    status = "❌ **Expired**" if now > expiry_date else "✅ **Active**"
    limit = "50" if plan_type == 'plan1' else "200" if plan_type == 'plan2' else "Unlimited"
    formatted_date = expiry_date.strftime("%Y-%m-%d %H:%M:%S")

    text = f"📋 **Your Subscription Details**\n\n**Status:** {status}\n**Current Plan:** {plan_type.upper()}\n"
    text += f"**Weekly Usage:** {checks_used} / {limit} checks\n**Expiry Date:** `{formatted_date}`\n\n"

    markup = types.InlineKeyboardMarkup()
    if now > expiry_date or limit != "Unlimited":
        admin_url = f"https://t.me/{ADMIN_USERNAME.replace('@', '')}"
        markup.add(types.InlineKeyboardButton("🚀 Upgrade / Renew Plan", url=admin_url))

    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['start', 'startfresh'])
def send_welcome(message):
    my_id = message.from_user.id
    has_access, msg = check_or_create_user(my_id)
    
    if not has_access:
        bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=get_contact_admin_markup())
        return
    if "Welcome!" in msg:
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    welcome_text = (
        "👋 **ID Bot**\n\n"
        "I can help you find the ID and **Registration Date** of any Telegram account, channel, or group.\n\n"
        "👇 **Forward me a message, or tap a button below:**"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    my_username = f"@{message.from_user.username}" if message.from_user.username else "None"
    my_name = message.from_user.first_name + (f" {message.from_user.last_name}" if message.from_user.last_name else "")
    
    # Escape characters to prevent crash
    my_username = escape_md(my_username)
    my_name = escape_md(my_name)

    info_text = f"👤 **User**\n\n🆔 **ID:** `{my_id}`\n🔗 **Username:** {my_username}\n📝 **Name:** {my_name}\n"
    info_text += f"🏳️ **Lang:** {message.from_user.language_code or 'EN'} 🇺🇸\n\n"
    info_text += f"📆 **Registered:** {estimate_date(my_id)}\n*(Verified by @idbot)*\n\n" + get_ad_text()

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"📋 Copy {my_id}", callback_data=f"copy_{my_id}"))
    markup.add(types.InlineKeyboardButton("🚀 Share ID", switch_inline_query=str(my_id)))
    bot.send_message(message.chat.id, info_text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)

@bot.message_handler(commands=['contact'])
def contact_admin(message):
    bot.send_message(message.chat.id, "Need help or want to buy a subscription?", reply_markup=get_contact_admin_markup())


# ==========================================
# ADMIN COMMANDS 
# ==========================================
@bot.message_handler(commands=['auth'])
def admin_auth(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split()[1])
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("Plan 1 (50 checks/wk for 30 days)", callback_data=f"ask_plan1_{target_id}"),
            types.InlineKeyboardButton("Plan 2 (200 checks/wk for 30 days)", callback_data=f"ask_plan2_{target_id}"),
            types.InlineKeyboardButton("Unlimited (100 days)", callback_data=f"ask_unlimited_{target_id}")
        )
        bot.send_message(message.chat.id, f"Select a plan for user `{target_id}`:", parse_mode="Markdown", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, "Usage: `/auth <user_id>`", parse_mode="Markdown")

@bot.message_handler(commands=['unauth'])
def admin_unauth(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split()[1])
        with sqlite3.connect('users.db') as conn:
            c = conn.cursor()
            c.execute("DELETE FROM users WHERE user_id=?", (target_id,))
            conn.commit()
        bot.send_message(message.chat.id, f"✅ User `{target_id}` unauthorized.")
    except:
        bot.send_message(message.chat.id, "Usage: `/unauth <user_id>`", parse_mode="Markdown")

@bot.message_handler(commands=['users'])
def admin_users(message):
    if message.from_user.id != ADMIN_ID: return
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, plan_type, checks_used, expiry_date FROM users")
        users = c.fetchall()
    if not users:
        bot.send_message(message.chat.id, "No users found in database.")
        return
    text = "📋 **Authorized Users List:**\n\n"
    for u in users:
        exp_date = datetime.datetime.fromisoformat(u[3]).strftime("%Y-%m-%d")
        text += f"👤 `{u[0]}` | **{u[1]}** | Used: {u[2]} | Exp: {exp_date}\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


# ==========================================
# CATCH ALL SHARED DATA & FORWARDS
# ==========================================
# List of all content types so it can process forwarded photos, videos, etc.
ALL_TYPES =['text', 'audio', 'document', 'photo', 'sticker', 'video', 'video_note', 'voice', 'location', 'contact', 'user_shared', 'users_shared', 'chat_shared', 'animation', 'poll', 'dice']

@bot.message_handler(func=lambda message: True, content_types=ALL_TYPES)
def handle_all_messages(message):
    """Broadband handler to catch Forwarded messages and Keyboard Shared Requests."""
    try:
        user_id = message.from_user.id
        has_access, msg = check_or_create_user(user_id)
        if not has_access:
            bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=get_contact_admin_markup())
            return
            
        msg_data = message.json 
        
        # -----------------------------------------------------------------
        # 1. PROCESSING FORWARDED MESSAGES (New Telegram API & Old API support)
        # -----------------------------------------------------------------
        is_forward = False
        f_id, f_name, f_user, f_type, is_hidden = None, "Unknown", "None", None, False
        
        # Check Telegram API v7.0+ Forward format
        if 'forward_origin' in msg_data:
            is_forward = True
            origin = msg_data['forward_origin']
            t = origin.get('type')
            
            if t == 'user':
                u = origin.get('sender_user', {})
                f_id = u.get('id')
                f_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                f_user = f"@{u.get('username')}" if u.get('username') else "None"
                f_type = "🤖 Bot" if u.get('is_bot') else "👤 User"
            elif t == 'hidden_user':
                is_hidden = True
                f_name = origin.get('sender_user_name', 'Unknown')
            elif t in ['chat', 'channel']:
                c = origin.get('sender_chat') or origin.get('chat', {})
                f_id = c.get('id')
                f_name = c.get('title', 'Unknown')
                f_user = f"@{c.get('username')}" if c.get('username') else "None"
                f_type = "📢 Channel" if c.get('type', t) == 'channel' else "👥 Group"
                
        # Check Telegram API < v7.0 Forward format (Fallback)
        elif 'forward_from' in msg_data:
            is_forward = True
            u = msg_data['forward_from']
            f_id = u.get('id')
            f_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
            f_user = f"@{u.get('username')}" if u.get('username') else "None"
            f_type = "🤖 Bot" if u.get('is_bot') else "👤 User"
        elif 'forward_from_chat' in msg_data:
            is_forward = True
            c = msg_data['forward_from_chat']
            f_id = c.get('id')
            f_name = c.get('title', 'Unknown')
            f_user = f"@{c.get('username')}" if c.get('username') else "None"
            f_type = "📢 Channel" if c.get('type') == 'channel' else "👥 Group"
        elif 'forward_sender_name' in msg_data:
            is_forward = True
            is_hidden = True
            f_name = msg_data['forward_sender_name']

        # If we successfully detected a forward, send the results!
        if is_forward:
            if is_hidden:
                text = f"❌ **Hidden User**\n\nThis user has hidden their forwarded messages in their privacy settings. I cannot extract their ID or Registration Date.\n\n📝 **Hidden Name:** {escape_md(f_name)}"
                bot.reply_to(message, text, parse_mode="Markdown")
                return
                
            f_name = escape_md(f_name)
            f_user = escape_md(f_user)
            
            text = f"**{f_type}** (Forwarded)\n\n🆔 **ID:** `{f_id}`\n"
            if f_user != "None": text += f"🔗 **Username:** {f_user}\n"
            text += f"📝 **Name/Title:** {f_name}\n\n"
            text += f"📆 **Registered/Created:** {estimate_date(f_id)}\n\n" + get_ad_text()
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"📋 Copy {f_id}", callback_data=f"copy_{f_id}"))
            markup.add(types.InlineKeyboardButton("🚀 Share ID", switch_inline_query=str(f_id)))

            bot.reply_to(message, text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)
            return

        # -----------------------------------------------------------------
        # 2. PROCESSING KEYBOARD SHARED USERS & BOTS
        # -----------------------------------------------------------------
        if 'users_shared' in msg_data or 'user_shared' in msg_data:
            users = msg_data.get('users_shared', {}).get('users',[]) if 'users_shared' in msg_data else[msg_data.get('user_shared')]
            req_id = msg_data.get('users_shared', {}).get('request_id') or msg_data.get('user_shared', {}).get('request_id')
                
            for u in users:
                target_id = u.get('user_id')
                name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or "Unknown"
                username = f"@{u['username']}" if 'username' in u else "None"
                
                if name == "Unknown" and username == "None":
                    try:
                        info = bot.get_chat(target_id)
                        name = info.first_name + (f" {info.last_name}" if info.last_name else "")
                        username = f"@{info.username}" if info.username else "None"
                    except: pass
                    
                name = escape_md(name)
                username = escape_md(username)
                
                is_bot = (req_id == 2)
                shared_type = "Bot" if is_bot else "User"
                icon = "🤖" if is_bot else "👤"

                text = f"{icon} **{shared_type}**\n\n🆔 **ID:** `{target_id}`\n🔗 **Username:** {username}\n📝 **Name:** {name}\n"
                text += f"\n📆 **Registered:** {estimate_date(target_id)}\n\n" + get_ad_text()

                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(f"📋 Copy {target_id}", callback_data=f"copy_{target_id}"))
                markup.add(types.InlineKeyboardButton("🚀 Share ID", switch_inline_query=str(target_id)))

                bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)

        # -----------------------------------------------------------------
        # 3. PROCESSING KEYBOARD SHARED CHANNELS, GROUPS & FORUMS
        # -----------------------------------------------------------------
        elif 'chat_shared' in msg_data:
            chat = msg_data['chat_shared']
            chat_id = chat.get('chat_id')
            req_id = chat.get('request_id')
            title = chat.get('title', 'Unknown')
            username = f"@{chat['username']}" if 'username' in chat else "None"
            
            if title == "Unknown" and username == "None":
                try:
                    info = bot.get_chat(chat_id)
                    title = info.title or "Unknown"
                    username = f"@{info.username}" if info.username else "None"
                except: pass

            title = escape_md(title)
            username = escape_md(username)

            if req_id in[3, 5]: chat_type, icon = ("Channel", "📢")
            elif req_id in[4, 6]: chat_type, icon = ("Group", "👥")
            else: chat_type, icon = ("Forum", "💬")

            text = f"{icon} **{chat_type}**\n\n🆔 **ID:** `{chat_id}`\n"
            if username != "None": text += f"🔗 **Username:** {username}\n"
            text += f"📝 **Title:** {title}\n\n"
            text += f"📆 **Created:** {estimate_date(chat_id)}\n\n"

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"📋 Copy {chat_id}", callback_data=f"copy_{chat_id}"))
            markup.add(types.InlineKeyboardButton("🚀 Share ID", switch_inline_query=str(chat_id)))

            bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
            
    except Exception as e:
        print(f"Error processing message: {e}")

# ==========================================
# CALLBACKS
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data.startswith("copy_"):
        bot.answer_callback_query(call.id, "ID Copied! (Tap the ID text above to copy it to clipboard)", show_alert=True)
    elif call.data.startswith("check_date_"):
        bot.answer_callback_query(call.id, "Cannot fetch precise registration dates for shared users.", show_alert=True)
    
    elif call.data.startswith("ask_"):
        if call.from_user.id != ADMIN_ID: return
        plan, target_id = call.data.split('_')[1], call.data.split('_')[2]
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ YES", callback_data=f"confirm_{plan}_{target_id}"),
            types.InlineKeyboardButton("❌ NO", callback_data="cancel_auth")
        )
        bot.edit_message_text(f"Are you sure you want to grant **{plan.upper()}** to user `{target_id}`?", 
                              chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              parse_mode="Markdown", reply_markup=markup)

    elif call.data == "cancel_auth":
        if call.from_user.id != ADMIN_ID: return
        bot.edit_message_text("❌ Authorization cancelled.", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif call.data.startswith("confirm_"):
        if call.from_user.id != ADMIN_ID: return
        plan, target_id = call.data.split('_')[1], int(call.data.split('_')[2])
        now = datetime.datetime.now()
        days = 100 if plan == 'unlimited' else 30
        expiry = now + datetime.timedelta(days=days)

        with sqlite3.connect('users.db') as conn:
            c = conn.cursor()
            c.execute("REPLACE INTO users (user_id, plan_type, expiry_date, week_start, checks_used) VALUES (?, ?, ?, ?, ?)",
                      (target_id, plan, expiry.isoformat(), now.isoformat(), 0))
            conn.commit()

        bot.edit_message_text(f"✅ Successfully granted **{plan.upper()}** to `{target_id}` for {days} days.", 
                              chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        try: bot.send_message(target_id, f"🎉 **Good News!**\nThe Admin has granted you the **{plan.upper()}** subscription for {days} days!\nEnjoy your access. Send /myplan to check details.", parse_mode="Markdown")
        except: pass

print("🤖 ID Bot initialized successfully. Waiting for requests...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
