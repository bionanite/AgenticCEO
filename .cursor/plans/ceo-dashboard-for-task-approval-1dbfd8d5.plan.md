<!-- 1dbfd8d5-2a27-4120-953d-b2ec7728ee25 4d11578a-e3db-4d59-aea6-20b72034de80 -->
# Async Task Execution Upgrade Plan

## Objective

Transition the Agentic CEO from synchronous (serial) task execution to asynchronous (parallel) execution. This will allow multiple Virtual Employees and C-suite agents to execute tasks simultaneously, reducing the "daily run" time from linear (O(n)) to effectively constant (O(1)) depending on concurrency limits.

## Current State (Blocking)

- `CompanyBrain.run_pending_tasks()` iterates through tasks one by one.
- `AgenticCEO.run_task()` and `BaseVirtualEmployee.run_task()` use synchronous LLM calls.
- The Dashboard and API block while tasks run.

## Target State (Non-Blocking)

- `CompanyBrain.run_pending_tasks()` gathers tasks and runs them via `asyncio.gather()`.
- `LLMClient` needs an async method (`acall` or `acomplete`).
- `BaseVirtualEmployee` and `AgenticCEO` need `async def run_task()`.
- API/Dashboard endpoints become `async def`.

## Implementation Steps

### 1. Async LLM Support

- Update `llm_openai.py`: Add `async def acomplete()` using `AsyncOpenAI` client.
- Update `LLMClient` protocol to include async methods.

### 2. Async Virtual Employees

- Update `virtual_employees/base.py`:
    - Change `run_task` to `async def run_task`.
    - Await the LLM call.

### 3. Async C-Suite Agents

- Update `agents.py`:
    - Change `run` to `async def run`.

### 4. Async Company Brain

- Update `company_brain.py`:
    - Convert `_maybe_route_task_to_virtual_staff` to async.
    - Convert `_maybe_delegate_task_to_agent` to async.
    - Convert `run_pending_tasks` to async.
    - Use `asyncio.gather` with a semaphore (e.g., limit to 10 concurrent tasks) to prevent rate-limiting.

### 5. Update Consumers

- Update `main.py` (API) to await `brain.run_pending_tasks()`.
- Update `ceo_auto.py` (CLI runner) to run the async loop.
- Update `slack_events_server.py` to await calls.

## Verification

- Create a test script `test_async_scale.py`.
- Create 20 dummy tasks.
- Measure execution time (should be ~runtime of 1 task, not 20x).

## Risk Management

- **Rate Limits**: We must implement a `Semaphore` to control concurrency so we don't blow up OpenAI rate limits.
- **State Consistency**: Ensure `save_state` isn't called concurrently in a way that corrupts the JSON (locking might be needed, or sequential saving after gather).

## Scalability Impact

- **Before**: 50 tasks @ 10s each = ~8 minutes.
- **After**: 50 tasks @ 10s each (with 10 concurrent) = ~50 seconds.

### To-dos

- [ ] Create dashboard.py with FastAPI server and API endpoints for tasks and approval
- [ ] Create templates/dashboard.html with task list and approve/reject UI
- [ ] Add get_tasks_requiring_approval() and approve_task() wrapper to CompanyBrain
- [ ] Test dashboard loads tasks and approval flow works without breaking existing code