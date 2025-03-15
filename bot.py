from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, CallbackQueryHandler
import mysql.connector
import random
import config
import re

# Connect to the database
conn = mysql.connector.connect(**config.DB_CONFIG)
cursor = conn.cursor()

CHANNEL_ID = "@lucky_wh2el"  # Channel for subscription verification
PAYMENT_METHODS = ["Etisalat Cash", "Orange Cash", "Vodafone Cash", "PayPal", "Binance", "Western Union", "Instapay"]
user_withdraw_requests = {}

# Function to add a new user
def add_user(user_id, username, referred_by=None):
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    if not user:
        referral_code = f"ref{random.randint(1000,9999)}"
        if not username:
            username = f"User_{user_id}"
        cursor.execute("""
            INSERT INTO users (user_id, username, balance, referral_code, referred_by) 
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, username, 0, referral_code, referred_by))
        conn.commit()

# Function to check if the user is subscribed to the channel
async def is_user_subscribed(user_id, context):
    try:
        chat_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False

# Start command handler
async def start(update: Update, context: CallbackContext):
    user = update.message.from_user
    referred_by = None

    if context.args:
        referred_by = context.args[0]
    
    user_keyboard = ReplyKeyboardMarkup(
        [["💰 Check Balance", "🎁 Invite a Friend"], ["💵 Withdraw Balance"]],
        resize_keyboard=True
    )

    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user.id,))
    existing_user = cursor.fetchone()

    if not existing_user:
        add_user(user.id, user.username, referred_by)
        referral_link = f"https://t.me/Easy_Money_win_bot?start={user.id}"
        
        message = (
            f"Welcome {user.first_name}! 🎉\n"
            "Earn $50 for each invited friend!\n"
            f"Share this link with your friends:\n\n{referral_link}"
        )

        await update.message.reply_text(message, reply_markup=user_keyboard)

        if referred_by:
            referred_by = int(referred_by)
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (referred_by,))
            referrer = cursor.fetchone()

            if referrer:
                cursor.execute("UPDATE users SET balance = balance + 50 WHERE user_id = %s", (referred_by,))
                conn.commit()

                cursor.execute("UPDATE users SET referred_by = %s WHERE user_id = %s", (referred_by, user.id))
                conn.commit()

                await context.bot.send_message(
                    chat_id=referred_by,
                    text=f"🎉 A friend joined using your invite link! You earned $50!",
                    reply_markup=user_keyboard
                )
    else:
        await update.message.reply_text("✅ Welcome back! Use the menu below to continue.", reply_markup=user_keyboard)

# Command handler for user commands
async def handle_user_commands(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text

    if context.user_data.get("awaiting_amount"):
        await handle_withdraw_amount(update, context)
        return

    if context.user_data.get("awaiting_payment_method"):
        await handle_payment_method(update, context)
        return

    if context.user_data.get("awaiting_payment_info"):
        await handle_payment_info(update, context)
        return

    if user_id == config.ADMIN_ID:
        await handle_admin_commands(update, context)
        return

    if text == "💰 Check Balance":
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        balance = cursor.fetchone()[0]
        await update.message.reply_text(f"Your balance: ${balance}")

    elif text == "🎁 Invite a Friend":
        referral_link = f"https://t.me/Easy_Money_win_bot?start={user_id}"
        await update.message.reply_text(f"Invite a friend and earn $50!\nHere is your invite link:\n{referral_link}")

    elif text == "💵 Withdraw Balance":
        if await is_user_subscribed(user_id, context):
            await update.message.reply_text("Enter the amount you want to withdraw:")
            context.user_data["awaiting_amount"] = True
        else:
            await update.message.reply_text(
                "To withdraw, you must join our channel first:\n"
                "👉 [Join Channel](https://t.me/lucky_wh2el)\n"
                "Once you have joined, press 'Withdraw Balance' again.",
                parse_mode="Markdown"
            )

# Handler for withdraw amount input
async def handle_withdraw_amount(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text

    try:
        amount = int(text)
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        balance = cursor.fetchone()[0]

        if amount > balance:
            await update.message.reply_text(f"❌ Insufficient balance! You only have ${balance}. Please enter a valid amount.")
            return  
        elif amount <= 0:
            await update.message.reply_text("❌ Please enter a valid amount greater than 0.")
            return
        
        user_withdraw_requests[user_id] = amount
        context.user_data.pop("awaiting_amount")

        payment_keyboard = ReplyKeyboardMarkup([[method] for method in PAYMENT_METHODS], resize_keyboard=True)
        await update.message.reply_text("✅ Choose your withdrawal method:", reply_markup=payment_keyboard)
        context.user_data["awaiting_payment_method"] = True
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid numeric amount.")

# Handler for payment method selection
async def handle_payment_method(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text

    if context.user_data.get("awaiting_payment_method"):
        if text in PAYMENT_METHODS:
            amount = user_withdraw_requests.get(user_id)
            if amount is None:
                await update.message.reply_text("❌ Something went wrong. Please try again.")
                return
            
            user_withdraw_requests[user_id] = {"amount": amount, "method": text}
            context.user_data.pop("awaiting_payment_method")

            if text in ["PayPal", "Binance", "Western Union"]:
                await update.message.reply_text(f"Enter your {text} email:")
            else:
                await update.message.reply_text("Enter your phone number:")
            
            context.user_data["awaiting_payment_info"] = True
        else:
            await update.message.reply_text("❌ Please choose a valid payment method from the list.")

# Function to validate phone number
def is_valid_phone_number(number, method):
    if not number.isdigit() or len(number) != 11:
        return False
    
    if method == "Vodafone Cash" and not number.startswith("010"):
        return False
    elif method == "Etisalat Cash" and not number.startswith("011"):
        return False
    elif method == "Orange Cash" and not number.startswith("012"):
        return False

    return True

# Function to validate email
def is_valid_email(email):
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(email_regex, email)

# Handler for payment info input
async def handle_payment_info(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text

    if context.user_data.get("awaiting_payment_info"):
        withdraw_data = user_withdraw_requests.get(user_id)
        if not withdraw_data:
            await update.message.reply_text("❌ Something went wrong. Please try again.")
            return

        amount = withdraw_data["amount"]
        method = withdraw_data["method"]

        if method in ["PayPal", "Binance", "Western Union"]:
            if not is_valid_email(text):
                await update.message.reply_text("❌ Invalid email format! Please enter a valid email.")
                return
        else:
            if not is_valid_phone_number(text, method):
                await update.message.reply_text(f"❌ Invalid phone number! Please enter a valid {method} number.")
                return

        user_withdraw_requests[user_id]["info"] = text
        context.user_data.pop("awaiting_payment_info")

        cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount, user_id))
        conn.commit()

        user_keyboard = ReplyKeyboardMarkup(
            [["💰 Check Balance", "🎁 Invite a Friend"], ["💵 Withdraw Balance"]],
            resize_keyboard=True
        )

        await update.message.reply_text(
            f"✅ Your withdrawal request of ${amount} via {method} is being processed! 🚀\n"
            "You will be notified once the transaction is complete.",
            reply_markup=user_keyboard
        )

# Admin command handler
async def admin(update: Update, context: CallbackContext):
    admin_keyboard = ReplyKeyboardMarkup(
        [["💰 Check Balance", "🎁 Invite a Friend"], ["💵 Withdraw Balance"]],
        resize_keyboard=True
    )
    
    user_id = update.message.from_user.id

    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ Access denied.", reply_markup=admin_keyboard)
        return

    admin_keyboard = ReplyKeyboardMarkup(
        [["📢 Broadcast Message", "👥 View Users Count"]],
        resize_keyboard=True
    )

    await update.message.reply_text("🔹 Admin Dashboard\nChoose an option:", reply_markup=admin_keyboard)

# Handler for admin commands
async def handle_admin_commands(update: Update, context: CallbackContext):
    admin_keyboard = ReplyKeyboardMarkup(
        [["📢 Broadcast Message", "👥 View Users Count"]],
        resize_keyboard=True
    )
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ Access denied.")
        return

    if text == "📢 Broadcast Message":
        await update.message.reply_text("✏️ Enter the message you want to broadcast:")
        context.user_data["awaiting_broadcast"] = True

    elif text == "👥 View Users Count":
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        await update.message.reply_text(f"👥 Total users: {count}")

    elif context.user_data.get("awaiting_broadcast"):
        message_to_send = text
        context.user_data.pop("awaiting_broadcast")

        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()

        for user in users:
            try:
                await context.bot.send_message(chat_id=user[0], text=message_to_send)
            except Exception as e:
                print(f"Could not send message to {user[0]}: {e}")

        await update.message.reply_text("✅ Message sent to all users.", reply_markup=admin_keyboard)

# Main function to run the bot
def main():
    app = Application.builder().token(config.TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_commands))

    app.run_polling()

if __name__ == "__main__":
    main()
