from conf.conf import Conf

from cogs import profiles


name         = 'mafia bidoof'
owner_id     = 123456789012345678
client_token = 'your token here'

cogs = [
    profiles.Profiles,
]

plugins = [
    'hostbot'
]

prefix = ['##']

conf = Conf(
    greentick_id=632481525325103114,
    redtick_id=632481525979676712,
    plugins=plugins,
)