# Knowledge layout and retrieval

Use the [task cards](../src/inferrsi/knowledge/data/skill_library/tasks/inference-task-router/SKILL.md) when the deliverable is known. Use `inferrsi find` for symptom-based discovery or open a known owner directly. [Knowledge base contract](knowledge-base.md) · [Migration manifest](skill-layout-migration.csv)

## 1. Task entry, supporting knowledge and evidence

One registered entry exposes seven addressable cards. A compound request may have a primary and secondary task. The cards point to 20 distinct seed IDs across the library. The full catalog remains available.

```mermaid
flowchart TB
    A["Requested deliverable"] --> T["tasks / inference-task-router · 1 registered entry"]
    T --> R1["Day-0 model · performance · debug · accuracy"]
    T --> R2["Version alignment · derived engine · independent engine"]
    R1 --> C["Conditions: model stages, engine / revision, backend, device, OS, dtype, workload"]
    R2 --> C
    C --> S["systems · 53<br/>platform, framework, engine"]
    C --> P["playbooks · 17<br/>measurement, planning, optimization"]
    C --> W["workflows · 8<br/>research, governance, maintenance"]
    C --> B["casebooks · 2<br/>prior outcomes and retry conditions"]
    S --> E["Read source at revision and check applicability"]
    P --> E
    W --> E
    B --> E
```

[Chinese diagram (PNG)](assets/knowledge-layout/01-task-layers.png)

## 2. Physical directory and provenance

Counts refer to registered bundles. Each ID has one source location. Individual bundles may carry references or cases. Contribution records, dependency and peer records, and frozen experiments have separate owners.

```mermaid
flowchart LR
    ROOT["InferRSI"] --> DATA["src/inferrsi/knowledge/data/"]
    ROOT --> EV["evidence / campaign<br/>frozen plans, results, validators"]
    DATA --> REG["skill_library / skill-index.json<br/>stable ID → path + declared backend"]
    DATA --> SRC["repo_packs/ and knowledge_packs/<br/>contribution, dependency, peer records"]
    DATA --> L["skill_library/"]
    L --> T["tasks/inference-task-router/<br/>SKILL.md · metadata.json · references/routes/*.json"]
    L --> S["systems/<br/>platforms/{ascend,cuda,host} · frameworks · engines"]
    L --> P["playbooks/<br/>measurement · planning · optimization"]
    L --> W["workflows/<br/>research · governance · maintenance"]
    L --> C["casebooks/<br/>inference · ascend"]
```

[Chinese diagram (PNG)](assets/knowledge-layout/02-physical-layout.png)

## 3. Search, direct reads and delivery

Default `find` ranks 135 evidence entries: 80 skills, 48 records and 7 cases. The entry skill is excluded before IDF is computed. The caller checks applicability and records gaps. Dashed items are proposed extensions.

```mermaid
flowchart TB
    Q["Engineer or agent"] --> T["Known task: skills show → read one route card"]
    Q --> F["Symptom: find → ranked evidence owners"]
    Q --> I["Known ID / resource: direct read"]
    T --> SE["Candidate IDs + required inputs + acceptance checks"]
    SE --> V["Reader / caller verifies revision, device, version and workload"]
    F --> V
    I --> V
    V --> OK["Applicable evidence → cite owner, revision and resource"]
    V --> GAP["Analogue or gap → name missing evidence and smallest target check"]
    F -.-> NEXT["Proposed: exact symbol / finding lookup and automatic condition matching"]
```

[Chinese diagram (PNG)](assets/knowledge-layout/03-search-and-delivery.png)

## 4. Mapping the 80 original registered bundles

Edge labels count bundles, grouped by stable ID. The new entry adds one registration. The seven route cards are resources in that entry.

```mermaid
flowchart LR
    H["hardware · 22"] -->|21| S["systems · 53"]
    H -->|1| C["casebooks · 2"]
    FW["frameworks · 5"] -->|5| S
    RE["repositories · 27"] -->|27| S
    M["methods · 20"] -->|17| P["playbooks · 17"]
    M -->|2| W["workflows · 8"]
    M -->|1| C
    OW["workflows · 6"] -->|6| W
    NEW["New entry"] -->|1| T["tasks · 1"]
```

[Chinese diagram (PNG)](assets/knowledge-layout/04-before-after.png)
