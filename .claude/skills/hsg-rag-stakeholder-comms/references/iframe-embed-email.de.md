# Proven iframe-embed e-mail to the EMBA web team (German)

This is the exact e-mail sent to the web team on 2026-07-07 (proven format —
send it as-is). Placeholders to fill in before sending: `[Name]` (recipient)
and the sign-off (sign with the maintainer's name, never as an AI). If the
snippet or the allowed embedding domains change, update `deploy/Caddyfile`
first (via `hsg-rag-change-control`) and mirror the change here in the same PR.

The full e-mail text (verbatim):

```text
Betreff: Einbettung EMBA-Chatbot auf emba.unisg.ch — Schritt-für-Schritt-Anleitung

Hallo [Name],

der Chatbot für die EMBA-Website ist live und erreichbar unter https://chatbot.emba.unisg.ch (DNS und TLS-Zertifikat sind bereits eingerichtet, da musst du nichts tun). Damit er auf der Website erscheint, muss er nur noch als iframe eingebettet werden. Hier die genaue Anleitung:

Schritt 1 — Seite auswählen
Öffne im WordPress-Backend die Seite, auf welcher der Chatbot erscheinen soll (zunächst gerne eine nicht verlinkte Testseite, z. B. emba.unisg.ch/chatbot-test). Wichtig: Die Seite muss unter emba.unisg.ch (bzw. einer anderen *.unisg.ch- oder embax.ch-Adresse) und über HTTPS laufen — auf anderen Domains (z. B. Staging-Umgebungen des Hosters) blockiert der Browser die Einbettung aus Sicherheitsgründen.

Schritt 2 — HTML-Block einfügen
Füge im Gutenberg-Editor an der gewünschten Stelle einen Block vom Typ „Individuelles HTML" / „Custom HTML" ein und kopiere exakt diesen Code hinein:

<iframe
  src="https://chatbot.emba.unisg.ch"
  title="EMBA HSG Chatbot"
  style="width:100%; height:800px; border:none;"
  loading="lazy"
  allow="clipboard-write"
></iframe>

Bitte den Code nicht verändern, insbesondere kein sandbox-Attribut ergänzen (das würde den Chat und das eingebaute Terminbuchungs-Widget brechen). Die Höhe (800 px) kann bei Bedarf angepasst werden, sollte aber mindestens 650 px betragen.

Schritt 3 — Speichern und veröffentlichen
Seite speichern/veröffentlichen. Es sind keine Plugins, Skripte, Cookies oder API-Schlüssel nötig — der eine iframe ist alles. Auch am Cookie-Banner der Website muss nichts geändert werden: Der Chatbot holt die Datenschutz-Einwilligung selbst innerhalb des Fensters ein, bevor ein Chat möglich ist.

Schritt 4 — Funktionstest
1. Seite im Browser aufrufen (idealerweise einmal auch in einem privaten Fenster).
2. Im Chatbot-Fenster erscheint zuerst ein Datenschutzhinweis → auf „Akzeptieren" klicken.
3. Testfrage stellen, z. B. „Was kostet der EMBA?" → es muss eine inhaltliche Antwort kommen.
4. Danach schreiben: „Ich möchte einen Beratungstermin vereinbaren." → unterhalb des Chats muss ein aufklappbares Terminbuchungs-Widget erscheinen.
5. Einmal oben die Sprache auf English umstellen und eine Frage auf Englisch stellen.

Falls der Frame leer bleibt:
Browser-Konsole öffnen (F12 → „Konsole"). Steht dort eine Meldung mit „frame-ancestors" oder „X-Frame-Options", läuft die Seite nicht unter einer freigegebenen Domain — in dem Fall schick mir bitte die genaue URL der Testseite, dann schalten wir sie serverseitig frei. Bei allen anderen Problemen: Screenshot der Konsole + URL an mich.

Gib mir bitte kurz Bescheid, sobald die Testseite steht — ich prüfe dann von unserer Seite noch einmal alles durch, bevor der Chatbot auf die richtige Seite kommt.

Vielen Dank und viele Grüße
```
