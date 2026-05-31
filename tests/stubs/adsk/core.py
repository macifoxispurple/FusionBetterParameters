# Stub for adsk.core — covers all surfaces used by BetterParameters.py at
# import time (class bases, enum constants) and in tested functions.


class _Sentinel:
    """Generic sentinel for enum-like constants."""
    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return f"<adsk.core.{self._name}>"


# --------------------------------------------------------------------------
# Event handler base classes (used as bases for handler classes defined in
# the module body — must be importable, need no real implementation).
# --------------------------------------------------------------------------

class CommandCreatedEventHandler:
    pass


class CommandEventHandler:
    pass


class DocumentEventHandler:
    pass


class HTMLEventHandler:
    pass


class UserInterfaceGeneralEventHandler:
    pass


class ApplicationCommandEventHandler:
    pass


# --------------------------------------------------------------------------
# Cast helpers
# --------------------------------------------------------------------------

class Application:
    @staticmethod
    def cast(obj):
        return obj

    @staticmethod
    def get():
        return None


class UserInterface:
    @staticmethod
    def cast(obj):
        return obj


class HTMLEventArgs:
    @staticmethod
    def cast(obj):
        return obj


# --------------------------------------------------------------------------
# ValueInput
# --------------------------------------------------------------------------

class ValueInput:
    def __init__(self, s=""):
        self._str = s

    @staticmethod
    def createByString(s):
        return ValueInput(str(s or ""))

    def __repr__(self):
        return f"ValueInput({self._str!r})"


# --------------------------------------------------------------------------
# Dialog results
# --------------------------------------------------------------------------

class DialogResults:
    DialogOK = 0
    DialogCancel = 1
    DialogError = 2


# --------------------------------------------------------------------------
# Enum-like constants
# --------------------------------------------------------------------------

class BooleanOptions:
    DefaultBooleanOption = _Sentinel("BooleanOptions.DefaultBooleanOption")


class UserInterfaceThemes:
    DarkUserInterfaceTheme = _Sentinel("UserInterfaceThemes.DarkUserInterfaceTheme")
    LightUserInterfaceTheme = _Sentinel("UserInterfaceThemes.LightUserInterfaceTheme")
