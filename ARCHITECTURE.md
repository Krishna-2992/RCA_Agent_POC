# Technical Architecture — Agentic RCA Assistant

## Overview

A multi-agent Root Cause Analysis (RCA) system that investigates production incidents by combining historical ServiceNow incident data with a SharePoint knowledge base. The system is orchestrated using LangGraph and exposed via a Streamlit UI.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (`StateGraph`) |
| LLM | OpenAI `gpt-4.1-mini` via `langchain-openai` |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dimensions) |
| Vector Store | Qdrant (cloud, cosine similarity) |
| UI | Streamlit |
| Data Sources | ServiceNow (CSV), SharePoint (PDF via Microsoft Graph API) |
| Structured Output | Pydantic models via `llm.with_structured_output()` |

---

## Project Structure

```
RCA_Agent_2/
├── app.py                        # Streamlit UI entry point
├── main.py                       # (reserved)
├── requirements.txt
├── ingestion/
│   ├── ingest_servicenow.py      # CSV → Qdrant (servicenow_incidents)
│   └── ingest_sharepoint.py      # PDF → Qdrant (sharepoint_kb)
├── sharepoint/
│   ├── 01_acquire_key.py         # OAuth token acquisition
│   ├── 02_file_names.py          # List SharePoint drive files
│   └── 03_download_file.py       # Download PDFs via Microsoft Graph API
├── knowledge_source/             # Raw PDF knowledge base documents
├── sharepoing_downloads/         # PDFs downloaded from SharePoint
├── src/
│   ├── graph/
│   │   ├── state.py              # RCAState TypedDict (shared graph state)
│   │   └── workflow.py           # LangGraph graph definition and compilation
│   ├── nodes/
│   │   ├── query_analyzer.py     # Extracts entities, detects missing info
│   │   ├── servicenow_retriever.py  # Vector search on ServiceNow incidents
│   │   ├── kb_retriever.py       # Vector search on SharePoint KB
│   │   └── evidence_aggregator.py   # Merges ServiceNow + KB evidence
│   ├── agents/
│   │   ├── clarification_agent.py   # Generates follow-up questions
│   │   ├── servicenow_evaluator.py  # Scores and filters retrieved incidents
│   │   ├── kb_evaluator.py          # Filters irrelevant KB chunks
│   │   ├── rca_agent.py             # Generates structured RCA report
│   │   └── validation_agent.py      # Quality-gates the RCA output
│   └── utils/
│       ├── llm.py                # ChatOpenAI + embedding client setup
│       └── qdrant_client.py      # Qdrant client singleton
```

---

## Shared State — `RCAState`

All nodes and agents communicate through a single `TypedDict` passed through the LangGraph graph:

```
user_query              → raw incident description from user
extracted_entities      → service, symptom, category, priority, deployment_related
missing_information     → fields required before investigation can start
needs_clarification     → bool: gate before ServiceNow retrieval

servicenow_results      → top-5 vector search results from Qdrant
servicenow_confidence   → float score from evaluator
servicenow_analysis     → evaluator reasoning string
matching_incidents      → list of relevant ticket IDs
need_kb                 → bool: gate before KB retrieval

kb_results              → top-5 vector search results from Qdrant
filtered_kb_results     → KB chunks passing evaluator filter

combined_evidence       → merged list from ServiceNow + KB
rca_result              → structured RCA (root_cause, evidence, steps, actions, confidence)

validation_result       → structured validation output
rca_valid               → bool
needs_human_input       → bool: triggers re-clarification loop
final_missing_information → fields requested by validation agent
final_response          → clarification message returned to user
```

---

## LangGraph Workflow

```
[user_query]
     │
     ▼
query_analyzer
     │
     ├─ needs_clarification=True ──► clarification ──► END
     │
     └─ needs_clarification=False
          │
          ▼
     servicenow (retriever)
          │
          ▼
     servicenow_evaluator
          │
          ├─ need_kb=True ──► kb_retriever ──► kb_evaluator ──► evidence
          │
          └─ need_kb=False ──────────────────────────────────► evidence
                                                                    │
                                                                    ▼
                                                                   rca
                                                                    │
                                                                    ▼
                                                               validation
                                                                    │
                                                  ┌─────────────────┴──────────────────┐
                                                  │                                    │
                                         needs_human_input=True            needs_human_input=False
                                                  │                                    │
                                             clarification                            END
                                                  │
                                                 END
```

### Router Functions

| Router | Condition | Branches |
|---|---|---|
| `clarification_router` | `needs_clarification` | `clarification` / `servicenow` |
| `kb_router` | `need_kb` | `kb_retriever` / `evidence` |
| `validation_router` | `needs_human_input` | `clarification` / `end` |

---

## Nodes

### `query_analyzer`
- Uses `gpt-4.1-mini` with structured output (`QueryUnderstanding` Pydantic model)
- Extracts: `service`, `symptom`, `category`, `priority`, `deployment_related`
- Populates `missing_critical_information` only if service or symptom is absent
- Sets `needs_clarification` flag to gate the rest of the pipeline

### `servicenow_retriever`
- Builds a semantic search query from extracted entities
- Embeds query using `text-embedding-3-small`
- Queries Qdrant collection `servicenow_incidents`, returns top-5 results with payload

