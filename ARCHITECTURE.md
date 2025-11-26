# AgenticCEO Architecture Overview

## System Architecture

AgenticCEO is a multi-layered AI orchestration system that simulates an autonomous CEO managing a company through LLM-powered decision-making, task delegation, and KPI monitoring.

---

## Core Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Dashboard   │  │  Slack API   │  │  REST API    │     │
│  │  (FastAPI)   │  │  (FastAPI)   │  │  (FastAPI)   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                   ORCHESTRATION LAYER                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           CompanyBrain (Main Orchestrator)            │  │
│  │  - Loads company config & KPIs                        │  │
│  │  - Coordinates all subsystems                         │  │
│  │  - Routes tasks to appropriate handlers               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌───────▼────────┐  ┌───────▼────────┐
│  AgenticCEO    │  │  KPI Engine    │  │ Task Manager   │
│  (Core CEO)    │  │  (Monitoring)  │  │ (Hierarchy)    │
└───────┬────────┘  └───────┬────────┘  └───────┬────────┘
        │                   │                   │
┌───────▼───────────────────────────────────────────────────┐
│              EXECUTION LAYER                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ CRO/COO/CTO  │  │   Virtual    │  │   Tools      │  │
│  │   Agents     │  │   Staff      │  │  (Slack,     │  │
│  │              │  │   Manager    │  │   Email, etc) │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└───────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                    PERSISTENCE LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Memory     │  │   KPI Trend  │  │  Learning    │     │
│  │   Engine     │  │   Analyzer   │  │  Engine      │     │
│  │  (JSON)      │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   OpenAI     │  │   Config     │  │   Env        │     │
│  │   LLM        │  │   (YAML)     │  │   Loader     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. **Presentation Layer**

#### Dashboard (`dashboard.py`)
- **Purpose**: Web-based control panel for monitoring and controlling the CEO
- **Tech**: FastAPI + HTML/JS (Tailwind CSS, Chart.js)
- **Features**:
  - Real-time metrics visualization
  - Task management (approve/run)
  - Virtual employee status
  - KPI charts and trends
  - System load monitoring

#### Slack Integration (`slack_events_server.py`)
- **Purpose**: Receive Slack events and route to CEO
- **Features**:
  - Event verification (signing secret)
  - Message parsing (CRO:/COO:/CTO: commands)
  - Real-time responses

#### REST API (`main.py`)
- **Purpose**: Programmatic API for external integrations
- **Endpoints**:
  - `/plan_day` - Generate daily plan
  - `/ingest_event` - Process external events
  - `/run_pending_tasks` - Execute tasks
  - `/state` - Get current state

---

### 2. **Orchestration Layer**

#### CompanyBrain (`company_brain.py`)
**The central orchestrator** that coordinates all subsystems.

**Responsibilities**:
- Loads company profile from YAML config
- Initializes all subsystems (CEO, KPI Engine, Agents, Virtual Staff)
- Routes tasks to appropriate handlers
- Manages task delegation and approval flows
- Coordinates KPI monitoring and alerts
- Provides high-level APIs (plan_day, record_kpi, ingest_event)

**Key Methods**:
- `plan_day()` - Generate daily operating plan
- `record_kpi()` - Record KPI and trigger alerts
- `ingest_event()` - Process external events
- `run_pending_tasks()` - Execute pending tasks
- `snapshot()` - Get current system state
- `personal_briefing()` - Generate CEO briefing

---

### 3. **Core CEO Engine**

#### AgenticCEO (`agentic_ceo.py`)
**The decision-making brain** that simulates CEO behavior.

**Core Components**:

1. **Schemas** (Pydantic models):
   - `CompanyProfile` - Company metadata
   - `CEOObjective` - Strategic objectives
   - `CEOTask` - Task model with priority, area, owner
   - `CEOEvent` - External events
   - `CEOState` - Current state (tasks, objectives, notes)

2. **Decision Engine**:
   - `plan_day()` - Uses LLM to generate daily plan
   - `ingest_event()` - Processes events and creates tasks
   - `_parse_tasks()` - Parses LLM output into structured tasks

3. **Task Execution**:
   - `run_task()` - Executes a task via registered tools
   - Tool routing based on task metadata
   - Result storage and status updates

4. **Tool System**:
   - Protocol-based tool interface
   - Built-in `LogTool` for basic logging
   - Extensible tool registry

---

### 4. **KPI Monitoring System**

#### KPIEngine (`kpi_engine.py`)
**Monitors business metrics and triggers alerts.**

