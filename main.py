import os
import sqlite3
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
import random
import logging
import requests

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# تنظیمات ثابت
TOKEN = os.getenv("TELEGRAM_TOKEN")
WALLET_ADDRESS = "UQAZEfdfeu-hjMZK-GsjpwAGJxPugS3MnHN6LlmhpKgk-iLd"
ADMIN_ID = "7836825805"
CHANNEL_ID = "@TonWinTx"  # کانال اعلام تراکنش‌ها
REQUIRED_CHATS = ["@TonWinNews", "@NDropCoin", "@TonWinTx"]  # کانال‌های اجباری
TONCENTER_API_KEY = os.getenv("TONCENTER_API_KEY")
API_URL = "https://toncenter.com/api/v2/getTransactions"
MAX_DEPOSIT_LIMIT = 600  # حداکثر TON برای قفل

# اتصال به دیتابیس
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

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
        tx_hash TEXT UNIQUE,
        status TEXT DEFAULT 'pending'
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS support_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        message TEXT,
        status TEXT DEFAULT 'pending'
    )
''')
conn.commit()

# توابع کمکی
def is_member(bot, user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        status = member.status in ["member", "administrator", "creator"]
        logger.info(f"Membership check: User {user_id} in {chat_id} - Status: {member.status}, Result: {status}")
        return status
    except Exception as e:
        logger.error(f"Error checking membership for {user_id} in {chat_id}: {str(e)}")
        return False

def get_missing_chats(bot, user_id):
    missing = [chat for chat in REQUIRED_CHATS if not is_member(bot, user_id, chat)]
    logger.info(f"Missing chats for {user_id}: {missing}")
    return missing

def join_channels_menu(missing_chats=None):
    if missing_chats is None or not missing_chats:
        missing_chats = REQUIRED_CHATS
    keyboard = [
        [InlineKeyboardButton(f"📢 Join {chat}", url=f"https://t.me/{chat[1:]}")] for chat in missing_chats
    ]
    keyboard.append([InlineKeyboardButton("✅ Submit", callback_data="check_membership")])
    return InlineKeyboardMarkup(keyboard)

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

def add_transaction(user_id, amount, tx_hash):
    try:
        cursor.execute("INSERT INTO transactions (user_id, amount, tx_hash) VALUES (?, ?, ?)", (user_id, amount, tx_hash))
        conn.commit()
    except sqlite3.IntegrityError:
        logger.error(f"Duplicate TX Hash: {tx_hash}")

def confirm_transaction(tx_hash):
    cursor.execute("UPDATE transactions SET status = 'confirmed' WHERE tx_hash = ?", (tx_hash,))
    conn.commit()

def get_total_deposited():
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE status = 'confirmed'")
    total = cursor.fetchone()[0]
    return total if total else 0

def check_transaction(tx_hash, user_id, expected_amount):
    params = {
        "address": WALLET_ADDRESS,
        "limit": 10,
        "api_key": TONCENTER_API_KEY
    }
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if not data["ok"]:
            logger.error(f"API Error: {data['error']}")
            return {"valid": False, "reason": data["error"]}
        for tx in data["result"]:
            if tx["transaction_id"]["hash"] == tx_hash:
                amount = int(tx["in_msg"]["value"]) / 1_000_000_000
                comment = tx["in_msg"].get("message", "")
                destination = tx["in_msg"]["destination"]
                logger.info(f"TX {tx_hash}: Amount={amount}, Comment={comment}, Destination={destination}")
                if destination != WALLET_ADDRESS:
                    return {"valid": False, "reason": "Wrong destination address"}
                if comment != str(user_id):
                    return {"valid": False, "reason": f"Comment mismatch: {comment} instead of {user_id}"}
                if not (1 <= amount <= 10):
                    return {"valid": False, "reason": f"Amount {amount} TON out of range (1-10)"}
                return {"valid": True, "amount": amount}
        return {"valid": False, "reason": "Transaction not found"}
    except Exception as e:
        logger.error(f"Error checking TX {tx_hash}: {str(e)}")
        return {"valid": False, "reason": str(e)}

def calculate_displayed_total(total_deposited):
    # هر 120 TON واقعی = 100 TON نمایشی
    return (total_deposited // 120) * 100

# منوها
def main_menu(is_locked=False):
    if is_locked:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Invite Friends", callback_data="invite")],
            [InlineKeyboardButton("🎲 My Chances", callback_data="my_chances"),
             InlineKeyboardButton("📞 Support", callback_data="support")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Deposit TON", callback_data="deposit_menu"),
             InlineKeyboardButton("👥 Invite Friends", callback_data="invite")],
            [InlineKeyboardButton("🎲 My Chances", callback_data="my_chances"),
             InlineKeyboardButton("📞 Support", callback_data="support")]
        ])

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

# هندلرها
def start(update, context):
    user_id = update.message.from_user.id
    bot = context.bot
    args = context.args
    logger.info(f"User {user_id} started bot with args: {args}")
    missing_chats = get_missing_chats(bot, user_id)
    if not missing_chats:
        handle_membership_success(update, context, args)
    else:
        update.message.reply_text("🎉 Welcome! Join these channels to get started:", reply_markup=join_channels_menu(missing_chats))

def handle_membership_success(update, context, args=None):
    user_id = update.message.from_user.id
    bot = context.bot
    total_deposited = get_total_deposited()
    is_locked = total_deposited >= MAX_DEPOSIT_LIMIT
    if args and len(args) > 0 and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].split("_")[1])
            if referrer_id != user_id:
                referrer = get_user(referrer_id)
                if referrer["user_id"] == referrer_id:
                    referrals = referrer["referrals"] + 1
                    update_user(referrer_id, {"referrals": referrals})
                    bot.send_message(referrer_id, f"👤 A new user joined with your referral link! Total referrals: {referrals}")
                    logger.info(f"Referral added for {referrer_id}. Total: {referrals}")
        except Exception as e:
            logger.error(f"Error processing referral for {user_id}: {str(e)}")
    update.message.reply_text("🎊 Welcome aboard! What would you like to do?", reply_markup=main_menu(is_locked))

def button(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    bot = context.bot
    total_deposited = get_total_deposited()
    is_locked = total_deposited >= MAX_DEPOSIT_LIMIT
    try:
        query.answer()
    except Exception as e:
        logger.error(f"Failed to answer callback for {user_id}: {str(e)}")
    try:
        missing_chats = get_missing_chats(bot, user_id)
        current_text = query.message.text if query.message else ""
        current_markup = query.message.reply_markup if query.message else None

        if missing_chats:
            new_text = f"⚠️ You need to join these channels to continue:\n{', '.join(missing_chats)}"
            new_markup = join_channels_menu(missing_chats)
            if current_text != new_text or str(current_markup) != str(new_markup):
                query.edit_message_text(new_text, reply_markup=new_markup)
            return

        if query.data == "check_membership":
            missing_chats = get_missing_chats(bot, user_id)
            if not missing_chats:
                query.edit_message_text("✅ Awesome! You're all set!", reply_markup=main_menu(is_locked))
            else:
                new_text = f"⚠️ Please join these channels first:\n{', '.join(missing_chats)}"
                new_markup = join_channels_menu(missing_chats)
                if current_text != new_text or str(current_markup) != str(new_markup):
                    query.edit_message_text(new_text, reply_markup=new_markup)
        elif query.data == "deposit_menu":
            if is_locked:
                query.edit_message_text("🔒 Deposit is locked! Please wait for the next lottery round.", reply_markup=main_menu(True))
            else:
                query.edit_message_text("💸 How much TON do you want to deposit?", reply_markup=deposit_menu())
        elif query.data.startswith("deposit_"):
            if is_locked:
                query.edit_message_text("🔒 Deposit is locked! Please wait for the next lottery round.", reply_markup=main_menu(True))
            else:
                amount = int(query.data.split("_")[1])
                remaining = MAX_DEPOSIT_LIMIT - total_deposited
                if remaining < amount and remaining > 0:
                    amount = remaining  # فقط مقدار باقی‌مانده را اجازه می‌دهیم
                context.user_data["pending_deposit"] = amount
                query.edit_message_text(
                    f"💰 Please send {amount} TON to this address:\n`{WALLET_ADDRESS}`\n\nYour User ID: `{user_id}`\n**Important**: Enter your User ID (`{user_id}`) in the transaction comment.\nAfter sending, press 'Continue'.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("➡️ Continue", callback_data="continue_to_wallet"),
                         InlineKeyboardButton("🔙 Back", callback_data="back_to_deposit")]
                    ])
                )
        elif query.data == "continue_to_wallet":
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
        elif query.data == "support":
            query.edit_message_text(
                "📞 Please type your question or issue below:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
            )
            context.user_data["waiting_for_support_message"] = True
        elif query.data == "back_to_main":
            query.edit_message_text("🎊 Back to main menu:", reply_markup=main_menu(is_locked))
            context.user_data.clear()
        elif query.data == "back_to_deposit":
            if is_locked:
                query.edit_message_text("🔒 Deposit is locked! Please wait for the next lottery round.", reply_markup=main_menu(True))
            else:
                query.edit_message_text("💸 How much TON do you want to deposit?", reply_markup=deposit_menu())
            context.user_data.clear()
    except Exception as e:
        logger.error(f"Error processing callback for {user_id}: {str(e)}")
        if "Message is not modified" not in str(e):
            query.edit_message_text("⚠️ Something went wrong. Please try again.", reply_markup=main_menu(is_locked))

def handle_message(update, context):
    user_id = update.message.from_user.id
    bot = context.bot
    text = update.message.text
    username = update.message.from_user.username or "No Username"
    total_deposited = get_total_deposited()
    is_locked = total_deposited >= MAX_DEPOSIT_LIMIT

    missing_chats = get_missing_chats(bot, user_id)
    if missing_chats:
        update.message.reply_text(
            f"⚠️ You need to join these channels to continue:\n{', '.join(missing_chats)}",
            reply_markup=join_channels_menu(missing_chats)
        )
        return

    if "waiting_for_wallet" in context.user_data and context.user_data["waiting_for_wallet"]:
        wallet_address = text
        amount = context.user_data["pending_deposit"]
        update_user(user_id, {"wallet_address": wallet_address})
        update.message.reply_text(
            "📤 Now, please send the TX Hash of your transaction:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_deposit")]])
        )
        del context.user_data["waiting_for_wallet"]
        context.user_data["waiting_for_tx_hash"] = True

    elif "waiting_for_tx_hash" in context.user_data and context.user_data["waiting_for_tx_hash"]:
        tx_hash = text
        expected_amount = context.user_data["pending_deposit"]
        user = get_user(user_id)
        add_transaction(user_id, expected_amount, tx_hash)

        tx_result = check_transaction(tx_hash, user_id, expected_amount)
        if tx_result["valid"]:
            confirm_transaction(tx_hash)
            new_deposited = user["deposited"] + tx_result["amount"]
            new_chances = user["chances"] + tx_result["amount"]
            update_user(user_id, {"deposited": new_deposited, "chances": new_chances})
            total_deposited = get_total_deposited()
            displayed_total = calculate_displayed_total(total_deposited)

            # پیام به کاربر
            if total_deposited >= MAX_DEPOSIT_LIMIT:
                update.message.reply_text(
                    "✅ Your deposit has been confirmed! The lottery limit has been reached.\nStay tuned for the next round of draws!",
                    reply_markup=main_menu(True)
                )
            else:
                update.message.reply_text(
                    f"✅ Your deposit of {tx_result['amount']} TON has been confirmed!\nYou now have {new_chances} chances.",
                    reply_markup=main_menu(False)
                )

            # پیام به ادمین
            bot.send_message(
                ADMIN_ID,
                f"✅ New Deposit:\nUser ID: {user_id}\nUsername: @{username}\nWallet Address: {user['wallet_address']}\nAmount: {tx_result['amount']} TON\nChances: {new_chances}\nTX Hash: {tx_hash}"
            )

            # اعلام در کانال
            if total_deposited >= MAX_DEPOSIT_LIMIT:
                bot.send_message(
                    CHANNEL_ID,
                    f"🎉 500 TON تکمیل شد!\nسلامت اتی 10 برنده خوش‌شانس مشخص خواهد شد."
                )
            elif displayed_total > calculate_displayed_total(total_deposited - tx_result["amount"]):
                bot.send_message(
                    CHANNEL_ID,
                    f"💰 {displayed_total} TON جمع شد!\nتا رسیدن به 500 TON و قرعه‌کشی ادامه دهید."
                )

            # اجرای قرعه‌کشی
            if total_deposited >= MAX_DEPOSIT_LIMIT:
                run_lottery(bot)
        else:
            update.message.reply_text(
                f"⚠️ Transaction verification failed!\nReason: {tx_result['reason']}\nPlease ensure the amount matches ({expected_amount} TON) and your User ID ({user_id}) is in the comment."
            )
            bot.send_message(
                ADMIN_ID,
                f"⚠️ Failed Transaction:\nUser ID: {user_id}\nUsername: @{username}\nWallet Address: {user['wallet_address']}\nAmount: {expected_amount} TON\nTX Hash: {tx_hash}\nReason: {tx_result['reason']}"
            )
        context.user_data.clear()

    elif "waiting_for_support_message" in context.user_data and context.user_data["waiting_for_support_message"]:
        support_message = text
        cursor.execute("INSERT INTO support_requests (user_id, username, message) VALUES (?, ?, ?)", (user_id, username, support_message))
        conn.commit()
        update.message.reply_text("✅ Your support request has been sent! Please wait for a response.", reply_markup=main_menu(is_locked))
        cursor.execute("SELECT last_insert_rowid()")
        request_id = cursor.fetchone()[0]
        bot.send_message(
            ADMIN_ID,
            f"📞 New Support Request:\nUser ID: {user_id}\nUsername: @{username}\nMessage: {support_message}\nRequest ID: {request_id}\nReply with /reply {request_id} <your_response>"
        )
        del context.user_data["waiting_for_support_message"]

    else:
        update.message.reply_text("⚠️ Please select an option from the menu first!", reply_markup=main_menu(is_locked))

def run_lottery(bot):
    cursor.execute("SELECT user_id, chances, referrals, wallet_address FROM users WHERE chances > 0 OR referrals > 0")
    eligible_users = cursor.fetchall()
    if not eligible_users:
        return
    weighted_users = []
    for user in eligible_users:
        user_id, chances, referrals, wallet = user
        weight = chances + referrals
        weighted_users.extend([{"user_id": user_id, "wallet": wallet}] * weight)
    if len(weighted_users) < 10:
        return
    winners = random.sample(weighted_users, 10)
    prize_per_winner = (500 * 0.8) / 10
    admin_share = 500 * 0.2
    for winner in winners:
        bot.send_message(winner["user_id"], f"🏆 Congrats! You won {prize_per_winner} TON in the lottery! Please wait for admin to send your prize.")
    winners_info = "\n".join([f"User ID: {w['user_id']} - Wallet: {w['wallet']}" for w in winners])
    bot.send_message(
        ADMIN_ID,
        f"🎉 Lottery completed!\nWinners (10):\n{winners_info}\nPrize per winner: {prize_per_winner} TON\nAdmin share: {admin_share} TON"
    )

def reset_bot(update, context):
    user_id = update.message.from_user.id
    if str(user_id) != ADMIN_ID:
        update.message.reply_text("⚠️ You are not authorized to use this command!")
        return
    cursor.execute("UPDATE users SET chances = 0, deposited = 0, referrals = 0")
    cursor.execute("DELETE FROM transactions")
    conn.commit()
    update.message.reply_text("✅ Bot has been reset! Deposits are now unlocked.")
    context.bot.send_message(CHANNEL_ID, "🎉 Bot reset! New lottery round started. Start depositing now!")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CommandHandler("reset", reset_bot))  # دستور ریست
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()