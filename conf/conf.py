from typing import Dict, List


class Conf:
    def __init__(self, greentick_id: int = None, redtick_id: int = None, plugins: List[str] = None,
                 imgur_keys: Dict[str, str] = None, trusted: List[int] = None):
        self.greentick_id = greentick_id
        self.redtick_id = redtick_id
        self.plugins = plugins

        self.imgur_keys = imgur_keys

        # TODO: do stuff with this
        if trusted is not None:
            self.trusted = trusted
        else:
            self.trusted = []
