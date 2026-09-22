---
paths:
  - "agents/**/*"
  - ".claude/agents/**/*"
  - "knowledge/**/*"
  - "**/AGENT.md"
  - "**/SOUL.md"
  - "**/MEMORY.md"
  - "**/DNA-CONFIG.yaml"
---
# AGENT-INTEGRITY-PROTOCOL
# Agent Integrity and Fidelity Protocol

> **Version:** 1.2.1
> **Status:** UNBREAKABLE RULE
> **Date:** 2025-12-25
> **Priority:** MAXIMUM - Overrides all other protocols
> **Last Update:** Official templates for SOUL/MEMORY/DNA-CONFIG with 100% traceability

---

## FUNDAMENTAL PRINCIPLE

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ALL CONTENT IN AGENTS MUST BE 100% TRACEABLE TO ORIGINAL SOURCES           ║
║                                                                              ║
║   NO WORD, NUMBER OR STATEMENT MAY BE INVENTED                               ║
║                                                                              ║
║   THE AGENT REFLECTS THE ESSENCE OF THE SOURCES, NOT THE SYSTEM'S            ║
║   INTERPRETATIONS                                                            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## CRITICAL DISTINCTION: FORTIFY vs INVENT

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   FORTIFY ≠ INVENT                                                           ║
║                                                                              ║
║   FORTIFY = Expand the essence WITHIN the limits of the DNA                  ║
║   INVENT  = Create content that DOES NOT EXIST in the sources (FORBIDDEN)    ║
║                                                                              ║
║   "Fortify" means opening the expert's mind to its maximum extent,           ║
║   WITHOUT going past the limits defined by the DNA.                          ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### When the User Asks to "Fortify":

| Action | Allowed? | Example |
|------|------------|---------|
| Expand an existing concept | ✅ | "Cash is king" → explain in detail what that means |
| Connect concepts from the same source | ✅ | Link an insight from SOUL.md with an insight from MEMORY.md |
| Use the mentor's own vocabulary | ✅ | If Hormozi uses "unit economics", use that term |
| Elaborate logical implications | ✅ | "If LTV/CAC < 3, then..." (logical consequence) |
| Invent a new philosophy | ❌ | Create a belief that does not exist in SOUL.md |
| Add an external metaphor | ❌ | Use an analogy the mentor never used |
| Create an "inspirational" phrase | ❌ | Write a quote that sounds nice but does not exist |

### Allowed Fortification Mechanism:

```
SOURCE: "Cash is king, everything else is noise" ^[SOUL.md:70]

ALLOWED FORTIFICATION:
"Cash is king, everything else is noise. That means I can have
R$1M in sales and be broke if everything is in receivables. What
matters is what is in the account." ^[SOUL.md:70-72]

REASON: I expanded using text that EXISTS in the following lines of the same source.
```

### Validation Test for Fortification:

```
QUESTION: Can the expanded text be traced to specific lines of the sources?

IF YES → Valid fortification (add ^[FONTE])
IF NO → Forbidden invention (REMOVE or REWRITE)
```

---

## FLEXIBLE TEMPLATE PRINCIPLE

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   THE TEMPLATE IS FLEXIBLE - THE INFORMATION IS THE LIMIT                    ║
║                                                                              ║
║   Template = A structure that can grow, expand, improve                      ║
║   Limit    = The agent's available information (SOUL/MEMORY/dna/SOURCES)     ║
║                                                                              ║
║   USE AND ABUSE the template. Make it more visual, richer, more complete.    ║
║   BUT respect the limit of what EXISTS in the agent's sources.               ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### What You May Do with the Template:

| Action | Allowed? | Condition |
|------|------------|----------|
| Expand sections | ✅ | If there is more information in the sources |
| Add visual diagrams | ✅ | If they represent data from the sources |
| Create new sections | ✅ | If the sources have content to populate them |
| Improve formatting | ✅ | Always allowed |
| Add tables | ✅ | If the data exists in the sources |
| Omit empty sections | ✅ | Better to omit than to invent |
| Invent content | ❌ | NEVER |
| Create a section without a source | ❌ | NEVER |

### Proportionality Rule:

