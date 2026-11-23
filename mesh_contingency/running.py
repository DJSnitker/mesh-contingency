"""Running a command for a sender. Who may run it, and how often, is checked
before; this runs it, logs it and turns what it returns (or raises) into the
messages of its reply.
"""

import asyncio
from dataclasses import dataclass, field

from .api import CommandError, CommandResult, to_messages


@dataclass
class Answer:
    """What running a command gave: the messages of its reply (none if it
    has nothing to say), and whether it ran (False if it refused, failed or
    timed out: the messages say why)."""

    messages: list[str] = field(default_factory=list)
    ok: bool = True


async def run_command(command, text, sender):
    """Run command with text for sender, and return its Answer. A command
    that times out, refuses or fails gets a one-message reply saying so. Only
    what happened is printed (ran, refused, failed, timed out), never the
    command's text, the reason it was refused or its reply: they're the
    sender's, and the log is kept for months."""
    print(f"  -> running {command.name}", flush=True)
    try:
        result = await asyncio.wait_for(command.execute(text, sender), command.timeout)
    except TimeoutError:
        print(f"  {command.name} timed out after {command.timeout}s", flush=True)
        return Answer([f"{command.name}: timed out"], ok=False)
    except CommandError as e:
        print(f"  {command.name}: refused", flush=True)
        return Answer([str(e)], ok=False)
    except Exception as e:
        # The reply an error carries says why without the sender's text.
        why = getattr(e, "reply", None)
        print(f"  {command.name} failed: {type(e).__name__}" + (f" ({why})" if why else ""), flush=True)
        # An error may carry a reply that says why, safe to send.
        return Answer([getattr(e, "reply", None) or f"{command.name}: failed"], ok=False)
    if not isinstance(result, CommandResult):
        # Function commands may return just the reply.
        result = CommandResult(console=result if isinstance(result, str) else "", reply=result)
    messages = to_messages(result.reply)
    if not messages:
        print("  -> no reply", flush=True)
    return Answer(messages)
