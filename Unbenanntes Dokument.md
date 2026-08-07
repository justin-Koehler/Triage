# **FACHKONZEPT**

## **AI Change-Management & Jira Intake System**

*„Simplicity is the ultimate sophistication.“* — Leonardo da Vinci

### **1\. Vision & Das Problem mit Komplexität**

#### **Der Status Quo**

Aktuell werden Ideen, Change-Requests und IT-Fehler in unübersichtlichen Excel-Tabellen verwaltet. Das Ergebnis ist vorhersehbar:

* **Frustration:** Die Hürde, ein Anliegen einzureichen, ist unnötig hoch.  
* **Datenmüll:** Unvollständige Angaben, fehlender Kontext, keine saubere Kategorisierung.  
* **Zeitverschwendung:** Dutzende E-Mails und Nachfragen, bevor ein Entwickler überhaupt mit der Arbeit beginnen kann.

#### **Die Lösung**

Ein intelligentes, dialogbasiertes Intake-System. Keine Formulare. Keine Excel-Tabellen. Keine Jira-Vorkenntnisse erforderlich.

Der Nutzer beschreibt sein Anliegen in natürlicher Sprache (Text oder Voice). Die KI versteht den Kontext, nimmt die automatische Triage vor, erfragt **ausschließlich** fehlende Schlüsselinformationen und erstellt ein zu 100 % strukturiertes, valides Ticket in Jira.

### **2\. Die drei Grundprinzipien**

**1\. Radikale Einfachheit für den Nutzer**  
Ein einziges Eingabefeld. Keine 15 Dropdowns. Wenn die KI etwas wissen muss, fragt sie gezielt nach  
**2\. Strenge Struktur für das Entwicklerteam**  
Am Ende steht immer ein perfekt klassifiziertes und priorisiertes Jira-Ticket mit allen nötigen technischen Details.  
**3\. Respekt vor der Zeit**  
Maximal zwei kurze Nachfragen. In weniger als 30 Sekunden ist das Ticket angelegt.

### **3\. Scope & Fokus**

Fokus bedeutet, zu Hunderten von guten Ideen *Nein* zu sagen, um sich auf das Wesentliche zu konzentrieren.

#### **In-Scope (Was das System exzellent beherrscht)**

* Erfassung von Freitext- und Spracheingaben.  
* Automatische Erkennung des Anliegens (Bug, Change Request, Support, Projekt-Idee).  
* Dynamische Nachforderung fehlender Pflichtdaten (Smart Inquiry Loop).  
* Vollautomatische Erstellung von Jira-Tickets über die REST API v3.  
* Automatische Duplikatsprüfung vor dem Anlegen.


### **4\. Der Nutzer-Prozess (The User Journey)**

Der gesamte Ablauf erfolgt in vier nahtlosen Schritten:

```css
[ 1. Dialog ] ──► [ 2. Auto-Triage ] ──► [ 3. Smart Inquiry ] ──► [ 4. Jira Sync ]

```

#### **Die Schritte im Detail**

**Schritt 1: Der Einstieg**  
Der Nutzer öffnet das Interface und tippt (oder spricht) sein Anliegen frei heraus:  
*„Der Login auf der Staging-Umgebung wirft seit heute Morgen einen 500er Fehler, wenn man sich mit Google anmelden will.“*

**Schritt 2: Auto-Triage & Extraktion**  
Die KI analysiert die Eingabe im Hintergrund gegen das hinterlegte Jira-Schema:  
Anliegen-Typ: Bug / Störung  
Komponente: Authentication / Staging  
Priorität: High (Blocker für Staging-Tests)  
Erkannte Daten: Google Login, Status 500\.

**Schritt 3: Smart Inquiry (Die verfeinernde Rückfrage)**  
Fehlt eine kritische Information (z. B. der verwendete Browser), stellt die KI **eine** präzise Frage:  
*„Welcher Browser wurde verwendet und betrifft das alle Test-Accounts?“*  
**Schritt 4: Bestätigung & Jira-Creation**  
Der Nutzer antwortet kurz (*„Chrome, alle @company.com Accounts“*). Die KI zeigt eine kompakte Zusammenfassung und legt das Ticket direkt per API in Jira an.

### **5\. Triage- & Mapping-Matrix**

| Signale im Freitext | Erkannter Issue Type | Pflichtfelder für KI-Rückfrage | Standard Priority |
| :---- | :---- | :---- | :---- |
| *„Fehler“*, *„Absturz“*, *„geht nicht“*, *„500“*, *„Bug“* | **Bug / Störung** | Betroffenes System/Environment, Schritte zur Reproduktion | High / Critical |
| *„Ich wünsche mir“*, *„Wäre cool wenn“*, *„Change“* | **Change Request / Feature** | Fachlicher Nutzen (Business Value), Zielgruppe | Medium |
| *„Wie geht...“*, *„Zugang beantragen“*, *„Hilfe“* | **Support / Service Request** | Betroffenes Modul, Dringlichkeit | Low / Medium |
| *„Idee für neues Projekt“*, *„Initiative“* | **Project Proposal (Wizard)** | Problemstellung, Erwarteter ROI, Risiken | Medium |

### **6\. Tone of Voice & KI-Verhaltensregeln**

**Direkt & klar:** Keine Floskeln (*„Hallo\! Wie kann ich dir heute helfen?“* ist verboten).  
**Fokussiert:** Es stellt immer nur **eine** Frage auf einmal.  
**Effizient:** Maximal 2 Fragen-Loops. Sind danach noch Felder offen, wird das Ticket mit der Kennzeichnung \[Triage unvollständig\] angelegt.  
**Kein Halbwissen:** Wenn das Anliegen unklar ist, fordert die KI den Nutzer auf, das Problem in eigenen Worten neu zu beschreiben.

### **7\. Nicht-funktionale Qualitäts-Standards**

**Geschwindigkeit:** Antwortzeit der KI unter 1,5 Sekunden pro Dialogschritt. Total-Time-to-Ticket unter 30 Sekunden.  
**Datenschutz & Security:** Keine Speicherung von Prompts oder Nutzerdaten im Modell-Training (Zero Data Retention / Enterprise Privacy API).  
**Usability:** 0 Minuten Schulungsaufwand. Wer eine Chat-Nachricht schreiben kann, kann dieses System bedienen.

### **8\. Abnahmekriterien & Test-Szenarien**

Das System gilt als fachlich abnahmebereit, wenn mindestens 9 von 10 Test-Prompts im First-Pass fehlerfrei klassifiziert und in Jira angelegt werden:

1. **Test-Case 1 (Vager Bug):** *„Das Login geht nicht mehr*  
2. $\\rightarrow$ *Erwartung:* KI erkennt Bug, fragt nach System/Umgebung und Fehlermeldung.  
3. **Test-Case 2 (Kompakter Change Request):** *„Wir brauchen im Dashboard einen Export-Button als CSV für die Monatsberichte.“*  
4. $\\rightarrow$ *Erwartung:* KI erkennt Feature Request, zieht Nutzen & Zielgruppe heraus, legt Ticket mit Prio Medium an.  
5. **Test-Case 3 (Projekt-Idee / Wizard):** *„Ich habe eine Idee für ein neues KI-Tool zur Automatisierung der Lieferanten-Rechnungen.“*  
6. $\\rightarrow$ *Erwartung:* KI startet den Projekt-Wizard und fragt nach Problemstellung und Risiken.