### `kb_retriever`
- Builds a richer search query including deployment context
- Embeds and queries Qdrant collection `sharepoint_kb`, returns top-5 chunks with payload

### `evidence_aggregator`
- Filters `servicenow_results` to only `matching_incidents` (from evaluator)
- Combines filtered ServiceNow incidents + `filtered_kb_results` into `combined_evidence`
- Tags each item with `source_type` (`servicenow` or `knowledge_base`)

---

## Agents

### `clarification_agent`
- Invoked when `needs_clarification=True` or `needs_human_input=True`
- Generates up to 3 focused follow-up questions from `missing_information`
- Returns `final_response` (plain text, shown as a warning in the UI)

### `servicenow_evaluator`
- Structured output: `IncidentEvaluation` (`confidence_score`, `matching_incidents`, `reasoning`, `enough_information`)
- Scores relevance of retrieved incidents against the current incident
- Sets `need_kb=True` when ServiceNow evidence alone is insufficient

### `kb_evaluator`
- Structured output: `KBEvaluation` (`relevant_chunks`, `reasoning`)
- Filters KB chunks to only those directly useful for RCA (same service, same failure pattern)
- Produces `filtered_kb_results`

### `rca_agent`
- Structured output: `RCAResult` (`root_cause`, `evidence`, `resolution_steps`, `preventive_actions`, `confidence_score`, `requires_more_information`, `missing_information`)
- Operates strictly on `combined_evidence` — no hallucination of systems or components
- Output is the primary artifact consumed by the UI

### `validation_agent`
- Structured output: `ValidationResult` (`is_valid`, `confidence_score`, `issues_found`, `missing_information`, `final_decision`)
- Validates that root cause is evidence-backed, resolution steps are grounded, and no hallucinations exist
- `final_decision` is either `APPROVE` or `NEED_MORE_INFO`
- Sets `needs_human_input=True` to trigger re-clarification loop if rejected

---

## Data Ingestion

### ServiceNow (`ingest_servicenow.py`)
- Source: CSV file (`customer_support_tickets_100_poc.csv` / `_1000_poc.csv`)
- Embedding text includes: affected application, issue category, reported problem, resolution notes
- Payload stored: `ticket_id`, `product`, `category`, `priority`, `status`, `region`, `sla_breached`, `escalated`, `resolution_time_hours`, `issue_complexity_score`
- Qdrant collection: `servicenow_incidents`
- Deduplication: deterministic UUID via `uuid.uuid5(NAMESPACE_DNS, ticket_id)`
- Batch upsert: 50 records per batch

### SharePoint KB (`ingest_sharepoint.py`)
- Source: PDF files from `knowledge_source/` directory
- PDF parsing: `pypdf.PdfReader`, page-by-page text extraction
- Chunking: `RecursiveCharacterTextSplitter` — chunk size 1000, overlap 200, separators `\n\n`, `\n`, `.`, ` `
- Metadata tagging by filename keyword: `payment` → Payment Gateway Runbook, `authentication` → Auth SOP, `database` → DB Runbook, `api` → API Gateway Runbook, `deployment` → Deployment Playbook
- Payload stored: `text`, `source`, `document_name`, `chunk_id`, `page`, `service`, `document_type`
- Qdrant collection: `sharepoint_kb`
- Chunk ID format: `{pdf_stem}_page_{page}_chunk_{index}`

### SharePoint File Download (`sharepoint/`)
- Uses Microsoft Graph API with delegated OAuth token
- `01_acquire_key.py` — token acquisition
- `02_file_names.py` — lists files in a SharePoint drive folder
- `03_download_file.py` — downloads all files from a drive folder to `sharepoing_downloads/`
- Endpoints used: `GET /drives/{driveId}/items/{folderId}/children`, `GET /drives/{driveId}/items/{itemId}/content`

---

## LLM & Embedding Configuration

| Setting | Value |
|---|---|
| LLM model | `gpt-4.1-mini` |
| LLM temperature | `0` (deterministic) |
| Embedding model | `text-embedding-3-small` |
| Embedding dimensions | `1536` |
| Structured output | Pydantic via `llm.with_structured_output()` |
| Config source | `.env` via `python-dotenv` |

Required environment variables:
```
OPENAI_API_KEY
QDRANT_URL
QDRANT_API_KEY
```

---

## Qdrant Vector Store

| Collection | Content | Distance |
|---|---|---|
| `servicenow_incidents` | Historical incident records | Cosine |
| `sharepoint_kb` | PDF knowledge base chunks | Cosine |

- Both collections use 1536-dimensional vectors
- Retrieval: top-5 results per query with full payload
- Client timeout: 60 seconds

---

## Streamlit UI (`app.py`)

- Single-page layout with sidebar showing the 9-step agent workflow
- User submits a free-text incident description
- Graph is invoked via `graph.invoke({"user_query": query})`
- Three outcome paths:
  1. **Clarification required** — displays a `st.warning` with friendly follow-up questions mapped via `FIELD_MAP`
  2. **RCA unavailable** — displays error with debug state expander
  3. **RCA approved** — displays root cause, confidence score, validation decision, evidence list, resolution steps, preventive actions
- "View Agent Trace" expander shows the full raw `RCAState` for debugging
- Execution time is measured and displayed on success
