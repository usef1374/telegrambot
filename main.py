import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from pymongo import MongoClient
import random

# تنظیمات
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WALLET_ADDRESS = "UQAZEfdfeu-hjMZK-GsjpwAGJxPugS3MnHN6LlmhpKgk-iLd"
ADMIN_ID = "7836825805"
REQUIRED_CHATS = ["@CoinTCoinTon", "@MyTonCoinT", "@MyToCoin"]

# اتصال به MongoDB
client = MongoClient(MONGO_URI)
db = client["ton_bot"]
users_collection = db["users"]
transactions_collection = db["transactions"]

def get_user(user_id):
    user = users_collection.find_one({"user_id": user_id})
    if not user:
        user = {"user_id": user_id, "chances": 0, "referrals": 0, "deposited": 0, "username": ""}
        users_collection.insert_one(user)
    return user

def update_user(user_id, data):
    users_collection.update_one({"user_id": user_id}, {"$set": data}, upsert=True)

def add_transaction(user_id, amount, tx_hash):
    transaction = {"user_id": user_id, "amount": amount, "tx_hash": tx_hash, "status": "pending"}
    transactions_collection.insert_one(transaction)

def get_total_deposited():
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    result = transactions_collection.aggregate(pipeline)
    return next(result, {"total": 0})["total"]

def check_membership(bot, user_id):
    for chat in REQUIRED_CHATS:
        try:
            member = bot.get_chat_member(chat_id=chat, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

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
    users = list(users_collection.find({"chances": {"$gt": 0}}))
    if len(users) < 10:
        return

    winners = random.sample(users, 10)
    prize_per_winner = (500 * 0.8) / 10
    admin_share = 500 * 0.2

    for winner in winners:
        bot.send_message(winner["user_id"], f"Congratulations! You won {prize_per_winner} TON in the lottery!")
    
    bot.send_message(
        ADMIN_ID,
        f"Lottery completed!\nWinners: {', '.join([str(w['user_id']) for w in winners])}\nPrize per winner: {prize_per_winner} TON\nAdmin share: {admin_share} TON"
    )
    users_collection.update_many({}, {"$set": {"chances": 0, "deposited": 0, "referrals": 0}})
    transactions_collection.delete_many({})

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