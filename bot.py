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
PAYMENT_METHODS = ["اتصالات كاش", "أورانج كاش", "فودافون كاش", "باي بال", "بينانس", "ويسترن يونيون", "إنستاباي"]
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
        [["💰 التحقق من الرصيد", "🎁 دعوة صديق"], ["💵 سحب الرصيد"]],
        resize_keyboard=True
    )

    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user.id,))
    existing_user = cursor.fetchone()

    
    referral_link = f"https://t.me/Easy_Money_win_bot?start={user.id}"
    message = (
        f"مرحبًا {user.first_name}! 🎉\n"
        "اكسب 50 جنيه مصري لكل صديق تدعوه!\n"
        f"شارك هذا الرابط مع أصدقائك:\n\n{referral_link}"
    )

    await update.message.reply_text(message, reply_markup=user_keyboard)

    
    if not existing_user:
        add_user(user.id, user.username, referred_by)

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
                    text=f"🎉 انضم صديق باستخدام رابط الدعوة الخاص بك! لقد ربحت 50 جنيه مصري!",
                    reply_markup=user_keyboard
                )

# Command handler for user commands
async def handle_user_commands(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text

    if text in ["💰 التحقق من الرصيد", "🎁 دعوة صديق", "💵 سحب الرصيد"]:
        context.user_data.pop("awaiting_amount", None)
        context.user_data.pop("awaiting_payment_method", None)
        context.user_data.pop("awaiting_payment_info", None)

    if text == "💰 التحقق من الرصيد":
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        balance = cursor.fetchone()[0]
        await update.message.reply_text(f"رصيدك: {balance} جنيه مصري")
        return

    elif text == "🎁 دعوة صديق":
        referral_link = f"https://t.me/Easy_Money_win_bot?start={user_id}"
        await update.message.reply_text(f"ادعُ صديقًا واربح 50 جنيه مصري!\nإليك رابط الدعوة الخاص بك:\n{referral_link}")
        return

    elif text == "💵 سحب الرصيد":
        if await is_user_subscribed(user_id, context):
            print(f"[DEBUG] User {user_id} selected Withdraw Balance")  
            await update.message.reply_text("أدخل المبلغ الذي تريد سحبه:")
            context.user_data["awaiting_amount"] = True
        else:
            await update.message.reply_text(
                "لسحب الرصيد، يجب عليك الانضمام إلى قناتنا أولاً:\n"
                "👉 [انضم إلى القناة](https://t.me/lucky_wh2el)\n"
                "بمجرد الانضمام، اضغط على 'سحب الرصيد' مرة أخرى.",
                parse_mode="Markdown"
            )
        return

    if context.user_data.get("awaiting_amount"):
        await handle_withdraw_amount(update, context)
        return

    if context.user_data.get("awaiting_payment_method"):
        await handle_payment_method(update, context)
        return

    if context.user_data.get("awaiting_payment_info"):
        await handle_payment_info(update, context)
        return

    await update.message.reply_text("❌ خيار غير صالح. يرجى اختيار خيار من القائمة.")

# Handler for withdraw amount input
async def handle_withdraw_amount(update: Update, context: CallbackContext):
    user_keyboard = ReplyKeyboardMarkup(
        [["💰 التحقق من الرصيد", "🎁 دعوة صديق"], ["💵 سحب الرصيد"]],
        resize_keyboard=True
    )
    user_id = update.message.from_user.id
    text = update.message.text

    print(f"[DEBUG] Received withdraw amount input: {text} from user {user_id}") 

    try:
        amount = int(text)
        
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()

        if result is None:
            await update.message.reply_text("❌ حدث خطأ: لم يتم العثور على حسابك في قاعدة البيانات.")
            return

        balance = result[0]

        if amount > balance:
            await update.message.reply_text(f"❌ رصيد غير كافٍ! لديك فقط {balance} جنيه مصري. يرجى إدخال مبلغ صالح.", reply_markup=user_keyboard)
            return  
        elif amount <= 0:
            await update.message.reply_text("❌ يرجى إدخال مبلغ أكبر من 0.", reply_markup=user_keyboard)
            return

        print(f"[DEBUG] Saving withdraw request: {amount} for user {user_id}")

        user_withdraw_requests[user_id] = amount
        context.user_data.pop("awaiting_amount", None)

        
        payment_keyboard = ReplyKeyboardMarkup([[method] for method in PAYMENT_METHODS], resize_keyboard=True)
        await update.message.reply_text("✅ اختر طريقة السحب:", reply_markup=payment_keyboard)

        
        context.user_data["awaiting_payment_method"] = True

    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح.")

# Handler for payment method selection
async def handle_payment_method(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text

    print(f"[DEBUG] User {user_id} selected payment method: {text}")  # ✅ Debugging

    if "awaiting_payment_method" in context.user_data:
        if text in PAYMENT_METHODS:
            amount = user_withdraw_requests.get(user_id)

            if amount is None:
                await update.message.reply_text("❌ حدث خطأ ما. يرجى المحاولة مرة أخرى.")
                return
            
            # ✅ تخزين طريقة الدفع والمبلغ في القاموس
            user_withdraw_requests[user_id] = {"amount": amount, "method": text}
            context.user_data.pop("awaiting_payment_method")

            # ✅ طلب معلومات إضافية بناءً على طريقة الدفع
            if text in ["باي بال", "بينانس", "ويسترن يونيون"]:
                await update.message.reply_text(f"أدخل بريدك الإلكتروني الخاص بـ {text}:")
            else:
                await update.message.reply_text("أدخل رقم هاتفك المرتبط بطريقة الدفع:")

            # ✅ تعيين انتظار إدخال البيانات
            context.user_data["awaiting_payment_info"] = True
        else:
            await update.message.reply_text("❌ يرجى اختيار طريقة دفع صالحة من القائمة.")

# Function to validate phone number
def is_valid_phone_number(number, method):
    if not number.isdigit() or len(number) != 11:
        return False
    
    if method == "فودافون كاش" and not number.startswith("010"):
        return False
    elif method == "اتصالات كاش" and not number.startswith("011"):
        return False
    elif method == "أورانج كاش" and not number.startswith("012"):
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
            await update.message.reply_text("❌ حدث خطأ ما. يرجى المحاولة مرة أخرى.")
            return

        amount = withdraw_data["amount"]
        method = withdraw_data["method"]

        if method in ["باي بال", "بينانس", "ويسترن يونيون"]:
            if not is_valid_email(text):
                await update.message.reply_text("❌ تنسيق البريد الإلكتروني غير صالح! يرجى إدخال بريد إلكتروني صالح.")
                return
        else:
            if not is_valid_phone_number(text, method):
                await update.message.reply_text(f"❌ رقم الهاتف غير صالح! يرجى إدخال رقم {method} صالح.")
                return

        user_withdraw_requests[user_id]["info"] = text
        context.user_data.pop("awaiting_payment_info")

        cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount, user_id))
        conn.commit()

        user_keyboard = ReplyKeyboardMarkup(
            [["💰 التحقق من الرصيد", "🎁 دعوة صديق"], ["💵 سحب الرصيد"]],
            resize_keyboard=True
        )

        await update.message.reply_text(
            f"✅ طلب السحب الخاص بك بمبلغ {amount} جنيه مصري عبر {method} قيد المعالجة! 🚀\n"
            "سيتم إخطارك بمجرد اكتمال المعاملة.",
            reply_markup=user_keyboard
        )

