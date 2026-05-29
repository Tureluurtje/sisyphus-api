# models package
# Import model modules relatively so importing the package registers the models
# Legacy PostgreSQL model snapshots are intentionally kept in this folder:
# - auth-postgres.py
# - hours-postgres.py

from api.models import auth  # type: ignore[reportUnusedImport]
