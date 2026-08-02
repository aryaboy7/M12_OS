import importlib
import inspect
import pkgutil

from services.ai_plugin import (
    AIPlugin,
    PLUGIN_NOT_HANDLED,
)


class AIPluginManager:
    """
    Automatically finds and runs M12 AI plugins.
    """

    def __init__(
        self,
        package_name="plugins",
    ):
        self.package_name = package_name
        self.plugins = []
        self.load_errors = []

        self.load_plugins()

    def load_plugins(self):
        """
        Discover plugin classes inside the plugins package.
        """
        self.plugins.clear()
        self.load_errors.clear()

        try:
            package = importlib.import_module(
                self.package_name
            )
        except Exception as error:
            self.load_errors.append(
                f"Cannot load plugin package "
                f"'{self.package_name}': "
                f"{type(error).__name__}: {error}"
            )
            return

        package_paths = getattr(
            package,
            "__path__",
            None,
        )

        if package_paths is None:
            self.load_errors.append(
                f"'{self.package_name}' is not a package."
            )
            return

        for module_info in pkgutil.iter_modules(
            package_paths
        ):
            module_name = module_info.name

            if module_name.startswith("_"):
                continue

            full_module_name = (
                f"{self.package_name}.{module_name}"
            )

            try:
                module = importlib.import_module(
                    full_module_name
                )

                self._load_plugins_from_module(
                    module
                )

            except Exception as error:
                self.load_errors.append(
                    f"Cannot load {full_module_name}: "
                    f"{type(error).__name__}: {error}"
                )

        self.plugins.sort(
            key=lambda plugin: getattr(
                plugin,
                "priority",
                100,
            )
        )

    def _load_plugins_from_module(
        self,
        module,
    ):
        """
        Create every AIPlugin class declared in a module.
        """
        for _, plugin_class in inspect.getmembers(
            module,
            inspect.isclass,
        ):
            if plugin_class is AIPlugin:
                continue

            if not issubclass(
                plugin_class,
                AIPlugin,
            ):
                continue

            if plugin_class.__module__ != module.__name__:
                continue

            try:
                self.plugins.append(
                    plugin_class()
                )

            except Exception as error:
                self.load_errors.append(
                    f"Cannot create plugin "
                    f"{plugin_class.__name__}: "
                    f"{type(error).__name__}: {error}"
                )

    def process(
        self,
        message,
        context,
    ):
        """
        Process a message using plugins in priority order.
        """
        for plugin in self.plugins:
            try:
                can_handle = plugin.can_handle(
                    message=message,
                    context=context,
                )

                if not can_handle:
                    continue

                response = plugin.execute(
                    message=message,
                    context=context,
                )

                if response is PLUGIN_NOT_HANDLED:
                    continue

                return True, response

            except Exception as error:
                plugin_name = getattr(
                    plugin,
                    "name",
                    plugin.__class__.__name__,
                )

                return (
                    True,
                    (
                        f"Plugin error in {plugin_name}: "
                        f"{type(error).__name__}: {error}"
                    ),
                )

        return False, None

    def reload_plugins(self):
        """
        Search the plugins folder again.
        """
        self.load_plugins()

    def get_plugin_names(self):
        """
        Return all loaded plugin names.
        """
        return [
            getattr(
                plugin,
                "name",
                plugin.__class__.__name__,
            )
            for plugin in self.plugins
        ]

    def get_plugin_info(self):
        """
        Return information about every loaded plugin.
        """
        return [
            {
                "name": getattr(
                    plugin,
                    "name",
                    plugin.__class__.__name__,
                ),
                "description": getattr(
                    plugin,
                    "description",
                    "",
                ),
                "priority": getattr(
                    plugin,
                    "priority",
                    100,
                ),
            }
            for plugin in self.plugins
        ]