# Admin command handler
async def admin(update: Update, context: CallbackContext):
    admin_keyboard = ReplyKeyboardMarkup(
        [["💰 التحقق من الرصيد", "🎁 دعوة صديق"], ["💵 سحب الرصيد"]],
        resize_keyboard=True
    )
    
    user_id = update.message.from_user.id

    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ الوصول مرفوض.", reply_markup=admin_keyboard)
        return

    admin_keyboard = ReplyKeyboardMarkup(
        [["📢 رسالة جماعية", "👥 عرض عدد المستخدمين"]],
        resize_keyboard=True
    )

    await update.message.reply_text("🔹 لوحة تحكم الأدمن\nاختر خيارًا:", reply_markup=admin_keyboard)

# Handler for admin commands
async def handle_admin_commands(update: Update, context: CallbackContext):
    admin_keyboard = ReplyKeyboardMarkup(
        [["📢 رسالة جماعية", "👥 عرض عدد المستخدمين"]],
        resize_keyboard=True
    )
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ الوصول مرفوض.")
        return

    if text == "📢 رسالة جماعية":
        await update.message.reply_text("✏️ أدخل الرسالة التي تريد إرسالها:")
        context.user_data["awaiting_broadcast"] = True

    elif text == "👥 عرض عدد المستخدمين":
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        await update.message.reply_text(f"👥 إجمالي المستخدمين: {count}")

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

        await update.message.reply_text("✅ تم إرسال الرسالة إلى جميع المستخدمين.", reply_markup=admin_keyboard)

# Main function to run the bot
def main():
    app = Application.builder().token(config.TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_commands))
    app.add_handler(MessageHandler(filters.TEXT, handle_withdraw_amount))  
    app.add_handler(MessageHandler(filters.TEXT, handle_payment_method)) 
    app.add_handler(MessageHandler(filters.TEXT, handle_payment_info)) 

    app.run_polling()

if __name__ == "__main__":
    main()