**Features**:
- Threshold-based monitoring (min/max values)
- Automatic alert generation when KPIs breach thresholds
- Integration with CEO decision engine
- Trend analysis support

**Flow**:
1. `record_kpi()` receives a metric value
2. Checks against registered thresholds
3. If breached → creates `CEOEvent` → triggers CEO decision
4. Stores reading in memory

#### KPITrendAnalyzer (`kpi_trend_analyzer.py`)
**Proactive KPI analysis** to predict issues before they occur.

**Features**:
- Historical trend analysis
- Anomaly detection
- Predictive alerts
- Pattern recognition

---

### 5. **Task Management System**

#### TaskManager (`task_manager.py`)
**Manages task hierarchies and approval workflows.**

**Features**:
- Parent-child task relationships
- Approval workflow (awaiting/approved/rejected)
- Task review system
- Automatic parent closure when children complete
- Metadata storage (separate from CEOTask schema)

**Storage**: JSON metadata file (`{company_id}_tasks_meta.json`)

---

### 6. **Execution Layer**

#### Functional Agents (`agents.py`)
**Specialist AI agents** for different business functions.

**Agents**:
- `CROAgent` - Chief Revenue Officer (growth, MRR, MAU)
- `COOAgent` - Chief Operating Officer (operations, efficiency)
- `CTOAgent` - Chief Technology Officer (product, tech, AI)

**Pattern**: Each agent wraps the LLM with role-specific system prompts

#### Virtual Staff Manager (`virtual_staff_manager.py`)
**Autonomous virtual employees** that own KPIs and execute tasks.

**Features**:
- Auto-spawning when KPIs are under stress
- Role-based task allocation
- Performance tracking
- Persistent employee state
- Department/skill matching

**Virtual Employee Types** (50+ roles):
- Sales & Marketing (SDR, Growth Marketer, SEO Specialist)
- Operations (Ops Manager, Customer Support, QA)
- Finance (Accountant, Finance Manager, Credit Controller)
- Product (Product Manager, UX Designer, QA Engineer)
- And many more...

**Storage**: `{company_id}_virtual_staff.json`

#### Delegation Tools (`delegation_tools.py`)
**Tool wrappers** that let CEO "call" agents as tools.

- `CRODelegationTool`
- `COODelegationTool`
- `CTODelegationTool`

---

### 7. **Persistence Layer**

#### MemoryEngine (`memory_engine.py`)
**Centralized memory store** for all system activity.

**Stores**:
- Events (external inputs)
- Decisions (CEO reasoning)
- Tool calls (execution logs)
- Reflections (daily summaries)
- KPI readings (metric history)
- Token usage (LLM cost tracking)

**Storage**: JSON file (`ceo_memory.json`)

#### Learning Engine (`learning_engine.py`)
**Adaptive learning system** that improves over time.

**Features**:
- Pattern recognition from past decisions
- Success/failure tracking
- Strategy refinement
- Context-aware recommendations

---

### 8. **Infrastructure Layer**

#### LLM Client (`llm_openai.py`)
**OpenAI integration** with usage tracking.

**Features**:
- Token usage tracking
- Cost estimation
- Configurable models (gpt-4.1-mini default)
- Environment-based API key loading

#### Configuration (`company_config.yaml`)
**Company profiles and KPI definitions** in YAML format.

**Structure**:
```yaml
companies:
  company_key:
    name: "Company Name"
    industry: "..."
    vision: "..."
    mission: "..."
    north_star_metric: "..."
    kpis:
      - name: "MRR"
        min: 150000
        max: null
        unit: "GBP"
```

#### Environment Loader (`env_loader.py`)
**Automatic .env file loading** for secrets and config.

---

## Data Flow

### Daily Planning Flow
```
1. User/System → CompanyBrain.plan_day()
2. CompanyBrain → AgenticCEO.plan_day()
3. AgenticCEO → LLM (with company context)
4. LLM → Returns plan text
5. AgenticCEO → Parses tasks from plan
6. AgenticCEO → Stores tasks in CEOState
7. CompanyBrain → Records decision in MemoryEngine
```

### KPI Alert Flow
```
1. External System → CompanyBrain.record_kpi(value)
2. CompanyBrain → KPIEngine.record_kpi()
3. KPIEngine → Checks threshold
4. If breached → Creates CEOEvent
5. KPIEngine → AgenticCEO.ingest_event(event)
6. AgenticCEO → LLM generates response tasks
7. AgenticCEO → Stores tasks in CEOState
8. Optionally → VirtualStaffManager spawns employee
```