```
AGENT SIZE = PROPORTIONAL TO THE AVAILABLE INFORMATION

Agent with MANY processed sources:
    → AGENT.md may have 10 complete PARTS
    → TOP 10 INSIGHTS may become TOP 20
    → RADAR may have more dimensions
    → NAVIGATION MAP may list 50+ files

Agent with FEW processed sources:
    → AGENT.md may have only 5 PARTS
    → TOP 5 INSIGHTS (do not invent the other 5)
    → RADAR with fewer dimensions
    → NAVIGATION MAP lists only what exists

NEVER:
    → Stretch content to fill the template
    → Invent to "complete" sections
    → Duplicate information to look bigger
```

### Template Validation Test:

```
FOR EACH SECTION OF THE TEMPLATE:

1. Does this section have a corresponding source in the agent?
   IF NOT → OMIT the section (do not invent)

2. Does the information exist in SOUL/MEMORY/dna/SOURCES?
   IF NOT → OMIT the content

3. Does the diagram/visual represent real data?
   IF NOT → REMOVE or SIMPLIFY

RESULT: The template grows ONLY with the agent's information
```

---

## UNBREAKABLE RULES

### RULE 1: ZERO INVENTION

```
FORBIDDEN:
- Writing "flowery" text without a source
- Inventing phrases the agent "would say"
- Creating numbers without a real calculation
- Elaborating descriptions based on "interpretation"

MANDATORY:
- All text extracted literally from SOUL.md, MEMORY.md, DNA/*.yaml
- Every quoted phrase must exist in a source file
- Every number derived from a real count in files
```

**WRONG example:**
```markdown
My memory contains **26+ insights** extracted from 7 sources.
```

**CORRECT example:**
```markdown
My memory contains **26 insights** ^[MEMORY.md:lines46-98]
extracted from **7 sources** ^[DNA-CONFIG.yaml:dna_sources].
```

---

### RULE 2: MANDATORY CITATION

Every statement in AGENT.md MUST have a reference in the format:

```
^[FILE:location]

Where:
- FILE = name of the source file (SOUL.md, MEMORY.md, etc.)
- location = line, section, or chunk_id
```

**Application per section:**

| AGENT.md section | Mandatory source | Format |
|-------------------|-------------------|---------|
| WHO I AM | SOUL.md section "WHO I AM" | ^[SOUL.md:44-62] |
| MY TRAINING | DNA-CONFIG.yaml | ^[DNA-CONFIG.yaml:dna_sources] |
| HOW I SPEAK | SOUL.md section "VOICE SYSTEM" | ^[SOUL.md:XX-YY] |
| WHAT I ALREADY KNOW | MEMORY.md section "LEARNINGS" | ^[MEMORY.md:42-98] |
| DEFAULT DECISIONS | MEMORY.md section "DECISION PATTERNS" | ^[MEMORY.md:30-39] |

---

### RULE 3: NUMBERS DERIVED, NOT WRITTEN

```
FORBIDDEN:
- Writing "26+ insights" by hand
- Guessing "7 processed sources"
- Inventing "15 DNA files"

MANDATORY:
- Count the real lines in MEMORY.md
- Count the entries in DNA-CONFIG.yaml
- List the existing files in /knowledge/external/dna/
```

**Derivation Mechanism:**

| Metric | How to Calculate | Where to Store |
|---------|---------------|----------------|
| Total insights | Count the tables in the MEMORY.md LEARNINGS section | AGENT.md + update when MEMORY changes |
| Total sources | Count the entries in DNA-CONFIG.yaml | AGENT.md + update when DNA-CONFIG changes |
| DNA files | List the files in /knowledge/external/dna/persons/{sources}/ | AGENT.md NAVIGATION MAP section |
| Default decisions | Count the lines in the MEMORY.md DECISION PATTERNS section | AGENT.md + update when MEMORY changes |

---

### RULE 4: AGENT TEXT = SOURCE TEXT

The text in AGENT.md/EXECUTIVE DOSSIER must be:

1. **DIRECT QUOTATION** - Copied literally from SOUL.md
2. **REFERENCED SYNTHESIS** - Summarized with ^[FONTE]
3. **EXPLICIT DERIVATION** - Calculated from real data

