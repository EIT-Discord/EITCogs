import asyncio

from .utils import get_member

ongoing = []


class UserInput:
    def __init__(self, eitcog, member, channel):
        self.eitcog = eitcog
        self.member = get_member(eitcog.guild, member)
        self.channel = channel
        self.queue = asyncio.Queue()

        eitcog.bot.add_listener(self.on_message)

    def __eq__(self, other):
        if self.channel == other.channel and self.member == other.member:
            return True

    def delete(self):
        self.eitcog.bot.remove_listener(self.on_message)
        ongoing.remove(self)

    async def on_message(self, message):
        if message.author.id == self.member.id and message.channel == self.channel:
            await self.queue.put(message)

    @classmethod
    async def userinput(cls, eitcog, member, channel):
        new_ui = cls(eitcog, member, channel)

        # check if ongoing userinput already exists for given member and channel
        for ui in ongoing:
            if ui == new_ui:
                ui.delete()

        ongoing.append(new_ui)
        answer = await new_ui.queue.get()
        new_ui.delete()
        return answer.content
