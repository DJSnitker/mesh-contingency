"""verse [reference]: a Bible verse (BSB), or the verse of the day.

The text is bundled with the bot (see bible/), so no network is needed. Long
passages are sent as several numbered messages: "(1/3) ...".
"""

import asyncio
import datetime
import textwrap

from ..api import MAX_PARTS, Command, CommandError, CommandResult
from ..bible import default_bible
from ..bible.votd import reference_for


class VerseCommand(Command):
    args = "[book chapter:verse[-verse]]"
    summary = "A Bible verse (BSB), or the verse of the day"

    def __init__(self, ctx, load=default_bible, today=datetime.date.today):
        super().__init__(ctx)
        self.load = load  # returns the Bible; cached after the first call
        self.today = today

    async def execute(self, text, sender):
        bible = await asyncio.to_thread(self.load)
        reference = text or reference_for(self.today())
        try:
            passage = bible.lookup(reference)
        except ValueError as e:
            raise CommandError(f"{self.name}: {e}") from e

        reply = self.split_reply(f"{passage.reference} {passage.text}")
        if len(reply) > MAX_PARTS:
            # Refuse rather than let the bot cut the passage short. The
            # longest single verse (2 Kings 16:15) needs 4 messages.
            raise CommandError(f"{self.name}: {passage.reference} needs {len(reply)} messages, "
                               f"max {MAX_PARTS}; ask for fewer verses")
        title = f"{'Verse of the day: ' if not text else ''}{passage.reference} ({bible.translation})"
        body = textwrap.fill(passage.text, 76, initial_indent="  ", subsequent_indent="  ")
        return CommandResult(console=f"{title}\n{body}", reply=reply)
