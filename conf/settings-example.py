from discord import Status

from conf.conf import Conf

name = 'mafia bidoof'
owner_id = 123456789012345678  # this is me! it is not you! change it to be you!
client_token = 'your token here'
status = None

cogs = [
    'eimm',
    'hostbot',
    # Interview is a complex cog and is not part of the core utility; you're welcome to use it but it is complex.
    # 'interview',
    'macro',
    'profiles',
    # Add more cogs here!
]

plugins = [
    # Add more plugins here!
    # Plugins are used mostly for simple, one-off commands, rather than groups, which are best done as cogs!
    # (These may be phased out in the future, they're not nearly as useful as cogs.)
]

imgur_keys = {
    'id': 'your keys go here',
    'secret': 'your keys go here',
    'access': 'your keys go here',
    'refresh': 'your keys go here',
}

prefix = ['##']

conf = Conf(
    # NOTE: Emojis must be uploaded to your own server or add your bot to the discord.py server. They're used
    #  to acknowledge commands and report errors. You can use your own, or steal them; their URLs, for now, are:
    #  https://cdn.discordapp.com/emojis/596576670815879169.png?v=1
    #  https://cdn.discordapp.com/emojis/596576672149667840.png?v=1
    greentick_id=632481525325103114,  # change these to reflect your own emoji ID
    redtick_id=632481525979676712,  # change these to reflect your own emoji ID
    boostemoji_id=797974971137654845,  # change these to reflect your own emoji ID
    waitemoji_id=833565752035639316,  # change these to reflect your own emoji ID
    plugins=plugins,
    imgur_keys=imgur_keys,
    google_email='your-bot-here@your-bot-here.iam.gserviceaccount.com',
)
