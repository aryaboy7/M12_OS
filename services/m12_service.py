class M12Service:
    """
    Base class for all M12 OS services.

    Every service should inherit from this class.
    """

    NAME = "Service"
    VERSION = "1.0"
    DESCRIPTION = ""

    CAPABILITIES = []

    def __init__(self):
        self.running = False

    def start(self):
        """
        Start the service.
        """
        self.running = True

    def stop(self):
        """
        Stop the service.
        """
        self.running = False

    def restart(self):
        """
        Restart the service.
        """
        self.stop()
        self.start()

    def is_running(self):
        return self.running

    def status(self):
        """
        Return information about this service.
        """
        return {
            "name": self.NAME,
            "version": self.VERSION,
            "description": self.DESCRIPTION,
            "running": self.running,
            "capabilities": list(self.CAPABILITIES),
        }

    def health_check(self):
        """
        Override if the service performs diagnostics.
        """
        return True