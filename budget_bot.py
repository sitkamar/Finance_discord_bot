import discord
from discord.ext import commands, tasks
import pandas as pd
import os
import asyncio
from datetime import datetime
import json
import datetime
import matplotlib.pyplot as plt
import numpy as np

# --- CONFIGURATION ---
# Ensure matplotlib works without a display (headless mode for servers)
plt.switch_backend('Agg')

with open("token.json", "r") as f:
    conf = json.load(f)
    TOKEN = conf.get("token", "")

DATA_FILE = 'budget_data.csv'
INCOME_FILE = 'income_data.csv'
BUDGET_FILE = 'budget_plan.json'

# Set up the bot with the necessary intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- HELPER FUNCTIONS ---

def save_data(filename, date, item, amount, category):
    """Saves a single transaction to the specified CSV file."""
    if not os.path.exists(filename):
        df = pd.DataFrame(columns=['Date', 'Item', 'Amount', 'Category'])
        df.to_csv(filename, index=False)

    new_data = pd.DataFrame([[date, item, amount, category]], 
                            columns=['Date', 'Item', 'Amount', 'Category'])
    new_data.to_csv(filename, mode='a', header=False, index=False)

def load_budget_plan():
    """Loads the budget plan from JSON."""
    if not os.path.exists(BUDGET_FILE):
        return {}
    with open(BUDGET_FILE, 'r') as f:
        return json.load(f)

def save_budget_plan(plan):
    """Saves the budget plan to JSON."""
    with open(BUDGET_FILE, 'w') as f:
        json.dump(plan, f, indent=4)

def get_current_month_data(filename):
    """Returns a DataFrame filtered for the current month from the specified file."""
    if not os.path.exists(filename):
        return pd.DataFrame()
    
    df = pd.read_csv(filename)
    if df.empty:
        return df

    df['Date'] = pd.to_datetime(df['Date'])
    now = datetime.datetime.now()
    # Filter for current year and month
    mask = (df['Date'].dt.year == now.year) & (df['Date'].dt.month == now.month)
    return df.loc[mask]

def create_excel_report():
    """Converts CSVs to an Excel file with Budget vs Actual and Income vs Expense comparison."""
    filename = f"Budget_Report_{datetime.datetime.now().strftime('%Y-%m-%d')}.xlsx"
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # --- EXPENSES ---
        if os.path.exists(DATA_FILE):
            df_exp = pd.read_csv(DATA_FILE)
            if not df_exp.empty:
                df_exp['Date'] = pd.to_datetime(df_exp['Date'])
                df_exp.to_excel(writer, sheet_name='Výdaje - Log', index=False)
                
                # Summary
                summary_exp = df_exp.groupby('Category')['Amount'].sum()
                summary_exp.to_excel(writer, sheet_name='Výdaje - Souhrn')

                # Budget vs Actual (Current Month)
                now = datetime.datetime.now()
                current_month_mask = (df_exp['Date'].dt.year == now.year) & (df_exp['Date'].dt.month == now.month)
                monthly_df = df_exp.loc[current_month_mask]
                monthly_actual = monthly_df.groupby('Category')['Amount'].sum()
                
                budget_plan = load_budget_plan()
                all_categories = set(monthly_actual.index) | set(budget_plan.keys())
                
                comparison_data = []
                for cat in all_categories:
                    actual = monthly_actual.get(cat, 0)
                    planned = budget_plan.get(cat, 0)
                    variance = planned - actual
                    status = "Překročení" if variance < 0 else "V limitu"
                    comparison_data.append([cat, planned, actual, variance, status])
                
                comparison_df = pd.DataFrame(comparison_data, columns=['Kategorie', 'Plán', 'Realita', 'Zbývá', 'Stav'])
                comparison_df.to_excel(writer, sheet_name='Plán vs Realita', index=False)
        
        # --- INCOME ---
        total_income = 0
        total_expense = 0
        
        if os.path.exists(INCOME_FILE):
            df_inc = pd.read_csv(INCOME_FILE)
            if not df_inc.empty:
                df_inc['Date'] = pd.to_datetime(df_inc['Date'])
                df_inc.to_excel(writer, sheet_name='Příjmy - Log', index=False)
                
                # Income Summary
                summary_inc = df_inc.groupby('Category')['Amount'].sum()
                summary_inc.to_excel(writer, sheet_name='Příjmy - Souhrn')
                total_income = df_inc['Amount'].sum()

        if os.path.exists(DATA_FILE):
             df_exp = pd.read_csv(DATA_FILE)
             if not df_exp.empty:
                 total_expense = df_exp['Amount'].sum()

        # --- FINANCIAL OVERVIEW ---
        balance = total_income - total_expense
        overview_df = pd.DataFrame([
            ['Celkové Příjmy', total_income],
            ['Celkové Výdaje', total_expense],
            ['Bilance', balance]
        ], columns=['Položka', 'Částka (Kč)'])
        overview_df.to_excel(writer, sheet_name='Finanční Bilance', index=False)

    return filename

