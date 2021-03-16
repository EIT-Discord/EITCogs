import asyncio
import datetime
import re
import sys
from typing import Dict, List, Any

from googleapiclient.discovery import build
import dateutil.parser
import html2text as html2text
import pytz
from discord.ext import tasks

from .utils import *


active_calendar = None


class GoogleCalendar:
    def __init__(self, eitcog, credentials: Any, channel_mapping: Any,
                 fallback_channel: discord.TextChannel = None,
                 refresh_interval: int = 60, timezone: str = 'Europe/Berlin'):
        global active_calendar
        if active_calendar:
            return

        self.eitcog = eitcog
        self.timezone = pytz.timezone(timezone)
        self.service = build('calendar', 'v3', credentials=credentials)
        self.channel_mapping = channel_mapping
        self.fallback_channel = fallback_channel

        self.reminders = []
        self.active_reminders = {}
        self.refresh = tasks.loop(seconds=refresh_interval)(self.refresh)
        self.refresh.start()

        self.update_reminders = tasks.loop(seconds=60)(self.update_reminders)
        self.update_reminders.start()

        active_calendar = self

    async def refresh(self) -> None:
        global active_calendar
        active_calendar = self

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
            try:
                group_name, course_name = entry.calendar_name.split('-')
                if group_name in self.channel_mapping:
                    channel = self.channel_mapping[group_name]
                elif self.fallback_channel:
                    channel = self.fallback_channel
                else:
                    await self.eitcog.log(
                        f'EITBOT: Could not find an appropriate channel for calendar entry "{entry.summary}"')
                    return
                self.reminders.append(Reminder(self, entry, channel))
            except ValueError:
                pass

    def __del__(self):
        print('Kalender wurde Garbage collected')

    async def stop(self):
        global active_calendar
        self.update_reminders.cancel()
        self.refresh.cancel()
        active_calendar = None

        for reminder in self.reminders:
            await reminder.delete_message()

    async def update_reminders(self) -> None:
        global active_calendar
        active_calendar = self

        for reminder in self.reminders:
            await reminder.update()

    def fetch_entries(self, limit: int = 5, max_seconds_until_remind: int = 300) -> List:
        # TODO: warum nur einträge mit remindern in 5 minuten oder weniger?
        """ Fetches upcoming calendar entries

        Parameters
        ----------
        limit:  The maximum amount of calendar entries fetched per calendar
        max_seconds_until_remind:
        Returns
        -------
        A flattened list of calendar entries
        """

        entries = []
        for calendar_info, entry in self._fetch_calendar(limit):
            time_until_remind = parse_remind_time(entry, self.timezone) - datetime.datetime.now(self.timezone)
            if time_until_remind.total_seconds() <= max_seconds_until_remind:
                if 'backgroundColor' in entry:
                    entry['calendarColorId'] = calendar_info['backgroundColor']
                entries.append(entry)
        return entries

    def _fetch_calendar(self, limit):
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        calendar_result = self.service.calendarList().list().execute()
        for calendar_info in calendar_result['items']:
            calendar = self.service.events().list(calendarId=calendar_info['id'], timeMin=now, maxResults=limit,
                                                  singleEvents=True, orderBy='startTime').execute()
            for entry in calendar['items']:
                yield calendar_info, entry


class CalendarEntry:
    def __init__(self, raw_entry: Dict, timezone: pytz.timezone):

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
            self.colour = discord.Colour(0xFFFFFF)
        prof_regexp = re.compile('(?<=\[).+?(?=\])')
        try:
            prof_name = prof_regexp.search(self.summary).group(0).lower(). \
                replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
            if prof_name in embed_links.keys():
                self.url = embed_links[prof_name]
            else:
                self.url = f"https://w3-mediapool.hm.edu/mediapool/media/fk04/fk04_lokal/professoren_4/" \
                           f"{prof_name}/{prof_name}_ContactBild.jpg"
        except Exception as e:
            print(f'{e}: Could not load calendarimage!')

    def generate_embed(self) -> discord.Embed:
        embed = discord.Embed(description=self.description, colour=self.colour)
        try:
            embed.set_thumbnail(url=self.url)
        except Exception as e:
            print(e)

        if self.location:
            embed.add_field(name="Ort / URL", value=self.location, inline=False)

        embed.add_field(name="Datum", value=self.event_start.strftime("%d.%m.%Y"), inline=False)
        embed.add_field(name="Beginn", value=self.event_start.strftime("%H:%M"), inline=True)

        if self.event_duration and self.event_end:
            embed.add_field(name="Dauer", value=(str(self.event_duration)[:-3]), inline=True)
            embed.add_field(name="Ende", value=self.event_end.strftime("%H:%M"), inline=True)

        return embed


