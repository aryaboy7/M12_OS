class ServiceRegistry:
    """
    Central registry for all M12 OS services.

    AI plugins access services through:

        context.services.notes
        context.services.calendar
        context.services.music

    Services can be added gradually as M12 develops.
    """

    def __init__(self):
        self._services = {}

    def register(
        self,
        name,
        service,
    ):
        """
        Register a service.

        Example:

            registry.register(
                "notes",
                NotesService(),
            )
        """
        service_name = str(
            name
        ).strip().lower()

        if not service_name:
            raise ValueError(
                "Service name cannot be empty."
            )

        if service is None:
            raise ValueError(
                f"Service '{service_name}' cannot be None."
            )

        self._services[
            service_name
        ] = service

        return service

    def unregister(
        self,
        name,
    ):
        """
        Remove a service from the registry.
        """
        service_name = str(
            name
        ).strip().lower()

        return self._services.pop(
            service_name,
            None,
        )

    def get(
        self,
        name,
        default=None,
    ):
        """
        Return a service by name.
        """
        service_name = str(
            name
        ).strip().lower()

        return self._services.get(
            service_name,
            default,
        )

    def require(
        self,
        name,
    ):
        """
        Return a service or raise an error if unavailable.
        """
        service_name = str(
            name
        ).strip().lower()

        service = self.get(
            service_name
        )

        if service is None:
            raise RuntimeError(
                f"M12 service is unavailable: "
                f"{service_name}"
            )

        return service

    def has(
        self,
        name,
    ):
        """
        Return True when a service is registered.
        """
        service_name = str(
            name
        ).strip().lower()

        return (
            service_name
            in self._services
        )

    def names(self):
        """
        Return all registered service names.
        """
        return sorted(
            self._services.keys()
        )

    def items(self):
        """
        Return registered service name/object pairs.
        """
        return list(
            self._services.items()
        )

    def capabilities(self):
        """
        Return capabilities published by registered services.
        """
        result = {}

        for name, service in self._services.items():
            capabilities = getattr(
                service,
                "CAPABILITIES",
                [],
            )

            result[name] = list(
                capabilities
            )

        return result

    def __getattr__(
        self,
        name,
    ):
        """
        Allow attribute access:

            context.services.notes

        instead of:

            context.services.get("notes")
        """
        if name.startswith("_"):
            raise AttributeError(name)

        service = self.get(
            name
        )

        if service is None:
            raise AttributeError(
                f"Service '{name}' is not registered."
            )

        return service