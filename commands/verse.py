"""verse [reference]: a Bible verse (BSB), or the verse of the day.

The text is bundled with the bot (see bible/), so no network is needed. Long
passages are sent as several numbered messages: "(1/3) ...".
"""

import asyncio
import datetime
import textwrap

from bible import default_bible
from bible.votd import reference_for

from .base import Command, CommandError, CommandResult

# The most messages one reply may take, to keep a long range from tying up
# the mesh. The longest single verse (2 Kings 16:15) needs 4.
MAX_PARTS = 8


class VerseCommand(Command):
    name = "verse"
    usage = "verse [book chapter:verse[-verse]]"

    def __init__(self, load=default_bible, today=datetime.date.today):
        self.load = load  # returns the Bible; cached after the first call
        self.today = today

    async def execute(self, text, sender):
        bible = await asyncio.to_thread(self.load)
        reference = text or reference_for(self.today())
        try:
            passage = bible.lookup(reference)
        except ValueError as e:
            raise CommandError(f"verse: {e}") from e

        reply = self.split_reply(f"{passage.reference} {passage.text}")
        if len(reply) > MAX_PARTS:
            raise CommandError(f"verse: {passage.reference} needs {len(reply)} messages, "
                               f"max {MAX_PARTS}; ask for fewer verses")
        title = f"{'Verse of the day: ' if not text else ''}{passage.reference} ({bible.translation})"
        body = textwrap.fill(passage.text, 76, initial_indent="  ", subsequent_indent="  ")
        return CommandResult(console=f"{title}\n{body}", reply=reply)
