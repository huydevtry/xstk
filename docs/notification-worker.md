# Notification Worker

The web app and notification worker run from the same source checkout and share
the same `.env` file and database.

## Runtime Layout

```text
xstk-web.service
  -> uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1

xstk-notify.service
  -> python scripts/notification_worker.py
```

The FastAPI app only writes notification jobs to the `notification_jobs` table.
The worker polls pending jobs, sends Web Push or Telegram notifications, then
marks each job as sent or schedules a retry.

## Low-Resource Defaults

These defaults are intended for a small production host with limited RAM/CPU:

```env
NOTIFICATION_WORKER_BATCH_SIZE=10
NOTIFICATION_WORKER_CONCURRENCY=3
NOTIFICATION_WORKER_POLL_INTERVAL_SECONDS=2
NOTIFICATION_WORKER_STALE_AFTER_SECONDS=300
```

## Systemd Example

```ini
[Unit]
Description=XSTK notification worker
After=network.target

[Service]
WorkingDirectory=/path/to/xstk
EnvironmentFile=/path/to/xstk/.env
ExecStart=/path/to/xstk/venv/bin/python scripts/notification_worker.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
