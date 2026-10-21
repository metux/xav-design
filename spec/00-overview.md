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

> Split from the consolidated working draft. The original remains at [`wip/wip-2026-10-20.md`](../wip/wip-2026-10-20.md). Content is reorganized here; unresolved design decisions remain unresolved.
