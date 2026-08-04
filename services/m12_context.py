from services.service_manager import ServiceManager


class M12Context:
    """
    Stable interface between AI plugins and M12 OS.

    Plugins should use this context instead of accessing
    Kivy objects or importing application services directly.
    """

    def __init__(
        self,
        ai_screen,
        router,
    ):
        self.ai_screen = ai_screen
        self.router = router

        self.screen_manager = getattr(
            ai_screen,
            "manager",
            None,
        )

        self.services = (
            ServiceManager.get_registry()
        )

    def get(
        self,
        name,
        default=None,
    ):
        """
        Compatibility with older plugins that used context as a dict.
        """
        values = {
            "ai_screen": self.ai_screen,
            "router": self.router,
            "screen_manager": self.screen_manager,
            "services": self.services,
        }

        return values.get(
            name,
            default,
        )

    #
    # Screens
    #

    def open_screen(
        self,
        screen_name,
    ):
        """
        Open an M12 screen.

        Returns True when successful.
        """
        if self.screen_manager is None:
            return False

        target = str(
            screen_name
        ).strip()

        if not target:
            return False

        try:
            self.screen_manager.current = target
            return True

        except Exception as error:
            print(
                "M12Context open_screen error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    def has_screen(
        self,
        screen_name,
    ):
        """
        Return True when ScreenManager contains the screen.
        """
        if self.screen_manager is None:
            return False

        target = str(
            screen_name
        ).strip()

        try:
            return self.screen_manager.has_screen(
                target
            )

        except Exception:
            return False

    def get_screen(
        self,
        screen_name,
    ):
        """
        Return a Kivy screen when needed by a compatibility
        plugin.

        New plugins should prefer service methods.
        """
        if self.screen_manager is None:
            return None

        try:
            return self.screen_manager.get_screen(
                screen_name
            )

        except Exception:
            return None

    def open_notes_filter(
        self,
        note_type,
    ):
        """
        Open Notes and apply a note-type filter.
        """
        if not self.open_screen("notes"):
            return False

        notes_screen = self.get_screen(
            "notes"
        )

        if notes_screen is None:
            return False

        try:
            notes_screen.set_filter(
                str(note_type).strip()
            )
            return True

        except Exception as error:
            print(
                "M12Context Notes filter error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    #
    # Services
    #

    def get_service(
        self,
        service_name,
        default=None,
    ):
        """
        Return an M12 service by name.
        """
        return self.services.get(
            service_name,
            default,
        )

    def require_service(
        self,
        service_name,
    ):
        """
        Return a service or raise an error.
        """
        return self.services.require(
            service_name
        )

    def has_service(
        self,
        service_name,
    ):
        """
        Return True when a service is registered.
        """
        return self.services.has(
            service_name
        )

    def get_capabilities(self):
        """
        Return capabilities published by all M12 services.
        """
        return self.services.capabilities()

    #
    # AI
    #

    def ask_ai(
        self,
        message,
    ):
        """
        Send a request directly to the OpenAI service.
        """
        return self.router.ask_openai(
            message
        )

    #
    # Notifications
    #

    def notify(
        self,
        text,
    ):
        """
        Temporary notification interface.

        Later this will use NotificationService.
        """
        message = str(
            text
        ).strip()

        if message:
            print(
                f"M12 notification: {message}"
            )
