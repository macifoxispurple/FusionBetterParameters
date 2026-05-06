# Stub for adsk.fusion — covers all surfaces used by BetterParameters.py.


class ObjectCollection:
    """Minimal stub for adsk.core.ObjectCollection — iterable, not a list/tuple."""

    def __init__(self, items=None):
        self._items = list(items) if items else []

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    @property
    def count(self):
        return len(self._items)


class Design:
    @staticmethod
    def cast(obj):
        return obj


class ModelParameter:
    def __init__(self):
        self.name = ""
        self.expression = ""
        self.unit = ""
        self.comment = ""
        self.isFavorite = False

    @staticmethod
    def cast(obj):
        if isinstance(obj, ModelParameter):
            return obj
        return None


class UserParameter:
    def __init__(self):
        self.name = ""
        self.expression = ""
        self.unit = ""
        self.comment = ""
        self.isFavorite = False

    @staticmethod
    def cast(obj):
        if isinstance(obj, UserParameter):
            return obj
        return None
