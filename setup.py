from __future__ import annotations
import logging
from typing import List

import discord

from .userinput import userinput_loop, is_valid_name

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
                                 title="Value Error")


def semester_start(semesters: List) -> discord.Embed:
    embed = discord.Embed(description="Hallo liebe Kommolitionen und Kommolitioninnen!\n\n"
                                      "Das neue Semester steht schon wieder vor der Tür obwohl "
                                      "das Letzte noch nicht mal richtig verdaut wurde.\n"
                                      "Nichts desto trotz müssen wir alle im 3ten (und hoffentlich letzten) "
                                      "Coronasemester nochmal die Zähne zusammen beißen und die paar wenigen "
                                      "Monate gemeinsam überstehen.\n\n"
                                      "Damit auf dem Elektrotechnik Studium Server die Studien"
                                      "gruppen wieder übereinstimmen, **antworte bitte mit deiner "
                                      "entsprechenden Studiengruppe** auf diese Nachricht!\n",
                          colour=discord.Colour(0x2fb923),
                          title="Semesterstart")

    group_select(embed, semesters)

    return embed


def setup_group_select(name: str, semesters: List) -> discord.Embed:
    embed = discord.Embed(description=f'Hallo **{name}**!\n'
                                      f'Antworte jetzt noch mit deiner Studiengruppe, '
                                      f'um dieses Setup abzuschließen.\n\n'
                                      f'**Folgende Studiengruppen stehen zur Auswahl:**\n\n',
                          colour=discord.Colour(0x2fb923),
                          title="Studiengruppen Auswahl")

    group_select(embed, semesters)

    return embed


def group_select(embed, semesters: List) -> discord.Embed:
    # add known studygroups to embed
    for semester in semesters:
        group_string = ''
        for group in semester.groups:
            group_string += str(group) + '\n'
        embed.add_field(name=str(semester), value=group_string, inline=True)

    # add guest role to embed
    embed.add_field(name='Sonstige', value="Gast", inline=True)

    return embed


def setup_group_error(message: str) -> discord.Embed:
    embed = discord.Embed(description=f'Hoppla!\n'
                                      f'Wie es scheint, ist "{message}" keine gültige Studiengruppe.\n'
                                      f'Probiere es bitte nochmal mit einer Studiengruppe aus der Liste!\n',
                          colour=discord.Colour(0x2fb923),
                          title="Value Error")
    return embed


def setup_end(study_group_name: str) -> discord.Embed:
    embed = discord.Embed(description=f'Vielen Dank für die Einschreibung in unseren EIT-Server.\n'
                                      f'Du wurdest der Gruppe **{study_group_name}** zugewiesen.\n\n'
                                      f'Hiermit hast du das Setup abgeschlossen und deine Angaben\n'
                                      f'werden in den Server eingetragen.\n\n'
                                      f'**Falls etwas mit deiner Eingabe nicht stimmt,\n'
                                      f'führe das Setup einfach nochmal aus und pass deine Eingabe an!**',
                          colour=discord.Colour(0x2fb923),
                          title="Ende")
    return embed


async def setup_dialog(eitcog, member: discord.Member) -> None:
    try:
        await member.send(embed=setup_start)
    except (AttributeError, discord.HTTPException):
        return
    answer = await userinput_loop(eitcog, member, member.dm_channel,
                                  filterfunc=is_valid_name, error_embed=setup_name_error)
    # change Users Nickname to tiped name
    try:
        await member.edit(nick=answer)
    except discord.Forbidden:
        logging.info(f'could not asign new nickname to member "{answer}"')

    await member.send(embed=setup_group_select(answer, eitcog.semesters))
    await group_selection(eitcog, member)


async def group_selection(eitcog, member: discord.Member) -> None:
    # loop until User tiped in a valid studygroup
    role = await userinput_loop(eitcog, member, member.dm_channel,
                                converter=convert_object_roles, error_embed=setup_group_error)

    await remove_groups(eitcog, member)
    await member.add_roles(role)

    if role == eitcog.roles['Gast']:
        await member.remove_roles(eitcog.roles['Student'])
    else:
        await member.add_roles(eitcog.roles['Student'])

    await member.send(embed=setup_end(role.name))
    return


def convert_object_roles(answer, eitcog):
    for name, role in eitcog.roles.items():
        if answer.lower() == name.lower():
            return role
    for group in eitcog.groups:
        if answer.upper() in group.name.upper():
            return group.role


async def remove_groups(eitcog, member: discord.Member) -> None:
    for role in member.roles:
        if role in [group.role for group in eitcog.groups]:
            await member.remove_roles(role)


async def semester_start_dialog(eitcog, member: discord.Member) -> None:
    try:
        await member.send(embed=semester_start(eitcog.semesters))
    except (AttributeError, discord.HTTPException):
        print('Kot')
    await group_selection(eitcog, member)
