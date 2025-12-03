import discord
from discord.ext import commands, tasks
import pandas as pd
import os
from datetime import datetime
import json
import datetime

# --- CONFIGURATION ---
with open("token.json","r") as f:
    conf = json.load(f)
    TOKEN = conf.get("token",{})
    
DATA_FILE = 'budget_data.csv'

# Set up the bot with the necessary intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- HELPER FUNCTIONS ---

def save_to_csv(date, item, amount, category):
    """Saves a single transaction to the CSV file."""
    # Check if file exists, if not create with headers
    if not os.path.exists(DATA_FILE):
        df = pd.DataFrame(columns=['Date', 'Item', 'Amount', 'Category'])
        df.to_csv(DATA_FILE, index=False)

    # Append new data
    new_data = pd.DataFrame([[date, item, amount, category]], 
                            columns=['Date', 'Item', 'Amount', 'Category'])
    new_data.to_csv(DATA_FILE, mode='a', header=False, index=False)

def create_excel_report():
    """Converts the CSV to an Excel file and returns the filename."""
    if not os.path.exists(DATA_FILE):
        return None
    
    df = pd.read_csv(DATA_FILE)
    # Convert 'Date' to datetime objects for better sorting/formatting in Excel
    df['Date'] = pd.to_datetime(df['Date'])
    
    filename = f"Budget_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    
    # Create an Excel writer
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Log', index=False)
        # Create a summary sheet (Pivot table style)
        summary = df.groupby('Category')['Amount'].sum()
        summary.to_excel(writer, sheet_name='Summary')
        
    return filename

# --- BOT EVENTS & COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    # Start the background task for monthly checks (optional logic)
    # check_end_of_month.start() 

@bot.command(name='log')
async def log_expense(ctx, amount: float, category: str, *, item: str):
    """
    Usage: !log <amount> <category> <description>
    Example: !log 15.50 Food Lunch at subway
    """
    date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Save the data
    save_to_csv(date, item, amount, category)
    
    await ctx.send(f"✅ **Saved:** {category} - ${amount} ({item})")

@bot.command(name='report')
async def send_report(ctx):
    """Generates an Excel file of all logs and sends it."""
    filename = create_excel_report()
    
    if filename:
        await ctx.send("Here is your budget report:", file=discord.File(filename))
        # Optional: Clean up file after sending
        # os.remove(filename) 
    else:
        await ctx.send("No data found! Log some expenses first.")

# --- ERROR HANDLING ---
@log_expense.error
async def log_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ Error: Make sure the amount is a number. Format: `!log 50 Food Groceries`")
    else:
        await ctx.send(f"❌ Error: {error}")

@tasks.loop(hours=24) # Check once every 24 hours
async def check_end_of_month():
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    
    # If tomorrow is the 1st of a new month, today is the end of the month
    if tomorrow.day == 1:
        # Replace YOUR_USER_ID with your actual Discord User ID (enable Developer Mode in Discord to copy it)
        user = await bot.fetch_user(YOUR_USER_ID) 
        filename = create_excel_report()
        if filename:
            await user.send("📅 End of month! Here is your budget report:", file=discord.File(filename))

@check_end_of_month.before_loop
async def before_check():
    await bot.wait_until_ready()

# Don't forget to start the loop in on_ready():
# check_end_of_month.start()

# Run the bot
bot.run(TOKEN)