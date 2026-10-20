"""help [command]: the commands the sender may run, or how to use one."""

from ..api import Command, CommandError, CommandResult


class HelpCommand(Command):
    args = "[command]"
    summary = "List the commands you can use, or show how to use one"

    async def execute(self, text, sender):
        allowed = {name: cmd for name, cmd in self.ctx.commands.items() if self.ctx.allowed(cmd, sender)}
        if not text:
            reply = f"commands: {', '.join(allowed)}. Send {self.name} <command> for usage"
        else:
            name = text.split()[0].lower()
            # Commands the sender can't run get the same answer as unknown
            # ones, so help never reveals what others are allowed to do.
            if name not in allowed:
                raise CommandError(f"{self.name}: no command {name}")
            cmd = allowed[name]
            reply = f"{cmd.usage} - {cmd.summary}" if cmd.summary else cmd.usage
        return CommandResult(console=reply, reply=reply)
