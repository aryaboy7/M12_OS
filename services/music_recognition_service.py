class MusicRecognitionService:
    """
    Identifies music captured by M12.

    Audio capture and recognition providers are intentionally kept
    separate from the Music Recognition skill.
    """

    def __init__(self):
        self.provider = "audd"

    def recognize(self):
        """
        Recognize music currently audible to M12.

        Audio capture and AudD integration will be added after
        skill routing has been verified.
        """
        return {
            "success": False,
            "status": "not_configured",
            "title": "",
            "artist": "",
            "album": "",
            "provider": self.provider,
        }
