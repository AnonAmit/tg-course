import os
import sys
import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    Message, CallbackQuery
)
import datetime
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config import (
    API_ID, API_HASH, BOT_TOKEN, WELCOME_MESSAGE,
    AUTO_DELETE_SECONDS, AUTO_APPROVE, BOT_PASSWORD, PAYMENT_OPTIONS
)
from database.models import get_db, User, Course, Payment, Log, Category, BotSetting, CourseRequest
from utils.helpers import (
    log_action, save_payment_proof, is_valid_image,
    is_spam, detect_duplicate_payment, format_course_info,
    shorten_url
)

# Initialize the bot
app = Client(
    "course_delivery_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# User states dictionary
user_states = {}

# Callback data prefixes
CB_COURSE = "course_"
CB_BUY = "buy_"
CB_PAYMENT = "payment_"
CB_ADMIN = "admin_"
CB_BACK = "back"
CB_CANCEL = "cancel"
CB_CATEGORY_SELECT = "cat_select_"       # Select a category
CB_VIEW_CATEGORY_COURSES = "cat_courses_" # View courses in a category
CB_BACK_TO_COURSES = "back_courses"       # Go to full course list view
CB_SHOW_CATEGORIES_MENU = "show_cat_menu" # Go back to category list menu

# State enum
class State:
    IDLE = 0
    AWAITING_PASSWORD = 1
    VIEWING_COURSES = 2
    SELECTING_PAYMENT = 3
    SENDING_PROOF = 4
    ADMIN_LOGIN = 5
    ADMIN_DASHBOARD = 6
    SEARCHING_COURSES = 7
    ENTERING_GIFT_CODE = 8
    AWAITING_COURSE_REQUEST = 9

# Helper functions
async def delete_after_delay(message, delay=AUTO_DELETE_SECONDS):
    """Delete a message after specified delay"""
    if delay > 0:
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except Exception as e:
            print(f"Error deleting message: {e}")

async def get_or_create_user(user):
    """Get or create a user in the database"""
    db = get_db()
    db_user = db.query(User).filter_by(telegram_id=str(user.id)).first()
    
    if not db_user:
        db_user = User(
            telegram_id=str(user.id),
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            joined_date=datetime.datetime.now(datetime.UTC)
        )
        db.add(db_user)
        db.commit()
        
        log_action(
            str(user.id),
            "user_joined",
            details=f"New user joined: {user.first_name} {user.last_name} (@{user.username})"
        )
    
    return db_user

async def get_course_list_markup():
    """Get markup for the course list"""
    db = get_db()
    courses = db.query(Course).filter_by(is_active=True).all()
    
    keyboard = []
    for course in courses:
        keyboard.append([
            InlineKeyboardButton(
                f"{course.title} - ₹{course.price:.2f}",
                callback_data=f"{CB_COURSE}{course.id}"
            )
        ])
    
    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data=CB_BACK)])
    
    return InlineKeyboardMarkup(keyboard)

