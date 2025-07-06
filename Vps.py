import logging
import os
import subprocess
import asyncio
from telegram import Update, BotCommand, Document, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
import shlex # For safer command splitting
import time

# --- Configuration ---
# !! IMPORTANT: Get these from environment variables on Koyeb !!
BOT_TOKEN = "7361179706:AAEeX6Cx8Q7zYBRXPwFswbZWU33jJFfgY-M"
ADMIN_USER_ID = 6094316605 # Set your Telegram User ID here

if not BOT_TOKEN or ADMIN_USER_ID == 0:
    raise ValueError("Error: BOT_TOKEN and ADMIN_USER_ID environment variables must be set.")

# Directory for uploads (relative to where the script runs)
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True) # Create upload directory if it doesn't exist

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Reduce library verbosity
logger = logging.getLogger(__name__)

# --- Security Decorator ---
def restricted(func):
    """Decorator to restrict access to the admin user."""
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN_USER_ID:
            logger.warning(f"Unauthorized access denied for {user_id}.")
            await update.message.reply_text("Sorry, you are not authorized to use this command.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Bot Command Handlers ---

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends explanation on how to use the bot."""
    user_name = update.effective_user.first_name
    help_text = (
        f"Hi {user_name}! I am your Koyeb control bot.\n\n"
        "**Available commands:**\n"
        "/run `<command>` - Execute a shell command.\n"
        "/upload - Reply to this message with the file you want to upload.\n"
        f"/download `<path>` - Download a file from the server (relative path, e.g., `uploads/myfile.txt` or `myfile.txt`).\n"
        "/pwd - Show current working directory.\n"
        "/ls `<path>` - List directory contents (optional path).\n"
        "/help - Show this help message.\n\n"
        f"**Upload Directory:** `{UPLOAD_DIR}/`\n\n"
        "⚠️ **Warning:** Use with extreme caution! Especially the `/run` command."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

@restricted
async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Executes a shell command."""
    if not context.args:
        await update.message.reply_text("Usage: /run `<command>`\nExample: /run pip install requests")
        return

    command_str = " ".join(context.args)
    message = await update.message.reply_text(f"⏳ Running command:\n`{command_str}`", parse_mode=ParseMode.MARKDOWN)

    try:
        # Use subprocess.Popen for better control over streams
        logger.info(f"Running command: {command_str}")
        # Use shlex.split for safer argument parsing, especially with quotes
        proc = await asyncio.create_subprocess_shell(
            command_str,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        stdout_output = ""
        stderr_output = ""
        last_update_time = time.time()
        update_interval = 2 # Seconds between updates to Telegram

        # Read streams asynchronously
        while proc.returncode is None:
            output_updated = False
            try:
                # Read stdout non-blockingly (or with a timeout)
                stdout_line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.1)
                if stdout_line:
                    stdout_output += stdout_line.decode('utf-8', errors='replace')
                    output_updated = True

                # Read stderr non-blockingly
                stderr_line = await asyncio.wait_for(proc.stderr.readline(), timeout=0.1)
                if stderr_line:
                     # Add a marker for stderr
                    stderr_output += f"[STDERR] {stderr_line.decode('utf-8', errors='replace')}"
                    output_updated = True

            except asyncio.TimeoutError:
                pass # No new output within the timeout

            # Update Telegram periodically or if output changed significantly
            current_time = time.time()
            if output_updated and (current_time - last_update_time > update_interval or len(stdout_output) + len(stderr_output) > 3500): # Avoid hitting message length limits
                combined_output = stdout_output + stderr_output
                status_text = f"⏳ Running command:\n`{command_str}`\n\nOutput:\n```\n{combined_output[-3800:]}\n```" # Show tail end
                try:
                    await message.edit_text(status_text, parse_mode=ParseMode.MARKDOWN)
                    last_update_time = current_time
                except BadRequest as e:
                    if "Message is not modified" in str(e):
                        pass # Ignore if message hasn't changed
                    else:
                        logger.error(f"Error editing message: {e}")
                        # May need to send a new message if editing fails repeatedly

            await asyncio.sleep(0.2) # Short sleep to yield control

        # Process finished, get final output
        stdout_final, stderr_final = await proc.communicate()
        stdout_output += stdout_final.decode('utf-8', errors='replace')
        stderr_output += f"[STDERR] {stderr_final.decode('utf-8', errors='replace')}" if stderr_final else ""

        exit_code = proc.returncode
        status = "✅ Success" if exit_code == 0 else f"❌ Failed (Exit Code: {exit_code})"

        final_text = f"{status} executing:\n`{command_str}`\n\nOutput:\n```\n{stdout_output + stderr_output}\n```"

        # Send final output (potentially truncated if too long)
        if len(final_text) > 4090:
             await message.edit_text(final_text[:4090] + "\n... (output truncated)", parse_mode=ParseMode.MARKDOWN)
             logger.warning(f"Command output for '{command_str}' was truncated.")
        else:
             await message.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
        logger.info(f"Command '{command_str}' finished with exit code {exit_code}")

    except Exception as e:
        logger.error(f"Error running command '{command_str}': {e}", exc_info=True)
        await message.edit_text(f"❌ Error running command:\n`{command_str}`\n\nDetails: {e}", parse_mode=ParseMode.MARKDOWN)

@restricted
async def pwd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the current working directory."""
    current_dir = os.getcwd()
    await update.message.reply_text(f"Current working directory:\n`{current_dir}`", parse_mode=ParseMode.MARKDOWN)

@restricted
async def ls_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists directory contents."""
    target_path_str = " ".join(context.args) if context.args else "."
    
    try:
        # Basic security: prevent accessing parent directories directly in the arg
        # More robust path validation is recommended for production
        if ".." in target_path_str.split('/'):
             await update.message.reply_text("Error: '..' path components are not allowed.")
             return

        target_path = os.path.abspath(target_path_str)
        
        # Further security: ensure it's within a reasonable base dir if needed
        # base_dir = os.getcwd()
        # if not target_path.startswith(base_dir):
        #    await update.message.reply_text("Error: Access denied outside working directory.")
        #    return

        if not os.path.exists(target_path):
            await update.message.reply_text(f"Error: Path not found: `{target_path_str}`", parse_mode=ParseMode.MARKDOWN)
            return

        if not os.path.isdir(target_path):
             await update.message.reply_text(f"Error: Not a directory: `{target_path_str}`", parse_mode=ParseMode.MARKDOWN)
             return

        logger.info(f"Listing directory: {target_path}")
        listing = os.listdir(target_path)
        
        if not listing:
            await update.message.reply_text(f"Directory is empty: `{target_path}`", parse_mode=ParseMode.MARKDOWN)
        else:
            # Format listing nicely
            output_lines = [f"Contents of `{target_path}`:", "```"]
            for item in sorted(listing):
                item_path = os.path.join(target_path, item)
                prefix = " D" if os.path.isdir(item_path) else " F"
                output_lines.append(f"{prefix} {item}")
            output_lines.append("```")
            
            output_text = "\n".join(output_lines)
            
            if len(output_text) > 4090:
                 await update.message.reply_text(output_text[:4090] + "\n... (listing truncated)", parse_mode=ParseMode.MARKDOWN)
            else:
                 await update.message.reply_text(output_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Error listing directory '{target_path_str}': {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error listing directory: {e}")


@restricted
async def upload_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts user to send the file."""
    await update.message.reply_text(f"Okay, please send the file you want to upload to the `{UPLOAD_DIR}/` directory on the server.",)

@restricted
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles receiving a document (file)."""
    if not update.message.document:
        return # Should not happen if filter is correct, but good practice

    document = update.message.document
    file_name = document.file_name
    file_id = document.file_id
    
    # Construct safe path within the designated upload directory
    # Prevent path traversal by taking only the basename
    safe_filename = os.path.basename(file_name) 
    destination_path = os.path.join(UPLOAD_DIR, safe_filename)

    # Check if filename is empty after basename (e.g., if input was '/')
    if not safe_filename:
        await update.message.reply_text("Error: Invalid filename provided.")
        return

    logger.info(f"Attempting to download file '{file_name}' to '{destination_path}'")

    try:
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(destination_path)
        logger.info(f"File '{file_name}' successfully saved to '{destination_path}'")
        await update.message.reply_text(
            f"✅ File `{safe_filename}` uploaded successfully to `{UPLOAD_DIR}/`.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error saving file '{file_name}': {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error uploading file: {e}")

@restricted
async def download_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a file from the server to the user."""
    if not context.args:
        await update.message.reply_text("Usage: /download `<path_to_file>`\nExample: /download uploads/my_document.txt")
        return

    relative_path = " ".join(context.args)
    
    # --- Basic Security: Prevent Path Traversal ---
    # 1. Get absolute path
    base_dir = os.getcwd() # Or define a specific allowed download root
    requested_path = os.path.abspath(os.path.join(base_dir, relative_path))

    # 2. Check if the absolute path is still within the intended directory
    #    This prevents '/download ../../etc/passwd' type attacks
    if not requested_path.startswith(base_dir):
        logger.warning(f"Potential path traversal attempt blocked: '{relative_path}' resolved outside base dir '{base_dir}'")
        await update.message.reply_text("❌ Error: Access denied. Invalid path.")
        return
        
    # 3. Check if path exists and is a file
    if not os.path.exists(requested_path):
        await update.message.reply_text(f"❌ Error: File not found: `{relative_path}`", parse_mode=ParseMode.MARKDOWN)
        return
    if not os.path.isfile(requested_path):
         await update.message.reply_text(f"❌ Error: Not a file: `{relative_path}`", parse_mode=ParseMode.MARKDOWN)
         return

    logger.info(f"Attempting to send file: {requested_path}")
    try:
        await update.message.reply_document(document=open(requested_path, 'rb'))
        logger.info(f"Successfully sent file: {requested_path}")
    except Exception as e:
        logger.error(f"Error sending file '{relative_path}': {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error sending file: {e}")


async def post_init(application: Application) -> None:
    """Set bot commands after initialization."""
    commands = [
        BotCommand("start", "Start the bot and show help"),
        BotCommand("help", "Show help message"),
        BotCommand("run", "Execute a shell command (e.g., /run ls -l)"),
        BotCommand("upload", "Prompt to upload a file"),
        BotCommand("download", "Download a file (e.g., /download path/to/file)"),
        BotCommand("pwd", "Show current working directory"),
        BotCommand("ls", "List directory contents (e.g., /ls uploads)"),
    ]
    await application.bot.set_my_commands(commands)


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Starting bot...")
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start)) # Alias help to start
    application.add_handler(CommandHandler("run", run_command))
    application.add_handler(CommandHandler("pwd", pwd_command))
    application.add_handler(CommandHandler("ls", ls_command))
    application.add_handler(CommandHandler("upload", upload_prompt))
    application.add_handler(CommandHandler("download", download_file))

    # Add a handler for receiving documents (files) - Make sure it's ONLY triggered by the admin
    # Note: This checks the user *after* receiving the message.
    # If you only want the bot to *react* to files sent *after* /upload, you'd need state management (e.g., using context.user_data)
    # This simpler approach handles any file sent by the admin.
    application.add_handler(MessageHandler(filters.User(ADMIN_USER_ID) & filters.Document.ALL, handle_document))

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot started. Using Polling.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
