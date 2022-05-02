#!/usr/bin/python3

import os
import asyncio
import croniter
import discord
import json
from discord.ext import commands
import pytz
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ske48schedule.ske48schedule import todays_schedule_str
from ske48blog import ske48blog

import pprint

import logging

logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

tz = pytz.timezone('Japan')
default_schedule_cron = '* * * * *'

client = commands.Bot(command_prefix='!')

scheduler = AsyncIOScheduler(event_loop=client.loop, timezone=tz)

schedule_info = {}
schedule_jobs = {}

def dump_info(data: dict, name: str):
    with open(f'{name}.json', 'w') as f:
        json.dump(data, f)

def load_info(name: str):
    if not os.path.isfile(f'{name}.json'): 
        return {}
    with open(f'{name}.json', 'r') as f:
        return json.load(f)

def ske48schedule_init_jobs():
    global schedule_info
    global schedule_jobs
    for guild_id in list(schedule_info.keys()):
        guild = client.get_guild(guild_id)
        if(guild == None):
            print("guild == none")
            continue

        channel = guild.get_channel(schedule_info[guild_id]['channel'])
        if((channel == None) or (type(channel) != discord.channel.TextChannel)):
            print("invalid channel")
            continue

        print("adding job")
        job = scheduler.add_job(ske48schedule_task,
                                CronTrigger.from_crontab(schedule_info[guild_id]['cron']),
                                args=[channel])
        schedule_jobs[guild.id] = job

async def ske48schedule_task(channel):
    await channel.send(todays_schedule_str())

@client.command(name='schedule')
async def schedule_command(ctx, *args):

    if ctx.guild == None: return

    if not len(args):
        await ctx.send(todays_schedule_str())
        return

    if not ctx.message.author.guild_permissions.manage_guild: return

    global schedule_info
    global schedule_jobs
    response = ''
    operation = args[0]
    update = False
    channel = None

    info_entry = {'channel' : ctx.channel.id,
                  'cron' : default_schedule_cron
                 }
    if ctx.guild.id in schedule_info:
        info_entry = schedule_info[ctx.guild.id]

    if operation == 'cron':
        if croniter.croniter.is_valid(args[1]):
            info_entry['cron'] = args[1]
            response = f'Auto schedule crontab set to {args[1]}'
            update = True
        else:
            resposne = f'Invalid crontab {args[1]}'
    elif operation == 'channel':
        for channel in ctx.guild.channels:
            if(channel.name == args[1]):
                info_entry['channel'] = channel.id
                update = True
                response = f'Auto schedule will be posted to {args[1]}'
    elif operation == 'enable':
        response = 'Auto schedule posting enabled on this channel'
        update = True
    elif operation == 'disable':
        if ctx.guild.id in schedule_jobs:
            if schedule_jobs[ctx.guild.id] == None:
                raise RuntimeError('job is none!!')
            schedule_jobs[ctx.guild.id].remove()
            schedule_jobs.pop(ctx.guild.id)
            schedule_info.pop(ctx.guild.id)
            dump_info(schedule_info, 'schedule_info')
            response = 'Auto schedule posting disabled'
    else:
        response = f'Invalid argument {operation}'

    if update == True:
        for channel in ctx.guild.channels:
            if channel.id == info_entry['channel']:
                channel_h = channel
        if ctx.guild.id not in schedule_jobs:
            job = scheduler.add_job(ske48schedule_task,
                                    CronTrigger.from_crontab(info_entry['cron']),
                                    args=[channel_h])
            schedule_jobs[ctx.guild.id] = job
        else:
            schedule_jobs[ctx.guild.id].modify(args=[channel_h],
                                               trigger=CronTrigger.from_crontab(info_entry['cron']))
        schedule_info[ctx.guild.id] = info_entry
        dump_info(schedule_info, 'schedule_info')
    await ctx.send(response)

@client.event
async def on_ready():
    print(f'{client.user} has connected to discord!')
    global schedule_info
    schedule_info = load_info('schedule_info')
    schedule_info = {int(k) : v for k, v in schedule_info.items()}

    await ske48blog.init()

    ske48schedule_init_jobs()
    scheduler.start()

@client.event
async def on_error(event, *args, **kwargs):
    print(f'{event}')
    exit()

#TOKEN = os.getenv('DISCORD_TOKEN')
with open('token', 'r') as f:
    TOKEN = f.read()
print(TOKEN)

client.run(TOKEN)