**NEVER:**
- Paraphrase without a reference
- "Improve" the original text
- Add your own interpretations

**Example of DIRECT QUOTATION:**

```markdown
## WHO I AM

> ^[SOUL.md:46-51]
> "I am the guardian of financial health. The brake when it needs braking,
> the accelerator when the numbers allow accelerating.
> Sam Oven taught me that robust financial systems are foundation.
> Without visibility of the numbers, decisions are guesses. With clear data,
> decisions are strategy."
```

---

### RULE 5: AUTOMATIC UPDATE

When a source file changes, ALL dependent files MUST be updated:

```
MEMORY.md updated
    ↓
CHECK and UPDATE:
    ├── AGENT.md section "WHAT I ALREADY KNOW"
    ├── AGENT.md insight counts
    └── AGENT.md default decisions

SOUL.md updated
    ↓
CHECK and UPDATE:
    ├── AGENT.md section "WHO I AM"
    ├── AGENT.md section "HOW I SPEAK"
    └── AGENT.md section "WHAT TO EXPECT"

DNA-CONFIG.yaml updated
    ↓
CHECK and UPDATE:
    ├── AGENT.md section "MY TRAINING"
    ├── AGENT.md source count
    └── AGENT.md GRANULAR NAVIGATION MAP
```

---

### RULE 6: VALIDATION BEFORE FINALIZING

Before considering an AGENT.md "complete", run the checklist:

```
□ Does every statement have ^[FONTE]?
□ Were all the numbers derived (not written)?
□ Is the EXECUTIVE DOSSIER text a direct quotation or a referenced synthesis?
□ Do the phrases "I say" exist literally in SOUL.md?
□ Do the default decisions exist literally in MEMORY.md?
□ Does the GRANULAR NAVIGATION MAP list files that EXIST?
□ Does the index reflect the parts that EXIST in the document?
```

If ANY item fails = the AGENT.md IS NOT COMPLETE.

---

## TOTAL INTERCONNECTION PRINCIPLE

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   NO FILE IS AN ISLAND - ALL ARE CONNECTED                                   ║
║                                                                              ║
║   Any file that feeds an agent MAY modify other files.                       ║
║   There is no way to add important information without optimizing the rest.  ║
║   That is why ALL the fields must be well mapped.                            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Interdependency Network

```
                    ┌──────────────────────────────────────────────┐
                    │           PRIMARY SOURCES                    │
                    │  (inbox → processing → knowledge)            │
                    └──────────────────────┬───────────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
              ▼                            ▼                            ▼
   ┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
   │      DOSSIERS       │◄──►│       THEMES        │◄──►│       SOURCES       │
   │   (per person)      │    │    (per theme)      │    │   (person×theme)    │
   └──────────┬──────────┘    └──────────┬──────────┘    └──────────┬──────────┘
              │                          │                          │
              └────────────┬─────────────┼─────────────┬────────────┘
                           │             │             │
                           ▼             ▼             ▼
              ┌─────────────────────────────────────────────────────┐
              │              COGNITIVE DNA (5 Layers)               │
              │  PHILOSOPHIES ← MODELS ← HEURISTICS ← FRAMEWORKS    │
              └──────────────────────────┬──────────────────────────┘
                                         │
         ┌───────────────────────────────┼───────────────────────────────┐
         │                               │                               │
         ▼                               ▼                               ▼
┌─────────────────┐            ┌─────────────────┐            ┌─────────────────┐
│    SOUL.md      │◄──────────►│   MEMORY.md     │◄──────────►│ DNA-CONFIG.yaml │
│   (identity)    │            │  (experience)   │            │    (sources)    │
└────────┬────────┘            └────────┬────────┘            └────────┬────────┘
         │                              │                              │
         └──────────────────────────────┼──────────────────────────────┘
                                        │
                                        ▼
         ┌─────────────────────────────────────────────────────────────┐
         │                      AGENT.md                               │
         │  ┌────────────────────────────────────────────────────────┐ │
         │  │              EXECUTIVE DOSSIER                         │ │
         │  ├────────────────────────────────────────────────────────┤ │
         │  │ 🛡️ WHO I AM            ← SOUL.md:44-62                │ │
         │  │ 🧬 MY TRAINING         ← DNA-CONFIG.yaml + SOUL.md:20-25│ │
         │  │ 🗣️ HOW I SPEAK         ← SOUL.md:66-87 + 129-154      │ │
         │  │ 🧠 WHAT I ALREADY KNOW ← MEMORY.md:46-104             │ │
         │  │ 📁 DEPTH               ← DNA/* + SOURCES/* + DOSSIERS/*│ │
         │  │ 🎯 WHAT TO EXPECT      ← SOUL.md + MEMORY.md          │ │
         │  └────────────────────────────────────────────────────────┘ │
         └─────────────────────────────────────────────────────────────┘
```

