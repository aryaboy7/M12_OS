from abc import ABC, abstractmethod


class _PluginNotHandled:
    """
    Marker returned when a plugin inspected a message but
    decided not to handle it.
    """

    def __repr__(self):
        return "PLUGIN_NOT_HANDLED"


PLUGIN_NOT_HANDLED = _PluginNotHandled()


class AIPlugin(ABC):
    """
    Base class for every M12 AI plugin.
    """

    name = "base_plugin"
    description = "Base AI plugin"
    priority = 100

    @abstractmethod
    def can_handle(
        self,
        message,
        context,
    ):
        """
        Return True when this plugin may handle the message.
        """
        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        message,
        context,
    ):
        """
        Execute the command.

        Return a response string or PLUGIN_NOT_HANDLED.
        """
        raise NotImplementedError