class Reminder:
    def __init__(self, calendar: GoogleCalendar, entry: CalendarEntry, channel: discord.TextChannel):

        self.calendar = calendar
        self.entry = entry
        self.channel = channel

        self.id = self.entry.id
        self.updated = self.entry.updated

        self.message = None
        self.embed = self.entry.generate_embed()

    async def update(self) -> None:
        now = datetime.datetime.now(self.calendar.timezone)

        if self.entry.event_end <= now:
            await self.delete_message()

        elif self.entry.reminder_start <= now:
            self.set_embed_title()
            if self.message:
                await self.update_message()
            else:
                await self.send_message()

        elif self.message:
            await self.delete_message()

    async def send_message(self):
        self.message = await self.channel.send(embed=self.embed)

        self.calendar.active_reminders.update({self.message.id: (self.message, self.entry)})

    async def delete_message(self) -> None:
        if not self.message:
            return
        try:
            await self.message.delete()
        except discord.NotFound:
            pass
        finally:
            self.calendar.active_reminders.pop(self.message.id)

    async def update_message(self) -> None:
        try:
            await self.message.edit(embed=self.embed)
        except discord.NotFound:
            await self.calendar.eitcog.log(f'Konnte die Nachricht nicht updaten', self.embed)

    async def update_reminder(self, entry: CalendarEntry) -> None:
        self.entry = entry
        self.embed = entry.generate_embed()
        await self.update()

    def set_embed_title(self) -> None:
        time_until_event = self.entry.event_start - datetime.datetime.now(self.calendar.timezone)
        if time_until_event.total_seconds() > 0:
            preposition = 'in'
        else:
            preposition = 'seit'
        self.embed.title = f'**{self.entry.calendar_name}**:  ' \
                           f'{self.entry.summary} {preposition} {reformat_timedelta(timedelta=time_until_event)}!'


def parse_remind_time(raw_entry: Dict, timezone: datetime.tzinfo):
    """Returns the time when the entries reminder should fire as a dateime object."""
    if 'reminders' in raw_entry and 'overrides' in raw_entry['reminders']:
        remind_minutes = raw_entry['reminders']['overrides'][0]['minutes']
    else:
        remind_minutes = 30
    return parse_time(raw_entry['start'], timezone) - datetime.timedelta(minutes=remind_minutes)


def parse_time(time: Dict, timezone: datetime.tzinfo):
    if 'dateTime' in time:
        return dateutil.parser.parse(time['dateTime']).astimezone(timezone)
    elif 'date' in time:
        return dateutil.parser.parse(time['date']).astimezone(timezone)
    else:
        print("EITBOT: No date or dateTime key in entry dict recieved from Google Calendar API. Ignoring entry.")


def reformat_timedelta(timedelta) -> str:
    try:
        obj = abs(timedelta.total_seconds())
    except AttributeError:
        raise ValueError("You must provide either a timedelta")

    seconds = int(obj)

    periods = [
        ("Jahr", "Jahren", 60 * 60 * 24 * 365),
        ("Monat", "Monaten", 60 * 60 * 24 * 30),
        ("Tag", "Tagen", 60 * 60 * 24),
        ("Stunde", "Stunden", 60 * 60),
        ("Minute", "Minuten", 60),
    ]
    strings = []
    for period_name, plural_period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            if period_value == 0:
                continue
            unit = plural_period_name if period_value > 1 else period_name
            strings.append(f"{period_value} {unit}")

    return_string = ", ".join(strings)
    if int(obj) < 60:
        return_string = "weniger als 1 Minute"

    return return_string


embed_links = {
    'striegler': 'https://w3-mediapool.hm.edu/mediapool/media/fk04/fk04_lokal/professoren_4/striegler/me_ContactBild.jpg',
    'zuccaro': 'https://w3-mediapool.hm.edu/mediapool/media/fk04/fk04_lokal/professoren_4/zuccaro/zuccaro1_ContactBild.jpg',
    'rosehr': 'https://w3-mediapool.hm.edu/mediapool/media/fk04/fk04_lokal/professoren_4/rosehr/Rosehr.jpg',
    'galek': 'https://w3-mediapool.hm.edu/mediapool/media/fk04/fk04_lokal/professoren_4/galek/Galek.jpg',
    'unterricker': 'https://w3-mediapool.hm.edu/mediapool/media/fk04/fk04_lokal/professoren_4/unterricker/Unterricker.jpg',
    'hiebel': 'https://w3-mediapool.hm.edu/mediapool/media/fk04/fk04_lokal/professoren_4/hiebel/45050_2_klein.jpg',
    'muenker': 'https://w3-mediapool.hm.edu/mediapool/media/fk04/fk04_lokal/professoren_4/muenker/muenker_2.jpg',
    'stehr': 'https://www.hallo-muenchen.de/bilder/2019/10/16/13120679/275521894-online_super-prof-3ya7.jpg'
}
