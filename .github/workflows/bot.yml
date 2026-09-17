name: grass-bot-24-7-instant
on:
  push:
  workflow_dispatch:
  schedule:
    - cron: '*/2 * * * *'

concurrency:
  group: grass-bot-single
  cancel-in-progress: false

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 4
    steps:
      - uses: actions/checkout@v4

      - name: Restore cooldown
        uses: actions/cache/restore@v4
        with:
          path: cooldown.json
          key: cooldown-v14

      - run: pip install requests

      - name: Run V14 VOL-RADAR
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT: ${{ secrets.TELEGRAM_CHAT_ID }}
          PYTHONUNBUFFERED: 1
        run: |
          echo "=== V14 VOL-RADAR ==="
          python -u bot_v14.py --once

      - name: Save cooldown
        uses: actions/cache/save@v4
        if: always()
        with:
          path: cooldown.json
          key: cooldown-v14
