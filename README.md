# parkrun event monitor

Checks the [official event feed](https://images.parkrun.com/events.json) at **08:00 every day**, plus **hourly from Friday 18:00 through Saturday 08:00**, in **Europe/London** time (GMT/BST automatically). Saturday 08:00 runs only once. GitHub may delay scheduled runs; these are requested times, not guaranteed delivery times.

## First run

1. In **Settings → Secrets and variables → Actions → Secrets**, add repository secrets `SMTP_USER` and `SMTP_APP_PASSWORD` (a Gmail app password). Never commit their values.
2. Open **Actions → Check for new parkruns → Run workflow**, use branch `main`, and tick **Allow first baseline if no snapshot exists** for the first run.
3. Confirm the run is green and `data/events_snapshot.json` exists on `main`. The run authenticates to Gmail, reads the feed and commits a baseline without emailing historical events. It sends no test email. Later runs need no initialization option.

Alerts go to `djeffery92@gmail.com`. Change `ALERT_EMAIL` in the workflow to change the destination. The workflow explicitly requests `contents: write` to commit its snapshot; no extra token is needed. If repository/organization policy blocks writes, the persistence step fails visibly; allow workflow writes or adjust the applicable branch rule before rerunning.

## Comparison and persistence

- `data/events_snapshot.json` holds **all IDs ever successfully processed**, including IDs later removed from the feed. Renaming, editing or reintroducing an existing ID never causes another alert.
- A new ID triggers one email listing its name, available location/country, coordinates and event link. Unchanged checks send nothing.
- Missing state fails closed unless initialization is explicitly selected. Invalid state, failed fetches, empty/very small feeds and failed email delivery never replace the last good snapshot.
- Runs are serialized, always check out current `main`, and commit successful state back to `main`. Snapshot writes are atomic locally; pushes retry after rebasing. A failed run preserves a snapshot artifact for up to 90 days when state is available.
- Gmail authentication is checked on every run without printing credentials. Actual inbox delivery is verified only when a real new-ID alert arrives.

SMTP delivery and Git commits are separate operations. If an email is accepted but the runner stops or the snapshot push fails, a retry can resend it. If persistence fails **after sending an alert**, recover that run's `parkrun-snapshot-recovery-*` artifact to `data/events_snapshot.json` on `main` before rerunning. If failure occurs after SMTP acceptance but before the updated file is written, reconcile the emailed IDs manually. Exactly-once email delivery cannot be guaranteed by SMTP.

## Maintenance

Monitor failed-run notifications and the Actions page periodically. GitHub can disable scheduled workflows in public repositories after 60 days without activity. Snapshot commits provide regular repository activity when checks succeed, but verify the workflow remains enabled.

Run the regression checks locally with `python -m unittest discover -s tests -v`. They cover initial baseline, new/renamed/returning IDs, failed fetch/email, invalid state, incomplete feeds and UK summer/winter schedules.