def create_visual_report():
    """Generates a combined Pie (Exp), Bar (Budget), and Bar (Income vs Exp) chart."""
    df_exp = get_current_month_data(DATA_FILE)
    df_inc = get_current_month_data(INCOME_FILE)
    
    budget_plan = load_budget_plan()

    # Calculate Totals for Title
    total_inc = df_inc['Amount'].sum() if not df_inc.empty else 0
    total_exp = df_exp['Amount'].sum() if not df_exp.empty else 0
    balance = total_inc - total_exp

    # Layout: 2 rows, 2 cols. 
    # Top Left: Pie Chart. Top Right: Income vs Expense. Bottom: Budget Plan (span 2 cols)
    fig = plt.figure(figsize=(12, 12))
    
    # Add Main Title (Bilance) with color coding
    balance_color = 'green' if balance >= 0 else 'red'
    fig.suptitle(f'Finanční Bilance: {balance:+.2f} Kč', fontsize=20, color=balance_color, fontweight='bold')

    gs = fig.add_gridspec(2, 2)
    ax1 = fig.add_subplot(gs[0, 0]) # Expense Pie
    ax2 = fig.add_subplot(gs[0, 1]) # Income vs Expense (Stacked)
    ax3 = fig.add_subplot(gs[1, :]) # Budget Plan

    # --- PLOT 1: PIE CHART (Expense Distribution) ---
    if not df_exp.empty:
        actuals = df_exp.groupby('Category')['Amount'].sum()
        pie_labels = [cat for i, cat in enumerate(actuals.index) if actuals[i] > 0]
        pie_values = [val for val in actuals if val > 0]
        
        if pie_values:
            colors = plt.cm.Paired(np.linspace(0, 1, len(pie_values)))
            ax1.pie(pie_values, labels=pie_labels, autopct='%1.1f%%', startangle=140, colors=colors)
            ax1.set_title(f'Rozložení výdajů ({datetime.datetime.now().strftime("%B")})')
        else:
            ax1.text(0.5, 0.5, "Žádné výdaje", ha='center')
    else:
        ax1.text(0.5, 0.5, "Žádná data výdajů", ha='center')
        actuals = pd.Series()

    # --- PLOT 2: INCOME vs EXPENSE (Cash Flow) - STACKED ---
    # Prepare Income Data
    if not df_inc.empty:
        inc_cats = df_inc.groupby('Category')['Amount'].sum()
    else:
        inc_cats = pd.Series()

    # Stacked Income Bar (x=0)
    x_inc = 0
    bottom_y = 0
    
    if not inc_cats.empty:
        # Generate colors for income categories
        inc_colors = plt.cm.tab20(np.linspace(0, 1, len(inc_cats)))
        
        for i, (cat, amount) in enumerate(inc_cats.items()):
            ax2.bar(x_inc, amount, bottom=bottom_y, width=0.5, label=cat, color=inc_colors[i])
            bottom_y += amount
    else:
        # Empty bar placeholder if no income
        ax2.bar(x_inc, 0, width=0.5)

    # Expense Bar (x=1) - Single block
    x_exp = 1
    ax2.bar(x_exp, total_exp, width=0.5, color='#e76f51', label='Výdaje')

    # Formatting Plot 2
    ax2.set_title('Příjmy (Dle zdroje) vs Výdaje')
    ax2.set_ylabel('Kč')
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(['Příjmy', 'Výdaje'])
    
    # Legend for Income Categories (and Expense)
    # We place legend outside or best location
    ax2.legend(title="Zdroje", loc='best', fontsize='small')

    # Add total labels on top of the columns
    ax2.text(x_inc, total_inc, f'{int(total_inc)} Kč', ha='center', va='bottom', fontweight='bold')
    ax2.text(x_exp, total_exp, f'{int(total_exp)} Kč', ha='center', va='bottom', fontweight='bold')

    # --- PLOT 3: BUDGET PLAN vs REALITY ---
    # Align Actuals and Budget data
    all_categories = sorted(list(set(actuals.index) | set(budget_plan.keys())))
    
    actual_values = [actuals.get(cat, 0) for cat in all_categories]
    plan_values = [budget_plan.get(cat, 0) for cat in all_categories]
    
    x = np.arange(len(all_categories))
    width = 0.35
    
    if all_categories:
        rects1 = ax3.bar(x - width/2, plan_values, width, label='Plán', color='#a8dadc')
        rects2 = ax3.bar(x + width/2, actual_values, width, label='Realita', color='#e63946')
        
        ax3.set_ylabel('Částka (Kč)')
        ax3.set_title('Plán vs Realita (Podrobnosti)')
        ax3.set_xticks(x)
        ax3.set_xticklabels(all_categories, rotation=45, ha='right')
        ax3.legend()
        
        # Add values
        def autolabel(rects):
            for rect in rects:
                height = rect.get_height()
                if height > 0:
                    ax3.annotate('{}'.format(int(height)),
                                xy=(rect.get_x() + rect.get_width() / 2, height),
                                xytext=(0, 3),
                                textcoords="offset points",
                                ha='center', va='bottom', fontsize=8)
        autolabel(rects1)
        autolabel(rects2)
    else:
        ax3.text(0.5, 0.5, "Žádné rozpočtové kategorie", ha='center')

    plt.tight_layout(rect=[0, 0.03, 1, 0.95]) # Adjust for suptitle
    
    filename = 'budget_visual_report.png'
    plt.savefig(filename)
    plt.close()
    
    return filename

