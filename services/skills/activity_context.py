import threading
import time


class ActivityContext:
    """
    Remembers which local activity the user is currently controlling.

    Examples:

        Start stopwatch
            -> activity = "stopwatch"

        Stop it
            -> routed to StopwatchSkill

        Start timer
            -> activity = "timer"

        Pause it
            -> routed to TimerSkill
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._activity = None
        self._timestamp = 0.0
        self.timeout = 300.0      # 5 minutes

    @classmethod
    def instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def set(self, activity):
        self._activity = str(activity)
        self._timestamp = time.monotonic()

    def clear(self):
        self._activity = None
        self._timestamp = 0.0

    def current(self):
        if self._activity is None:
            return None

        if (
            time.monotonic()
            - self._timestamp
        ) > self.timeout:
            self.clear()
            return None

        return self._activity

    def is_active(self, activity):
        return self.current() == activity