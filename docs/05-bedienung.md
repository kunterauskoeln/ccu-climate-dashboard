# 5 Bedienung

Diese Anleitung beschreibt die Oberfläche für Benutzer. Die Anwendung läuft im Browser
(`http://<server>:3000`) auf Handy, Tablet und PC. Auf dem Handy erscheinen die Kacheln
untereinander, auf Tablet und PC nebeneinander.

## 5.1 Grundprinzipien

- **Kacheln antippen** öffnet Details. Der **Pfeil links oben** in der Kopfleiste führt
  eine Ebene zurück.
- **Bestätigen und Abbrechen:** Bearbeitungsfelder haben unten eine Zeile mit einem
  **Zurück-Pfeil** (links, abbrechen) und einem **Haken** (rechts, übernehmen).
- **Werte kommen von der CCU.** Die Übersicht aktualisiert sich alle 15 Sekunden und
  beim Zurückkehren in die App selbst.
- **Nicht erreichbare Geräte** zeigen „–" statt einer Zahl und im Raumdetail den Hinweis
  „nicht erreichbar".
- **Schreibvorgänge dauern**: Ein Profil zu ändern oder ein Profil zu wechseln geht per
  Funk und kann bis zu einigen Sekunden dauern. Während des Speicherns erscheint eine
  Einblendung; sie wartet, bis das Gerät den neuen Wert bestätigt hat.

## 5.2 Startseite (Raumübersicht)

