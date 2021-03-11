from __future__ import annotations
import asyncio
import os
import pickle
import typing
import discord
import yaml
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import List, Any

from .userinput import UserInput, is_bool_expression, stop_keys
from .calendar import GoogleCalendar
from .setup import setup_dialog, semester_start_dialog
from .utils import get_member, toggle_role, codeblock, get_obj_by_name
from .configvalidator import validate

RequestType = typing.Literal["discord_deleted_user", "owner", "user", "user_strict"]
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_google_creds(creds: Any = None) -> Any:
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

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8192739812739812)

        default_reminder = {
            'running': False,
            'reminder': [],
            'member': None
        }

        self.guild = None
        self.roles = {}
        self.channels = {}
        self.semesters = []
        self.groups = []
        self.calendar = None
        self.bot.add_listener(self.on_member_join)

        self.config.init_custom('Kalender', 1)
        self.config.register_custom('Kalender', **default_reminder)

    def cog_check(self, ctx) -> bool:
        if self.guild is None:
            self.parse_config()
        return self.guild is not None

    async def on_member_join(self, member: discord.Member) -> None:
        await setup_dialog(self, member)

    def is_student(self) -> bool:
        """Checks if the member who invoked the command has administrator permissions on this server"""

        async def _is_student(context: commands.context):
            try:
                return self.roles['student'] in context.author.roles
            except AttributeError:
                return False

        return commands.check(_is_student)

    def is_admin(self) -> bool:
        """Checks if the member who invoked the command has administrator permissions on this server"""

        async def _is_admin(context: commands.context):
            try:
                return self.roles['Admin'] in context.author.roles
            except AttributeError:
                return False

        return commands.check(_is_admin)

    def parse_config(self) -> None:
        # parse guild
        try:
            with open('./data/config.yml', 'r') as file:
                config = validate(yaml.load(file, Loader=yaml.Loader))
        except FileNotFoundError:
            print('EITBOT: No configuration file found')

        for guild in self.bot.guilds:
            if config['server'] == guild.id:
                self.guild = guild
                break
        else:
            print('EITBOT: The bot is not a member of the guild with the specified guild id')
            return

        # parse roles
        for role_name in config['roles']:
            role = get_obj_by_name(role_name, guild.roles)
            if role:
                self.roles.update({role_name: role})

        # parse channels
        for channel_name in config['channels']:
            channel = get_obj_by_name(channel_name, self.guild.text_channels)
            if channel:
                self.channels.update({channel_name: channel})

        # parse semesters
        for semester_year, semester_group_names in config['semesters'].items():
            new_semester = Semester(semester_year)

            # parse semester channel
            channel = discord.utils.find(lambda ch: str(semester_year) in ch.name and 'termine' in ch.name,
                                         self.guild.text_channels)
            if channel:
                new_semester.channel = channel
            else:
                print(f'EITBOT: no announcement channel found for {new_semester}')

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
    async def gamer(self, context: commands.context) -> None:
        """Erhalte/Entferne die Rolle Gamer"""
        member = get_member(self.guild, context.author)
        await toggle_role(member, self.roles['Gamer'])

    @commands.command()
    async def setup(self, context: commands.context) -> None:
        """Startet den Setup-Dialog"""
        member = get_member(self.guild, context.author)
        await setup_dialog(self, member)

    async def semester_start(self, context: commands.context) -> None:
        member = get_member(self.guild, context.author)
        await semester_start_dialog(self, member)

    @commands.command()
    async def admin(self, context: commands.context) -> None:
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
    async def poll(self, context: commands.context, channel: discord.TextChannel = None):
        await context.channel.send('Die Umfrage wird jetzt vorbereitet, gib deine Fragen im Dialog an!')
        poll = []
        while True:
            message = await UserInput.userinput(self, context.author, context.author.dm_channel, only_content=True)
            if stop_keys(message):
                output = ''
                for entry in poll:
                    output += entry + '\n'
                    await context.channel.send(output)
                    break
            if is_bool_expression(message) is False:
                await context.channel.send('Wiederhole bitte deine Eingabe!')
            elif is_bool_expression(message) is not False:
                poll.append(message)
                await context.channel.send(f'Deine Eingabe lauten wie folgt: {message} - einverstanden?')

    @commands.command()
    async def broadcast(self, context: commands.context, roles: commands.Greedy[discord.Role],
                        channel: typing.Optional[discord.TextChannel] = None,
                        command=None):
        """Erlaubt das Ausführen der Dialoge an alle Servermitglieder mit der ausgewählten Rolle"""

        available_commands = {'setup': setup_dialog,
                              'semesterstart': semester_start_dialog}

        receiver = []
        for role in roles:
            if role in context.guild.roles:
                for member in role.members:
                    receiver.append(member)

        if command in available_commands:
            for member in receiver:
                try:
                    asyncio.create_task(available_commands[command](self, member))
                except (AttributeError, discord.HTTPException):
                    print(f'Memberid: {member.id} - Kein DM-Channel - Vermutlich ein Bot')

    @commands.check(is_student)
    @commands.command()
    async def ongoing(self, context: commands.context) -> None:
        """Zeigt alle laufenden Termine an"""
        output = ''
        if not self.calendar.reminders:
            await context.channel.send('Es gibt momentan keine laufenden Termine!')
        else:
            for reminder in self.calendar.reminders:
                if reminder.entry:
                    output += f'{reminder.entry.calendar_name}: {reminder.entry.summary}\n'
            await context.channel.send(codeblock(output))

    async def add_course(self):
        pass

    async def remove_course(self):
        pass

    async def overview(self):
        pass

    @commands.command()
    async def start(self, ctx):
        channel_mapping = {group.name: group.semester.channel for group in self.groups}
        self.calendar = GoogleCalendar(self, get_google_creds(),
                                       channel_mapping, fallback_channel=self.channels['kalender'])


class Group:
    def __init__(self, name: str, role: discord.Role, semester: Semester):
        super().__init__()
        self.name = name
        self.semester = semester
        self.role = role

    def __str__(self) -> str:
        return self.name


class Semester:
    def __init__(self, year: int, channel: discord.TextChannel = None, groups: List[Group] = None):
        super().__init__()
        self.year = year
        self.channel = channel
        if groups:
            self.groups = list(groups)
        else:
            self.groups = []

    def __str__(self) -> str:
        return f'{self.year}.Semester'

    def __contains__(self, item: Group) -> bool:
        return item in self.groups
