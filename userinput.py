from __future__ import annotations

import asyncio
from typing import Any

import discord

from .utils import get_member, codeblock, test_message

ongoing = []


class UserInput:
    def __init__(self, eitcog, user: [discord.User, discord.Member], channel: discord.TextChannel):
        """

        :param eitcog:
        :param user:
        :param channel:
        :param test:
        """
        self.eitcog = eitcog
        self.user = user
        self.channel = channel
        self.queue = asyncio.Queue()

        eitcog.bot.add_listener(self.on_message)

    def __eq__(self, other: UserInput) -> bool:
        if self.channel == other.channel and self.user == other.user:
            return True

    @classmethod
    async def userinput(cls, eitcog, user: [discord.User, discord.Member],
                        channel: discord.TextChannel, only_content=False) -> Any:
        """

        :param eitcog: the EITCogs Object
        :param user: the user
        :param channel:
        :param only_content:
        :return:
        """

        new_ui = cls(eitcog, user, channel)

        # check if ongoing userinput already exists for given member and channel
        for ui in ongoing:
            if ui == new_ui:
                ui.delete()

        ongoing.append(new_ui)
        answer = await new_ui.queue.get()
        new_ui.delete()
        if only_content:
            return answer.content
        return answer

    def delete(self):
        self.eitcog.bot.remove_listener(self.on_message)
        ongoing.remove(self)

    async def on_message(self, message: discord.Message):
        if await self.command_invoke(self.eitcog.bot, message):
            return
        elif message.author.id == self.user.id and message.channel == self.channel:
            await self.queue.put(message)

    @staticmethod
    async def command_invoke(bot, message: discord.Message) -> bool:
        prefixes = await bot.command_prefix(bot, message)
        for prefix in prefixes:
            if message.content.startswith(prefix):
                return True


async def userinput_loop(eitcog, user, channel, filterfunc=None,
                         converter=None, max_repetitions=10, error_embed=None, **kwargs) -> Any:
    """

    :param eitcog:
    :param user:
    :param channel:
    :param filterfunc:
    :param converter:
    :param max_repetitions:
    :param error_embed:
    :param kwargs:
    :return:
    """
    counter = 0
    while counter < (max_repetitions + 1):
        answer = await UserInput.userinput(eitcog, user, channel)
        content = answer.content
        if filterfunc is not None:
            if filterfunc(content, **kwargs):
                return answer.content
        elif converter:
            output = converter(content, eitcog)
            if output:
                return output
        if error_embed:
            if callable(error_embed):
                await user.send(embed=error_embed(content))
            else:
                await user.send(embed=error_embed)
        counter += 1


def is_valid_name(name: str) -> bool:
    """Checks if the typed in name is valid Was genau alda"""
    return False if len(name) > 32 or not all(x.isalpha() or x.isspace() for x in name) else True


def is_bool_expression(message: str) -> bool:
    if message.lower() in ['ja', 'j', 'yes', 'y']:
        return True
    elif message.lower() in ['nein', 'n', 'no']:
        return False


def stop_keys(message: str) -> bool:
    return True if message.lower() in ['stop', 'halt', 'ende'] else False
