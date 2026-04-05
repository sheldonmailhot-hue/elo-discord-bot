import discord
from discord.ext import commands
from discord.ui import Button, View
import json
import os

import os
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "elo_data.json"
BACKUP_FILE = "elo_backup.json"

# ---------------- DATA ----------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_backup(data):
    with open(BACKUP_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_backup():
    if not os.path.exists(BACKUP_FILE):
        return None
    with open(BACKUP_FILE, "r") as f:
        return json.load(f)

def get_elo(data, user_id):
    if str(user_id) not in data:
        data[str(user_id)] = 1000
    return data[str(user_id)]

# ---------------- EVENTS ----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ---------------- COMMANDS ----------------

@bot.command()
async def elo(ctx, member: discord.Member = None):
    data = load_data()
    member = member or ctx.author
    rating = get_elo(data, member.id)
    await ctx.send(f"{member.display_name} has {rating} ELO")

@bot.command()
async def leaderboard(ctx):
    data = load_data()
    if not data:
        await ctx.send("No data yet.")
        return

    sorted_players = sorted(data.items(), key=lambda x: x[1], reverse=True)
    msg = "**Leaderboard**\n"

    for i, (user_id, rating) in enumerate(sorted_players[:10], 1):
        user = await bot.fetch_user(int(user_id))
        msg += f"{i}. {user.name} - {rating}\n"

    await ctx.send(msg)

@bot.command()
async def undo(ctx):
    backup = load_backup()
    if not backup:
        await ctx.send("No backup found.")
        return

    save_data(backup)
    await ctx.send("Last match undone.")

# ---------------- CONFIRMATION VIEW ----------------

class ConfirmView(View):
    def __init__(self, players, elos, winner):
        super().__init__(timeout=120)
        self.players = players
        self.elos = elos
        self.winner = winner
        self.confirmed = set()

    async def finalize(self, interaction):
        data = load_data()
        save_backup(data.copy())

        stakes = {p.id: int(self.elos[p.id] * 0.10) for p in self.players}
        total_pot = sum(stakes.values())

        if self.winner is None:
            split = total_pot // len(self.players)
            for p in self.players:
                data[str(p.id)] = self.elos[p.id] - stakes[p.id] + split
        else:
            for p in self.players:
                if p == self.winner:
                    data[str(p.id)] = self.elos[p.id] + total_pot - stakes[p.id]
                else:
                    data[str(p.id)] = self.elos[p.id] - stakes[p.id]

        save_data(data)

        if self.winner:
            await interaction.channel.send(f"{self.winner.display_name} confirmed as winner!")
        else:
            await interaction.channel.send("Tie confirmed!")

        self.stop()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.players:
            await interaction.response.send_message("You are not in this match.", ephemeral=True)
            return

        self.confirmed.add(interaction.user.id)

        await interaction.response.send_message("Confirmed.", ephemeral=True)

        if len(self.confirmed) == len(self.players):
            await self.finalize(interaction)

# ---------------- RESULT VIEW ----------------

class ResultView(View):
    def __init__(self, players, elos):
        super().__init__(timeout=60)
        self.players = players
        self.elos = elos

    async def start_confirmation(self, interaction, winner):
        view = ConfirmView(self.players, self.elos, winner)

        if winner:
            msg = f"{winner.display_name} selected. All players must confirm."
        else:
            msg = "Tie selected. All players must confirm."

        await interaction.response.send_message(msg, view=view)
        self.stop()

    def create_button(self, player):
        button = Button(label=player.display_name, style=discord.ButtonStyle.primary)

        async def callback(interaction):
            await self.start_confirmation(interaction, winner=player)

        button.callback = callback
        self.add_item(button)

    def add_tie_button(self):
        button = Button(label="Tie", style=discord.ButtonStyle.secondary)

        async def callback(interaction):
            await self.start_confirmation(interaction, winner=None)

        button.callback = callback
        self.add_item(button)

# ---------------- REPORT ----------------

@bot.command()
async def report(ctx, p1: discord.Member, p2: discord.Member, p3: discord.Member, p4: discord.Member):
    data = load_data()
    players = [p1, p2, p3, p4]

    elos = {p.id: get_elo(data, p.id) for p in players}

    view = ResultView(players, elos)

    for p in players:
        view.create_button(p)

    view.add_tie_button()

    await ctx.send("Select the winner or tie:", view=view)

# ---------------- RUN ----------------

bot.run(TOKEN)
