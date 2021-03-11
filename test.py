import unittest

import discord
from .userinput import UserInput
from .utils import test_user, test_message

eitcog = None


class TestUserInput(unittest.IsolatedAsyncioTestCase):

    def __init__(self):
        super().__init__()
        self.eitcog = None
        self.data = []

    def load_eitcog(self, eitcog):
        self.eitcog = eitcog
        self.test_data()
        self.test_userinput()

    @property
    def userinput_data(self):
        for user in self.data:
            yield user, user.dmchannel

    def test_data(self, amount=10):
        counter = 0
        while amount < counter:
            self.data.append(test_message(self.eitcog))
            counter += 1

    async def asyncSetUp(self) -> None:
        user, channel = self.userinput_data
        self.answer = await UserInput.userinput(self.eitcog, user, channel, test=True)

    def test_userinput(self):
        for i in range(len(self.data)):
            assert isinstance(self.answer, discord.Message)
