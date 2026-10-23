"""Running a command for a sender: what a direct message over the radio and
the web console share, so a command behaves the same from both. Who may run
it, and how often, is checked before; this runs it, logs it and turns what
it returns (or raises) into the messages of its reply.
"""

import asyncio

from .api import CommandError, CommandResult, to_messages


async def run_command(command, text, sender, state):
    """Run command with text for sender, and return its reply as messages
    (none if it has nothing to say). A command that times out, refuses or
    fails gets a one-message reply saying so; errors and timeouts are
    counted for health and the node watch. A private command's text, and
    the reason it failed, are never printed."""
    private = command.private
    print(f"  -> running {command.name} {'' if private else text}".rstrip(), flush=True)
    try:
        result = await asyncio.wait_for(command.execute(text, sender), command.timeout)
    except TimeoutError:
        print(f"  {command.name} timed out after {command.timeout}s", flush=True)
        state.error(f"{command.name} timed out")
        return [f"{command.name}: timed out"]
    except CommandError as e:
        print(f"  {command.name}: refused" if private else f"  {e}", flush=True)
        return [str(e)]
    except Exception as e:
        print(f"  {command.name} failed: {type(e).__name__ if private else e}", flush=True)
        state.error(f"{command.name} failed")
        # An error may carry a reply that says why, safe to send.
        return [getattr(e, "reply", None) or f"{command.name}: failed"]
    if not isinstance(result, CommandResult):
        # Function commands may return just the reply.
        result = CommandResult(console=result if isinstance(result, str) else "", reply=result)
    if result.console:
        print(result.console, flush=True)
    messages = to_messages(result.reply)
    if not messages:
        print("  -> no reply", flush=True)
    return messages
