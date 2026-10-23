"""Running a command for a sender: what a direct message over the radio and
the web console share, so a command behaves the same from both. Who may run
it, and how often, is checked before; this runs it, logs it and turns what
it returns (or raises) into the messages of its reply.
"""

import asyncio
from dataclasses import dataclass, field

from .api import CommandError, CommandResult, to_messages


@dataclass
class Answer:
    """What running a command gave: the messages of its reply (none if it
    has nothing to say), whether they only ask to confirm, and whether it ran
    (False if it refused, failed or timed out: the messages say why)."""

    messages: list[str] = field(default_factory=list)
    asks: bool = False
    ok: bool = True


async def run_command(command, text, sender, state):
    """Run command with text for sender, and return its Answer. A command
    that times out, refuses or fails gets a one-message reply saying so;
    errors and timeouts are counted for health and the node watch. A private
    command's text, and the reason it failed, are never printed."""
    private = command.private
    print(f"  -> running {command.name} {'' if private else text}".rstrip(), flush=True)
    try:
        result = await asyncio.wait_for(command.execute(text, sender), command.timeout)
    except TimeoutError:
        print(f"  {command.name} timed out after {command.timeout}s", flush=True)
        state.error(f"{command.name} timed out")
        return Answer([f"{command.name}: timed out"], ok=False)
    except CommandError as e:
        print(f"  {command.name}: refused" if private else f"  {e}", flush=True)
        return Answer([str(e)], ok=False)
    except Exception as e:
        print(f"  {command.name} failed: {type(e).__name__ if private else e}", flush=True)
        state.error(f"{command.name} failed")
        # An error may carry a reply that says why, safe to send.
        return Answer([getattr(e, "reply", None) or f"{command.name}: failed"], ok=False)
    if not isinstance(result, CommandResult):
        # Function commands may return just the reply.
        result = CommandResult(console=result if isinstance(result, str) else "", reply=result)
    if result.console:
        print(result.console, flush=True)
    messages = to_messages(result.reply)
    if not messages:
        print("  -> no reply", flush=True)
    return Answer(messages, result.asks)
