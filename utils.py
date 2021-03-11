import discord


async def toggle_role(member: discord.Member, role: discord.Role) -> None:
    """Gives/removes the specified role to/from the specified member"""
    if role in member.roles:
        await member.remove_roles(role)
        await member.send(f'Deine Rolle **{role.name}** wurde entfernt!')
    else:
        await member.add_roles(role)
        await member.send(f'Du hast die Rolle **{role.name}** erhalten!')


async def send_more(messageable: discord.object, content: str) -> None:
    """Takes a string and sends it as multiple messages if
    needed to bypass the discord limit of 2000 chars per message."""
    # TODO: ausgeklügelteren algorithmus implementieren
    while True:
        if len(content) > 1995:
            await messageable.send(codeblock(content[:1994]))
            content = content[1994:]
        else:
            await messageable.send(codeblock(content))
            return


def codeblock(string: str) -> str:
    """Wraps a string into a codeblock"""
    return f'```{string}```'


def get_member(guild: discord.Guild, user: [discord.User, discord.Member]) -> discord.Member:
    return discord.utils.get(guild.members, id=user.id)


def add_quicklinks(embed: discord.Embed) -> discord.Embed:
    embed.add_field(name="__Quicklinks:__",
                    value="*[HM-Startseite](https://www.hm.edu/)*   |  "
                          "*[FK 04](https://www.ee.hm.edu/aktuelles/stundenplaene/schwarzesbrett.de.html)*   |  "
                          "*[Moodle](https://moodle.hm.edu/my)*   |  "
                          "*[Primuss](https://www3.primuss.de/cgi-bin/login/index.pl?FH=fhm)*")
    return embed


def get_obj_by_name(name: str, dc_obj: discord.object) -> discord.object:
    obj = discord.utils.get(dc_obj, name=name)
    if not obj:
        print(f'EITBOT: {name} not found in guild!')
    else:
        return obj


async def test_user(eitcog):
    member_ids = [member.id for member in eitcog.guild.members]
    for ids in member_ids:
        yield await eitcog.bot.fetch_user(ids)


async def test_message(eitcog):
    for guild in eitcog.bot.guilds:
        for textchannel in guild:
            for message in await textchannel.history(limit=200).flatten():
                yield message

