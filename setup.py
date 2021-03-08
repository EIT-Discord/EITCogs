import logging
import discord

from .userinput import UserInput

setup_start = discord.Embed(description="Willkommen auf unserem Elektrotechnik Discord Server!\n\n"
                                        "Dieses Setup ist dafür da, damit wir und deine Kommilitonen "
                                        "dich auf dem Server "
                                        "(besser) erkennen und du zu deiner Gruppe passende Informationen erhältst.\n\n"
                                        "*Deine Angaben werden von diesem Bot weder gespeichert noch auf irgendeine "
                                        "Weise verarbeitet, du erhältst ledeglich deinen Namen und deine Studiengruppe "
                                        "auf unserem Server zugewiesen.*\n\n"
                                        "**Antworte bitte mit deinem Vor- und Nachnamen auf diese Nachricht**\n"
                                        "_Wenn du deinen vollen Namen hier nicht angeben willst, "
                                        "darfst du auch nur deinen Vornamen oder einen Spitznamen benutzen._",
                            colour=discord.Colour(0x2fb923),
                            title="Setup")

setup_name_error = discord.Embed(description="Hoppla!\n"
                                             "Dein eingegebener Name ist ungültig.\n"
                                             "Gehe sicher, dass dein Name nicht länger als 32 Zeichen ist und keine "
                                             "Zahlen oder Sonderzeichen enthält!",
                                 colour=discord.Colour(0x2fb923),
                                 title="Setup")


def setup_group_select(name, semesters):
    embed = discord.Embed(description=f'Hallo **{name}**!\n'
                                      f'Antworte jetzt noch mit deiner Studiengruppe, '
                                      f'um dieses Setup abzuschließen.\n\n'
                                      f'**Folgende Studiengruppen stehen zur Auswahl:**\n\n',
                          colour=discord.Colour(0x2fb923),
                          title="Setup")

    # add known studygroups to embed
    for semester in semesters:
        group_string = ''
        for group in semester.groups:
            group_string += str(group) + '\n'
        embed.add_field(name=str(semester), value=group_string, inline=True)

    # add guest role to embed
    embed.add_field(name='Sonstige', value="Gast", inline=True)

    return embed


def setup_group_error(message):
    embed = discord.Embed(description=f'Hoppla!\n'
                                      f'Wie es scheint, ist "{message}" keine gültige Studiengruppe.\n'
                                      f'Probiere es bitte nochmal mit einer Studiengruppe aus der Liste!\n',
                          colour=discord.Colour(0x2fb923),
                          title="Setup")
    return embed


def setup_end(study_group_name):
    embed = discord.Embed(description=f'Vielen Dank für die Einschreibung in unseren EIT-Server.\n'
                                      f'Du wurdest der Gruppe **{study_group_name}** zugewiesen.\n\n'
                                      f'Hiermit hast du das Setup abgeschlossen und deine Angaben\n'
                                      f'werden in den Server eingetragen.\n\n'
                                      f'**Falls etwas mit deiner Eingabe nicht stimmt,\n'
                                      f'führe das Setup einfach nochmal aus und pass deine Eingabe an!**',
                          colour=discord.Colour(0x2fb923),
                          title="Setup")
    return embed


def is_valid(name):
    """Checks if the typed in name is valid"""
    if len(name) > 32 or not all(x.isalpha() or x.isspace() for x in name):
        return False
    else:
        return True


async def setup_dialog(eitcog, member):
    try:
        await member.send(embed=setup_start)
    except (AttributeError, discord.HTTPException):
        return

    # loop until User tiped in a valid name
    while True:
        answer = await UserInput.userinput(eitcog, member, member.dm_channel)
        if answer.startswith(eitcog.bot.command_prefix):
            return
        if is_valid(answer):
            break
        else:
            await member.send(embed=setup_name_error)

    # change Users Nickname to tiped name
    try:
        await member.edit(nick=answer)
    except discord.Forbidden:
        logging.info(f'could not asign new nickname to member "{member.name}"')

    await member.send(embed=setup_group_select(answer, eitcog.semesters))

    # loop until User tiped in a valid studygroup
    flag = True

    while flag:
        answer = await UserInput.userinput(eitcog, member, member.dm_channel)
        if answer.startswith(eitcog.bot.command_prefix):
            return
        if answer.upper() == 'GAST':
            await remove_groups(eitcog, member)

            if eitcog.roles['Student'] in member.roles:
                await member.remove_roles(eitcog.roles['Student'])

            await member.add_roles(eitcog.roles['Gast'])
            await member.send(embed=setup_end("Gast"))

            break

        for group in eitcog.groups:
            if answer.upper() == group.name:
                await remove_groups(eitcog, member)

                if eitcog.roles['Gast'] in member.roles:
                    await member.remove_roles(eitcog.roles['Gast'])

                await member.add_roles(group.role, eitcog.roles['Student'])
                await member.send(embed=setup_end(group.name))

                flag = False
                break

        else:
            await member.send(embed=setup_group_error(answer))


async def remove_groups(eitcog, member):
    for role in member.roles:
        if role in [group.role for group in eitcog.groups]:
            await member.remove_roles(role)
