from __future__ import annotations

import asyncio
from typing import Any

import discord

from .utils import get_member, codeblock

ongoing = []


class UserInput:
    def __init__(self, eitcog, member: discord.Member, channel: discord.TextChannel):
        self.eitcog = eitcog
        self.member = get_member(eitcog.guild, member)
        self.channel = channel
        self.queue = asyncio.Queue()

        eitcog.bot.add_listener(self.on_message)

    def __eq__(self, other: UserInput) -> bool:
        if self.channel == other.channel and self.member == other.member:
            return True

    @classmethod
    async def userinput(cls, eitcog, user: [discord.User, discord.Member],
                        channel: discord.TextChannel) -> Any:

        new_ui = cls(eitcog, user, channel)

        # check if ongoing userinput already exists for given member and channel
        for ui in ongoing:
            if ui == new_ui:
                ui.delete()

        ongoing.append(new_ui)
        answer = await new_ui.queue.get()
        new_ui.delete()
        return answer

    def delete(self):
        self.eitcog.bot.remove_listener(self.on_message)
        ongoing.remove(self)

    async def on_message(self, message: discord.Message):
        if self.stop_keys(message.content):
            return
        # bisschen madig
        elif await self.command_invoke(self.eitcog.bot, message):
            return
        elif message.author.id == self.member.id and message.channel == self.channel:
            await self.queue.put(message)

    @staticmethod
    async def command_invoke(bot, message: discord.Message) -> bool:
        prefixes = await bot.command_prefix(bot, message)
        for prefix in prefixes:
            if message.content.startswith(prefix):
                return True

    @staticmethod
    def stop_keys(message: str) -> bool:
        if message.lower in ['stop', 'halt', 'ende']:
            return True

# TODO: Funktioniert noch nicht richtig!
async def userinput_loop(eitcog, member, channel, filterfunc=None,
                         triggerfunc=None, max_repetitions=10, error_embed=None, *kwargs) -> Any:
    counter = 0
    while counter < (max_repetitions + 1):
        answer = await UserInput.userinput(eitcog, member, channel)
        content = answer.content
        if filterfunc(content, *kwargs):
            return answer.content
        elif triggerfunc:
            try:
                return triggerfunc(content)
            except:
                print('uff')
        elif error_embed:
            await member.send(embed=error_embed(content))
        counter += 1


def is_valid_name(name: str) -> bool:
    """Checks if the typed in name is valid Was genau alda"""
    if len(name) > 32 or not all(x.isalpha() or x.isspace() for x in name):
        return False
    else:
        return True