async def get_payment_options_markup(course_id):
    """Get markup for payment options"""
    keyboard = []
    
    if PAYMENT_OPTIONS['UPI']:
        keyboard.append([
            InlineKeyboardButton("UPI Payment", callback_data=f"{CB_PAYMENT}upi_{course_id}")
        ])
    
    if PAYMENT_OPTIONS['CRYPTO']:
        keyboard.append([
            InlineKeyboardButton("Cryptocurrency", callback_data=f"{CB_PAYMENT}crypto_{course_id}")
        ])
    
    if PAYMENT_OPTIONS['PAYPAL']:
        keyboard.append([
            InlineKeyboardButton("PayPal", callback_data=f"{CB_PAYMENT}paypal_{course_id}")
        ])
    
    if PAYMENT_OPTIONS['COD']:
        keyboard.append([
            InlineKeyboardButton("Cash on Delivery", callback_data=f"{CB_PAYMENT}cod_{course_id}")
        ])
    
    if PAYMENT_OPTIONS['GIFT_CARD']:
        keyboard.append([
            InlineKeyboardButton("Gift Card", callback_data=f"{CB_PAYMENT}gift_{course_id}")
        ])
    
    # Add back buttons
    keyboard.append([
        InlineKeyboardButton("⬅️ Back to Course", callback_data=f"{CB_COURSE}{course_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("🏠 Main Menu", callback_data=CB_BACK)
    ])
    
    return InlineKeyboardMarkup(keyboard)

async def get_main_menu_markup():
    """Get markup for the main menu"""
    keyboard = [
        [KeyboardButton("📚 Browse Courses"), KeyboardButton("🔍 Search Courses")],
        [KeyboardButton("🗂️ Course Categories"), KeyboardButton("👤 My Purchases")],
        [KeyboardButton("✍️ Request Course"), KeyboardButton("📜 DMCA & Policy")],
        [KeyboardButton("❓ Help")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Command handlers
@app.on_message(filters.command("start"))
async def start_command(client, message):
    """Handle /start command"""
    user = message.from_user
    await get_or_create_user(user)
    
    # Check if the bot has a password set
    if BOT_PASSWORD:
        user_states[user.id] = State.AWAITING_PASSWORD
        welcome_msg = "🔐 This bot is password protected. Please enter the password to continue."
        await message.reply(welcome_msg, quote=True)
    else:
        user_states[user.id] = State.IDLE
        welcome_msg = f"👋 {WELCOME_MESSAGE}\n\nUse the buttons below to navigate."
        reply = await message.reply(
            welcome_msg,
            quote=True,
            reply_markup=await get_main_menu_markup()
        )
    
    log_action(str(user.id), "command_start")

@app.on_message(filters.command("courses"))
async def courses_command(client, message):
    """Handle /courses command"""
    user = message.from_user
    
    # Check if user is authenticated (if password is set)
    if BOT_PASSWORD and user.id not in user_states:
        await start_command(client, message)
        return
    
    user_states[user.id] = State.VIEWING_COURSES
    
    reply = await message.reply(
        "📚 Here are our available courses. Click on any course to view details:",
        quote=True,
        reply_markup=await get_course_list_markup()
    )
    
    log_action(str(user.id), "command_courses")
    asyncio.create_task(delete_after_delay(reply))

@app.on_message(filters.command("help"))
async def help_command(client, message):
    """Handle /help command"""
    user = message.from_user
    
    help_text = (
        "🤖 **Course Delivery Bot Help**\n\n"
        "This bot allows you to browse and purchase courses. After payment verification, "
        "you'll receive access to the course content.\n\n"
        "**Available commands:**\n"
        "/start - Start the bot and view the main menu\n"
        "/courses - Browse available courses\n"
        "/help - Show this help message\n\n"
        "**How to purchase:**\n"
        "1. Browse courses using /courses command\n"
        "2. Select a course to view details\n"
        "3. Click 'Buy Now' and choose a payment method\n"
        "4. Make the payment and send a screenshot as proof\n"
        "5. Wait for approval (instant or manual)\n"
        "6. Receive your course access link\n\n"
        "For any issues, please contact the admin."
    )
    
    reply = await message.reply(
        help_text,
        quote=True
    )
    
    log_action(str(user.id), "command_help")
    asyncio.create_task(delete_after_delay(reply))

# Add a search command
@app.on_message(filters.command("search"))
async def search_command(client, message):
    """Handle /search command"""
    user = message.from_user
    
    # Check if user is authenticated (if password is set)
    if BOT_PASSWORD and user.id not in user_states:
        await start_command(client, message)
        return
    
    await message.reply(
        "🔍 Please enter your search query. You can search by course name or category.",
        quote=True
    )
    
    user_states[user.id] = State.SEARCHING_COURSES
    log_action(str(user.id), "command_search")

# Callback query handlers
@app.on_callback_query()
async def handle_callback(client, callback_query):
    """Handle callback queries from inline buttons"""
    user = callback_query.from_user
    data = callback_query.data
    message = callback_query.message
    
    # Course selection
    if data.startswith(CB_COURSE):
        course_id = int(data[len(CB_COURSE):])
        await show_course_details(client, message, user, course_id)
    
    # View courses in a category (after selecting a category from category list)
    elif data.startswith(CB_VIEW_CATEGORY_COURSES):
        category_id = int(data[len(CB_VIEW_CATEGORY_COURSES):])
        await show_courses_in_category(client, callback_query, user, category_id)
    
    # Go back to category menu
    elif data == CB_SHOW_CATEGORIES_MENU:
        await callback_query.message.delete()
        mock_message_for_reply = Message(chat=callback_query.message.chat, from_user=user, message_id=0)
        await show_categories_menu(client, mock_message_for_reply)

    # Go back to all courses list
    elif data == CB_BACK_TO_COURSES:
        await callback_query.message.delete()
        mock_message_for_reply = Message(chat=callback_query.message.chat, from_user=user, message_id=0)
        await courses_command(client, mock_message_for_reply)
    
    # Buy now
    elif data.startswith(CB_BUY):
        course_id = int(data[len(CB_BUY):])
        await show_payment_options(client, message, user, course_id)
    
    # Payment method selection
    elif data.startswith(CB_PAYMENT):
        parts = data[len(CB_PAYMENT):].split('_')
        payment_method = parts[0]
        course_id = int(parts[1])
        await handle_payment_selection(client, message, user, payment_method, course_id)
    
    # Back to main menu
    elif data == CB_BACK:
        # Check if this was a message with an image
        if message.photo:
            # If it's a photo message, we need to delete it and send a new text message
            await message.delete()
            await client.send_message(
                chat_id=message.chat.id,
                text="🏠 Main Menu - Please use the keyboard buttons below to navigate."
            )
        else:
            # Regular text message
            await message.edit_text(
                "🏠 Main Menu - Please use the keyboard buttons below to navigate.",
                reply_markup=None
            )
        user_states[user.id] = State.IDLE
    
    # Cancel operation
    elif data == CB_CANCEL:
        # Check if this was a message with an image
        if message.photo:
            # If it's a photo message, we need to delete it and send a new text message
            await message.delete()
            await client.send_message(
                chat_id=message.chat.id,
                text="❌ Operation cancelled. Use /courses to browse courses or /start to begin again."
            )
        else:
            # Regular text message
            await message.edit_text(
                "❌ Operation cancelled. Use /courses to browse courses or /start to begin again.",
                reply_markup=None
            )
        user_states[user.id] = State.IDLE
    
    # Admin actions
    elif data.startswith(CB_ADMIN):
        # Admin functionality will be implemented separately
        pass
    
    # Acknowledge the callback
    await callback_query.answer()

async def show_course_details(client, message, user, course_id):
    """Show course details and buy option"""
    db = get_db()
    course = db.query(Course).filter_by(id=course_id, is_active=True).first()
    
    if not course:
        if message.photo:
            await message.delete()
            new_message = await client.send_message(
                chat_id=message.chat.id,
                text="❌ Course not found or no longer available.",
                reply_markup=await get_course_list_markup()
            )
            return
        else:
            await message.edit_text(
                "❌ Course not found or no longer available.",
                reply_markup=await get_course_list_markup()
            )
        return
    
    # Create keyboard with Buy Now button and other options
    keyboard = []
    if course.is_free:
        keyboard.append([InlineKeyboardButton("🎁 Get Now for FREE", callback_data=f"{CB_BUY}{course.id}")])
    else:
        keyboard.append([InlineKeyboardButton("💲 Buy Now", callback_data=f"{CB_BUY}{course.id}")])
    
    keyboard.append([InlineKeyboardButton("👨‍💼 Buy Directly from Admin", url=f"https://t.me/ANONYMOUS_AMIT")])
    
    # Add Demo Video button if link exists
    if course.demo_video_link:
        keyboard.append([InlineKeyboardButton("🎬 DEMO VIDEOS ✅", url=course.demo_video_link)])

    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Back to Courses", callback_data=CB_BACK)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Format course details
    course_text = format_course_info(course)
    
    # Check if the course has an image
    if course.image_link and not message.photo:
        try:
            # For a new image, we need to delete the old message and send a new one
            chat_id = message.chat.id
            message_id = message.id
            
            # Try to delete the original message
            try:
                await message.delete()
            except Exception as e:
                print(f"Error deleting message: {e}")
            
            # For local development URLs, we need a different approach
            # Check if the URL is a local URL (contains localhost, 127.0.0.1, or specific patterns)
            if "localhost" in course.image_link or "127.0.0.1" in course.image_link or "192.168" in course.image_link:
                # Instead of using the URL directly, just send a message with the course info
                await client.send_message(
                    chat_id=chat_id,
                    text=f"{course_text}\n\n_Note: Course image available on website_",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Try to send the photo using the URL
                try:
                    await client.send_photo(
                        chat_id=chat_id,
                        photo=course.image_link,
                        caption=course_text,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    print(f"Error sending photo, falling back to text: {e}")
                    await client.send_message(
                        chat_id=chat_id,
                        text=f"{course_text}\n\n_Note: Course image available on website_",
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN
                    )
        except Exception as e:
            print(f"Error in show_course_details: {e}")
            # If any error occurs, try to update the original message
            try:
                await message.edit_text(
                    course_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e2:
                print(f"Secondary error in show_course_details: {e2}")
    else:
        # If no image or already showing an image, just update the text
        try:
            await message.edit_text(
                course_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Error updating message: {e}")
    
    user_states[user.id] = State.VIEWING_COURSES
    log_action(str(user.id), "view_course", details=f"Viewed course: {course.title}")

async def show_payment_options(client, message, user, course_id):
    """Show payment options for a course"""
    db = get_db()
    course = db.query(Course).filter_by(id=course_id, is_active=True).first()
    
    if not course:
        if message.photo:
            await message.delete()
            new_message = await client.send_message(
                chat_id=message.chat.id,
                text="❌ Course not found or no longer available.",
                reply_markup=await get_course_list_markup()
            )
            return
        else:
            await message.edit_text(
                "❌ Course not found or no longer available.",
                reply_markup=await get_course_list_markup()
            )
        return
    
    if course.is_free:
        # If course is free, directly grant access (or simulate it for now)
        await send_course_link(client, message, user, course, is_free_course=True)
        log_action(str(user.id), "get_free_course", details=f"Accessed free course: {course.title}")
        user_states[user.id] = State.IDLE # Reset state
        return

    # Get course-specific payment options if available
    payment_options = []
    if course.payment_options:
        payment_options = course.payment_options.split(',')
    
    # If no course-specific options, use global options
    if not payment_options:
        if PAYMENT_OPTIONS['UPI']:
            payment_options.append('upi')
        if PAYMENT_OPTIONS['CRYPTO']:
            payment_options.append('crypto')
        if PAYMENT_OPTIONS['PAYPAL']:
            payment_options.append('paypal')
        if PAYMENT_OPTIONS['COD']:
            payment_options.append('cod')
        if PAYMENT_OPTIONS['GIFT_CARD']:
            payment_options.append('gift')
    
    # Create keyboard with payment options
    keyboard = []
    
    if 'upi' in payment_options:
        keyboard.append([
            InlineKeyboardButton("UPI Payment", callback_data=f"{CB_PAYMENT}upi_{course_id}")
        ])
    
    if 'crypto' in payment_options:
        keyboard.append([
            InlineKeyboardButton("Cryptocurrency", callback_data=f"{CB_PAYMENT}crypto_{course_id}")
        ])
    
    if 'paypal' in payment_options:
        keyboard.append([
            InlineKeyboardButton("PayPal", callback_data=f"{CB_PAYMENT}paypal_{course_id}")
        ])
    
    if 'cod' in payment_options:
        keyboard.append([
            InlineKeyboardButton("Cash on Delivery", callback_data=f"{CB_PAYMENT}cod_{course_id}")
        ])
    
    if 'gift' in payment_options:
        keyboard.append([
            InlineKeyboardButton("Gift Card", callback_data=f"{CB_PAYMENT}gift_{course_id}")
        ])
    
    # Add direct admin purchase option
    keyboard.append([
        InlineKeyboardButton("👨‍💼 Buy Directly from Admin ", url="https://t.me/ANONYMOUS_AMIT")
    ])
    
    # Add back buttons
    keyboard.append([
        InlineKeyboardButton("⬅️ Back to Course", callback_data=f"{CB_COURSE}{course_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("🏠 Main Menu", callback_data=CB_BACK)
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    payment_text = (
        f"💰 **Payment for: {course.title}**\n\n"
        f"💵 Amount: ₹{course.price:.2f}\n\n"
        f"Please select your preferred payment method:\n\n"
        f"_Note: For faster processing, you can buy directly from our admin._"
    )
    
    if message.photo:
        await message.delete()
        new_message = await client.send_message(
            chat_id=message.chat.id,
            text=payment_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.edit_text(
            payment_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    user_states[user.id] = State.SELECTING_PAYMENT
    log_action(str(user.id), "select_payment", details=f"Selected payment for: {course.title}")

async def handle_payment_selection(client, message, user, payment_method, course_id):
    """Handle payment method selection"""
    db = get_db()
    course = db.query(Course).filter_by(id=course_id, is_active=True).first()
    
    if not course:
        if message.photo:
            await message.delete()
            await client.send_message(
                chat_id=message.chat.id,
                text="❌ Course not found or no longer available.",
                reply_markup=await get_course_list_markup()
            )
        else:
            await message.edit_text(
                "❌ Course not found or no longer available.",
                reply_markup=await get_course_list_markup()
            )
        return
    
    # Get payment details based on method
    payment_details = ""
    qr_image_path = None

    if payment_method == "upi":
        payment_details = f"UPI ID: {PAYMENT_OPTIONS['UPI']}"
        if course.qr_code_image:
            qr_image_path = os.path.join("qr", course.qr_code_image) # Assuming qr codes are in qr/ directory relative to bot.py
            if not os.path.exists(qr_image_path):
                qr_image_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qr", course.qr_code_image) # adjust path if bot.py is in a subdir
                if not os.path.exists(qr_image_path):
                    print(f"QR Code image not found: {qr_image_path}") # Log if not found
                    qr_image_path = None # Reset if still not found
    elif payment_method == "crypto":
        payment_details = f"Crypto Address: {PAYMENT_OPTIONS['CRYPTO']}"
    elif payment_method == "paypal":
        payment_details = f"PayPal: {PAYMENT_OPTIONS['PAYPAL']}"
    elif payment_method == "cod":
        payment_details = f"Cash on Delivery: Please provide your address."
    elif payment_method == "gift":
        # Special handling for gift cards
        if message.photo:
            await message.delete()
            await client.send_message(
                chat_id=message.chat.id,
                text=f"💳 **Gift Card Redemption**\n\n"
                     f"You've selected to pay with a gift card for: **{course.title}**\n\n"
                     f"💰 **Amount:** ₹{course.price:.2f}\n\n"
                     f"Please enter your gift card code. We accept Amazon, Google Play, and other popular gift cards.\n\n"
                     f"_Note: Gift card redemption is subject to manual verification and may take up to 24 hours._",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL)]]),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.edit_text(
                f"💳 **Gift Card Redemption**\n\n"
                f"You've selected to pay with a gift card for: **{course.title}**\n\n"
                f"💰 **Amount:** ₹{course.price:.2f}\n\n"
                f"Please enter your gift card code. We accept Amazon, Google Play, and other popular gift cards.\n\n"
                f"_Note: Gift card redemption is subject to manual verification and may take up to 24 hours._",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL)]]),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Set user state for awaiting gift code
        user_states[user.id] = State.ENTERING_GIFT_CODE
        user_states[f"{user.id}_course"] = course_id
        user_states[f"{user.id}_payment_method"] = payment_method
        
        log_action(
            str(user.id),
            "gift_card_selected",
            details=f"Selected gift card payment for course: {course.title}"
        )
        return
    
    # Create keyboard with cancel button
    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Set user state for awaiting payment proof
    user_states[user.id] = State.SENDING_PROOF
    user_states[f"{user.id}_course"] = course_id
    user_states[f"{user.id}_payment_method"] = payment_method
    
    payment_instructions = (
        f"💳 **Payment Instructions**\n\n"
        f"You've selected: **{payment_method.upper()}**\n\n"
        f"📝 **Details:**\n{payment_details}\n\n"
        f"💰 **Amount:** ₹{course.price:.2f}\n\n"
        f"Please make the payment and send a screenshot as proof. "
        f"Once verified, you'll receive access to the course."
    )
    
    if message.photo:
        await message.delete()
        # Send QR code first if available
        if qr_image_path:
            try:
                await client.send_photo(
                    chat_id=message.chat.id,
                    photo=qr_image_path,
                    caption=f"Scan this QR Code for UPI Payment (₹{course.price:.2f})"
                )
            except Exception as e:
                print(f"Error sending QR photo: {e}")
                # Fallback to text if photo send fails
                payment_instructions = f"{payment_instructions}\n\n(QR code image for {course.price:.2f} was intended here but failed to send)"

        await client.send_message(
            chat_id=message.chat.id,
            text=payment_instructions,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Send QR code first if available
        if qr_image_path:
            try:
                await client.send_photo(
                    chat_id=message.chat.id,
                    photo=qr_image_path,
                    caption=f"Scan this QR Code for UPI Payment (₹{course.price:.2f})"
                )
            except Exception as e:
                print(f"Error sending QR photo: {e}")
                # Fallback to text if photo send fails
                payment_instructions = f"{payment_instructions}\n\n(QR code image for {course.price:.2f} was intended here but failed to send)"

        await message.edit_text(
            payment_instructions,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    log_action(
        str(user.id),
        "payment_method_selected",
        details=f"Selected {payment_method} for course: {course.title}"
    )

async def handle_gift_code(client, message, user, gift_code):
    """Handle gift card code submission"""
    # Delete the message with the gift code for security
    try:
        await message.delete()
    except Exception as e:
        print(f"Error deleting gift code message: {e}")
    
    # Get course details
    course_id = user_states.get(f"{user.id}_course")
    
    if not course_id:
        await client.send_message(
            chat_id=message.chat.id,
            text="❌ Error processing gift card. Please try again or contact support.",
            reply_markup=await get_main_menu_markup()
        )
        user_states[user.id] = State.IDLE
        return
    
    db = get_db()
    course = db.query(Course).filter_by(id=course_id).first()
    
    if not course:
        await client.send_message(
            chat_id=message.chat.id,
            text="❌ Course not found or no longer available.",
            reply_markup=await get_main_menu_markup()
        )
        user_states[user.id] = State.IDLE
        return
    
    # Create user record if not exists
    db_user = await get_or_create_user(user)
    
    # Create payment record with full gift card code
    gift_details = f"Gift Card Code: {gift_code}"
    
    payment = Payment(
        user_id=db_user.id,
        course_id=course.id,
        payment_method="gift",
        payment_proof=None,  # No screenshot for gift cards
        amount=course.price,
        status='pending',
        submission_date=datetime.datetime.now(datetime.UTC),
        ip_address=None,  # We don't have IP in Telegram
        details=gift_details  # Store full gift code
    )
    db.add(payment)
    db.commit()
    
    await client.send_message(
        chat_id=message.chat.id,
        text=f"✅ Your gift card code has been submitted successfully!\n\n"
             f"📝 **Details:**\n"
             f"- Course: {course.title}\n"
             f"- Amount: ₹{course.price:.2f}\n"
             f"- Gift Card: {gift_code}\n\n"
             f"⏳ Your code is being verified by our admin team. This process may take up to 24 hours.\n\n"
             f"You'll be notified once your payment is approved.",
        reply_markup=await get_main_menu_markup(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Reset user state
    user_states[user.id] = State.IDLE
    if f"{user.id}_course" in user_states:
        del user_states[f"{user.id}_course"]
    if f"{user.id}_payment_method" in user_states:
        del user_states[f"{user.id}_payment_method"]
    
    log_action(
        str(user.id),
        "gift_card_submitted",
        details=f"Submitted gift card for course: {course.title}"
    )

# Handle text messages (for password and other text inputs)
@app.on_message(filters.text)
async def handle_text(client, message):
    """Handle text messages"""
    user = message.from_user
    text = message.text
    
    # Skip command messages
    if text.startswith('/'):
        return
    
    # Check if awaiting password
    if user.id in user_states and user_states[user.id] == State.AWAITING_PASSWORD:
        if text == BOT_PASSWORD:
            user_states[user.id] = State.IDLE
            welcome_msg = f"✅ Password correct!\n\n👋 {WELCOME_MESSAGE}\n\nUse the buttons below to navigate."
            await message.reply(
                welcome_msg,
                quote=True,
                reply_markup=await get_main_menu_markup()
            )
            log_action(str(user.id), "password_correct")
        else:
            await message.reply(
                "❌ Incorrect password. Please try again or contact the admin.",
                quote=True
            )
            log_action(str(user.id), "password_incorrect")
        
        # Delete the message containing the password attempt
        await message.delete()
        return
    
    # Check if user is searching for courses
    elif user.id in user_states and user_states[user.id] == State.SEARCHING_COURSES:
        await handle_course_search(client, message, user, text)
        return
    
    # Check if user is entering gift code
    elif user.id in user_states and user_states[user.id] == State.ENTERING_GIFT_CODE:
        await handle_gift_code(client, message, user, text)
        return
    
    # Check if user is awaiting course request
    elif user.id in user_states and user_states[user.id] == State.AWAITING_COURSE_REQUEST:
        await save_course_request(client, message, user, text)
        return
    
    # Handle keyboard button presses
    if text == "📚 Browse Courses":
        await courses_command(client, message)
    elif text == "🔍 Search Courses":
        await search_command(client, message)
    elif text == "🗂️ Course Categories":
        await show_categories_menu(client, message)
    elif text == "📜 DMCA & Policy":
        await show_dmca_policy(client, message)
    elif text == "✍️ Request Course":
        await handle_request_course_button(client, message)
    elif text == "❓ Help":
        await help_command(client, message)
    elif text == "👤 My Purchases":
        await show_purchases(client, message)
    else:
        # Handle other text inputs
        if is_spam(text):
            log_action(str(user.id), "spam_detected", details=f"Spam message: {text[:50]}...")
            await message.reply(
                "⚠️ Your message has been flagged as potential spam and will not be processed.",
                quote=True
            )
            return
        
        await message.reply(
            "I don't understand this command. Please use the buttons or /help for assistance.",
            quote=True
        )

async def show_purchases(client, message):
    """Show user's purchases"""
    user = message.from_user
    db = get_db()
    db_user = await get_or_create_user(user)
    
    # Get approved payments
    payments = db.query(Payment).filter_by(
        user_id=db_user.id,
        status='approved'
    ).all()
    
    if not payments:
        await message.reply(
            "You haven't purchased any courses yet. Use /courses to browse available courses.",
            quote=True
        )
        return
    
    purchases_text = "🛒 **Your Purchases:**\n\n"
    
    for i, payment in enumerate(payments, 1):
        course = db.query(Course).filter_by(id=payment.course_id).first()
        if course:
            purchases_text += (
                f"{i}. **{course.title}**\n"
                f"   💰 Price: ₹{payment.amount:.2f}\n"
                f"   📅 Purchased: {payment.approval_date.strftime('%Y-%m-%d')}\n"
                f"   🔗 [Access Course]({shorten_url(course.file_link)})\n\n"
            )
    
    await message.reply(
        purchases_text,
        quote=True,
        disable_web_page_preview=True
    )
    
    log_action(str(user.id), "view_purchases")

# Handle photo messages (payment proofs)
@app.on_message(filters.photo)
async def handle_photo(client, message):
    """Handle photo uploads (payment proofs)"""
    user = message.from_user
    
    # Check if user is in sending proof state
    if (user.id not in user_states or
            user_states[user.id] != State.SENDING_PROOF or
            f"{user.id}_course" not in user_states):
        await message.reply(
            "❓ I wasn't expecting a photo. If you're trying to submit a payment proof, "
            "please select a course and payment method first.",
            quote=True
        )
        return
    
    # Get photo file
    photo = message.photo.file_id
    file = await client.download_media(photo, in_memory=True)
    
    # Validate image
    if not is_valid_image(file.getvalue()):
        await message.reply(
            "❌ The file you sent doesn't appear to be a valid image. Please try again.",
            quote=True
        )
        return
    
    # Check for duplicate payments
    if detect_duplicate_payment(file.getvalue(), user.id):
        await message.reply(
            "⚠️ This payment proof appears to be a duplicate. If this is a mistake, "
            "please contact the admin.",
            quote=True
        )
        log_action(str(user.id), "duplicate_payment_detected")
        return
    
    # Get course and payment info
    course_id = user_states[f"{user.id}_course"]
    payment_method = user_states[f"{user.id}_payment_method"]
    
    db = get_db()
    course = db.query(Course).filter_by(id=course_id).first()
    db_user = await get_or_create_user(user)
    
    if not course:
        await message.reply(
            "❌ Course not found. Please try again.",
            quote=True
        )
        return
    
    # Save payment proof
    filename = save_payment_proof(str(user.id), file.getvalue())
    
    if not filename:
        await message.reply(
            "❌ Error saving payment proof. Please try again or contact admin.",
            quote=True
        )
        return
    
    # Create payment record
    payment = Payment(
        user_id=db_user.id,
        course_id=course.id,
        payment_method=payment_method,
        payment_proof=filename,
        amount=course.price,
        status='pending',
        submission_date=datetime.datetime.now(datetime.UTC),
        ip_address=None  # We don't have IP in Telegram
    )
    db.add(payment)
    db.commit()
    
    # Auto-approve or manual verification
    if AUTO_APPROVE:
        # Auto approve
        payment.status = 'approved'
        payment.approval_date = datetime.datetime.now(datetime.UTC)
        db.commit()
        
        # Send course link
        await send_course_link(client, message, user, course)
        
        log_action(
            str(user.id),
            "payment_auto_approved",
            details=f"Auto-approved payment for course: {course.title}"
        )
    else:
        # Manual verification needed
        await message.reply(
            "✅ Your payment proof has been submitted and is pending verification by an admin. "
            "You'll be notified once it's approved.",
            quote=True
        )
        
        log_action(
            str(user.id),
            "payment_submitted",
            details=f"Submitted payment for course: {course.title}"
        )
    
    # Reset user state
    user_states[user.id] = State.IDLE
    if f"{user.id}_course" in user_states:
        del user_states[f"{user.id}_course"]
    if f"{user.id}_payment_method" in user_states:
        del user_states[f"{user.id}_payment_method"]

async def send_course_link(client, message, user, course, is_free_course=False):
    """Send course link to the user"""
    # Shorten the link for security
    short_link = shorten_url(course.file_link)
    
    if is_free_course:
        course_access_message = (
            f"🎉 **Here is your free course!**\n\n"
            f"You now have access to: **{course.title}**\n\n"
            f"🔗 **Access your course here:**\n"
            f"[Course Link]({short_link})\n\n"
            f"Enjoy your learning!"
        )
    else:
        course_access_message = (
            f"🎉 **Payment Approved!**\n\n"
            f"You now have access to: **{course.title}**\n\n"
            f"🔗 **Access your course here:**\n"
            f"[Course Link]({short_link})\n\n"
            f"Thank you for your purchase! If you have any questions or issues, please contact support."
        )
    
    await message.reply(
        course_access_message,
        quote=True,
        disable_web_page_preview=True
    )

async def handle_course_search(client, message, user, query):
    """Handle course search by name or category"""
    db = get_db()
    
    # Search by title or category, both case-insensitive
    # We need to join with Category table to search by category name
    courses = db.query(Course).join(Category, Course.category_id == Category.id, isouter=True).filter(
        (Course.title.ilike(f'%{query}%') | Category.name.ilike(f'%{query}%')) & 
        (Course.is_active == True)
    ).all()
    
    if not courses:
        await message.reply(
            "❌ No courses found matching your search. Please try a different query or browse all courses.\n\nAlternatively, you can find a list of all available courses here: @Available_course_list",
            quote=True,
            reply_markup=await get_main_menu_markup(),
            disable_web_page_preview=True
        )
        user_states[user.id] = State.IDLE
        return
    
    # Create inline keyboard with search results
    keyboard = []
    for course in courses:
        keyboard.append([
            InlineKeyboardButton(
                f"{course.title} - ₹{course.price:.2f}",
                callback_data=f"{CB_COURSE}{course.id}"
            )
        ])
    
    # Add back button
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data=CB_BACK)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply(
        f"🔍 Search results for '{query}':\n\nFound {len(courses)} courses. Tap on a course to view details:",
        quote=True,
        reply_markup=reply_markup
    )
    
    user_states[user.id] = State.VIEWING_COURSES
    log_action(str(user.id), "search_courses", details=f"Searched for: {query}, Found: {len(courses)} courses")

async def show_categories_menu(client, message: Message):
    """Display a menu of course categories."""
    user = message.from_user
    db = get_db()
    # Only show categories that have at least one active course associated with them
    categories = db.query(Category).join(Category.courses).filter(Course.is_active == True).group_by(Category.id).order_by(Category.name).all()

    if not categories:
        await message.reply(
            "😔 No course categories are currently available. Please check back later or browse all courses.",
            quote=True,
            reply_markup=await get_main_menu_markup()
        )
        return

    keyboard = []
    for cat in categories:
        # Query count of active courses for this category
        active_courses_count = db.query(Course).filter(Course.category_id == cat.id, Course.is_active == True).count()
        if active_courses_count > 0: # Ensure we only show categories with active courses
            keyboard.append([InlineKeyboardButton(f"{cat.name} ({active_courses_count})", callback_data=f"{CB_VIEW_CATEGORY_COURSES}{cat.id}")])

    if not keyboard: # If all categories ended up having 0 active courses after filtering
        await message.reply(
            "😔 No courses are currently available in any category. Please check back later or browse all courses.",
            quote=True,
            reply_markup=await get_main_menu_markup()
        )
        return

    keyboard.append([InlineKeyboardButton("📚 All Courses", callback_data=CB_BACK_TO_COURSES)])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data=CB_BACK)])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply(
        "🗂️ **Course Categories**\n\nSelect a category to view its courses:",
        quote=True,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    user_states[user.id] = State.VIEWING_COURSES 
    log_action(str(user.id), "view_categories_menu")

async def show_courses_in_category(client, callback_query: CallbackQuery, user, category_id):
    """Display courses within a selected category."""
    message = callback_query.message # Get message from callback_query
    db = get_db()
    category = db.query(Category).filter_by(id=category_id).first()
    
    if not category:
        await message.edit_text("❌ Category not found.", reply_markup=await get_main_menu_markup())
        return

    courses = db.query(Course).filter_by(category_id=category_id, is_active=True).order_by(Course.title).all()

    if not courses:
        await message.edit_text(
            f"😔 No active courses found in the category: **{category.name}**.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Categories", callback_data=CB_SHOW_CATEGORIES_MENU)],
                [InlineKeyboardButton("🏠 Main Menu", callback_data=CB_BACK)]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    keyboard = []
    for course in courses:
        price_display = f"₹{course.price:.2f}" if not course.is_free else "FREE"
        keyboard.append([
            InlineKeyboardButton(
                f"{course.title} - {price_display}",
                callback_data=f"{CB_COURSE}{course.id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("⬅️ Back to Categories", callback_data=CB_SHOW_CATEGORIES_MENU)])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data=CB_BACK)])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.edit_text(
        f"📚 Courses in **{category.name}**:\n\nTap on a course to view details:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    user_states[user.id] = State.VIEWING_COURSES
    log_action(str(user.id), "view_category_courses", details=f"Category: {category.name}")

async def show_dmca_policy(client, message: Message):
    """Display the DMCA & Copyright Policy."""
    user = message.from_user
    db = get_db()
    policy_setting = db.query(BotSetting).filter_by(key='dmca_policy_text').first()

    policy_text = "No DMCA/Policy text has been set by the admin yet."
    if policy_setting and policy_setting.value:
        policy_text = policy_setting.value

    await message.reply(
        f"📜 **DMCA Copyright & Policy**\n\n{policy_text}",
        quote=True,
        reply_markup=await get_main_menu_markup(), # Or a simple back button
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )
    log_action(str(user.id), "view_dmca_policy")

async def handle_request_course_button(client, message: Message):
    """Handles the 'Request Course' button press.
    Sets user state to await their course request details.
    """
    user = message.from_user
    await message.reply(
        "✍️ Please describe the course you would like to request. Include as much detail as possible (e.g., name, instructor, topics).",
        quote=True,
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel Request")]], resize_keyboard=True, one_time_keyboard=True)
    )
    user_states[user.id] = State.AWAITING_COURSE_REQUEST
    log_action(str(user.id), "pressed_request_course_button")

async def save_course_request(client, message: Message, user_pyrogram, request_text: str):
    """Saves the user's course request to the database."""
    db_user = await get_or_create_user(user_pyrogram) # Ensure user is in our DB
    
    if request_text.lower() == "❌ cancel request":
        await message.reply(
            "✅ Course request cancelled.",
            quote=True,
            reply_markup=await get_main_menu_markup()
        )
        user_states[user_pyrogram.id] = State.IDLE
        log_action(str(user_pyrogram.id), "cancelled_course_request")
        return

    db = get_db()
    new_request = CourseRequest(
        user_id=db_user.id,
        request_text=request_text,
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    db.add(new_request)
    db.commit()

    await message.reply(
        "✅ Thank you! Your course request has been submitted. Our admin team will review it.",
        quote=True,
        reply_markup=await get_main_menu_markup()
    )
    user_states[user_pyrogram.id] = State.IDLE
    log_action(str(user_pyrogram.id), "submitted_course_request", details=request_text[:200])

# Main function to run the bot
async def main():
    await app.start()
    print("Bot started!")
    
    # Keep the bot running
    await asyncio.sleep(999999)
    
    await app.stop()

if __name__ == "__main__":
    app.run() 
