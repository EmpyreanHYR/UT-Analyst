# UT-Analyst Upgrade and Rollback

## Before Upgrade

1. Close the application.
2. Copy the complete `data/` directory to a backup location.
3. Record the current Git commit or release version.

## Database Migration

The application applies schema migrations on startup. Version 1 databases are
migrated in place to version 2 by adding report signature fields. Existing
sessions, defects, frame chunks, and reports are retained.

If migration fails, restore the backed-up `data/` directory before starting the
previous application version.

## Verify Upgrade

```powershell
python -m pytest -q
python -m compileall -q app tests main.py
```

Open a saved session, replay at least one frame, export a report, and verify the
report appears in the session report list.

## Rollback

1. Stop the application.
2. Restore the previous application version.
3. Replace `data/` with the pre-upgrade backup.
4. Start the previous version and verify a saved session can be opened.
