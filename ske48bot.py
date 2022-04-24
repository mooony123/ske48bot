#!/usr/bin/python3

import os

import discord

#TOKEN = os.getenv('DISCORD_TOKEN')
with open('token', 'r') as f:
    TOKEN = f.read()
print(TOKEN)
client = discord.Client()

@client.event
async def on_ready():
    print(f'{client.user} has connected to discord!')
    for guild in client.guilds:
        for channel in guild.channels:
            print(f'{channel.name} {channel.type}')
            if channel.name == 'ske-calendar':
                if type(channel) != discord.channel.TextChannel:
                    print(f'channel type is "{channel.type}"')
                    print(type(channel.type))
                    continue
                print('found')
                print(channel.id)
                await channel.send('Hello world ハローワールド')

client.run(TOKEN)
