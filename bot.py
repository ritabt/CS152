# bot.py
import discord
from discord.ext import commands
import os
import json
import logging
import re
import requests
from report import Report, State

# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'token.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']
    perspective_key = tokens['perspective']


class ModBot(discord.Client):
    def __init__(self, key):
        intents = discord.Intents.default()
        super().__init__(command_prefix='.', intents=intents)
        self.group_num = None   
        self.mod_channels = {} # Map from guild to the mod channel id for that guild
        self.reports = {} # Map from user IDs to the state of their report
        self.perspective_key = key
        self.warning_count = {} # no of times a user's message is flagged
        self._user_ban_message = None
        self._permission_denied = None
        self.state = None
        self.message = None

    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')

        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")
        
        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channels[guild.id] = channel

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # Ignore messages from us 
        if message.author.id == self.user.id:
            return
        
        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)

    async def handle_report(self, message, type_dm=False):
        author_id = message.author.id
        responses = []

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self)

        if author_id not in self.warning_count:
            self.warning_count[author_id] = 0
        
        self.message = message
        
        if type_dm:
            # Let the report class handle this message; forward all the messages it returns to uss
            responses = await self.reports[author_id].handle_message(message)
            for r in responses:
                await message.channel.send(r)

            # if the user inputs any other thing except a valid link to a message they intend to report
            if self.state and self.state != State.MESSAGE_IDENTIFIED:
                return
        
        # We want to evaluate all messages and check their threshold level
        scores = self.eval_text(self.message)
        threshold_results = self.reports[author_id].eval_threshold(scores)
        threshold_message = self.reports[author_id].perform_action(threshold_results, author_id)
        
        # Ban a user if he is flagged 3 or more times
        user_ban_message = "You've been banned from the group"
        if self.warning_count[author_id] >= 3:
            self._user_ban_message = user_ban_message
        
        #If a message is found wanting in any of the criteria, we want to delete the message
        if threshold_results:
            try:
                await message.delete()
                self._permission_denied = "This message has been removed"
            except discord.errors.Forbidden as e:
                print('Cannot delete message because ', e)
                self._permission_denied = "Message cannot be deleted because permission was denied"

        return threshold_message
    
    @property
    def user_ban_message(self):
        return self._user_ban_message

    async def handle_dm(self, message):
        # Handle a help message    
        if message.content == Report.HELP_KEYWORD:
            reply =  "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.startswith(Report.START_KEYWORD):
            return

        threshold_message = await self.handle_report(message, True)
 
        # If the report is complete or cancelled, remove it from our map
        if self.reports[author_id].report_complete():
            self.reports.pop(author_id)
        
        # Returns the evaluation of the reported message and if the user has been banned or message has been removed
        final_message = ''

        if threshold_message:
            final_message = threshold_message

            if self.user_ban_message:  
                final_message += f"\n{self.user_ban_message}"
            if self._permission_denied:
                final_message += f"\n{self._permission_denied}"
            await message.channel.send(final_message)


    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}':
            return 

        # Forward the message to the mod channel
        mod_channel = self.mod_channels[message.guild.id]
        await mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')
        
        response_message = await self.handle_report(message)
        await mod_channel.send(response_message)
        
        # send the final message to the mod channel
        final_message =''
        if self.user_ban_message:  
            final_message = self.user_ban_message
            await message.channel.send(self.user_ban_message)
        await message.channel.send(self._permission_denied if self._permission_denied else "")
    
        # await mod_channel.send(self.code_format(json.dumps(scores, indent=2)))


    def eval_text(self, message):
        '''
        Given a message, forwards the message to Perspective and returns a dictionary of scores.
        '''
        PERSPECTIVE_URL = 'https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze'

        url = PERSPECTIVE_URL + '?key=' + self.perspective_key
        data_dict = {
            'comment': {'text': message.content},
            'languages': ['en'],
            'requestedAttributes': {
                                    'SEVERE_TOXICITY': {}, 'PROFANITY': {},
                                    'IDENTITY_ATTACK': {}, 'THREAT': {},
                                    'TOXICITY': {}, 'FLIRTATION': {}
                                },
            'doNotStore': True
        }
        response = requests.post(url, data=json.dumps(data_dict))
        response_dict = response.json()

        scores = {}
        for attr in response_dict["attributeScores"]:
            scores[attr] = response_dict["attributeScores"][attr]["summaryScore"]["value"]

        return scores
    
    def code_format(self, text):
        return "```" + text + "```"
            
        
client = ModBot(perspective_key)
client.run(discord_token)