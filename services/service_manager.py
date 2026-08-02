from services.service_registry import ServiceRegistry
from services.notes_service import NotesService


class ServiceManager:
    """
    Creates and manages the shared M12 OS service registry.

    All AI plugins and M12 screens use the same service instances
    through:

        context.services.notes
        context.services.calendar
        context.services.music
    """

    _registry = None

    @classmethod
    def get_registry(cls):
        """
        Return the shared service registry.

        The registry and its services are created only once.
        """
        if cls._registry is None:
            cls._registry = ServiceRegistry()

            cls._register_services(
                cls._registry
            )

        return cls._registry

    @classmethod
    def _register_services(
        cls,
        registry,
    ):
        cls._register_service(
            registry=registry,
            service_class=NotesService,
        )
        """
        Create, start, and register all available M12 services.

        Add new services to this method as they are created.
        """

        # ---------------------------------------------------------
        # Notes Service
        # ---------------------------------------------------------
        #
        # Enable this block after creating:
        #
        #     services/notes_service.py
        #
        # from services.notes_service import NotesService
        #
        # cls._register_service(
        #     registry=registry,
        #     service_class=NotesService,
        # )

        # ---------------------------------------------------------
        # Future services
        # ---------------------------------------------------------
        #
        # from services.calendar_service import CalendarService
        # from services.music_service import MusicService
        # from services.file_service import FileService
        # from services.weather_service import WeatherService
        #
        # cls._register_service(
        #     registry,
        #     CalendarService,
        # )
        #
        # cls._register_service(
        #     registry,
        #     MusicService,
        # )
        #
        # cls._register_service(
        #     registry,
        #     FileService,
        # )
        #
        # cls._register_service(
        #     registry,
        #     WeatherService,
        # )

        pass

    @classmethod
    def _register_service(
        cls,
        registry,
        service_class,
    ):
        """
        Create, start, and register one service.

        The service class should inherit from M12Service and define:

            SERVICE_ID
            NAME
            VERSION
            CAPABILITIES
        """
        try:
            service = service_class()

            service_id = str(
                getattr(
                    service,
                    "SERVICE_ID",
                    "",
                )
            ).strip().lower()

            if not service_id:
                raise ValueError(
                    f"{service_class.__name__} "
                    "does not define SERVICE_ID."
                )

            start_method = getattr(
                service,
                "start",
                None,
            )

            if callable(start_method):
                start_method()

            registry.register(
                service_id,
                service,
            )

            print(
                "M12 service registered: "
                f"{service_id}"
            )

            return service

        except Exception as error:
            print(
                "M12 service registration error: "
                f"{service_class.__name__}: "
                f"{type(error).__name__}: {error}"
            )

            return None

    @classmethod
    def get_service(
        cls,
        service_name,
        default=None,
    ):
        """
        Return a registered service by name.
        """
        registry = cls.get_registry()

        return registry.get(
            service_name,
            default,
        )

    @classmethod
    def has_service(
        cls,
        service_name,
    ):
        """
        Return True when a service is registered.
        """
        registry = cls.get_registry()

        return registry.has(
            service_name
        )

    @classmethod
    def get_capabilities(cls):
        """
        Return capabilities published by all services.
        """
        registry = cls.get_registry()

        return registry.capabilities()

    @classmethod
    def get_status(cls):
        """
        Return status information for every registered service.
        """
        registry = cls.get_registry()

        result = {}

        for service_id, service in registry.items():
            try:
                status_method = getattr(
                    service,
                    "status",
                    None,
                )

                if callable(status_method):
                    result[service_id] = status_method()
                else:
                    result[service_id] = {
                        "name": getattr(
                            service,
                            "NAME",
                            service_id,
                        ),
                        "running": True,
                    }

            except Exception as error:
                result[service_id] = {
                    "name": service_id,
                    "running": False,
                    "error": (
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                }

        return result

    @classmethod
    def stop_all(cls):
        """
        Stop all registered services.
        """
        if cls._registry is None:
            return

        for service_id, service in cls._registry.items():
            try:
                stop_method = getattr(
                    service,
                    "stop",
                    None,
                )

                if callable(stop_method):
                    stop_method()

                print(
                    "M12 service stopped: "
                    f"{service_id}"
                )

            except Exception as error:
                print(
                    "M12 service stop error: "
                    f"{service_id}: "
                    f"{type(error).__name__}: {error}"
                )

    @classmethod
    def reset(cls):
        """
        Stop all services and recreate the registry.

        Useful during development or after settings changes.
        """
        cls.stop_all()

        cls._registry = None

        return cls.get_registry()