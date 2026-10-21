# XAverius Protocol Specification

**Version:** 0.1 — konsolidierter Arbeitsentwurf  
**Status:** Designentwurf; Wire-Protocol und Registries noch nicht vollständig eingefroren  
**Transport:** X11 Extension  
**Backend:** Vulkan  
**Initiale Implementierung:** Xvfb, Compute-only  
**Zielsprache der Spezifikation:** Englisch für die technische Norm; Erläuterungen können Deutsch sein.

---

## 0. Status und normative Sprache

Diese Spezifikation konsolidiert die bisher erarbeiteten XAverius-Entscheidungen.

Die Schlüsselwörter **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** und **MAY** bezeichnen normative Anforderungen.

Es gelten drei Statusklassen:

- **Festgelegt:** Als Designentscheidung beschlossen.
- **Entwurfsregel:** Vorgeschlagene Regel, die noch gegen die vollständige Vulkan- und X11-Semantik geprüft werden muss.
- **Offen:** Muss vor einem stabilen Wire-Protocol-Release entschieden werden.

Ein offener numerischer Registry-Wert darf nicht von einer Implementierung eigenmächtig festgelegt werden, wenn er später mit einem zentral vergebenen Wert kollidieren könnte.

Diese Spezifikation ersetzt weder die X11- noch die Vulkan-Spezifikation. XAverius definiert die netzwerkseitige API und ihre zusätzlichen Garantien.
# 1. Ziel und Architektur

XAverius ist eine X11-Extension, die Vulkan-Operationen über das X11-Protokoll verfügbar macht. Vulkan-Objekte und Vulkan-Handles bleiben serverseitig. Clients adressieren Ressourcen mit XIDs.

Die erste Implementierung zielt auf Xvfb und Compute-Workloads. Grafik und Präsentation bleiben Teil der langfristigen Architektur, sind aber keine Voraussetzung für die erste funktionsfähige Implementierung.

## 1.1 Grundprinzipien

1. Vulkan-Handles werden niemals als rohe Handles über das Netzwerk übertragen.
2. Pointer, `size_t`, native C-Strukturen und compilerabhängiges Padding sind auf dem Wire verboten.
3. Alle Wire-Felder besitzen eine explizite Breite und Position.
4. Jedes logische Device besitzt seine eigenen Ressourcen.
5. Ressourcen unterschiedlicher logischer Devices dürfen nicht miteinander vermischt werden.
6. Vor Annahme eines Requests müssen alle synchron prüfbaren Bedingungen validiert werden.
7. Abgelehnte Requests dürfen keine partiellen Zustandsänderungen hinterlassen.
8. Angenommene asynchrone GPU-Arbeit kann später fehlschlagen; solche Fehler werden über XAverius-Events und Synchronisationszustände gemeldet.
9. Öffentliche XID-Gültigkeit und interne Vulkan-Objektlebensdauer sind voneinander getrennt.
10. Device-Auswahl erfolgt explizit oder durch eine definierte serverseitige Auswahlfunktion.

## 1.2 Request-Familien

Die vorgeschlagene Familienorganisation lautet:

| Familie | Inhalt |
|---:|---|
| 0 | Protocol und Version |
| 1 | Devices und Queues |
| 2 | Memory |
| 3 | Buffers und Images |
| 4 | Shaders und Pipelines |
| 5 | Commands |
| 6 | Synchronization |
| 7 | Submission und Presentation |
| 8 | Queries und optionale Features |

Diese Familiennummern sind eine Organisationsstruktur, **keine bereits zugewiesenen Subopcodes**.
