import unittest

import discord
from .userinput import UserInput
from .utils import test_user, test_message

eitcog = None


class TestUserInput(unittest.IsolatedAsyncioTestCase):

    def __init__(self):
        super().__init__()

    async def load_eitcog(self, message):
        self.eitcog = eitcog

        self.test_userinput(message)

    def userinput_data(self, message):
        for user in self.message:
            yield user, user.dmchannel

    async def asyncSetUp(self) -> None:
        user, channel = self.userinput_data()
        self.answer = await UserInput.userinput(self.eitcog, user, channel, test=True)

    def test_userinput(self):
        assert isinstance(self.answer, discord.Message)
