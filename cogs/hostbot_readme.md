# Mafia Bidoof Setup Guide

1. On a game server admin account, click the link: https://discordapp.com/oauth2/authorize?&client_id={BOT_ID_HERE}&scope=bot&permissions=0x00000008 _(fill this in with your own bot ID)_.

2. To initialize your server, enter the following command:
````yml
::init server ```yml
name: Server Name
channels:
  announcements: Announcements Channel Name
  flips: Flips Channel Name
  gamechat: Gamechat Channel Name
  graveyard: Graveyard Channel Name
  confessionals: Confesionals Channel Name
  music: Music Channel Name
roles:
  host:
    name: Host Role Name
    color: 0x8855ee
  player:
    name: Player Role Name
    color: 0x00bb99
  dead:
    name: Dead Role Name
    color: 0xbb0055
  spec:
    name: Spec Role Name
    color: 0x8181bb
sheet: Sheet Name Here  # this isn't actually used right now
```
````
Feel free to fill out these fields as you wish. They can be freely edited after the server is initialized, as well.

3. To create Role PM channels, enter the following command:
````
::init pmlist ```
player1#1234
player2#1234
player3#1234
...
```
````

4. You're done! This is it for basic host bot features.