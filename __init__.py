def __getattr__(name):
    if name == "MessageRecorder":
        from .main import MessageRecorder
        return MessageRecorder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