async def edit_generic(ctx, filename, label):
    """Generic function to edit last N items of a CSV file."""
    if not os.path.exists(filename):
        await ctx.send(f"Žádná data pro {label}!")
        return

    df = pd.read_csv(filename)
    if df.empty:
        await ctx.send(f"Žádné záznamy {label} k úpravě.")
        return

    num_items = 5
    subset = df.tail(num_items).reset_index()
    
    msg_lines = [f"**Úprava {label} (posledních {num_items}):**",
                 "**Odpovězte:** `<Číslo> <Částka> <Kategorie/Zdroj> <Popis>`",
                 "Příklad: `1 25000 Práce Výplata`\n"]
    
    selection_map = {}
    
    for i, row in enumerate(subset.itertuples()):
        display_num = i + 1
        original_idx = row.index 
        selection_map[display_num] = original_idx
        msg_lines.append(f"**{display_num}.** {row.Date} | **{row.Category}** | {row.Amount} Kč | {row.Item}")
        
    await ctx.send("\n".join(msg_lines))
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=60.0)
        parts = msg.content.split(maxsplit=3)
        
        if len(parts) < 4:
            await ctx.send("❌ Špatný formát. Úprava zrušena.")
            return
            
        choice = int(parts[0])
        new_amount = float(parts[1])
        new_category = parts[2]
        new_item = parts[3]
        
        if choice not in selection_map:
            await ctx.send("❌ Neplatné číslo výběru.")
            return
            
        original_index = selection_map[choice]
        
        df.at[original_index, 'Amount'] = new_amount
        df.at[original_index, 'Category'] = new_category
        df.at[original_index, 'Item'] = new_item
        
        df.to_csv(filename, index=False)
        
        await ctx.send(f"✅ **{label} - Záznam č. {choice} aktualizován**.")
        
    except asyncio.TimeoutError:
        await ctx.send("⏰ Čas vypršel.")
    except Exception as e:
        await ctx.send(f"❌ Chyba: {e}")

