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
    CONTINUE_REPORT = auto()


class ToxicThreshold(Enum):
    IDENTITY_ATTACK = 0.87
    THREAT = 0.88
    FLIRTATION = 1
    TOXICITY = 0.86
    SEVERE_TOXICITY = 0.75
    PROFANITY = 0.85


class QuestionableThreshold(Enum):
    IDENTITY_ATTACK = 0.65
    THREAT = 0.64
    FLIRTATION = 0.60
    TOXICITY = 0.66
    SEVERE_TOXICITY = 0.68
    PROFANITY = 0.62


class Type(Enum):
    SPAM_KEYWORD = "spam"
    DISLIKE_KEYWORD = "dislike"
    HATE_KEYWORD = "hate speech"
    DOXXING_KEYWORD = "doxxing"
    THREAT_KEYWORD = "threat"
    HARRASS_KEYWORD = "harassment"
    HEALTH_KEYWORD = "suicide/self-harm"
    GRAPHIC_KEYWORD = "nudity/pornagraphy"
    CSA_KEYWORD = "csa"
    ASA_KEYWORD = "asa"


class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        self.client.state = self.state
        self.client.continue_report = None

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
            reply = "Thank you for starting the reporting process. "
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
            self.client.private_dm_guild = guild = self.client.get_guild(int(m.group(1)))
            if not guild:
                return [
                    "I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."]
            channel = guild.get_channel(int(m.group(2)))
            if not channel:
                return [
                    "It seems this channel was deleted or never existed. Please try again or say `cancel` to cancel."]
            try:
                message = await channel.fetch_message(int(m.group(3)))
                self.client.message = message
            except discord.errors.NotFound:
                return [
                    "It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            # Here we've found the message - it's up to you to decide what to do next!
            self.client.state = self.state = State.MESSAGE_IDENTIFIED
            reply = "I found this message:\n" + "```" + message.author.name + ": " + message.content + "```\n"
            reply += "Please choose why you wish to report this content\n\n"
            reply += "`" + "spam" + "`" + "\n"
            reply += "`" + "dislike" + "`" + "\n"
            reply += "`" + "hate speech" + "`" + "\n"
            reply += "`" + "doxxing" + "`" + "\n"
            reply += "`" + "threat" + "`" + "\n"
            reply += "`" + "harassment" + "`" + "\n"
            reply += "`" + "suicide/self-harm" + "`" + "\n"
            reply += "`" + "nudity/pornography" + "`" + "\n"
            reply += "`" + "csa" + "`" + " - child abuse, child exploitation, or grooming behaviors\n"
            reply += "`" + "adult-abuse/adult-exploitation" + "`" + "\n"
            reply += "\n\n"

            return [reply]

        if self.client.state == State.CONTINUE_REPORT:
            try:
                result = Type[message.content.upper()]
                self.state = self.client.state
                return result
            except KeyError:
                return "Invalid response"

        return []

    def handle_report_reply(self, message):
        try:
            type_key = f'{message.upper()}_KEYWORD'
            result = f'High Priority - This message was reported  as {Type[type_key].value}'
            return result
        except KeyError:
            "Invalid response"

    def eval_threshold(self, scores):
        '''
        Check the threshold of of every message
        '''

        toxic_results = []
        questionable_results = []
        for key in scores.keys():
            if scores.get(key, 0) > ToxicThreshold[key].value:
                toxic_results.append(ToxicThreshold[key])
            elif scores.get(key, 0) > QuestionableThreshold[key].value:
                questionable_results.append(QuestionableThreshold[key])

        if toxic_results:
            return 1, toxic_results
        elif questionable_results:
            return 2, questionable_results
        else:
            return 0, []

    def perform_toxic_action(self, toxic_results, author_id):
        self.client.warning_count[author_id] += 1

        threshold_phrase = {
            ToxicThreshold.IDENTITY_ATTACK: 'attacking identity',
            ToxicThreshold.PROFANITY: 'profane',
            ToxicThreshold.THREAT: 'threatening',
            ToxicThreshold.TOXICITY: 'toxic',
            ToxicThreshold.SEVERE_TOXICITY: 'vulgar',
            ToxicThreshold.FLIRTATION: 'flirtatious'
        }

        for threshold in toxic_results:
            message = threshold_phrase.get(threshold, '') + ', '

        if len(toxic_results) == 1:
            return message.rstrip(', ')

        formatted_message = message.rstrip(', ').split(', ')
        last = formatted_message.pop()
        return f"{', '.join(formatted_message)} and {last}."

    def perform_questionable_action(self, questionable_results):

        if not questionable_results:
            return "This message seems to be okay"

        threshold_phrase = {
            QuestionableThreshold.IDENTITY_ATTACK: 'attacking identity',
            QuestionableThreshold.PROFANITY: 'profane',
            QuestionableThreshold.THREAT: 'threatening',
            QuestionableThreshold.TOXICITY: 'toxic',
            QuestionableThreshold.SEVERE_TOXICITY: 'vulgar',
            QuestionableThreshold.FLIRTATION: 'flirtatious'
        }

        message = 'WARNING: This message might be '

        for threshold in questionable_results:
            message += threshold_phrase.get(threshold) + ', '

        if len(questionable_results) == 1:
            return message.rstrip(', ')

        formatted_message = message.rstrip(', ').split(', ')
        last = formatted_message.pop()
        return f"{', '.join(formatted_message)} and {last}."

    def report_complete(self):
        return self.state == State.REPORT_COMPLETE
