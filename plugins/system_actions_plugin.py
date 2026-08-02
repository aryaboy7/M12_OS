from services.ai_actions import AIActions
from services.ai_plugin import (
    AIPlugin,
    PLUGIN_NOT_HANDLED,
)


class SystemActionsPlugin(AIPlugin):
    """
    Makes the existing AIActions system available as a plugin.
    """

    name = "system_actions"
    description = "Controls M12OS applications and local actions"
    priority = 10

    def can_handle(
        self,
        message,
        context,
    ):
        # The current AIActions class checks support in execute().
        return True

    def execute(
        self,
        message,
        context,
    ):
        ai_screen = context.get(
            "ai_screen"
        )

        handled, response = AIActions.execute(
            message=message,
            ai_screen=ai_screen,
        )

        if not handled:
            return PLUGIN_NOT_HANDLED

        return response