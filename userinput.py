from __future__ import annotations

import asyncio

import discord

from .utils import get_member

ongoing = []


class UserInput:
    def __init__(self, eitcog, user: discord.User, channel: discord.TextChannel):
        self.eitcog = eitcog
        self.member = get_member(eitcog.guild, user)
        self.channel = channel
        self.queue = asyncio.Queue()

        eitcog.bot.add_listener(self.on_message)

    def __eq__(self, other: UserInput) -> bool:
        if self.channel == other.channel and self.member == other.member:
            return True

    def delete(self) -> None:
        self.eitcog.bot.remove_listener(self.on_message)
        ongoing.remove(self)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.id == self.member.id and message.channel == self.channel:
            await self.queue.put(message)

    @classmethod
    async def userinput(cls, eitcog, user: discord.User, channel: discord.TextChannel) -> str:
        new_ui = cls(eitcog, user, channel)

        # check if ongoing userinput already exists for given member and channel
        for ui in ongoing:
            if ui == new_ui:
                ui.delete()

        ongoing.append(new_ui)
        answer = await new_ui.queue.get()
        new_ui.delete()
        return answer.content