# --- BOT EVENTS & COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command(name='log')
async def log_expense(ctx, amount: float, category: str = None, *, item: str = None):
    """
    Log expense.
    Usage: !log 150 Jídlo Oběd  OR  !log 150 (interactive)
    """
    date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if category is None:
        plan = load_budget_plan()
        if not plan:
            await ctx.send("⚠ Žádné kategorie. Použijte: `!log <částka> <kategorie> <položka>`.")
            return

        categories = list(plan.keys())
        msg_lines = ["**Vyberte kategorii a dopište položku:**", 
                     "Odpovězte: `<Číslo> <Položka>` (např. `1 Oběd`)"]
        
        for i, cat in enumerate(categories):
            msg_lines.append(f"**{i+1}.** {cat}")
            
        await ctx.send("\n".join(msg_lines))

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            parts = msg.content.split(maxsplit=1)
            
            if len(parts) < 2:
                await ctx.send("❌ Chybí popis položky.")
                return
            
            try:
                cat_idx = int(parts[0]) - 1
                if 0 <= cat_idx < len(categories):
                    category = categories[cat_idx]
                    item = parts[1]
                else:
                    await ctx.send("❌ Neplatné číslo.")
                    return
            except ValueError:
                await ctx.send("❌ První znak musí být číslo.")
                return
        except asyncio.TimeoutError:
            await ctx.send("⏰ Čas vypršel.")
            return

    if item is None:
         await ctx.send("❌ Chybí popis položky! Použití: `!log <částka> <kategorie> <položka>`")
         return
    
    save_data(DATA_FILE, date, item, amount, category)
    
    # Check budget
    plan = load_budget_plan()
    limit = plan.get(category)
    if limit:
        df = get_current_month_data(DATA_FILE)
        current_total = df[df['Category'] == category]['Amount'].sum()
        if current_total > limit:
             await ctx.send(f"⚠️ **Varování:** Překročen rozpočet **{category}**! ({current_total:.2f} / {limit} Kč)")
        elif current_total >= (limit * 0.9):
             await ctx.send(f"📉 **Upozornění:** Blížíte se limitu **{category}** ({current_total:.2f} / {limit} Kč)")
    
    await ctx.send(f"✅ **Výdaj Uložen:** {category} - {amount} Kč ({item})")

@bot.command(name='income')
async def log_income(ctx, amount: float, source: str = None, *, item: str = None):
    """
    Log income.
    Usage: !income 25000 Práce Výplata OR !income 500 (interactive)
    """
    date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Interactive mode for income (Simpler, just asks for text)
    if source is None:
        await ctx.send("**Zadejte zdroj a popis příjmu:**\nOdpovězte ve formátu: `<Zdroj> <Popis>` (např. `Práce Výplata` nebo `Babička Dárek`)")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            parts = msg.content.split(maxsplit=1)
            
            if len(parts) < 2:
                # Allow single word source if no description
                if len(parts) == 1:
                    source = parts[0]
                    item = "Příjem"
                else:
                    await ctx.send("❌ Chyba formátu.")
                    return
            else:
                source = parts[0]
                item = parts[1]
                
        except asyncio.TimeoutError:
            await ctx.send("⏰ Čas vypršel.")
            return

    if item is None:
         item = "Příjem" # Default if user used 3-arg command but somehow missed item? Unlikely with discord parsing but safe.

    save_data(INCOME_FILE, date, item, amount, source)
    await ctx.send(f"💰 **Příjem Uložen:** {source} - {amount} Kč ({item})")

@bot.command(name='set_budget')
async def set_budget(ctx, category: str, amount: float):
    plan = load_budget_plan()
    plan[category] = amount
    save_budget_plan(plan)
    await ctx.send(f"✅ Rozpočet pro **{category}** nastaven na **{amount:.2f} Kč**.")

@bot.command(name='view_budget')
async def view_budget(ctx):
    plan = load_budget_plan()
    if not plan:
        await ctx.send("Žádný rozpočet nenastaven.")
        return
    msg = "**📅 Měsíční rozpočet:**\n"
    for cat, amount in plan.items():
        msg += f"• **{cat}**: {amount:.2f} Kč\n"
    await ctx.send(msg)

@bot.command(name='report')
async def send_report(ctx):
    filename = create_visual_report()
    if filename:
        await ctx.send("📊 **Finanční přehled**", file=discord.File(filename))
        try:
            os.remove(filename)
        except:
            pass
    else:
        await ctx.send("Žádná data.")

@bot.command(name='detailed_report')
async def send_detailed_report(ctx):
    filename = create_excel_report()
    if filename:
        await ctx.send("Zde je detailní report (Příjmy i Výdaje):", file=discord.File(filename))
        try:
            os.remove(filename)
        except:
            pass 
    else:
        await ctx.send("Žádná data.")

@bot.command(name='edit')
async def edit_expense(ctx):
    """Edit last 5 expenses."""
    await edit_generic(ctx, DATA_FILE, "Výdaje")

@bot.command(name='edit_income')
async def edit_income_cmd(ctx):
    """Edit last 5 incomes."""
    await edit_generic(ctx, INCOME_FILE, "Příjmy")

# --- ERROR HANDLING ---
@log_expense.error
@log_income.error
async def log_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ Chyba: Částka musí být číslo.")
    else:
        await ctx.send(f"❌ Chyba: {error}")

@tasks.loop(hours=24) 
async def check_end_of_month():
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    if tomorrow.day == 1:
        pass

@check_end_of_month.before_loop
async def before_check():
    await bot.wait_until_ready()

bot.run(TOKEN)