import logging
import os
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv('OT_TOKEN') or os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables!")

ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID')) if os.getenv('LOG_CHANNEL_ID') else None
MAIN_CHANNEL_ID = int(os.getenv('MAIN_CHANNEL_ID')) if os.getenv('MAIN_CHANNEL_ID') else None
CONTACT_USERNAME = os.getenv('CONTACT_USERNAME')
CONTACT_PHONE = os.getenv('CONTACT_PHONE')
BOT_USERNAME = os.getenv('BOT_USERNAME')

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for the registration conversation
(
    GET_FULL_NAME,
    GET_SEMESTER,
    GET_STREAM,
    GET_GENDER,
    GET_PAYMENT_METHOD,
    AWAITING_SCREENSHOT,
    ANNOUNCEMENT_SEMESTER,
    ANNOUNCEMENT_CONTENT,
    ASK_COMMENT,
    REPLY_TO_COMMENT,
) = range(10)

# =============================================================================
# ERROR HANDLER
# =============================================================================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Notify admins of critical errors
    if ADMIN_IDS:
        error_msg = f"Bot error: {context.error}\nUpdate: {update}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, error_msg[:4000])
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id} about error: {e}")

# =============================================================================
# BOT WELCOME & START HANDLER
# =============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command with welcome message and menu buttons."""
    user = update.effective_user
    
    # Check user status
    user_status = context.bot_data.setdefault('user_statuses', {}).get(user.id, 'none')
    
    # Welcome message for all users
    welcome_message = f"""
🎓 Welcome to ABJ Tutorial Bot, {user.first_name}!

Your Gateway to Academic Excellence!

ABJ Tutorial helps Ethiopian university freshmen achieve outstanding results with:
• Comprehensive Video Tutorials
• Past Exam Solutions  
• Simplified Study Notes
• Audio Lessons
• Step-by-step Explanations

Join thousands of successful students who have improved their grades with ABJ Tutorial!
    """.strip()

    # Admin panel with menu buttons
    if user.id in ADMIN_IDS:
        admin_menu = [
            ["Send Announcement", "View Statistics"],
            ["Clear Pending", "View Questions"]
        ]
        reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Admin Control Panel\n\nWelcome back, {user.first_name}!",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    # Approved users - show main menu with menu buttons
    elif user_status == 'approved':
        user_data = context.bot_data.get('user_data', {}).get(user.id, {})
        
        user_menu = [
            ["Ask Question", "Help & Support"]
        ]
        reply_markup = ReplyKeyboardMarkup(user_menu, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Welcome back {user.first_name}!\n\n"
            f"Approved Member\n"
            f"Semester: {user_data.get('semester', 'Not specified')}\n"
            f"Stream: {user_data.get('stream', 'Not specified')}\n\n"
            "Choose an option below:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    # Pending users - show status message
    elif user_status == 'pending':
        await update.message.reply_text(
            f"Hello {user.first_name}!\n\n"
            "Payment Under Review\n\n"
            "Your registration is being processed\n"
            "Usually takes less than 24 hours\n"
            "You'll get full access upon approval\n\n"
            "We'll notify you immediately once approved!",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # New users - show welcome with Get Started button
    else:
        keyboard = [
            [InlineKeyboardButton("🚀 Get Started", callback_data="get_started")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=reply_markup
        )
        return ConversationHandler.END

async def handle_get_started_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Get Started button click."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is already approved
    user_status = context.bot_data.setdefault('user_statuses', {}).get(user.id, 'none')
    if user_status == 'approved':
        user_menu = [
            ["Ask Question", "Help & Support"]
        ]
        reply_markup = ReplyKeyboardMarkup(user_menu, resize_keyboard=True)
        await query.edit_message_text("You are already an approved member!")
        await query.message.reply_text("Choose an option below:", reply_markup=reply_markup)
        return ConversationHandler.END
    
    if user_status == 'pending':
        await query.edit_message_text("Your payment is under review. Please wait for approval.")
        return ConversationHandler.END
    
    # Start registration immediately
    await query.edit_message_text(
        f"Welcome to ABJ Tutorial Registration!\n\n"
        f"Hello {user.first_name}! Let's get you registered.\n\n"
        "Please tell me your Full Name (as it appears on your university ID):"
    )
    context.user_data['registration_in_progress'] = True
    return GET_FULL_NAME

# =============================================================================
# MENU BUTTON HANDLERS
# =============================================================================
async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all menu button clicks."""
    user = update.effective_user
    text = update.message.text
    
    # Get user status
    user_status = context.bot_data.setdefault('user_statuses', {}).get(user.id, 'none')
    
    # User menu handlers
    if text == "Ask Question":
        if user_status == 'approved':
            await ask_question_start(update, context)
        else:
            await update.message.reply_text("This feature is only available for approved members.")
    
    elif text == "Help & Support":
        await show_help_support(update, context)
    
    # Admin menu handlers
    elif user.id in ADMIN_IDS:
        if text == "Send Announcement":
            await announcement_start(update, context)
        
        elif text == "View Statistics":
            await view_stats(update, context)
        
        elif text == "Clear Pending":
            await clear_pending_requests(update, context)
        
        elif text == "View Questions":
            await view_pending_questions(update, context)
        

async def ask_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start asking a question via menu button."""
    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_question")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Ask a Question\n\n"
        "Please type your question about:\n"
        "• Course materials & content\n"
        "• Study techniques\n" 
        "• Exam preparation\n"
        "• Video tutorials\n"
        "• Any academic concerns\n\n"
        "Type your question below:",
        reply_markup=reply_markup
    )
    return ASK_COMMENT

async def show_help_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help and support information via menu button."""
    help_text = f"""
ABJ Tutorial Help & Support

Available Features:
• Ask Question - Get help from our tutors
• Access learning materials  
• Comprehensive course content

Contact Support:
Telegram: {CONTACT_USERNAME}
Phone: {CONTACT_PHONE}

Support Hours:
Monday-Friday: 8:00 AM - 8:00 PM
Saturday-Sunday: 9:00 AM - 6:00 PM

We're here to help you succeed!
    """.strip()
    
    user_menu = [
        ["Ask Question", "Help & Support"]
    ]
    reply_markup = ReplyKeyboardMarkup(user_menu, resize_keyboard=True)
    await update.message.reply_text(help_text, reply_markup=reply_markup)

# =============================================================================
# ADMIN MENU HANDLERS
# =============================================================================
async def announcement_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start announcement via menu button."""
    keyboard = [
        [InlineKeyboardButton("First Semester", callback_data='announce_First Semester')],
        [InlineKeyboardButton("Second Semester", callback_data='announce_Second Semester')],
        [InlineKeyboardButton("All Students", callback_data='announce_all')],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel_announcement')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Send Announcement\n\n"
        "Select which group should receive this announcement:",
        reply_markup=reply_markup
    )
    return ANNOUNCEMENT_SEMESTER

async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show stats via menu button."""
    user_statuses = context.bot_data.get('user_statuses', {})
    user_data = context.bot_data.get('user_data', {})
    pending_reviews = context.bot_data.get('pending_reviews', {})
    pending_comments = context.bot_data.get('pending_comments', {})
    
    # Calculate statistics
    total_users = len(user_statuses)
    approved_users = sum(1 for status in user_statuses.values() if status == 'approved')
    pending_users = sum(1 for status in user_statuses.values() if status == 'pending')
    
    # Semester distribution
    semester_counts = {}
    for user_id, data in user_data.items():
        if user_statuses.get(user_id) == 'approved':
            semester = data.get('semester', 'Unknown')
            semester_counts[semester] = semester_counts.get(semester, 0) + 1
    
    stats_text = f"""
Bot Statistics Dashboard

Users:
• Total: {total_users}
• Approved: {approved_users} 
• Pending: {pending_users}
• Awaiting Review: {len(pending_reviews)}

Pending Questions: {len(pending_comments)}

Semester Distribution:
"""
    
    for semester, count in semester_counts.items():
        stats_text += f"• {semester}: {count}\n"
    
    admin_menu = [
        ["Send Announcement", "View Statistics"],
        ["Clear Pending", "View Questions"]
    ]
    reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
    await update.message.reply_text(stats_text, reply_markup=reply_markup)

async def clear_pending_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear pending requests via menu button."""
    pending_count = len(context.bot_data.get('pending_reviews', {}))
    context.bot_data['pending_reviews'] = {}
    
    admin_menu = [
        ["Send Announcement", "View Statistics"],
        ["Clear Pending", "View Questions"]
    ]
    reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
    await update.message.reply_text(f"Cleared {pending_count} pending payment requests.", reply_markup=reply_markup)

async def view_pending_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View pending questions via menu button."""
    pending_comments = context.bot_data.get('pending_comments', {})
    
    if not pending_comments:
        admin_menu = [
            ["Send Announcement", "View Statistics"],
            ["Clear Pending", "View Questions"]
        ]
        reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
        await update.message.reply_text("No pending questions.", reply_markup=reply_markup)
        return
    
    for comment_id, comment_data in list(pending_comments.items())[:5]:
        comment_text = f"""
Pending Question

From: {comment_data.get('user_name', 'N/A')}
Username: @{comment_data.get('username', 'N/A')}
Semester: {comment_data.get('semester', 'N/A')}

Question:
{comment_data.get('comment', 'N/A')}
        """.strip()
        
        keyboard = [[InlineKeyboardButton("📝 Reply", callback_data=f"reply_{comment_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(comment_text, reply_markup=reply_markup)

# =============================================================================
# REGISTRATION CONVERSATION HANDLERS
# =============================================================================
async def get_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the user's full name."""
    user_full_name = update.message.text.strip()
    if not user_full_name:
        await update.message.reply_text("Please enter a valid name.")
        return GET_FULL_NAME

    context.user_data['full_name'] = user_full_name

    keyboard = [
        [InlineKeyboardButton("First Semester", callback_data='semester_First Semester')],
        [InlineKeyboardButton("Second Semester", callback_data='semester_Second Semester')],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel_registration')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Welcome, {user_full_name}!\n\n"
        "Now select your Semester:",
        reply_markup=reply_markup
    )
    return GET_SEMESTER

async def get_semester(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the user's semester via callback query."""
    query = update.callback_query
    await query.answer()

    semester = query.data.split('_')[1]
    context.user_data['semester'] = semester

    keyboard = []
    if semester == 'First Semester':
        keyboard = [
            [InlineKeyboardButton("Social Science", callback_data='stream_Social Science')],
            [InlineKeyboardButton("Natural Science", callback_data='stream_Natural Science')],
        ]
    elif semester == 'Second Semester':
        keyboard = [
            [InlineKeyboardButton("Pre-Engineering", callback_data='stream_Pre-Engineering')],
            [InlineKeyboardButton("Other Natural Science", callback_data='stream_Other Natural Science')],
            [InlineKeyboardButton("Social Science", callback_data='stream_Social Science')],
            [InlineKeyboardButton("Health Science", callback_data='stream_Health')],
        ]
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel_registration')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"You selected: {semester}\n\n"
        "Now choose your Stream:",
        reply_markup=reply_markup
    )
    return GET_STREAM

async def get_stream(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the user's stream via callback query."""
    query = update.callback_query
    await query.answer()

    stream = query.data.split('_')[1]
    context.user_data['stream'] = stream

    keyboard = [
        [InlineKeyboardButton("Male", callback_data='gender_Male')],
        [InlineKeyboardButton("Female", callback_data='gender_Female')],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel_registration')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"You selected: {stream}\n\n"
        "What is your Gender?",
        reply_markup=reply_markup
    )
    return GET_GENDER

async def get_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the user's gender via callback query."""
    query = update.callback_query
    await query.answer()

    gender = query.data.split('_')[1]
    context.user_data['gender'] = gender

    keyboard = [
        [InlineKeyboardButton("Telebirr", callback_data='method_Telebirr')],
        [InlineKeyboardButton("CBE", callback_data='method_CBE')],
        [InlineKeyboardButton("mPesa", callback_data='method_mPesa')],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel_registration')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"You selected: {gender}\n\n"
        "Choose your Payment Method:",
        reply_markup=reply_markup
    )
    return GET_PAYMENT_METHOD

async def get_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the user's payment method and provides instructions."""
    query = update.callback_query
    await query.answer()

    payment_method = query.data.split('_')[1]
    context.user_data['payment_method'] = payment_method

    payment_instructions_text = ""
    account_details = ""
    
    if payment_method == "Telebirr":
        payment_instructions_text = "Please transfer 120 birr to:"
        account_details = "0927429565 (ABDULMEJID SEHAB)"
    elif payment_method == "CBE":
        payment_instructions_text = "Please transfer 120 birr to:"
        account_details = "1000417007192 (ABDULMEJID SEHAB)"
    elif payment_method == "mPesa":
        payment_instructions_text = "Please transfer 120 birr to:"
        account_details = "0927429565 (ABDULMEJID SEHAB)"

    # Generate a unique payment ID
    user_id = query.from_user.id
    payment_id = f"ABJ{user_id}{query.message.message_id}" 
    context.user_data['payment_id'] = payment_id

    summary_text = f"""
Registration Summary

Personal Details:
• Full Name: {context.user_data['full_name']}
• Semester: {context.user_data['semester']}
• Stream: {context.user_data['stream']}
• Gender: {context.user_data['gender']}

Payment Information:
• Method: {payment_method}
• Payment ID: {payment_id}

Payment Instructions:
{payment_instructions_text}
{account_details}

Final Step: Send your payment screenshot as a photo.
    """.strip()

    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel_registration')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        summary_text,
        reply_markup=reply_markup
    )
    return AWAITING_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the payment screenshot and sends it to admins."""
    user = update.effective_user
    message = update.effective_message
    
    if not message.photo:
        await message.reply_text("Please send your payment screenshot as a photo.")
        return AWAITING_SCREENSHOT
    
    # Store payment data
    payment_id = context.user_data.get('payment_id', f"UNKNOWN_{user.id}_{message.message_id}")
    
    # Update user status
    context.bot_data.setdefault('user_statuses', {})[user.id] = 'pending'
    
    # Store user data
    user_info = {
        'full_name': context.user_data.get('full_name'),
        'semester': context.user_data.get('semester'),
        'stream': context.user_data.get('stream'),
        'gender': context.user_data.get('gender'),
        'payment_method': context.user_data.get('payment_method'),
        'username': user.username,
        'first_name': user.first_name,
        'user_id': user.id,
    }
    context.bot_data.setdefault('user_data', {})[user.id] = user_info

    # Store pending review with screenshot file_id
    pending_info = {
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'full_name': context.user_data.get('full_name'),
        'semester': context.user_data.get('semester'),
        'stream': context.user_data.get('stream'),
        'gender': context.user_data.get('gender'),
        'payment_method': context.user_data.get('payment_method'),
        'payment_id': payment_id,
        'screenshot_file_id': message.photo[-1].file_id,
        'timestamp': message.date.isoformat(),
        'user_info': user_info,
    }
    context.bot_data.setdefault('pending_reviews', {})[user.id] = pending_info

    # Create admin notification
    admin_caption = f"""
NEW PAYMENT REQUEST

Payment ID: {payment_id}
User: {user.first_name} (@{user.username or 'N/A'})
User ID: {user.id}

Details:
• Name: {context.user_data.get('full_name', 'N/A')}
• Semester: {context.user_data.get('semester', 'N/A')}
• Stream: {context.user_data.get('stream', 'N/A')}
• Payment Method: {context.user_data.get('payment_method', 'N/A')}

Time: {message.date.strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    # Send to admins with approval buttons
    keyboard = [[
        InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_{user.id}"),
        InlineKeyboardButton("❌ REJECT", callback_data=f"reject_{user.id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=message.photo[-1].file_id,
                caption=admin_caption,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send to admin {admin_id}: {e}")

    await message.reply_text(
        f"Thank you for your submission!\n\n"
        f"Payment ID: {payment_id}\n\n"
        "Your registration is under review\n"
        "We'll notify you once approved (usually within 24 hours)\n\n"
        "Thank you for choosing ABJ Tutorial!",
        reply_markup=ReplyKeyboardRemove()
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# =============================================================================
# ADMIN APPROVAL HANDLER
# =============================================================================
async def user_approval_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin approval/rejection of users."""
    query = update.callback_query
    admin_id = query.from_user.id
    
    # Check if user is admin
    if admin_id not in ADMIN_IDS:
        await query.answer("You are not authorized to perform this action.", show_alert=True)
        return
    
    await query.answer()
    
    try:
        action, user_id_str = query.data.split("_")
        user_id = int(user_id_str)
        
        # Get user data from pending reviews
        user_data = context.bot_data.get('pending_reviews', {}).get(user_id)
        if not user_data:
            await query.edit_message_text("Request already processed or not found.")
            return
        
        # Remove from pending reviews immediately
        context.bot_data.get('pending_reviews', {}).pop(user_id, None)
        
        if action == "approve":
            # Update user status
            context.bot_data.setdefault('user_statuses', {})[user_id] = 'approved'
            
            # Send to log channel
            try:
                log_message = f"""
USER APPROVED

Student Information:
• Full Name: {user_data.get('full_name', 'N/A')}
• Telegram: @{user_data.get('username', 'N/A')} ({user_data.get('first_name', 'N/A')})
• User ID: {user_id}
• Semester: {user_data.get('semester', 'N/A')}
• Stream: {user_data.get('stream', 'N/A')}
• Gender: {user_data.get('gender', 'N/A')}
• Payment Method: {user_data.get('payment_method', 'N/A')}
• Payment ID: {user_data.get('payment_id', 'N/A')}

Approved by: @{query.from_user.username or 'N/A'} ({admin_id})
Time: {query.message.date.strftime('%Y-%m-%d %H:%M:%S')}

Welcome to ABJ Tutorial!
                """.strip()
                
                if LOG_CHANNEL_ID:
                    await context.bot.send_photo(
                        chat_id=LOG_CHANNEL_ID,
                        photo=user_data.get('screenshot_file_id'),
                        caption=log_message
                    )
            except Exception as e:
                logger.error(f"Failed to send approval log: {e}")
            
            # Generate a one-time invite link (usable once) and send to the user
            try:
                invite = await context.bot.create_chat_invite_link(chat_id=MAIN_CHANNEL_ID, member_limit=1)
                keyboard = [[InlineKeyboardButton("Join Main Channel", url=invite.invite_link)]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await context.bot.send_message(
                    user_id,
                    "PAYMENT APPROVED! WELCOME TO ABJ TUTORIAL!\n\n"
                    "Your payment has been verified!\n"
                    "You now have full access to our learning materials\n\n"
                    "Click below to join our main channel (one-time link):",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Could not notify user {user_id} with invite link: {e}")
            
            # Delete the admin approval message
            await query.delete_message()
        
        elif action == "reject":
            # Update user status
            context.bot_data.setdefault('user_statuses', {})[user_id] = 'rejected'
            
            # Send rejection information to log channel
            try:
                log_message = f"""
USER REJECTED

Student Information:
• Full Name: {user_data.get('full_name', 'N/A')}
• Telegram: @{user_data.get('username', 'N/A')} ({user_data.get('first_name', 'N/A')})
• User ID: {user_id}
• Semester: {user_data.get('semester', 'N/A')}
• Stream: {user_data.get('stream', 'N/A')}
• Gender: {user_data.get('gender', 'N/A')}
• Payment Method: {user_data.get('payment_method', 'N/A')}
• Payment ID: {user_data.get('payment_id', 'N/A')}

Rejected by: @{query.from_user.username or 'N/A'} ({admin_id})
Time: {query.message.date.strftime('%Y-%m-%d %H:%M:%S')}

Payment verification failed
                """.strip()
                
                if LOG_CHANNEL_ID:
                    await context.bot.send_photo(
                        chat_id=LOG_CHANNEL_ID,
                        photo=user_data.get('screenshot_file_id'),
                        caption=log_message
                    )
            except Exception as e:
                logger.error(f"Failed to send rejection log: {e}")
            
            # Notify user
            try:
                await context.bot.send_message(
                    user_id,
                    "Payment Review Update\n\n"
                    "Unfortunately, we couldn't verify your payment\n\n"
                    "Possible reasons:\n"
                    "• Unclear screenshot\n"
                    "• Payment details didn't match\n"
                    "• Payment not received\n\n"
                    "Please check and try again"
                )
            except Exception as e:
                logger.error(f"Could not notify user {user_id}: {e}")
            
            # Delete the admin rejection message
            await query.delete_message()
            
    except Exception as e:
        logger.error(f"Error in user_approval_handler: {e}")
        await query.edit_message_text("Error processing request. Please try again.")

# =============================================================================
# CANCEL HANDLERS
# =============================================================================
async def cancel_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle registration cancellation via callback."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Registration Cancelled\n\n"
        "Your registration has been cancelled.\n"
        "You can start again anytime using /start\n\n"
        "Thank you for your interest in ABJ Tutorial!"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_announcement_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle announcement cancellation via callback."""
    query = update.callback_query
    await query.answer()
    
    admin_menu = [
        ["Send Announcement", "View Statistics"],
        ["Clear Pending", "View Questions"]
    ]
    reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
    
    await query.edit_message_text(
        "Announcement Cancelled\n\n"
        "Announcement creation has been cancelled.",
        reply_markup=reply_markup
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_question_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle question cancellation via callback."""
    query = update.callback_query
    await query.answer()
    
    user_menu = [["Ask Question", "Help & Support"]]
    reply_markup = ReplyKeyboardMarkup(user_menu, resize_keyboard=True)
    
    await query.edit_message_text(
        "Question Cancelled\n\n"
        "Your question has been cancelled.",
        reply_markup=reply_markup
    )
    context.user_data.clear()
    return ConversationHandler.END

# =============================================================================
# ASK COMMENT FEATURE
# =============================================================================
async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and forward user's comment to admins."""
    user = update.effective_user
    comment = update.message.text
    
    user_data = context.bot_data.get('user_data', {}).get(user.id, {})
    
    # Store comment with proper unique ID
    comment_id = f"comment_{user.id}_{update.message.message_id}"
    context.bot_data.setdefault('pending_comments', {})[comment_id] = {
        'user_id': user.id,
        'user_name': user_data.get('full_name', user.first_name),
        'username': user.username,
        'semester': user_data.get('semester', 'N/A'),
        'comment': comment,
        'timestamp': update.message.date.isoformat()
    }
    
    # Format for admins
    comment_message = f"""
New Question from Student

Student: {user_data.get('full_name', user.first_name)}
Username: @{user.username or 'N/A'}
Semester: {user_data.get('semester', 'N/A')}
Comment ID: {comment_id}

Question:
{comment}
    """.strip()
    
    # Send to admins
    keyboard = [[InlineKeyboardButton("📝 Reply", callback_data=f"reply_{comment_id}")]]
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=comment_message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Failed to send comment to admin {admin_id}: {e}")
    
    user_menu = [["Ask Question", "Help & Support"]]
    reply_markup = ReplyKeyboardMarkup(user_menu, resize_keyboard=True)
    
    await update.message.reply_text(
        "Question Sent Successfully!\n\n"
        "Our team will respond soon\n"
        "Check your messages for replies\n\n"
        "Thank you for your question!",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def reply_to_comment_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start replying to a user comment."""
    query = update.callback_query
    await query.answer()
    
    # Extract comment_id properly from callback data
    callback_data = query.data
    comment_id = callback_data.replace('reply_', '')
    
    comment_data = context.bot_data.get('pending_comments', {}).get(comment_id)
    
    if not comment_data:
        await query.edit_message_text("Comment no longer available or already replied.")
        return ConversationHandler.END
    
    context.user_data['reply_comment_id'] = comment_id
    context.user_data['reply_user_id'] = comment_data['user_id']
    context.user_data['reply_user_name'] = comment_data['user_name']
    
    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_reply")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Reply to {comment_data['user_name']}\n\n"
        f"Original Question:\n{comment_data['comment']}\n\n"
        "Type your reply below:",
        reply_markup=reply_markup
    )
    return REPLY_TO_COMMENT

async def send_reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send admin's reply to the user."""
    reply_text = update.message.text
    
    comment_id = context.user_data.get('reply_comment_id')
    user_id = context.user_data.get('reply_user_id')
    user_name = context.user_data.get('reply_user_name')
    
    if not comment_id or not user_id:
        admin_menu = [
            ["Send Announcement", "View Statistics"],
            ["Clear Pending", "View Questions"]
        ]
        reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
        await update.message.reply_text("Reply session expired. Please try again.", reply_markup=reply_markup)
        context.user_data.clear()
        return ConversationHandler.END
    
    # Remove the comment from pending
    context.bot_data.get('pending_comments', {}).pop(comment_id, None)
    
    # Send reply to user
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Reply from ABJ Tutorial\n\n"
                 f"Hello {user_name}!\n\n"
                 f"{reply_text}\n\n"
                 f"Thank you for your question!"
        )
        admin_menu = [
            ["Send Announcement", "View Statistics"],
            ["Clear Pending", "View Questions"]
        ]
        reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
        await update.message.reply_text("Reply sent successfully!", reply_markup=reply_markup)
            
    except Exception as e:
        admin_menu = [
            ["Send Announcement", "View Statistics"],
            ["Clear Pending", "View Questions"]
        ]
        reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
        await update.message.reply_text("Failed to send reply. User may have blocked the bot.", reply_markup=reply_markup)
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle reply cancellation via callback."""
    query = update.callback_query
    await query.answer()
    
    admin_menu = [
        ["Send Announcement", "View Statistics"],
        ["Clear Pending", "View Questions"]
    ]
    reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
    
    await query.edit_message_text(
        "Reply Cancelled\n\n"
        "Reply process has been cancelled.",
        reply_markup=reply_markup
    )
    context.user_data.clear()
    return ConversationHandler.END

# =============================================================================
# ANNOUNCEMENT FEATURE WITH CHANNEL LINK
# =============================================================================
async def announcement_semester(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store selected semester for announcement."""
    query = update.callback_query
    await query.answer()
    
    semester = query.data.split('_')[1]
    context.user_data['announcement_semester'] = semester
    
    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_announcement")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Announcement for {semester}\n\n"
        "Send the announcement content (text, photo, or document):",
        reply_markup=reply_markup
    )
    return ANNOUNCEMENT_CONTENT

async def announcement_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send announcement to selected users with channel link."""
    user = update.effective_user
    message = update.effective_message
    semester = context.user_data.get('announcement_semester', 'all')
    
    # Get target users
    user_statuses = context.bot_data.get('user_statuses', {})
    user_data = context.bot_data.get('user_data', {})
    
    target_users = []
    for user_id, status in user_statuses.items():
        if status == 'approved':
            user_semester = user_data.get(user_id, {}).get('semester')
            if semester == 'all' or user_semester == semester:
                target_users.append(user_id)
    
    # Send announcement with channel link
    sent_count = 0
    failed_count = 0
    
    for user_id in target_users:
        try:
            if message.text:
                await context.bot.send_message(
                    user_id,
                    f"Announcement from ABJ Tutorial\n\n{message.text}\n\n"
                    "Visit our resources for more updates."
                )
            elif message.photo:
                await context.bot.send_photo(
                    user_id,
                    photo=message.photo[-1].file_id,
                    caption=f"Announcement from ABJ Tutorial\n\n{message.caption or ''}\n\n"
                            "Visit our resources for more updates."
                )
            sent_count += 1
        except Exception as e:
            failed_count += 1
    
    admin_menu = [
        ["Send Announcement", "View Statistics"],
        ["Clear Pending", "View Questions"]
    ]
    reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
    
    await message.reply_text(
        f"Announcement Sent Successfully!\n\n"
        f"Target: {semester}\n"
        f"Successful: {sent_count}\n"
        f"Failed: {failed_count}",
        reply_markup=reply_markup
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# =============================================================================
# CONVERSATION CANCELLATION
# =============================================================================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    user = update.effective_user
    
    # Check user status to show appropriate menu
    user_status = context.bot_data.setdefault('user_statuses', {}).get(user.id, 'none')
    
    if user.id in ADMIN_IDS:
        admin_menu = [
            ["Send Announcement", "View Statistics"],
            ["Clear Pending", "View Questions"]
        ]
        reply_markup = ReplyKeyboardMarkup(admin_menu, resize_keyboard=True)
        await update.message.reply_text("Operation cancelled.", reply_markup=reply_markup)
    elif user_status == 'approved':
        user_menu = [["Ask Question", "Help & Support"]]
        reply_markup = ReplyKeyboardMarkup(user_menu, resize_keyboard=True)
        await update.message.reply_text("Operation cancelled.", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Operation cancelled. Send /start to begin again.")
    
    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
# BLOCK FORWARDED/INVITE LINK JOINS
# =============================================================================
async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detect users who join the main channel via an invite link and block them
    unless they are approved in `context.bot_data['user_statuses']`.
    """
    try:
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat:
            return

        # Only act on the configured main channel
        if chat.id != MAIN_CHANNEL_ID:
            return

        # Telegram provides `invite_link` on the message when the user joined via a link
        invite_link = getattr(message, 'invite_link', None)

        if not message.new_chat_members:
            return

        for member in message.new_chat_members:
            user_id = member.id

            # If joined via invite link (shared/forwarded) and not approved -> remove
            if invite_link:
                user_status = context.bot_data.get('user_statuses', {}).get(user_id, 'none')
                if user_status != 'approved':
                    try:
                        # Kick (ban then unban) to remove the user immediately
                        await context.bot.ban_chat_member(chat_id=chat.id, user_id=user_id)
                        await context.bot.unban_chat_member(chat_id=chat.id, user_id=user_id)
                    except Exception as e:
                        logger.error(f"Failed to remove unauthorized user {user_id}: {e}")

                    # Notify log channel and admins
                    try:
                        note = (
                            f"🚫 Unauthorized join blocked\n"
                            f"User: {member.full_name} (@{member.username or 'N/A'})\n"
                            f"User ID: {user_id}\n"
                            f"Joined via invite link: {invite_link}\n"
                            f"Action: removed from channel"
                        )
                        if LOG_CHANNEL_ID:
                            await context.bot.send_message(LOG_CHANNEL_ID, note)
                    except Exception as e:
                        logger.error(f"Failed to notify log channel about blocked join: {e}")

    except Exception as e:
        logger.error(f"Error in handle_new_chat_members: {e}")

# =============================================================================
# MAIN BOT SETUP
# =============================================================================
def main() -> None:
    """Start the bot."""
    print("=" * 50)
    print("🤖 ABJ Tutorial Bot is starting...")
    print(f"📊 Python version: {sys.version}")
    print("=" * 50)
    
    try:
        # Monkey patch for Python 3.14 compatibility
        import telegram.ext._updater
        if not hasattr(telegram.ext._updater.Updater, '_Updater__polling_cleanup_cb'):
            # Add the missing attribute
            telegram.ext._updater.Updater._Updater__polling_cleanup_cb = None
        
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Initialize bot data
        application.bot_data.setdefault('pending_reviews', {})
        application.bot_data.setdefault('user_statuses', {})
        application.bot_data.setdefault('user_data', {})
        application.bot_data.setdefault('pending_comments', {})

        # Main registration conversation handler
        registration_conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(handle_get_started_callback, pattern='^get_started$'),
                CommandHandler('start', start)
            ],
            states={
                GET_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
                GET_SEMESTER: [CallbackQueryHandler(get_semester, pattern='^semester_')],
                GET_STREAM: [CallbackQueryHandler(get_stream, pattern='^stream_')],
                GET_GENDER: [CallbackQueryHandler(get_gender, pattern='^gender_')],
                GET_PAYMENT_METHOD: [CallbackQueryHandler(get_payment_method, pattern='^method_')],
                AWAITING_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)],
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(cancel_registration_callback, pattern='^cancel_registration$')
            ],
        )

        # Ask comment conversation handler
        ask_comment_conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Text("Ask Question"), ask_question_start)],
            states={
                ASK_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_comment)],
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(cancel_question_callback, pattern='^cancel_question$')
            ],
        )

        # Reply to comment conversation handler
        reply_comment_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(reply_to_comment_start, pattern='^reply_')],
            states={
                REPLY_TO_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_reply_to_user)],
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(cancel_reply_callback, pattern='^cancel_reply$')
            ],
        )

        # Announcement conversation handler
        announcement_conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Text("Send Announcement"), announcement_start)],
            states={
                ANNOUNCEMENT_SEMESTER: [CallbackQueryHandler(announcement_semester, pattern='^announce_')],
                ANNOUNCEMENT_CONTENT: [MessageHandler(filters.ALL, announcement_content)],
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(cancel_announcement_callback, pattern='^cancel_announcement$')
            ],
        )

        # =========================================================================
        # HANDLER ORDER
        # =========================================================================
        
        # 1. Admin approval handler
        application.add_handler(CallbackQueryHandler(user_approval_handler, pattern='^(approve|reject)_'))
        
        # 2. Cancel handlers
        application.add_handler(CallbackQueryHandler(cancel_registration_callback, pattern='^cancel_registration$'))
        application.add_handler(CallbackQueryHandler(cancel_announcement_callback, pattern='^cancel_announcement$'))
        application.add_handler(CallbackQueryHandler(cancel_question_callback, pattern='^cancel_question$'))
        application.add_handler(CallbackQueryHandler(cancel_reply_callback, pattern='^cancel_reply$'))
        
        # 3. Conversation handlers
        application.add_handler(registration_conv_handler)
        application.add_handler(ask_comment_conv_handler)
        application.add_handler(reply_comment_conv_handler)
        application.add_handler(announcement_conv_handler)
        
        # 4. Menu button handler
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))
        
        # 5. Command handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('cancel', cancel))

        # 6. Prevent users joining main channel via forwarded/shared invite links
        if MAIN_CHANNEL_ID:
            application.add_handler(
                MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(MAIN_CHANNEL_ID), handle_new_chat_members)
            )

        # Add error handler
        application.add_error_handler(error_handler)

        print("✅ Bot configuration complete!")
        print("🚀 Bot is running with NO MINI-APP...")
        print("✅ Get Started button starts registration directly in Telegram")
        print("✅ All features work within Telegram only")
        print("=" * 50)
        
        # Start the bot
        application.run_polling()
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        print("Please check:")
        print("1. Your BOT_TOKEN is correct")
        print("2. You're using Python 3.11 or 3.12 (Python 3.14 may have issues)")
        print("3. All environment variables are set correctly")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
