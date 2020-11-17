from discord import Status

from conf.conf import Conf

name = 'mafia bidoof'
owner_id = 123456789012345678  # this is me! it is not you! change it to be you!
client_token = 'your token here'
status = None

cogs = [
    'eimm',
    'hostbot',
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
    greentick_id=632481525325103114,  # change these to reflect your own emojis
    redtick_id=632481525979676712,  # change these to reflect your own emojis
    plugins=plugins,
    imgur_keys=imgur_keys,
)