### Task Execution Flow
```
1. CompanyBrain.run_pending_tasks()
2. For each task:
   a. Check if requires approval → wait
   b. Route to appropriate handler:
      - CRO/COO/CTO agent (if area matches)
      - Virtual employee (if KPI owner matches)
      - Tool (if suggested_tool set)
   c. Execute task
   d. Store result
   e. Update status
3. TaskManager → Check if parent can close
4. MemoryEngine → Record tool call
```

---

## Key Design Patterns

### 1. **Orchestrator Pattern**
- `CompanyBrain` coordinates all subsystems
- Single entry point for external interactions
- Decoupled components

### 2. **Strategy Pattern**
- Multiple execution strategies (agents, virtual staff, tools)
- Runtime selection based on task metadata

### 3. **Observer Pattern**
- KPI monitoring triggers CEO events
- Event-driven task generation

### 4. **Factory Pattern**
- `CompanyBrain.from_config()` - Creates brain from config
- `VirtualEmployee.create()` - Creates employees with defaults
- `CROAgent.create()` - Creates agents with prompts

### 5. **Protocol/Interface Pattern**
- `Tool` protocol for extensible tools
- `LLMClient` protocol for LLM abstraction

---

## File Structure

```
AgenticCEO/
├── Core Engine
│   ├── agentic_ceo.py          # CEO decision engine
│   ├── company_brain.py         # Main orchestrator
│   └── memory_engine.py         # Persistence layer
│
├── Monitoring & Analysis
│   ├── kpi_engine.py           # KPI monitoring
│   ├── kpi_trend_analyzer.py   # Trend analysis
│   └── learning_engine.py      # Adaptive learning
│
├── Execution Layer
│   ├── agents.py               # CRO/COO/CTO agents
│   ├── virtual_staff_manager.py # Virtual employees
│   ├── task_manager.py         # Task hierarchy
│   └── delegation_tools.py     # Agent wrappers
│
├── Presentation Layer
│   ├── dashboard.py            # Web dashboard
│   ├── slack_events_server.py  # Slack integration
│   └── main.py                 # REST API
│
├── Infrastructure
│   ├── llm_openai.py           # LLM client
│   ├── env_loader.py           # Config loader
│   └── tools_real.py           # External tools
│
├── Configuration
│   └── company_config.yaml     # Company profiles
│
└── Virtual Employees
    └── virtual_employees/
        ├── base.py             # Base employee class
        ├── registry.py         # Role registry
        └── role_configs/       # 50+ role definitions
```

---

## State Management

### Persistent State
- **Memory**: `ceo_memory.json` - All system activity
- **Virtual Staff**: `{company_id}_virtual_staff.json` - Employee roster
- **Task Metadata**: `{company_id}_tasks_meta.json` - Task relationships
- **KPI History**: `.agentic_state/kpi_history.json` - Metric trends
- **Learning Data**: `.agentic_state/learning_data.json` - Adaptive patterns

### Runtime State
- **CEOState**: In-memory task list, objectives, notes
- **CompanyBrain**: Orchestrator state (agents, tools, KPIs)

---

## Extension Points

### Adding New Tools
1. Implement `Tool` protocol
2. Register in `CompanyBrain.__init__`
3. CEO will route tasks to it based on `suggested_tool`

### Adding New Virtual Employees
1. Create YAML config in `virtual_employees/role_configs/`
2. System auto-loads on startup
3. Can be spawned via `VirtualStaffManager`

### Adding New KPIs
1. Add to `company_config.yaml`
2. System auto-registers thresholds
3. Alerts trigger automatically on breach

### Adding New Agents
1. Create agent class in `agents.py`
2. Add delegation tool in `delegation_tools.py`
3. Register in `CompanyBrain.__init__`

---

## Scalability Considerations

- **Stateless Design**: Most components are stateless (except memory)
- **JSON Storage**: Simple but may need migration to DB at scale
- **LLM Calls**: Can be rate-limited or batched
- **Concurrent Execution**: Tasks can run in parallel (async support)
- **Multi-Company**: Supports multiple companies via config switching

---

## Security Considerations

- **API Keys**: Loaded from `.env` (not committed)
- **Slack Verification**: Request signing verification
- **CORS**: Configurable in dashboard
- **Input Validation**: Pydantic models validate all inputs

---

## Future Architecture Enhancements

See `IMPROVEMENT_ROADMAP.md` for planned improvements:
- Database migration (PostgreSQL/MongoDB)
- Real-time event streaming
- Multi-tenant support
- Advanced analytics dashboard
- API rate limiting
- Authentication/authorization

