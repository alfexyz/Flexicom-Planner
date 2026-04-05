__all__ = ["run_pipeline"]


def __getattr__(name: str):
    if name == "run_pipeline":
        from .pipeline import run_pipeline
        return run_pipeline
    raise AttributeError(name)
