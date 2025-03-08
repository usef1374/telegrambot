import os
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
import random
import logging

# تنظیم لاگ برای دیباگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# تنظیمات
TOKEN = os.getenv("TELEGRAM_TOKEN")
WALLET_ADDRESS = "UQAZEfdfeu-hjMZK-GsjpwAGJxPugS3MnHN6LlmhpKgk-iLd"
ADMIN_ID = "7836825805"
SUPPORT_ID = "7836825805"  # آیدی پشتیبانی (در اینجا ادمین)
REQUIRED_CHATS = ["@CoinTCoinTon", "@MyTonCoinT", "@MyToCoin"]

# اتصال به دیتابیس SQLite
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# ساخت جداول
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        chances INTEGER DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        deposited INTEGER DEFAULT 0,
        username TEXT DEFAULT '',
        wallet_address TEXT DEFAULT ''
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        status TEXT DEFAULT 'confirmed'
    )
''')
conn.commit()

# توابع دیتابیس
def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return {"user_id": user_id, "chances": 0, "referrals": 0, "deposited": 0, "username": "", "wallet_address": ""}
    return {"user_id": user[0], "chances": user[1], "referrals": user[2], "deposited": user[3], "username": user[4], "wallet_address": user[5]}

def update_user(user_id, data):
    existing_user = get_user(user_id)
    updated_user = {**existing_user, **data}
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, chances, referrals, deposited, username, wallet_address)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, updated_user["chances"], updated_user["referrals"], updated_user["deposited"], updated_user["username"], updated_user["wallet_address"]))
    conn.commit()

def add_transaction(user_id, amount):
    cursor.execute("INSERT INTO transactions (user_id, amount) VALUES (?, ?)", (user_id, amount))
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
                logger.info(f"User {user_id} is not a member of {chat}. Status: {member.status}")
                return False
        except Exception as e:
            logger.error(f"Error checking membership for {chat}: {str(e)}")
            return False
    return True

def is_member(bot, user_id, chat):
    try:
        member = bot.get_chat_member(chat_id=chat, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# منوها
def main_menu():
    keyboard = [
        [InlineKeyboardButton("💸 Deposit TON", callback_data="deposit_menu"),
         InlineKeyboardButton("👥 Invite Friends", callback_data="invite")],
        [InlineKeyboardButton("🎲 My Chances", callback_data="my_chances"),
         InlineKeyboardButton("📞 Support", url=f"https://t.me/{SUPPORT_ID}")],
    ]
    return InlineKeyboardMarkup(keyboard)

def deposit_menu():
    keyboard = [
        [InlineKeyboardButton("1 TON 💰", callback_data="deposit_1"),
         InlineKeyboardButton("2 TON 💰", callback_data="deposit_2"),
         InlineKeyboardButton("3 TON 💰", callback_data="deposit_3")],
        [InlineKeyboardButton("4 TON 💰", callback_data="deposit_4"),
         InlineKeyboardButton("5 TON 💰", callback_data="deposit_5"),
         InlineKeyboardButton("6 TON 💰", callback_data="deposit_6")],
        [InlineKeyboardButton("7 TON 💰", callback_data="deposit_7"),
         InlineKeyboardButton("8 TON 💰", callback_data="deposit_8"),
         InlineKeyboardButton("9 TON 💰", callback_data="deposit_9")],
        [InlineKeyboardButton("10 TON 💰", callback_data="deposit_10")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def join_channels_menu():
    keyboard = [
        [InlineKeyboardButton(f"📢 Join {chat}", url=f"https://t.me/{chat[1:]}")] for chat in REQUIRED_CHATS
    ]
    keyboard.append([InlineKeyboardButton("✅ Submit", callback_data="check_membership")])
    return InlineKeyboardMarkup(keyboard)

# دستورات بات
def start(update, context):
    user_id = update.message.from_user.id
    bot = context.bot
    args = context.args

    if check_membership(bot, user_id):
        handle_membership_success(update, context, args)
    else:
        update.message.reply_text(
            "🎉 Welcome! Join these channels to get started:",
            reply_markup=join_channels_menu()
        )

def handle_membership_success(update, context, args=None):
    user_id = update.message.from_user.id
    bot = context.bot

    if args and len(args) > 0 and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].split("_")[1])
            if referrer_id != user_id:
                referrer = get_user(referrer_id)
                referrals = referrer["referrals"] + 1
                update_user(referrer_id, {"referrals": referrals})
                bot.send_message(
                    referrer_id,
                    f"👤 You invited someone! Your total referrals: {referrals}"
                )
                logger.info(f"Referral added for user {referrer_id}. Total referrals: {referrals}")
        except (ValueError, IndexError) as e:
            logger.error(f"Error processing referral link for user {user_id}: {str(e)}")

    update.message.reply_text("🎊 Welcome aboard! What would you like to do?", reply_markup=main_menu())

def button(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    bot = context.bot

    try:
        query.answer()
    except Exception as e:
        logger.error(f"Failed to answer callback query for user {user_id}: {str(e)}")
        pass

    try:
        if query.data == "check_membership":
            if check_membership(bot, user_id):
                query.edit_message_text("✅ Awesome! You're all set!", reply_markup=main_menu())
            else:
                missing_chats = [chat for chat in REQUIRED_CHATS if not is_member(bot, user_id, chat)]
                query.edit_message_text(
                    f"⚠️ Please join these channels first:\n{', '.join(missing_chats)}",
                    reply_markup=join_channels_menu()
                )
        elif query.data == "deposit_menu":
            query.edit_message_text("💸 How much TON do you want to deposit?", reply_markup=deposit_menu())
        elif query.data.startswith("deposit_"):
            amount = int(query.data.split("_")[1])
            context.user_data["pending_deposit"] = amount
            query.edit_message_text(
                "💼 Please send your wallet address:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_deposit")]])
            )
            context.user_data["waiting_for_wallet"] = True
        elif query.data == "invite":
            user = get_user(user_id)
            invite_link = f"https://t.me/{bot.username}?start=ref_{user_id}"
            keyboard = [
                [InlineKeyboardButton("📤 Share Invite Link", url=f"https://t.me/share/url?url={invite_link}")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
            ]
            query.edit_message_text(
                f"👥 Invite friends!\nYour link: `{invite_link}`\nTotal referrals: {user['referrals']}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif query.data == "my_chances":
            user = get_user(user_id)
            query.edit_message_text(
                f"🎲 You have {user['chances']} chances!\nDeposited: {user['deposited']} TON\nReferrals: {user['referrals']}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
            )
        elif query.data == "back_to_main":
            query.edit_message_text("🎊 Back to main menu:", reply_markup=main_menu())
        elif query.data == "back_to_deposit":
            query.edit_message_text("💸 How much TON do you want to deposit?", reply_markup=deposit_menu())
            if "waiting_for_wallet" in context.user_data:
                del context.user_data["waiting_for_wallet"]
    except Exception as e:
        logger.error(f"Error processing callback for user {user_id}: {str(e)}")
        query.edit_message_text("⚠️ Something went wrong. Please try again.")

def handle_message(update, context):
    user_id = update.message.from_user.id
    bot = context.bot
    text = update.message.text

    if "waiting_for_wallet" in context.user_data and context.user_data["waiting_for_wallet"]:
        wallet_address = text
        amount = context.user_data["pending_deposit"]
        username = update.message.from_user.username or "No Username"
        user = get_user(user_id)
        new_deposited = user["deposited"] + amount
        new_chances = user["chances"] + amount  # شانس بر اساس واریزی
        update_user(user_id, {"wallet_address": wallet_address, "deposited": new_deposited, "chances": new_chances, "username": username})
        add_transaction(user_id, amount)

        bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💸 New Deposit:\nUser ID: {user_id}\nUsername: @{username}\nWallet Address: {wallet_address}\nAmount: {amount} TON"
        )
        update.message.reply_text(
            f"✅ Deposit of {amount} TON confirmed!\nSend {amount} TON to:\n`{WALLET_ADDRESS}`",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        del context.user_data["waiting_for_wallet"]

        total_deposited = get_total_deposited()
        if total_deposited >= 500:
            run_lottery(bot)
    else:
        update.message.reply_text("⚠️ Please select an amount from the Deposit menu first!", reply_markup=main_menu())

def run_lottery(bot):
    cursor.execute("SELECT user_id, chances, referrals, wallet_address FROM users WHERE chances > 0 OR referrals > 0")
    eligible_users = cursor.fetchall()
    if not eligible_users:
        return

    # محاسبه وزن هر کاربر (شانس + زیرمجموعه)
    weighted_users = []
    for user in eligible_users:
        user_id, chances, referrals, wallet = user
        weight = chances + referrals  # وزن = شانس + تعداد زیرمجموعه
        weighted_users.extend([{"user_id": user_id, "wallet": wallet}] * weight)

    if len(weighted_users) < 10:
        return

    winners = random.sample(weighted_users, 10)
    prize_per_winner = (500 * 0.8) / 10  # 80% برای برندگان
    admin_share = 500 * 0.2  # 20% برای ادمین

    # ارسال پیام به برندگان
    for winner in winners:
        bot.send_message(
            winner["user_id"],
            f"🏆 Congrats! You won {prize_per_winner} TON in the lottery!\nPlease wait for admin to send your prize."
        )

    # ارسال لیست برندگان به ادمین
    winners_info = "\n".join([f"User ID: {w['user_id']} - Wallet: {w['wallet']}" for w in winners])
    bot.send_message(
        ADMIN_ID,
        f"🎉 Lottery completed!\nWinners (10):\n{winners_info}\nPrize per winner: {prize_per_winner} TON\nAdmin share: {admin_share} TON"
    )

    # ریست دیتابیس
    cursor.execute("UPDATE users SET chances = 0, deposited = 0, referrals = 0")
    cursor.execute("DELETE FROM transactions")
    conn.commit()

def set_chances(update, context):
    user_id = update.message.from_user.id
    if str(user_id) != ADMIN_ID:
        update.message.reply_text("⚠️ You are not authorized to use this command!")
        return

    try:
        args = context.args
        if len(args) != 2:
            update.message.reply_text("Usage: /setchances <user_id> <chances>")
            return
        target_user_id = int(args[0])
        new_chances = int(args[1])
        user = get_user(target_user_id)
        if not user:
            update.message.reply_text(f"User {target_user_id} not found!")
            return
        update_user(target_user_id, {"chances": new_chances})
        update.message.reply_text(f"✅ Chances for user {target_user_id} updated to {new_chances}!")
        context.bot.send_message(target_user_id, f"🎲 Your chances have been updated to {new_chances} by admin!")
    except Exception as e:
        update.message.reply_text(f"Error: {str(e)}")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CommandHandler("setchances", set_chances))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()