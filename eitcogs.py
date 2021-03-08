import asyncio
import os
import pickle
import typing
import discord
import yaml
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from redbot.core import commands
from redbot.core.bot import Red

from .calendar import GoogleCalendar
from .setup import setup_dialog
from .utils import get_member, toggle_role, codeblock
from .configvalidator import validate


RequestType = typing.Literal["discord_deleted_user", "owner", "user", "user_strict"]
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_obj_by_name(name, dc_obj):
    obj = discord.utils.get(dc_obj, name=name)
    if not obj:
        print(f'EITBOT: {name} not found in guild!')
    else:
        return obj


def get_google_creds():
    if os.path.exists('./data/token.pickle'):
        with open('./data/token.pickle', 'rb') as token:
            creds = pickle.load(token)

        # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file('./data/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open('./data/token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds


class EitCogs(commands.Cog):
    """
    A short description of the cog.
    """

    def __init__(self, bot: Red, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.bot = bot

        try:
            with open('./data/config.yml', 'r') as file:
                self.config = validate(yaml.load(file, Loader=yaml.Loader))
        except FileNotFoundError:
            print('EITBOT: No configuration file found')

        self.guild = None
        self.roles = {}
        self.channels = {}
        self.semesters = []
        self.groups = []

        self.parse_config()

        self.bot.add_listener(self.on_member_join)

        channel_mapping = {group.name: group.semester.channel for group in self.groups}
        self.calendar = GoogleCalendar(get_google_creds(), channel_mapping, fallback_channel=self.channels['kalender'])

    async def on_member_join(self, member):
        await setup_dialog(self, member)

    def is_student(self):
        """Checks if the member who invoked the command has administrator permissions on this server"""

        async def predicate(context):
            try:
                return self.roles['student'] in context.author.roles
            except AttributeError:
                return False

        return commands.check(predicate)

    def parse_config(self):
        # parse guild
        for guild in self.bot.guilds:
            if self.config['server'] == guild.id:
                self.guild = guild
                break
        else:
            print('EITBOT: The bot is not a member of the guild with the specified guild id')
            return

        # parse roles
        for role_name in self.config['roles']:
            role = get_obj_by_name(role_name, self.guild.roles)
            if role:
                self.roles.update({role_name: role})

        # parse channels
        for channel_name in self.config['channels']:
            channel = get_obj_by_name(channel_name, self.guild.text_channels)
            if channel:
                self.channels.update({channel_name: channel})

        # parse semesters
        for semester_year, semester_group_names in self.config['semesters'].items():
            new_semester = Semester(semester_year)

            # parse semester channel
            channel = discord.utils.find(lambda ch: str(semester_year) in ch.name and 'termine' in ch.name,
                                         self.guild.text_channels)
            if channel:
                new_semester.channel = channel
            else:
                print(f'EITBOT: now announcement channel found for {new_semester}')

            # parse semester groups
            for group_name in semester_group_names:
                role = get_obj_by_name(group_name, self.guild.roles)
                if role:
                    new_group = Group(group_name, role, new_semester)
                    new_semester.groups.append(new_group)
                    self.groups.append(new_group)

            self.semesters.append(new_semester)

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int) -> None:
        # TODO: Replace this with the proper end user data removal handling.
        await super().red_delete_data_for_user(requester=requester, user_id=user_id)

    @commands.command()
    async def gamer(self, context):
        """Erhalte/Entferne die Rolle Gamer"""
        member = get_member(self.guild, context.author)
        await toggle_role(member, self.roles['gamer'])

    @commands.command()
    async def setup(self, context):
        """Startet den Setup-Dialog"""
        member = get_member(self.guild, context.author)
        await setup_dialog(self, member)

    @commands.command()
    async def admin(self, context):
        embed = discord.Embed(name='Admins')
        admin_dict = {"Yannic": "Yannic Breiting (Der Grüne)",
                      "Elias": "Elias Deking (The Brain)",
                      "Franz": "Franz Ostler (Da Wirtshausfranz)",
                      "Martin": "Martin Kistler (The Nerd)",
                      "Benni": "Benni Draxlbauer (The Beachboy)",
                      "Michi": "Michi Besl (Der Feuerwehrmann)",
                      "Merih": "Merih Cetin (Der TUM-Student)",
                      "Jan": "Jan Duchscherer (The Brain aus der B)"}

        for admin_name, description in admin_dict.items():
            for emoji in context.bot.emojis:
                if admin_name.lower() == emoji.name.lower():
                    embed.add_field(name=description, value=str(emoji), inline=False)
        await context.channel.send(embed=embed)

    @commands.admin()
    @commands.command()
    async def broadcast(self, context, roles: commands.Greedy[discord.Role],
                        channel: typing.Optional[discord.TextChannel] = None,
                        command=None):

        commands = {"setup": setup_dialog}

        receiver = []
        if roles:
            for role in roles:
                if role in context.guild.roles:
                    for member in role.members:
                        receiver.append(member)
        else:
            context.send('Es muss eine Rolle angegeben werden!')

        if command in commands:
            for member in receiver:
                try:
                    asyncio.create_task(commands[command](self.bot, member))
                except (AttributeError, discord.HTTPException):
                    print('Kein DM-Channel - Vermutlich ein Bot')

    @commands.command()
    async def ongoing(self, context):
        """Zeigt alle laufenden Termine an"""
        output = ''
        if not self.calendar.reminders:
            await context.channel.send('Es gibt momentan keine laufenden Termine!')
        else:
            for reminder in self.calendar.reminders:
                if reminder.is_running:
                    output += f'{reminder.calendar_name}: {reminder.summary}\n'
            await context.channel.send(codeblock(output))


class Semester:
    def __init__(self, year, channel=None, groups=None):
        self.year = year
        self.channel = channel
        if groups:
            self.groups = list(groups)
        else:
            self.groups = []

    def __str__(self):
        return f'{self.year}.Semester'

    def __contains__(self, item):
        return item in self.groups


class Group:
    def __init__(self, name, role, semester):
        self.name = name
        self.semester = semester
        self.role = role

    def __str__(self):
        return self.name
