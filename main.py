import os
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
import random

# تنظیمات
TOKEN = os.getenv("TELEGRAM_TOKEN")
WALLET_ADDRESS = "UQAZEfdfeu-hjMZK-GsjpwAGJxPugS3MnHN6LlmhpKgk-iLd"
ADMIN_ID = "7836825805"
REQUIRED_CHATS = ["@CoinTCoinTon", "@MyTonCoinT", "@MyToCoin"]

# اتصال به دیتابیس SQLite
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# ساخت جداول اگه وجود نداشته باشن
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        chances INTEGER DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        deposited INTEGER DEFAULT 0,
        username TEXT DEFAULT ''
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        tx_hash TEXT,
        status TEXT DEFAULT 'pending'
    )
''')
conn.commit()

# توابع کمکی برای دیتابیس
def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return {"user_id": user_id, "chances": 0, "referrals": 0, "deposited": 0, "username": ""}
    return {"user_id": user[0], "chances": user[1], "referrals": user[2], "deposited": user[3], "username": user[4]}

def update_user(user_id, data):
    existing_user = get_user(user_id)
    updated_user = {**existing_user, **data}
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, chances, referrals, deposited, username)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, updated_user["chances"], updated_user["referrals"], updated_user["deposited"], updated_user["username"]))
    conn.commit()

def add_transaction(user_id, amount, tx_hash):
    cursor.execute("INSERT INTO transactions (user_id, amount, tx_hash) VALUES (?, ?, ?)", (user_id, amount, tx_hash))
    conn.commit()

def get_total_deposited():
    cursor.execute("SELECT SUM(amount) FROM transactions")
    total = cursor.fetchone()[0]
    return total if total else 0

# بررسی عضویت
def check_membership(bot, user_id):
    for chat in REQUIRED_CHATS:
        try:
            member = bot.get_chat_member(chat_id=chat, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# منوها
def main_menu():
    keyboard = [
        [InlineKeyboardButton("Deposit TON", callback_data="deposit_menu"),
         InlineKeyboardButton("Invite Friends", callback_data="invite")],
        [InlineKeyboardButton("My Chances", callback_data="my_chances")]
    ]
    return InlineKeyboardMarkup(keyboard)

def deposit_menu():
    keyboard = [
        [InlineKeyboardButton("1 TON", callback_data="deposit_1"),
         InlineKeyboardButton("2 TON", callback_data="deposit_2"),
         InlineKeyboardButton("3 TON", callback_data="deposit_3")],
        [InlineKeyboardButton("4 TON", callback_data="deposit_4"),
         InlineKeyboardButton("5 TON", callback_data="deposit_5"),
         InlineKeyboardButton("6 TON", callback_data="deposit_6")],
        [InlineKeyboardButton("7 TON", callback_data="deposit_7"),
         InlineKeyboardButton("8 TON", callback_data="deposit_8"),
         InlineKeyboardButton("9 TON", callback_data="deposit_9")],
        [InlineKeyboardButton("10 TON", callback_data="deposit_10")]
    ]
    return InlineKeyboardMarkup(keyboard)

# دستورات بات
def start(update, context):
    user_id = update.message.from_user.id
    bot = context.bot
    args = context.args

    if not check_membership(bot, user_id):
        keyboard = [[InlineKeyboardButton("Join Channels", url=f"https://t.me/{chat[1:]}")] for chat in REQUIRED_CHATS]
        update.message.reply_text(
            "Please join the following channels first:\n\nAfter joining, press /start again.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if args and args[0].startswith("ref_"):
        referrer_id = int(args[0].split("_")[1])
        if referrer_id != user_id:
            referrer = get_user(referrer_id)
            referrals = referrer["referrals"] + 1
            update_user(referrer_id, {"referrals": referrals})
            if referrals >= 10 and referrer["deposited"] >= 1:
                update_user(referrer_id, {"chances": referrer["chances"] + 1})
                bot.send_message(referrer_id, "Congrats! You earned 1 extra chance for inviting 10 friends.")

    update.message.reply_text("Welcome! Please select an option below:", reply_markup=main_menu())

def button(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    bot = context.bot

    if query.data == "deposit_menu":
        query.edit_message_text("Select the amount of TON to deposit:", reply_markup=deposit_menu())
    elif query.data.startswith("deposit_"):
        amount = int(query.data.split("_")[1])
        query.edit_message_text(
            f"Please send {amount} TON to this wallet:\n`{WALLET_ADDRESS}`\n\nAfter sending, reply with your transaction hash.",
            parse_mode="Markdown"
        )
        context.user_data["pending_deposit"] = amount
    elif query.data == "invite":
        invite_link = f"https://t.me/{bot.username}?start=ref_{user_id}"
        query.edit_message_text(f"Your invite link:\n{invite_link}\n\nInvite 10 friends to earn an extra chance (requires at least 1 TON deposit).")
    elif query.data == "my_chances":
        user = get_user(user_id)
        query.edit_message_text(f"You currently have {user['chances']} chances.")

def handle_tx_hash(update, context):
    if "pending_deposit" not in context.user_data:
        update.message.reply_text("Please select an amount first using the Deposit TON option.")
        return

    tx_hash = update.message.text
    amount = context.user_data["pending_deposit"]
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "No Username"

    user = get_user(user_id)
    new_deposited = user["deposited"] + amount
    new_chances = user["chances"] + amount
    update_user(user_id, {"deposited": new_deposited, "chances": new_chances, "username": username})
    add_transaction(user_id, amount, tx_hash)

    context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"New Deposit:\nUser ID: {user_id}\nUsername: @{username}\nAmount: {amount} TON\nTX Hash: {tx_hash}"
    )
    update.message.reply_text("Thank you! Your deposit is under review. Your chances have been updated.")
    del context.user_data["pending_deposit"]

    total_deposited = get_total_deposited()
    if total_deposited >= 500:
        run_lottery(context.bot)

def run_lottery(bot):
    cursor.execute("SELECT user_id FROM users WHERE chances > 0")
    eligible_users = [row[0] for row in cursor.fetchall()]
    if len(eligible_users) < 10:
        return

    winners = random.sample(eligible_users, 10)
    prize_per_winner = (500 * 0.8) / 10
    admin_share = 500 * 0.2

    for winner_id in winners:
        bot.send_message(winner_id, f"Congratulations! You won {prize_per_winner} TON in the lottery!")
    
    bot.send_message(
        ADMIN_ID,
        f"Lottery completed!\nWinners: {', '.join([str(w) for w in winners])}\nPrize per winner: {prize_per_winner} TON\nAdmin share: {admin_share} TON"
    )
    # ریست دیتابیس بعد از قرعه‌کشی
    cursor.execute("UPDATE users SET chances = 0, deposited = 0, referrals = 0")
    cursor.execute("DELETE FROM transactions")
    conn.commit()

# راه‌اندازی بات
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_tx_hash))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()