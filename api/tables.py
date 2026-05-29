from importlib import import_module
import pkgutil
import importlib
import sys
from types import ModuleType

# Import models package dynamically to allow running this file as a script
try:
    # When imported as a package submodule, import models relative to the package name
    if __package__:
        models_pkg = importlib.import_module(f"{__package__}.models")
        from api.database import Base, engine
    else:
        # When executed as a script (module has no package), use absolute import after ensuring cwd is on sys.path
        sys.path.insert(0, ".")
        models_pkg = importlib.import_module("api.models")
        from api.database import Base, engine
except Exception:
    # Final fallback when imports fail
    sys.path.insert(0, ".")
    models_pkg = importlib.import_module(name="api.models")
    from api.database import Base, engine


def import_all_models(package: ModuleType) -> None:
    # Iterate over all modules in the package and import them so SQLAlchemy's Base
    # picks up all model classes defined in those modules.
    package_name = package.__name__
    for _, name, _ in pkgutil.iter_modules(path=package.__path__):
        if not name.startswith("__"):
            import_module(name=f"{package_name}.{name}")


if __name__ == "__main__":
    print("Importing model modules...")
    import_all_models(package=models_pkg)
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Done!")
