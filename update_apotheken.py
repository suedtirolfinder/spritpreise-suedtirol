name: Apotheken-Notdienst aktualisieren

on:
  schedule:
    - cron: "15 3 * * *"   # taeglich ca. 05:15 Uhr Suedtirol-Zeit
    - cron: "15 12 * * *"  # zweite Pruefung mittags, falls das Land nachtraeglich aendert
  workflow_dispatch:        # zum manuellen Starten

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Daten holen
        run: python update_apotheken.py
      - name: Aenderungen speichern
        run: |
          git config user.name "github-actions"
          git config user.email "actions@users.noreply.github.com"
          git add apotheken_turnus.json
          git diff --cached --quiet || (git commit -m "Apotheken-Notdienst aktualisiert" && git push)
