from enum import Enum, auto
import discord
import requests
import re
import json

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    MESSAGE_IDENTIFIED = auto()
    REPORT_COMPLETE = auto()

class ToxicThreshold(Enum):
    IDENTITY_ATTACK = 0.87
    THREAT = 0.88
    FLIRTATION = 0.865
    TOXICITY = 0.86
    SEVERE_TOXICITY = 0.75
    PROFANITY = 0.85



class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        self.client.state = self.state

    async def handle_message(self, message):
        '''
        This function makes up the meat of the user-side reporting flow. It defines how we transition between states and what
        prompts to offer at each of those states. You're welcome to change anything you want; this skeleton is just here to
        get you started and give you a model for working with Discord.
        '''

        if message.content == self.CANCEL_KEYWORD:

            self.client.state = self.state = State.REPORT_COMPLETE
            return ["Report cancelled."]

        if self.state == State.REPORT_START:
            reply =  "Thank you for starting the reporting process. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.client.state = self.state = State.AWAITING_MESSAGE
            return [reply]

        if self.state == State.AWAITING_MESSAGE:
            # Parse out the three ID strings from the message link
            m = re.search('/(\d+)/(\d+)/(\d+)', message.content)

            if not m:
                return ["I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."]
            guild = self.client.get_guild(int(m.group(1)))
            if not guild:
                return ["I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."]
            channel = guild.get_channel(int(m.group(2)))
            if not channel:
                return ["It seems this channel was deleted or never existed. Please try again or say `cancel` to cancel."]
            try:
                message = await channel.fetch_message(int(m.group(3)))
                self.client.message = message
            except discord.errors.NotFound:
                return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            # Here we've found the message - it's up to you to decide what to do next!
            self.client.state = self.state = State.MESSAGE_IDENTIFIED
            return ["I found this message:", "```" + message.author.name + ": " + message.content + "```"]

        return []

    def eval_threshold(self, scores):
        '''
        Check the threshold of of every message
        '''
        # 1. send to human moderator
        # 2. tell the author that the message is toxic?
        # 3. Add the user to the offence db and give him a strike count
        # 4. if user strike count > 3, delete user
        # 5. replace the message with "this message has been removed"

        results = []
        for key in scores.keys():
            if scores.get(key, 0) > ToxicThreshold[key].value:
                results.append(ToxicThreshold[key])
        return results

    def perform_action(self, threshold_results, author_id):

        if not threshold_results :
            return "This message seems to be okay"

        self.client.warning_count[author_id] += 1

        threshold_phrase = {
            ToxicThreshold.IDENTITY_ATTACK: 'attacking identity',
            ToxicThreshold.PROFANITY: 'profane',
            ToxicThreshold.THREAT: 'threatening',
            ToxicThreshold.TOXICITY: 'toxic',
            ToxicThreshold.SEVERE_TOXICITY: 'vulgar',
            ToxicThreshold.FLIRTATION: 'flirtatious'
        }

        message = 'This message is '

        for threshold in threshold_results:
            message += threshold_phrase.get(threshold) + ', '

        if len(threshold_results) == 1:
            return message.rstrip(', ')


        formatted_message = message.rstrip(', ').split(', ')
        last = formatted_message.pop()
        return f"{', '.join(formatted_message)} and {last}."


    def report_complete(self):
        return self.state == State.REPORT_COMPLETE