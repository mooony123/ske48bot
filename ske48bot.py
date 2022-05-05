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
from typing import Tuple
from typing import Callable
import tempfile
import requests

from ske48schedule.ske48schedule import todays_schedule_str
from ske48blog import ske48blog

import pprint

import logging

logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

tz = pytz.timezone('Japan')
default_schedule_cron = '* * * * *'

client = commands.Bot(command_prefix='!')

scheduler = AsyncIOScheduler(event_loop=client.loop, timezone=tz,
                             job_defaults={'coalesce': True, 'misfire_grace_time': None})

schedule_info = {}
schedule_jobs = {}

blog_info = {}
blog_job = None

def dump_info(data: dict, name: str):
    with open(f'{name}.json', 'w') as f:
        json.dump(data, f)

def load_info(name: str):
    if not os.path.isfile(f'{name}.json'):
        return {}
    with open(f'{name}.json', 'r') as f:
        return json.load(f)

def convert_keys_to_int(to_convert: dict):
    new_dict = {int(k): v for k, v in to_convert.items()}
    to_convert.clear()
    to_convert.update(new_dict)

def parse_op(ctx, info: dict, args: list, valid_ops: list) -> Tuple[bool, str]:
    op = args[0]
    all_valid_ops = ['cron', 'channel', 'enable', 'disable']

    if (op not in valid_ops) or (op not in all_valid_ops):
        return False, f'invalid op: {op}'

    if op == 'cron':
        if croniter.croniter.is_valid(args[1]):
            info['cron'] = args[1]
            return True, f'crontab set to {args[1]}'
        return False, f'Invalid crontab {args[1]}'
    elif op == 'channel':
        for channel in ctx.guild.channels:
            if channel.name == args[1]:
                info['channel'] = channel.id
                return True, f'will post to {args[1]}'
        return False, f'{args[1]} not found'
    elif op == 'enable':
        return True, 'enabled on this channel'
    elif op == 'disable':
        info.clear()
        return True, 'disabled'

def job_from_info(guild_id: int, info: dict, jobs: dict, task: Callable) -> bool:

    if len(info) == 0:
        jobs.pop(guild_id, None)
        return True

    if(
        ('channel' not in info) or
        ('cron' not in info) or
        not croniter.croniter.is_valid(info['cron'])
    ):
        return False

    guild = client.get_guild(guild_id)
    if guild == None:
        print(f'guild {guild_id} == None!!')
        return False
    channel = guild.get_channel(info['channel'])
    if (channel == None) or (type(channel) != discord.channel.TextChannel):
        print(f'invalid channel {info["channel"]}')
        return False

    trigger = None
    if len(info['cron']) != 0:
        trigger = CronTrigger.from_crontab(info['cron'])
    if guild_id not in jobs:
        print("adding job")
        job = scheduler.add_job(task,
                                trigger=trigger,
                                args=[channel])
        jobs[guild_id] = job
    else:
        if jobs[guild_id] == None:
            print(f'job handle for guild_id f{guild_id} is None!')
            return False
        jobs[guild_id].modify(trigger=trigger,
                              args=[channel])

    return True

def broadcast_job_from_info(info: dict, job, task: Callable) -> bool:
    channels = []
    for guild_id, guild_info in info.items():
        if type(guild_id) is not int or type(guild_info) is not dict:
            raise TypeError

        guild = client.get_guild(guild_id)
        if guild == None:
            continue
        channel = guild.get_channel(guild_info['channel'])
        if (channel == None) or (type(channel) != discord.channel.TextChannel):
            continue
        cron = guild_info.get('cron')
        channels.append(channel)
    if len(channels) == 0:
        if job != None:
            job.remove()
            job = None
        return True

    trigger = CronTrigger.from_crontab(cron)
    if job == None:
        job = scheduler.add_job(task, trigger=trigger, args=[channels])
    else:
        job.modify(trigger=trigger, args=[channels])
    return True

def init_jobs():
    for guild_id, info in schedule_info.items():
        if not job_from_info(guild_id, info, schedule_jobs, ske48schedule_task):
            raise RuntimeError('init_jobs schedule')
    if not broadcast_job_from_info(blog_info,
                                   blog_job,
                                   ske48blog_task):
        raise RuntimeError('init_jobs blog')

async def ske48schedule_task(channel):
    await channel.send(todays_schedule_str())

@client.command(name='schedule')
async def schedule_command(ctx, *args):

    if ctx.guild == None: return

    if len(args) == 0:
        await ctx.send(todays_schedule_str())
        return

    if not ctx.message.author.guild_permissions.manage_guild: return

    info_entry = {'channel' : ctx.channel.id,
                  'cron' : default_schedule_cron
                 }
    if ctx.guild.id in schedule_info:
        info_entry = schedule_info[ctx.guild.id]

    update, response = parse_op(ctx, info_entry, args,
                                ['cron', 'channel', 'enable', 'disable'])
    if update == True:
        res = job_from_info(ctx.guild.id, info_entry,
                            schedule_jobs, ske48schedule_task)
        if res is False:
            raise RuntimeError('schedule command job')

        if len(info_entry) == 0:
            schedule_info.pop(ctx.guild.id, None)
        else:
            schedule_info[ctx.guild.id] = info_entry
        dump_info(schedule_info, 'schedule_info')
    await ctx.send(response)

async def ske48blog_task(channels: list):
    new_blogs = await asyncio.create_task(ske48blog.get_new_blogs())
    for new_blog in new_blogs:
        blog_dict = ske48blog.parse_blog(new_blog)
        blog_str = ske48blog.blog_to_str(blog_dict)

        files = []
        for image_url in blog_dict.get(ske48blog.IMAGES):
            fp = tempfile.NamedTemporaryFile(suffix='.jpeg')
            resp = requests.get(image_url, stream=True)
            fp.write(resp.raw.read())
            files.append(discord.File(fp=fp.name))
        for channel in channels:
            await channel.send(blog_str, files=files)

@client.command('blog')
async def blog_command(ctx, *args):

    if ctx.guild == None: return
    if not ctx.message.author.guild_permissions.manage_guild: return
    if args[0] == 'cron' and ctx.author.id != 234525271531716609: return

    info_entry = {'channel' : ctx.channel.id,
                  'cron' : default_schedule_cron
                 }
    info_entry = blog_info.get(ctx.guild.id, info_entry)

    update, response = parse_op(ctx, info_entry, args,
                                ['cron', 'channel', 'enable', 'disable'])
    if update == True:
        if len(info_entry) == 0:
            blog_info.pop(ctx.guild.id, None)
        else:
            blog_info.update({ctx.guild.id: info_entry})
        for v in blog_info.values():
            v.update(cron=info_entry['cron'])

        res = broadcast_job_from_info(blog_info,
                                      blog_job,
                                      ske48blog_task)
        if res is False:
            raise RuntimeError('blog command job')

        dump_info(blog_info, 'blog_info')
    await ctx.send(f'blog {response}')

@client.event
async def on_ready():
    print(f'{client.user} has connected to discord!')
    schedule_info.update(load_info('schedule_info'))
    convert_keys_to_int(schedule_info)

    await ske48blog.init()
    blog_info.update(load_info('blog_info'))
    convert_keys_to_int(blog_info)

    init_jobs()
    scheduler.start()

@client.event
async def on_error(event, *args, **kwargs):
    print(f'{event}')
    exit()

IS_TEST = os.getenv('BOT_TEST')
token_filename = 'token_test' if IS_TEST else 'token'
with open(token_filename, 'r') as f:
    TOKEN = f.read()
print(TOKEN)

client.run(TOKEN)
