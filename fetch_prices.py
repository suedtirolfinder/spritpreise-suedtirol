name: Tägliche Spritpreis-Aktualisierung

on:
  schedule:
    - cron: '0 6 * * *'  # Täglich um 06:00 UTC (08:00 MEZ)
  workflow_dispatch:      # Erlaubt manuellen Start

jobs:
  update-data:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Code auschecken
        uses: actions/checkout@v4

      - name: Python einrichten
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Preise abrufen und verarbeiten
        run: python fetch_prices.py

      - name: Änderungen committen und pushen
        run: |
          git config --global user.name "GitHub Action"
          git config --global user.email "action@github.com"
          git add spritpreise_bz.json
          git diff --quiet && git diff --staged --quiet || (git commit -m "Automatisches Update der Spritpreise" && git push)
