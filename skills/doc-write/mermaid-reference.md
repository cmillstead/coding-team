# Mermaid Diagram Reference

## Safe Mermaid Rules (mermaid injection is real)

- NEVER use `click` directives — they execute JavaScript in browser renderers
- NEVER use HTML labels (`<b>`, `<script>`, etc.) — use plain text labels only
- NEVER embed URLs in node definitions — use a separate legend or prose links
- Keep node labels to alphanumeric text, hyphens, and spaces — no special characters from code symbols without sanitizing
- Wrap all node labels in double quotes to prevent syntax injection: `A["Auth Service"]`

## Common Diagram Types

### System Overview (graph TD)

```mermaid
graph TD
    A["Client"] --> B["API Gateway"]
    B --> C["Auth Service"]
    B --> D["Core Service"]
    D --> E["Database"]
```

### Data Flow (sequenceDiagram)

```mermaid
sequenceDiagram
    participant U as "User"
    participant A as "API"
    participant D as "DB"
    U->>A: Request
    A->>D: Query
    D-->>A: Result
    A-->>U: Response
```

### Component Relationships (graph LR)

```mermaid
graph LR
    A["Module A"] -->|"uses"| B["Module B"]
    A -->|"implements"| C["Interface C"]
    B -->|"depends on"| D["Module D"]
```
