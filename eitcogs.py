from __future__ import annotations
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
from typing import List, Any

from .userinput import UserInput
from .calendar import GoogleCalendar
from .setup import setup_dialog, semester_start_dialog
from .utils import get_member, toggle_role, codeblock
from .configvalidator import validate

RequestType = typing.Literal["discord_deleted_user", "owner", "user", "user_strict"]
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_obj_by_name(name: str, dc_obj: discord.object) -> discord.object:
    obj = discord.utils.get(dc_obj, name=name)
    if not obj:
        print(f'EITBOT: {name} not found in guild!')
    else:
        return obj


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

        # self.calendar = GoogleCalendar(get_google_creds(), channel_mapping, fallback_channel=self.channels['kalender'])

    async def on_member_join(self, member: discord.Member) -> None:
        await setup_dialog(self, member)

    def is_student(self) -> bool:
        """Checks if the member who invoked the command has administrator permissions on this server"""

        async def predicate(context: commands.context) -> bool:
            try:
                return self.roles['student'] in context.author.roles
            except AttributeError:
                return False

        return commands.check(predicate)

    def parse_config(self) -> None:
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
    async def config(self, context: commands.context) -> None:
        await context.send(codeblock(str(self)))

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

    @commands.command()
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

    # @commands.command()
    # async def poll(self, context: commands.context, channel: discord.TextChannel = None):
    #     await context.channel.send('Die Umfrage wird jetzt vorbereitet, gib deine Fragen im Dialog an!')
    #     questions = []
    #     while True:
    #         message = await UserInput.userinput(self, get_member(self.guild, context.author), context.author.dm_channel)
    #         if message.lower() in ['stop', 'end', 'aufhören', 'fertig']:
    #             output = ''
    #             for question in questions:
    #                 output += question + 'n'
    #             await context.channel.send(f'Deine Fragen lauten wie folgt: {output}')
    #         else:
    #             while True:
    #                 await context.channel.send(f'Ist die Frage {message} so richtig?')
    #                 answer = await UserInput.userinput(self, get_member(self.guild, context.author), context.author.dm_channel)
    #                 if answer.lower() in ['nein', 'no', 'n']:
    #                     await context.channel.send('Gib deine Frage erneut ein!')
    #                     message = await UserInput.userinput(self, context.member, context.member.dm_channel)
    #                 else:
    #                     break
    #             questions.append(message)

    @commands.admin()
    @commands.command()
    async def broadcast(self, context: commands.context, roles: commands.Greedy[discord.Role],
                        channel: typing.Optional[discord.TextChannel] = None,
                        command=None):

        available_commands = {'setup': setup_dialog,
                              'semesterstart': semester_start_dialog}

        receiver = []
        if roles:
            for role in roles:
                if role in context.guild.roles:
                    for member in role.members:
                        receiver.append(member)
        else:
            await context.send('Es muss eine Rolle angegeben werden!')

        if command in commands:
            for member in receiver:
                try:
                    asyncio.create_task(available_commands[command](self, member))
                except (AttributeError, discord.HTTPException):
                    print('Kein DM-Channel - Vermutlich ein Bot')

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
