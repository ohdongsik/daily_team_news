# daily_team_news

Google Chat webhook bot that sends a weekday 09:40 KST IT trend briefing card.

## What it sends

- ZDNet Korea 4 items
- ITWorld Korea 4 items
- TechCrunch 1 item
- The Verge 1 item
- Hacker News 1 item
- Brunch IT 트렌드 updates up to 5 items when there are same-day updates

## Schedule

- Weekdays at 09:40 KST
- GitHub Actions cron uses `00:40 UTC`

## Required secret

Set this repository secret before enabling the schedule:

- `GOOGLE_CHAT_WEBHOOK_URL`

## Manual run

You can trigger the workflow from the GitHub Actions tab with `workflow_dispatch`.