Eine Kachel je Raum mit:
- Raumname mit Symbol und **Luftfeuchte**,
- **Modus und aktives Profil** (zum Beispiel „Automatik • Standard"),
- **Soll**- und **Ist**-Temperatur,
- **Ventil**: Balken und Prozentzahl der Ventilöffnung. Der Balken ist bei geschlossenem
  Ventil bläulich-grau und wird mit zunehmender Öffnung orange. Bei mehreren Heizkreisen
  eines Raumes gilt der Mittelwert.

Die letzte Kachel öffnet die **Einstellungen**. Antippen einer Raumkachel öffnet das
Raumdetail.

## 5.3 Raumdetail

- **Drehregler** für die Solltemperatur: von 5 bis 30 °C in Schritten von 0,5 °C.
  Der neue Wert wird beim **Loslassen** an die CCU gesendet. Das Setzen einer
  Solltemperatur schaltet den Raum in den Modus *Manuell*.
- **Ventilbalken** wie in der Übersicht.
- **Modus:**

  | Anzeige | Bedeutung |
  |---|---|
  | Automatik | Der Thermostat folgt dem gewählten Wochenprofil |
  | Manuell | Feste Solltemperatur bis zur nächsten Änderung |
  | Urlaub | Party-/Urlaubsmodus des Thermostats (Modus 2) |
  | Boost | Kurzzeitiges Aufheizen (Modus 3) |

- **Profil:** Auswahl des aktiven Wochenprofils (1 bis 6, mit den von dir vergebenen
  Namen). Weichen die gespeicherten Pläne dieses Profils vom Thermostat ab, wird der Plan
  zuerst übertragen und **danach** umgeschaltet (siehe 5.8). Bis dahin zeigt das Feld
  noch das alte Profil, und oben erscheint der Übertragungsbalken.

Fehler beim Speichern (zum Beispiel „Eine Profilübertragung läuft noch") erscheinen als
roter Text unter dem Ventilbalken.

## 5.4 Einstellungen

| Kachel | Zweck |
|---|---|
| **Geräte** | Liste aller angelernten Geräte mit Typ, Adresse und Schnittstelle; ein Tipp zeigt Einzelheiten |
| **Heizprofile** | Wochenprofile aller Räume bearbeiten (5.5) |
| **Änderungshistorie** | Letzte Änderungen an Profilen und Profilnamen ansehen und zurücknehmen (5.9) |
| **Betriebsart** | Umschalten zwischen **Heizen** und **Kühlen**, auch automatisch zu festen Zeitpunkten (5.6) |
| **Abwesenheit** | Alle Räume für eine Zeit auf ein Profil, danach automatisch zurück (5.14) |
| **Ventilverlauf** | Ventilöffnung aller Räume über die letzten Stunden als Grafik (5.15) |
| **Taupunkt** | Kondensgefahr beim Kühlen je Raum (5.13) |
| **Datensicherung** | Export und Import aller Daten der App (5.12) |
| **Design** | Thema und Erhaben-Effekt (5.10) |

## 5.5 Wochenprofile bearbeiten

Jeder Raum hat **6 Profile** (P1 bis P6). Jedes Profil enthält für jeden Wochentag einen
lückenlosen Tagesverlauf aus **Zeitabschnitten** (Start, Ende, Solltemperatur), bis
maximal 13 pro Tag.

**Weg:** *Einstellungen → Heizprofile →* Raum wählen *→* Profil (P1 bis P6 mit Namen)
antippen. Das aktive Profil des Raumes ist hervorgehoben.

### Wohnung: alle Räume auf ein Profil

Die erste Kachel unter *Heizprofile* heißt **Wohnung**. Sie schaltet alle Räume auf
dasselbe Profil um, zum Beispiel alle auf „Urlaub". Hervorgehoben ist ein Profil dort nur,
wenn gerade alle Räume darauf stehen.

1. Profil antippen.
2. Rückfrage „Alle Räume auf … umschalten?" mit **„Ja, alle umschalten"** bestätigen
   (**„Abbrechen"** führt zurück).
3. Die App schaltet die Räume **nacheinander** im Hintergrund um, der Fortschritt steht im
   Übertragungsbalken (5.7).

Dabei gilt dieselbe Regel wie beim Profilwechsel in einem Raum (5.8): Weicht der
gespeicherte Plan des Profils vom Thermostat ab, wird er zuerst übertragen, erst danach
umgeschaltet. Schlägt das fehl, bleibt dieser Raum auf seinem bisherigen Profil, die
anderen werden trotzdem umgeschaltet. Räume, die schon auf dem Profil stehen, werden
übersprungen. Müssten in einem Lauf mehr als 14 Profil-Tage übertragen werden, folgen die
übrigen Räume beim nächsten Tippen.

### Profilseite (zum Beispiel „Ankleide – Standard")

- **Modus (Heizen/Kühlen):** Umschalter oben. Es sind **zwei getrennte Datensätze**
  vorhanden. Der mit „(aktiv)" gekennzeichnete gehört zur gerade laufenden Betriebsart.
  Den **anderen** Modus kannst du jederzeit ansehen und bearbeiten, **ohne umzuschalten**:
  Die Änderung wird nur in der Anwendung gespeichert (schnell, kein Funk) und beim
  nächsten Wechsel der Betriebsart übertragen.
- **Wo das Profil liegt** steht unter dem Umschalter:
  - „**Läuft gerade auf dem Thermostat**“: das Profil, das der Raum in der laufenden
    Betriebsart gerade benutzt. Änderungen gehen direkt auf das Thermostat.
  - „**Gespeicherter Plan, liegt noch nicht auf dem Thermostat**“: alle anderen Profile.
    Angezeigt und bearbeitet wird der Plan, den die App gespeichert hat; Änderungen kosten
    keinen Funk. Auf das Thermostat kommt er, sobald der Raum auf dieses Profil umschaltet
    (Profilwechsel, „Wohnung“, Abwesenheit). Das Thermostat hat nur eine Profiltabelle für
    Heizen und Kühlen zusammen; sein Inhalt für nicht benutzte Profile kann deshalb
    veraltet sein und wird nicht angezeigt.
- **Profil umbenennen:** Name eingeben, Haken tippen. Der Name gilt für dieses Profil in
  **allen** Räumen.
- **Profil kopieren:** Zielraum (auch „Alle anderen Räume") und Zielprofil wählen. Kopiert
  wird der ganze Wochenplan des angezeigten Modus.
- **Sieben Tagesgrafiken** (MO bis SO): Der Verlauf der Solltemperatur über 24 Stunden.
  Die Achse zeigt die Stunden 00 bis 24, die Linien laufen im 5-Minuten-Raster. Ein Tipp
  auf eine Grafik öffnet den Tag.

### Tag bearbeiten

- Die Liste zeigt alle Zeitabschnitte des Tages („06:00 – 09:00, 21 °C").
- **+ Zeitabschnitt hinzufügen:** Start, Ende und Temperatur mit den Rädern einstellen.
  Der neue Abschnitt **überschreibt** den betroffenen Zeitraum; angrenzende Abschnitte
  werden gekürzt, gleiche Nachbarn zusammengefasst. Der Start muss vor dem Ende liegen.
- **Zeitabschnitt ändern oder löschen:** Abschnitt in der Liste antippen. Beim Löschen
  erbt die entstehende Lücke die Temperatur des davor liegenden Abschnitts (am Tagesanfang
  die des folgenden).
- **Tag kopieren nach …:** auf einen anderen Wochentag oder „Alle anderen Tage".

**Zeitrad-Bedienung:** Start und Ende in 5-Minuten-Schritten, Temperatur von 15,0 bis
30,0 °C in 0,5-Schritten. Das Rad einrasten lassen, dann mit dem Haken speichern.

**Speichern dauert:** Beim Profil, das gerade auf dem Thermostat läuft, wird der Tag in
den Thermostat geschrieben und dort **zurückgelesen**. Erst wenn die Werte bestätigt sind, ist der
Vorgang beendet (bis zu etwa 25 Sekunden). Ein Fehler wird angezeigt, dann wurde nichts
Halbes gespeichert.

## 5.6 Betriebsart Heizen/Kühlen

*Einstellungen → Betriebsart →* Heizen oder Kühlen wählen *→* Haken *→* Rückfrage
bestätigen.

Der Haken ist erst aktiv, wenn du die **andere** Betriebsart gewählt hast. Danach fragt die
App ausdrücklich nach: „Wirklich auf Kühlen umschalten?“ mit dem Hinweis, dass alle Räume
betroffen sind, die gespeicherten Pläne übertragen werden und die
Profil-Änderungshistorie gelöscht wird. Erst **„Ja, auf … umschalten“** schaltet um;
**„Abbrechen“** führt zurück zur Auswahl.

Was passiert:
1. Der Aktor (HmIP-FALMOT-C12) wird umgeschaltet. Das gilt für **die ganze Anlage**.
2. Die Anwendung merkt sich das aktive Profil jedes Raums für die alte Betriebsart und
   stellt für die neue das dort zuletzt aktive Profil wieder ein.
3. Im Hintergrund wird der gespeicherte Plan der neuen Betriebsart auf die Thermostate
   geschrieben (nur das **aktive Profil** jedes Raumes, nur abweichende Tage).
   Der Fortschritt steht oben im Übertragungsbalken.

Wichtig:
- Die Übertragung ist **funkschonend**: ein Tag alle 4 Sekunden, höchstens **8 Tage je
  Wechsel**. Was darüber hinausgeht, wird „aufgeschoben" und lässt sich mit **Jetzt
  übertragen** im Balken nachziehen.
- **Vor dem Wechsel** die Solltemperaturen der neuen Betriebsart prüfen. Die Pläne
  übernehmen die Regelung, sobald sie geschrieben sind. Beispiel: Beim Wechsel auf
  **Kühlen** an einem kühlen Tag sollten die Kühlprofile hohe Sollwerte haben, sonst öffnen
  die Ventile.
- **Nicht mehrfach hintereinander umschalten.** Jeder Wechsel belastet den Funk.
- Bei einem Fehler wird der Wechsel der Betriebsart nicht rückgängig gemacht; die
  Übertragung lässt sich wiederholen.

### Automatisch umschalten

In der geöffneten Kachel *Betriebsart* steht unter der Auswahl der Abschnitt
**Automatisch umschalten**:

- ☐ **Auf Kühlen** am Tag/Monat um Stunde:Minute,
- ☐ **Auf Heizen** am Tag/Monat um Stunde:Minute,
- **Zeitplan speichern**.

Jede Richtung hat ihren **eigenen Haken**; du kannst also nur das Umschalten auf Kühlen,
nur das auf Heizen oder beides automatisch machen lassen. Ein angehakter Zeitpunkt gilt
**jedes Jahr**, bis du ihn änderst oder den Haken entfernst. Zum Zeitpunkt schaltet die
App genauso um wie von Hand (alle Schritte oben, inklusive Übertragung und Löschen der
Profil-Änderungshistorie). Steht die Anlage schon auf der Betriebsart, passiert nichts.

- **Beim Speichern wird nicht sofort umgeschaltet**, auch wenn der letzte Zeitpunkt schon
  vorbei ist. Es zählt erst der nächste.
- Wer nach einem automatischen Umschalten **von Hand zurückschaltet**, behält das; die App
  schaltet erst zum nächsten Zeitpunkt wieder.
- **War der Server zum Zeitpunkt aus**, holt die App die Umschaltung nach dem Start nach
  (innerhalb von etwa 30 Sekunden). Waren mehrere Zeitpunkte verpasst, gilt nur der
  letzte.
- Auch ein **nicht angehakter** Zeitpunkt beendet die Saison des anderen. Beispiel: Nur
  „Auf Kühlen am 15.05.“ ist angehakt, „Auf Heizen am 15.09.“ nicht. War der Server von
  April bis Oktober aus, schaltet die App im Oktober **nicht** mehr auf Kühlen, weil der
  15.09. schon vorbei ist.
- Ist die CCU zum Zeitpunkt nicht erreichbar, versucht es die App alle 30 Sekunden erneut.
- Die zugeklappte Kachel zeigt die nächste automatische Umschaltung, die geöffnete auch das
  Ergebnis der letzten („Zuletzt automatisch …“).
- Die Uhrzeiten gelten in deutscher Zeit (Sommer-/Winterzeit wird berücksichtigt),
  unabhängig von der Zeitzone des Servers. Der 29. Februar wird in anderen Jahren zum 28.

## 5.7 Übertragungsbalken

Der Balken oben (auf jeder Seite) zeigt Vorgänge im Hintergrund:

| Anzeige | Bedeutung |
|---|---|
| „Pläne werden übertragen · 3/8" mit Leiste | Ein Wechsel der Betriebsart schreibt Pläne |
| „Wechsel auf Wohnzimmer P2: Plan wird übertragen · 2/5" | Ein Profilwechsel schreibt zuerst den Plan |
| „Änderungen werden zurückgesetzt · 1/3" | Die Änderungshistorie schreibt einen früheren Stand zurück (5.9) |
| „Wohnung: Urlaub: Räume werden umgeschaltet · 2/9" | Alle Räume werden auf ein Profil umgeschaltet (5.5, „Wohnung") |
| „N Fehler bei der Übertragung" (roter Rand) | Mindestens ein Tag konnte nicht geschrieben werden. Die ersten Meldungen stehen darunter |
| „N Profil-Tag(e) stehen noch aus" + **Jetzt übertragen** | Aufgeschobene Tage; der Knopf schreibt die nächsten |
| „Funkauslastung der CCU bei 75 % – angehalten …“ | Die CCU sendet gerade viel. Die App hält die Übertragung an, statt sie ins Funk-Limit laufen zu lassen; der Rest ist aufgeschoben und lässt sich später mit **Jetzt übertragen** nachholen |

Der Balken lässt sich mit **×** ausblenden (gilt für diesen Vorgang; ein neuer Vorgang zeigt
ihn wieder). Solange eine Übertragung läuft, lehnt die Anwendung weitere Wechsel mit dem
Hinweis „Eine Profilübertragung läuft noch – bitte kurz warten" ab.

## 5.8 Profilwechsel im Raum

Wählst du im Raumdetail ein anderes Profil:
- Stimmt sein gespeicherter Plan schon mit dem Thermostat überein, wird **sofort** umgeschaltet.
- Weicht er ab (zum Beispiel nach einem Wechsel der Betriebsart, weil dort nur das aktive
  Profil übertragen wurde), schreibt die Anwendung **zuerst** die abweichenden Tage und
  schaltet **danach** um. So läuft der Thermostat nie mit dem Plan der falschen
  Betriebsart. Schlägt das Schreiben fehl, bleibt das alte Profil aktiv.

## 5.9 Änderungshistorie

*Einstellungen → Änderungshistorie* zeigt die letzten Änderungen, die neueste oben. Jeder
Eintrag nennt Zeitpunkt, Modus (Heizen/Kühlen) oder „Name", Raum und Profil sowie was
geändert wurde, zum Beispiel „Montag: 08:00–08:30 auf 23,5 °C".

**Erfasst werden:**
- Änderungen an Heizprofilen im **aktiven** Modus: Zeitabschnitt setzen oder löschen, Tag
  kopieren, ganzes Profil kopieren (beim Kopieren in einen anderen Raum steht der Eintrag
  beim Zielraum);
- Umbenennungen von Profilen.

**Nicht erfasst werden** Änderungen an gespeicherten Plänen, die nicht auf dem Thermostat
laufen (inaktiver Modus und nicht benutzte Profile), Änderungen ohne Wirkung und
Profilwechsel im Raum.

Wichtig: Gemeint sind mit „aktiv“ jetzt nur noch die Profile, die gerade auf einem
Thermostat laufen.

**Zurücksetzen:** Eintrag antippen, dann mit dem Haken bestätigen. Zurückgenommen werden
dieser Eintrag **und alle neueren**. Die Abfrage nennt, wie viele es sind.
- Profilnamen stehen sofort wieder auf dem alten Namen.
- Profile werden im Hintergrund zurück auf die Thermostate geschrieben (funkschonend,
  höchstens 14 Tage je Lauf); der Fortschritt steht im Übertragungsbalken (5.7).
- Die Einträge verschwinden erst, wenn alles zurück ist. Schlägt etwas fehl oder bleiben
  Tage offen, bleiben sie stehen: Denselben Eintrag einfach erneut zurücksetzen, dann wird
  nur noch der Rest geschrieben.

**Beim Wechsel zwischen Heizen und Kühlen wird die Profil-Änderungshistorie gelöscht, die
Historie der Profil-Umbenennungen bleibt erhalten.** Die gespeicherten Profile selbst
bleiben dabei unverändert; es wird nur das Protokoll geleert, weil seine Einträge zum
anderen Modus gehören. Die Historie hält höchstens 200 Einträge; ältere fallen heraus.

## 5.10 Design

*Einstellungen → Design.* Die Auswahl gilt sofort und wird **im Browser gespeichert**
(pro Gerät); du kannst mehrere Themen nacheinander ansehen und die Seite mit dem
Zurück-Pfeil selbst verlassen.

- **Themen:** Hellblau, Weiß, Dunkel, Sepia, Wald, Sonnenuntergang, Graphit (echtes
  Schwarz, sparsam auf OLED-Displays), Ozean.
- **Erhaben:** **Aus**, **Leicht**, **Stark**. Karten und Schaltflächen erhalten Lichtkante,
  Schatten und leichten Verlauf; Schaltflächen wirken beim Tippen eingedrückt.
- **Glanz:** **Aus** oder **An**. Legt einen Lichtreflex wie auf Glas über Karten und
  Schaltflächen; lässt sich mit jeder Erhaben-Stufe kombinieren.

## 5.11 Geräte

*Einstellungen → Geräte* listet die von der CCU gemeldeten Geräte (ohne die virtuellen
Heizgruppen) mit Name, Typ und Adresse. Ein Tipp öffnet die Einzelansicht. Diese Seite ist
nur eine Auskunft; hier lässt sich nichts ändern. Auf Tablet und PC sind alle Kacheln gleich
hoch.

**Gerätezustand.** Alle 5 Minuten prüft die App die Thermostate und den Aktor: erreichbar,
Batterie (Spannung; die Thermostate melden „schwach“ ab etwa 2,2 V), Funksignal und ob ein
Gerät sein eigenes Funk-Limit erreicht hat. Dazu kommt die **Funkauslastung der CCU**
(Duty Cycle, in Prozent der erlaubten Sendezeit; bei 100 % sendet die CCU eine Weile
nichts mehr).

**Einstellungen nicht übertragen.** Nach jeder Änderung meldet die CCU kurz
„Konfiguration ausstehend“, bis der Thermostat die neuen Daten abgeholt hat; das ist
normal. Dauert es länger als 30 Minuten (`CONFIG_PENDING_WARN_MINUTES`), wird es ein
Hinweis („Arbeitszimmer: Einstellungen seit 3 Tagen nicht übertragen“): Der Thermostat
arbeitet dann noch mit einem älteren Plan, obwohl die App und die CCU den neuen zeigen. Die
Raumkachel in der Übersicht und die Profilseite des Raums warnen zusätzlich. Abhilfe: am
Thermostat kurz die Systemtaste drücken. Hilft das nicht, steckt oft ein ungültiger Wert in
den Einstellungen ([CCU-Hintergrund 8.4](08-ccu-hintergrund.md#84-wochenprofile)).

- Oben auf der Seite stehen die Hinweise und die Funkauslastung; jede Kachel zeigt
  Batteriespannung und Signal, ein Problem in Rot mit gelbem Rand.
- Gibt es Hinweise, erscheint auf jeder Seite ein gelber Balken („Geräte: Bad: Batterie
  schwach (2,2 V)“); ein Tipp öffnet die Geräteseite. Die Kachel *Geräte* in den
  Einstellungen zeigt die Zahl der Hinweise.
- Ab 60 % Funkauslastung erscheint ein Hinweis; ab **70 %** hält die App laufende
  Profilübertragungen an (siehe 5.7).

## 5.12 Datensicherung

*Einstellungen → Datensicherung* öffnet eine eigene Seite mit **Export** und **Import**.

### Export

**Export herunterladen** speichert eine Datei `ccu-export-<datum>.json` mit allen Daten,
die die App selbst hält:

- Heiz- und Kühlprofile aller Räume, samt dem zuletzt aktiven Profil je Betriebsart,
- Profilnamen,
- Ventil-Zuordnung,
- Zeitplan für das automatische Umschalten (beide Zeitpunkte samt Haken),
- Änderungshistorie.

**Nicht enthalten** sind die CCU-Zugangsdaten (`backend/.env`), damit die Datei gefahrlos
weitergegeben oder abgelegt werden kann, und die Daten der CCU selbst.

### Import

1. **Datei auswählen…** und eine Export-Datei wählen.
2. Die Datei wird **vollständig geprüft**, ohne etwas zu verändern: Format und Version,
   jeder Raum, jedes Profil, jeder Tag und jeder Zeitabschnitt (lückenlos 00:00–24:00,
   höchstens 13 Abschnitte, 4,5–30,5 °C), die Profilnamen (1–64 Zeichen) und die
   Ventil-Zuordnung (Kanäle 1–12).
   - **Fehler** werden alle auf einmal mit Fundstelle aufgelistet (zum Beispiel
     „Raum „Bad“, Heizen, P2, Montag: Zeitabschnitte decken 00:00–24:00 nicht lückenlos …“).
     Eine fehlerhafte Datei lässt sich nicht importieren, es wird nichts verändert.
   - **Hinweise** vergleichen die Datei mit den Räumen der CCU: Räume ohne Thermostat,
     und Räume der CCU, für die die Datei keine Profile enthält (deren gespeicherte
     Profile würden entfernt).
3. **Import übernehmen** ersetzt dann
   - die Heiz- und Kühlprofile aller Räume samt aktivem Profil je Betriebsart,
   - die Profilnamen,
   - die Ventil-Zuordnung,
   - den Zeitplan für das automatische Umschalten. Wie beim Speichern von Hand zählt
     erst der nächste Zeitpunkt; ein Import schaltet also nie selbst um. Enthält die
     Datei keinen gesetzten Zeitplan, wird der bestehende entfernt. Ältere Exporte ohne
     Zeitplan lassen ihn unverändert (Hinweis bei der Prüfung).

   und **löscht die Änderungshistorie** (ihre Vorher-Stände passen nicht mehr). Die
   Änderungshistorie aus der Datei wird nicht übernommen.
4. Vorher legt die App den bisherigen Stand als `vor-import-<datum-uhrzeit>.json` im
   Datenordner `data/` ab (gleiches Format wie ein Export). Damit lässt sich ein Import
   rückgängig machen, indem man diese Datei importiert.
5. Danach werden die Pläne der **aktiven Betriebsart** im Hintergrund auf die Thermostate
   übertragen, wie nach einem Wechsel der Betriebsart (Fortschritt im Übertragungsbalken,
   gebremst, höchstens 8 Tage je Lauf; der Rest über „Jetzt übertragen“). Die Pläne der
   inaktiven Betriebsart werden nur gespeichert.

Während eine Profilübertragung läuft, ist kein Import möglich (Meldung „bitte kurz
warten“).

### Gespeicherte Sicherungen

Jede Nacht ab **03:00** legt die App selbst eine Sicherung an (gleicher Inhalt wie ein
Export) und behält die **letzten 14**. War der Server um 03:00 aus, wird die Sicherung des
Tages beim nächsten Start nachgeholt. Die Kachel *Gespeicherte Sicherungen* listet sie,
dazu die Kopien, die vor jedem Import entstehen:

- **Herunterladen** speichert die Datei auf dem Gerät, mit dem du die App bedienst.
- **Einspielen…** lädt die Sicherung in den Import: dieselbe vollständige Prüfung, dann
  „Import übernehmen“ oder „Abbrechen“ (siehe oben).
- **Jetzt sichern** legt die Sicherung des heutigen Tages sofort an (ersetzt eine schon
  vorhandene von heute), zum Beispiel vor größeren Änderungen.

Die Dateien liegen auf dem Server in `data/backups/`. Sie schützen vor Bedienfehlern,
nicht vor einem Ausfall des Servers; dafür gehört eine Kopie auf einen anderen Rechner
(siehe [Betrieb 4.3](04-betrieb-und-wartung.md#43-datensicherung)).

## 5.13 Taupunkt

Beim **Kühlen** über den Fußboden darf keine Fläche kälter werden als der Taupunkt der
Raumluft, sonst bildet sich Kondenswasser. Die App rechnet den Taupunkt jedes Raums aus
Temperatur und Luftfeuchte des Thermostats aus und vergleicht ihn mit der
**Vorlauftemperatur** des Kühlwassers, die ein Sensor per MQTT liefert
(Einrichtung: [Konfiguration 3.1](03-konfiguration.md#31-backendenv)). Der Vorlauf ist
die kälteste Stelle; der Vergleich ist damit auf der sicheren Seite.

*Einstellungen → Taupunkt* zeigt oben die Gesamtlage und den verwendeten Vorlaufwert,
darunter je Raum eine Kachel. Im Kühlbetrieb enthält sie **Bewertung**, Taupunkt und
**Abstand zum Vorlauf**:

| Anzeige | Bedeutung |
|---|---|
| **ok** (grün) | Abstand mindestens 3 K |
| **knapp** (gelb) | Abstand zwischen 1 und 3 K |
| **Kondensgefahr** (rot) | Abstand unter 1 K oder der Vorlauf ist schon kälter als der Taupunkt |
| **Ventil zu** | Der Raum bekommt gerade kein Kühlwasser, also keine Gefahr |
| **unbekannt** | Kein Sensor eingerichtet, noch kein gültiger Vorlaufwert, oder Temperatur/Feuchte fehlen |


Im **Heizbetrieb** besteht keine Kondensgefahr: Die Kacheln zeigen dann nur Taupunkt und
Raumwerte, ohne Bewertung und Abstand; oben steht der aktuelle Sensorwert. Vorlaufwerte
aus dem Heizbetrieb werden nie als Vergleichswert verwendet.

Bei **knapp** oder **Kondensgefahr** erscheint oben auf jeder Seite ein Warnbalken; ein
Tipp darauf öffnet die Übersicht. Er verschwindet von selbst, sobald der Abstand wieder
reicht. Im Raumdetail steht der Taupunkt unter dem Raumnamen. Die Werte werden jede
Minute aktualisiert.

**Der Vorlauf-Sensor misst nur bei Durchfluss richtig.** Er sitzt in einem warmen Raum;
sind alle Ventile zu, erwärmt sich das Rohr und der Messwert ist zu hoch. Die App nimmt
den Messwert deshalb erst, wenn seit mindestens **10 Minuten** ein Ventil offen ist. Bis
dahin verwendet sie den letzten Wert, der unter Durchfluss gemessen wurde (höchstens zwei
Tage alt). Welcher Wert gerade gilt, steht auf der Taupunkt-Seite („aktueller Messwert“
oder „letzter gültiger Wert“).

**Die App warnt nur, sie greift nicht ein.** Sie ist eine Überwachung, kein Schutzgerät:
Fällt der Server aus, warnt sie nicht. Den zuverlässigen Schutz bietet ein
Taupunktwächter am Kühlvorlauf, der am Aktor die Kühlung sperrt (der HmIP-FALMOT-C12
meldet dafür den Zustand `HUMIDITY_ALARM`).

## 5.14 Abwesenheit

Für Urlaub oder längere Abwesenheit: alle Räume laufen für eine Zeit auf **einem**
Profil (zum Beispiel „Urlaub“); zum Ende bekommt **jeder Raum automatisch das Profil
zurück, das er vorher hatte**.

*Einstellungen → Abwesenheit*:

1. **Profil für alle Räume** wählen.
2. **Beginn**: *sofort* oder *am* mit Datum und Uhrzeit (zum Beispiel Abfahrt am Samstag
   08:00).
3. **Ende** mit Datum und Uhrzeit. Wer vor der Rückkehr schon warme Räume möchte, setzt
   das Ende entsprechend früher.
4. **Abwesenheit planen**.

Was passiert:
- **Zum Beginn** merkt sich die App das aktive Profil jedes Raums und schaltet alle Räume
  um, wie bei „Wohnung“: Raum für Raum im Hintergrund, mit Übertragung des Plans, falls
  nötig (Fortschritt im Übertragungsbalken).
- **Während der Abwesenheit** greift die App nicht mehr ein. Schaltest du einen Raum von
  Hand um, bleibt das so bis zum Ende.
- **Zum Ende** geht jeder Raum auf sein gemerktes Profil zurück. Danach steht auf der
  Seite „Letzte Abwesenheit beendet“.
- Konnte ein Raum nicht umgeschaltet werden, versucht es die App noch zweimal und meldet
  ihn dann auf der Seite. Läuft gerade eine andere Übertragung, wartet sie.
- **War der Server zum Beginn oder Ende aus**, wird das beim nächsten Start nachgeholt.
  Sind Beginn und Ende beide verpasst, endet die Abwesenheit ohne Umschalten.

**Ändern:** Eine geplante Abwesenheit lässt sich ändern oder mit **Planung verwerfen**
löschen. Bei einer laufenden lassen sich Ende und Profil ändern (ein neues Profil wird
gleich umgeschaltet); **Jetzt zurückkehren…** beendet sie nach Rückfrage sofort.

Die Kachel *Abwesenheit* in den Einstellungen zeigt „Geplant ab …“, „Aktiv bis …“ oder
„Zuletzt beendet am …“; Einzelheiten stehen auf der Seite, die ein Tipp darauf öffnet.
In Home Assistant gibt es dazu `binary_sensor.ccu_dashboard_abwesenheit` und
`sensor.ccu_dashboard_abwesenheit_bis`.

Hinweis: Wird während der Abwesenheit zwischen Heizen und Kühlen umgeschaltet (von Hand
oder automatisch), gehen die Räume zum Ende trotzdem auf ihr gemerktes Profil zurück.

## 5.15 Ventilverlauf

*Einstellungen → Ventilverlauf* zeigt, wie weit die Ventile der Räume in den letzten
Stunden geöffnet waren: eine farbige Linie je Raum, die x-Achse ist die Zeit, die y-Achse
die Öffnung von 0 bis 100 %. Bei Räumen mit mehreren Heizkreisen (zum Beispiel Wohnzimmer)
ist es der Mittelwert.

- Oben wählst du den Zeitraum: **12 h, 24 h, 48 h** (Standard) oder **72 h**.
- Ein Tipp auf einen Raum in der **Legende** blendet seine Linie aus oder wieder ein, um
  einzelne Räume besser zu sehen.
- Fährst du mit der Maus oder dem Finger über die Grafik, stehen die Werte aller Räume zu
  diesem Zeitpunkt daneben.
- Die App zeichnet alle 5 Minuten auf und behält 3 Tage. Lief die App eine Zeit lang
  nicht, haben die Linien dort eine **Lücke**. Nach der Installation dauert es also eine
  Weile, bis die Grafik gefüllt ist.

Lesen lässt sich daraus zum Beispiel, wann ein Raum tatsächlich heizt, ob ein Profil zu
früh oder zu spät vorheizt, oder ob ein Raum ständig voll aufgedreht ist (Hinweis auf
zu hohe Solltemperatur oder einen schwachen Heizkreis).