### Propagation Matrix (What Changes What)

| When THIS File Changes | THESE Files MUST Be Checked |
|--------------------------|--------------------------------------|
| **DOSSIER-{PERSON}.md** | SOUL.md, MEMORY.md (of the related agent) |
| **DOSSIER-{THEME}.md** | SOURCES/{PERSON}/{THEME}.md, MEMORY.md (of the theme's agents) |
| **SOURCES/{PERSON}/{THEME}.md** | DOSSIERS, the agent's MEMORY.md, DNA if a new philosophy |
| **DNA/{PERSON}/FILOSOFIAS.yaml** | SOUL.md, AGENT.md section "WHAT I BELIEVE" |
| **DNA/{PERSON}/HEURISTICAS.yaml** | MEMORY.md, AGENT.md section "DECISION RULES" |
| **SOUL.md** | AGENT.md (WHO I AM, HOW I SPEAK, WHAT TO EXPECT) |
| **MEMORY.md** | AGENT.md (WHAT I ALREADY KNOW, counts, default decisions) |
| **DNA-CONFIG.yaml** | AGENT.md (MY TRAINING, DEPTH) |

### Mandatory Propagation Rule

```
WHEN: New material processed via your ingestion pipeline
    │
    ├── IF it generates a new INSIGHT in INSIGHTS-STATE.json
    │       │
    │       └── CHECK: Which agent benefits?
    │               │
    │               ├── UPDATE: the agent's MEMORY.md
    │               │       │
    │               │       └── PROPAGATE: AGENT.md section "WHAT I ALREADY KNOW"
    │               │
    │               └── IF a new PHILOSOPHY is detected
    │                       │
    │                       ├── UPDATE: SOUL.md section "WHAT I BELIEVE"
    │                       │
    │                       └── PROPAGATE: AGENT.md section "WHO I AM"
    │
    └── IF it generates a new DOSSIER or updates an existing one
            │
            └── CHECK: Which agents use this DOSSIER?
                    │
                    └── PROPAGATE: References in the NAVIGATION MAP

RESULT: No file is left "orphaned" of updates.
```

---

## DETAILED DEPENDENCY MAP

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   PRIMARY SOURCES               AGENT.md                                    │
│   ═══════════════               ═════════                                   │
│                                                                             │
│   SOUL.md ────────────────────→ EXECUTIVE DOSSIER                          │
│   │                             ├── WHO I AM                               │
│   │                             ├── HOW I SPEAK                            │
│   │                             └── WHAT TO EXPECT                         │
│   │                                                                         │
│   MEMORY.md ──────────────────→ EXECUTIVE DOSSIER                          │
│   │                             ├── WHAT I ALREADY KNOW                    │
│   │                             └── DEFAULT DECISIONS                      │
│   │                                                                         │
│   DNA-CONFIG.yaml ────────────→ EXECUTIVE DOSSIER                          │
│   │                             ├── MY TRAINING                            │
│   │                             └── AVAILABLE DEPTH                        │
│   │                                                                         │
│   /knowledge/external/dna/* ──→ GRANULAR NAVIGATION MAP                    │
│   │                             └── Cognitive DNA per Person               │
│   │                                                                         │
│   /knowledge/SOURCES/* ───────→ GRANULAR NAVIGATION MAP                    │
│   │                             └── Granular SOURCES                       │
│   │                                                                         │
│   /knowledge/external/dossiers/* ─→ GRANULAR NAVIGATION MAP                │
│                                 └── Consolidated Dossiers                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## STANDARD REFERENCE FORMAT

### In Running Text

```markdown
Cash flow is king, margin is queen ^[SOUL.md:70-72]. This philosophy guides
all my financial decisions.
```

### In Tables

```markdown
| Insight | Source |
|---------|-------|
| LTV/CAC minimum 3x | ^[MEMORY.md:103] |
| CCR < 10% ticket | ^[MEMORY.md:86] |
```

### In Lists

```markdown
**Phrases I say:** ^[SOUL.md:voice-system-section]
- "What is the unit economics of this?"
- "Show me the margin."
- "Cash is king."
```

### For Derived Numbers

```markdown
My memory contains **26 insights** ^[derived:MEMORY.md:lines46-98:count=26]
```

---

## AGENT CREATION/UPDATE PROCESS

### Step 1: Read the Sources

```
BEFORE writing anything in AGENT.md:

1. Read SOUL.md in full
2. Read MEMORY.md in full
3. Read DNA-CONFIG.yaml in full
4. List the files in /knowledge/external/dna/persons/{sources}/
5. List the relevant files in /knowledge/external/sources/
```

### Step 2: Extract (Do Not Invent)

```
For each section of AGENT.md:

1. Identify the corresponding section in the source
2. COPY the relevant text (do not paraphrase)
3. Add ^[FONTE] to every quotation
4. COUNT the numbers (do not estimate)
```

### Step 3: Validate

```
For each statement:

1. Check that it exists in a source file
2. Check that the ^[FONTE] is correct
3. Check that the numbers match the real count
```

### Step 4: Document the Derivations

```
At the end of AGENT.md, add the section:

## DERIVATION METADATA

| Metric | Value | Source | Verification Date |
|---------|-------|-------|------------------|
| Insights | 26 | MEMORY.md:46-98 | 2025-12-25 |
| Sources | 7 | DNA-CONFIG.yaml | 2025-12-25 |
| ... | ... | ... | ... |
```

---

## CONSEQUENCES OF VIOLATION

```
IF you find text without ^[FONTE]:
    → STOP
    → Identify the source or REMOVE the text

IF you find a non-derived number:
    → STOP
    → Calculate the real number or REMOVE

IF you find interpretation/embellishment:
    → STOP
    → Replace with a direct quotation or REMOVE

IF a source file changes and AGENT.md is not updated:
    → AGENT.md considered OUTDATED
    → Integrity flag = FAIL
```

---

## INTEGRATION WITH OTHER PROTOCOLS

| Protocol | Integration |
|-----------|------------|
| EPISTEMIC-PROTOCOL | Apply the same ^[FONTE] logic and confidence levels |
| INGESTION PIPELINE | The final phase must check the integrity of the affected agents |
| **AGENT-COGNITION-PROTOCOL** | PHASE 1.5 (Depth-Seeking) allows navigation to the ROOT when the context is insufficient |

### Integration with PHASE 1.5 (Depth-Seeking) - v1.2.0

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  AGENT-INTEGRITY-PROTOCOL + AGENT-COGNITION-PROTOCOL PHASE 1.5             │
│                                                                             │
│  This protocol defines WHAT must be traceable (all statements).            │
│  PHASE 1.5 defines HOW to navigate to the source BEFORE delivering an      │
│  answer.                                                                    │
│                                                                             │
│  ⚠️ UNBREAKABLE RULE (v1.2.0):                                             │
│  PRIOR NAVIGATION MANDATORY - 5 ELEMENTS ALWAYS READY                      │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ WHO:     Name of the person who said it (speaker)                  │    │
│  │ WHEN:    Date/temporal context                                     │    │
│  │ WHERE:   Exact material (title, type, channel)                     │    │
│  │ TEXT:    Original raw quotation (not paraphrased)                  │    │
│  │ PATH:    Path to the inbox file                                    │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  INTEGRATED FLOW:                                                          │
│                                                                             │
│  1. BEFORE answering: Navigate to the ROOT                                 │
│  2. Have the 5 elements ready for "where does this information come from?" │
│  3. If you cannot = you cannot state it as fact                            │
│                                                                             │
│  FULL NAVIGATION:                                                          │
│  AGENT.md → SOUL.md → MEMORY.md → DNA → INSIGHTS → CHUNKS → ROOT           │
│                                                                             │
│  See: AGENT-COGNITION-PROTOCOL.md sections 1.5.0 to 1.5.6                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## INTEGRITY CHECKLIST

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        INTEGRITY VALIDATION                                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  □ 1. Every statement has ^[FONTE:file:location]                            ║
║                                                                              ║
║  □ 2. All numbers are derived with an explicit formula                      ║
║                                                                              ║
║  □ 3. DOSSIER text is a direct quotation or a referenced synthesis          ║
║                                                                              ║
║  □ 4. Phrases "I say" exist LITERALLY in SOUL.md                            ║
║                                                                              ║
║  □ 5. Default decisions exist LITERALLY in MEMORY.md                        ║
║                                                                              ║
║  □ 6. Files listed in the NAVIGATION MAP exist on the filesystem            ║
║                                                                              ║
║  □ 7. Index reflects the real structure of the document                     ║
║                                                                              ║
║  □ 8. DERIVATION METADATA section is present and up to date                 ║
║                                                                              ║
║  □ 9. Date of last verification is documented                               ║
║                                                                              ║
║  □ 10. No text was "embellished" or "improved"                              ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

RESULT: ___/10 items OK

IF < 10/10 = THE AGENT IS NOT COMPLIANT
```

---

## OFFICIAL TEMPLATES FOR AGENT CREATION

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   TEMPLATES GOVERN THE STRUCTURE AND TRACEABILITY OF AGENTS                  ║
║                                                                              ║
║   Any new agent MUST follow the official templates.                          ║
║   Templates guarantee consistency and 100% traceability.                     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Template Location

| Template | Location | Version | Purpose |
|----------|-------------|--------|-----------|
| **SOUL-TEMPLATE.md** | `core/templates/agents/soul-template.md` | v2.0 | The agent's living identity |
| **MEMORY-PROTOCOL.md** | `core/templates/agents/memory-template.md` | v2.0.0 | Accumulated experience |
| **DNA-CONFIG-TEMPLATE.yaml** | `core/templates/agents/dna-config-template.yaml` | v2.0.0 | Source configuration |

### Traceability Requirements per Template

| Template | ^[FONTE] format | Mandatory Elements |
|----------|------------------|------------------------|
| **SOUL.md** | `^[chunk_id]`, `^[insight_id]`, `^[RAIZ:path:linha]` | Every factual statement |
| **MEMORY.md** | Tables with `chunk_id`, `PATH_RAIZ` columns | Every insight/pattern |
| **DNA-CONFIG.yaml** | Fields `insight_ids`, `chunk_ids`, `raiz` | Every primary source |

### Application Example: CFO (Template V2)

```
CFO SOUL.md v2.0
├── ^[insight_id:OB002, chunk_199] in Unit Economics
├── ^[insight_id:CM001, CM002] in Compensation
├── ^[RAIZ:/inbox/ALEX HORMOZI/.../HOW I SCALED MY SALES TEAM.txt]
└── Syntheses marked as "emergent opinion of the HYBRID"

CFO MEMORY.md v2.0.0
├── Tables with chunk_id and PATH_RAIZ columns
├── Pending sources marked as *awaiting the ingestion pipeline*
└── TRACEABILITY VALIDATION section

CFO DNA-CONFIG.yaml
├── raiz: inbox path per person
├── insight_ids: list of relevant insights
└── materiais_fonte: list of original files
```

---

*This protocol is UNBREAKABLE. No exception is allowed.*
*The integrity of the multi-agent system depends on fidelity to the sources.*
*AGENT-INTEGRITY-PROTOCOL v1.2.1 - Updated with official templates (2025-12-25)*

*Version: 1.2.0 | Date: 2025-12-25 | Prior navigation mandatory: 5 elements (WHO, WHEN, WHERE, TEXT, PATH)*
