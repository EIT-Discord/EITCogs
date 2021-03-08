import asyncio
import datetime

from googleapiclient.discovery import build
import dateutil.parser
import discord
import html2text as html2text
import pytz
from discord.ext import tasks
from redbot.core.utils.chat_formatting import humanize_timedelta


class GoogleCalendar:
    def __init__(self, credentials, channel_mapping,
                 fallback_channel=None, refresh_interval=20, timezone='Europe/Berlin'):
        self.timezone = pytz.timezone(timezone)
        self.service = build('calendar', 'v3', credentials=credentials)
        self.channel_mapping = dict(channel_mapping)
        self.fallback_channel = fallback_channel

        self.reminders = []

        self.refresh = tasks.loop(seconds=refresh_interval)(self.refresh)
        self.refresh.start()

        self.update_reminders = tasks.loop(seconds=20)(self.update_reminders)
        self.update_reminders.start()

    async def refresh(self):
        # Fetch the next 5 entries per calendar
        loop = asyncio.get_running_loop()
        raw_entries = await loop.run_in_executor(None, self.fetch_entries)

        entries = [CalendarEntry(raw_entry, self.timezone) for raw_entry in raw_entries]

        # Check all current reminders for updates
        for reminder in self.reminders:
            for entry in entries:
                if reminder.id == entry.id:
                    if entry.updated != reminder.updated:
                        await reminder.update_reminder(entry)
                    entries.remove(entry)
                    break
            else:
                await reminder.delete_message()
                self.reminders.remove(reminder)

        # Got new events
        for entry in entries:
            if entry.calendar_name in self.channel_mapping:
                channel = self.channel_mapping[entry.calendar_name]
            elif self.fallback_channel:
                channel = self.fallback_channel
            else:
                print(f'EITBOT: Could not find an appropriate channel for calendar entry "{entry.summary}"')
                return
            self.reminders.append(Reminder(entry, channel, self.timezone))

    async def update_reminders(self):
        for reminder in self.reminders:
            await reminder.update()

    def fetch_entries(self, limit=5, max_seconds_until_remind=300):
        # TODO: warum nur einträge mit remindern in 5 minuten oder weniger?
        """ Fetches upcoming calendar entries

        Parameters
        ----------
        limit:  The maximum amount of calendar entries fetched per calendar
        Returns
        -------
        A flattened list of calendar entries
        """

        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        calendars_result = self.service.calendarList().list().execute()

        events = []
        for calendar_info in calendars_result['items']:
            calendar = self.service.events().list(calendarId=calendar_info['id'], timeMin=now,
                                                  maxResults=limit,
                                                  singleEvents=True,
                                                  orderBy='startTime').execute()
            for entry in calendar['items']:
                time_until_remind = parse_remind_time(entry, self.timezone) - datetime.datetime.now(self.timezone)
                if time_until_remind.total_seconds() <= max_seconds_until_remind:
                    if 'backgroundColor' in calendar_info:
                        entry['calendarColorId'] = calendar_info['backgroundColor']
                    events.append(entry)
        return events


class Reminder:
    def __init__(self, entry, channel, timezone):
        self.entry = entry
        self.channel = channel
        self.timezone = timezone

        self.id = self.entry.id
        self.updated = self.entry.updated

        self.message = None
        self.embed = self.entry.generate_embed()

    async def update(self):
        now = datetime.datetime.now(self.timezone)

        if self.entry.event_end <= now:
            await self.delete_message()

        elif self.entry.reminder_start <= now:
            self.set_embed_title()
            if self.message:
                await self.update_message()
            else:
                self.message = await self.channel.send(embed=self.embed)

        elif self.message:
            await self.delete_message()

    async def delete_message(self):
        try:
            await self.message.delete()
            self.message = None
        except discord.NotFound:
            pass

    async def update_message(self):
        try:
            await self.message.edit(embed=self.embed)
        except discord.NotFound:
            pass

    async def update_reminder(self, entry):
        self.entry = entry
        self.embed = entry.generate_embed()
        await self.update()

    def set_embed_title(self):
        time_until_event = self.entry.event_start - datetime.datetime.now(self.timezone)
        self.embed.title = f'**{self.entry.calendar_name}**:  ' \
                           f'{self.entry.summary} {humanize_timedelta(timedelta=time_until_event)}'


class CalendarEntry:
    def __init__(self, raw_entry, timezone):
        self.updated = dateutil.parser.parse(raw_entry['updated']).astimezone(timezone)

        # mandatory
        self.id = raw_entry['id']
        self.calendar_name = raw_entry["organizer"]["displayName"]
        self.summary = raw_entry["summary"]
        self.event_start = parse_time(raw_entry['start'], timezone)

        # optional
        if 'end' in raw_entry:
            self.event_end = parse_time(raw_entry['end'], timezone)
            self.event_duration = self.event_end - self.event_start
        else:
            self.event_end = None
            self.event_duration = None

        self.reminder_start = parse_remind_time(raw_entry, timezone)

        if 'description' in raw_entry:
            self.description = html2text.html2text(raw_entry['description'])
        else:
            self.description = ''

        if 'location' in raw_entry:
            self.location = raw_entry['location']
        else:
            self.location = None

        if 'calendarColorId' in raw_entry:
            self.colour = discord.Colour(int(raw_entry['calendarColorId'].lstrip('#'), 16))
        else:
            self.colour = discord.Colour(0x000000)

    def generate_embed(self):
        embed = discord.Embed(description=self.description, colour=self.colour)

        if self.location:
            embed.add_field(name="Ort / URL", value=self.location, inline=False)

        embed.add_field(name="Datum", value=self.event_start.strftime("%d.%m.%Y"), inline=False)
        embed.add_field(name="Beginn", value=self.event_start.strftime("%H:%M"), inline=True)

        if self.event_duration and self.event_end:
            embed.add_field(name="Dauer", value=(str(self.event_duration)[:-3]), inline=True)
            embed.add_field(name="Ende", value=self.event_end.strftime("%H:%M"), inline=True)

        return embed


def parse_time(time, timezone):
    if 'dateTime' in time:
        return dateutil.parser.parse(time['dateTime']).astimezone(timezone)
    elif 'date' in time:
        return dateutil.parser.parse(time['date']).astimezone(timezone)
    else:
        print("EITBOT: No date or dateTime key in entry dict recieved from Google Calendar API. Ignoring entry.")


def format_time(dt):
    if dt < datetime.timedelta(seconds=0):
        output = 'seit'
    else:
        output = 'in'

    hours, remainder = divmod(dt.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f'{output} {dt.days}:{hours}:{minutes}'


def parse_remind_time(raw_entry, timezone):
    """Returns the time when the entries reminder should fire as a dateime object."""
    if 'reminders' in raw_entry and 'overrides' in raw_entry['reminders']:
        remind_minutes = raw_entry['reminders']['overrides'][0]['minutes']
    else:
        remind_minutes = 30
    return parse_time(raw_entry['start'], timezone) - datetime.timedelta(minutes=remind_minutes)
