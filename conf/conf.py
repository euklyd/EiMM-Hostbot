class Conf:
    def __init__(
        self,
        greentick_id: int = None,
        redtick_id: int = None,
        boostemoji_id: int = None,
        waitemoji_id: int = None,
        imgur_keys: dict[str, str] = None,
        trusted: list[int] = None,
        google_email: str = None,
    ):
        self.greentick_id = greentick_id
        self.redtick_id = redtick_id
        self.boostemoji_id = boostemoji_id
        self.waitemoji_id = waitemoji_id

        self.imgur_keys = imgur_keys

        self.google_email = google_email

        # TODO: do stuff with this
        if trusted is not None:
            self.trusted = trusted
        else:
            self.trusted = []
