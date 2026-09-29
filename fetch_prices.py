name: Tägliche Spritpreis-Aktualisierung

on:
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:

jobs:
  update-data:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Run Script
        run: python fetch_prices.py

      - name: Commit and Push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add spritpreise_bz.json
          git commit -m "Update Spritpreise" || echo "Keine Änderungen"
          git push
