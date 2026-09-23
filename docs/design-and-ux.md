# Oberfläche

Referenz: https://www.fabricerio.com/

- Hintergrund `#f4f4f4`, schwarze Schrift, graue Rahmen.
- Sora Regular für Überschriften, IBM Plex Sans für Bedienelemente.
- Schriften unter `frontend/fonts/`, inklusive OFL-Lizenzen.
- Bootstrap 5.3.8 als lokale Basis für Formularfelder und Schaltflächen.
- Eine Seite: Foto-Upload, Plattformwahl, Editor.
- Konten sowie Artikelanalyse und Preisvergleich sind aufklappbar.
- Keine Sidebar, Fortschrittsleiste, Werbetexte, Illustrationen oder Infokarten.

## Verhalten

Dateiprüfung, Tastaturbedienung, Klartexteditor mit eBay-Formatierung,
Eingabevalidierung und Schutz vor doppelter Veröffentlichung bleiben erhalten.
Entwürfe werden im Sitzungsspeicher des Tabs gespeichert. Nach einem Neuladen
sind die Originalfotos weiter im Backend vorhanden, aber ihre lokalen
Vorschaubilder nicht mehr verfügbar. Das Schließen des Tabs kann den Entwurf
verwerfen.

Die API-Verträge und Backend-Funktionen sind unverändert. Browserprüfungen
verwenden simulierte Antworten und veröffentlichen keine echten Anzeigen.
Die Regressionstests stehen in `tests/test_frontend.py`.
