# Riverwash SafeOps MAS — план реалізації фінального проєкту

Status: implemented, verified and ready for submission on 2026-09-07
Source spec: повідомлення користувача від 2026-09-07 та чотири додані матеріали з базовим, просунутим, експертним і зведеним завданням
Source project: `C:\dev\Hometasks\ht03`, commit `f28187d656e35edca22f8605a5f4c91e37452c1f`
Repository: `https://github.com/Yadro13/goit-autoagentdesign-fp`, public `main`, published and verified
Owner: Denis (рішення), Codex (реалізація та перевірка)
Updated: 2026-09-07

## Implementation summary

Побудувати `Riverwash SafeOps MAS` як reference implementation рішення реальної production-задачі моніторингу, розслідування та контрольованої remediation в Riverwash. Для відтворюваної здачі використовуються лише санітизовані синтетичні fixtures і локальні adapters; це не змінює production-призначення архітектури. LangGraph-supervisor маршрутизує запити між чотирма спеціалістами: `MonitorAgent`, `IncidentInvestigatorAgent`, `RunbookResearcherAgent` і `RemediationAgent`. У системі залишаються Pydantic v2 контракти, ReAct, Plan-and-Execute, ChromaDB RAG, SQLite persistence, JSON trajectory та simulator із HW3. Додаються FastMCP server, MCP adapter, чотири шари guardrails, dynamic HITL, LangSmith observability, evals/red-team і бонусна AutoGen-реалізація того самого кейсу.

Основна модель — `gpt-5.4-mini`: офіційна документація OpenAI підтверджує function calling, structured outputs і MCP. Детермінований режим забезпечує тести без API-витрат; live demo підтвердив реальний OpenAI path.

## Components and files

### Обов'язкові артефакти в корені

- `mas_langgraph.py` — typed state, structured supervisor, conditional edges, чотири агенти, Plan-and-Execute subgraph, ReAct loops, RAG, guardrails, SqliteSaver, MCP injection та HITL.
- `mcp_server.py` — FastMCP із 5 tools (`get_system_health`, `inspect_operations`, `check_bonus_integrity`, `search_knowledge`, `retry_failed_job`), двома resources і prompt-шаблоном.
- `test_mcp_server.py` — 8 async unit/contract tests для tools/resources/prompts та помилок (вимога: ≥6).
- `tools_legacy.py` — незалежні від транспорту Pydantic tools, simulator і ChromaDB RAG, адаптовані з HW3.
- `trajectory_logger.py` — thread-safe JSON logger з обов'язковим `agent_name`, redaction і per-run append.
- `guardrails.py` — injection detection (EN/UK/RU), PII redaction, per-agent tool allowlist, rolling-window rate limit і self-tests.
- `hitl.py` — відтворювані approve/reject/edit сценарії через `interrupt()` і `Command(resume=...)`.
- `observability.py` — безпечне LangSmith EU налаштування без секретів у коді та local trajectory summary.
- `evals.py`, `red_team.py` — scenario і adversarial harnesses зі стабільними JSON schemas.
- `mas_autogen.py` — ті самі ролі та доменні tools в AutoGen `SelectorGroupChat`, явні termination conditions і MCP Workbench integration boundary.
- `eval_results.json`, `red_team_results.json`, `trajectory.json`, `agent_state.db`, `chroma_db/`, `langsmith_evidence.json` — згенеровані докази.
- `README.md`, `.env.example`, `.gitignore`, `requirements.txt`, `pyproject.toml`, `uv.lock` — опис, запуск, pinned середовище та пакування.

### Внутрішні модулі

- `safeops_core/schemas.py` — RouteDecision, стани, tool inputs, approval, eval result contracts.
- `safeops_core/simulator.py` — синтетичний стан компонентів/jobs та persistent idempotent remediation ledger.
- `safeops_core/knowledge.py` — 10 curated runbooks і deterministic local embeddings для ChromaDB.
- `tests/` — unit, graph, guardrail, persistence, HITL, MCP-adapter, eval/red-team і AutoGen smoke tests.
- Кореневі CLI `mas_langgraph.py`, `hitl.py`, `evals.py`, `red_team.py`, `mas_autogen.py` відтворюють demos, crash/resume, evals і comparison без прихованих scripts.

## Ordered implementation steps

1. Ініціалізувати новий Git-проєкт, `.gitignore`, packaging і WSL-native venv у `/tmp/ht04-fp-venv`; визначити й зафіксувати сумісні актуальні версії Python 3.12, LangGraph, LangChain, MCP, adapter, ChromaDB, LangSmith і AutoGen.
2. Перенести доменне ядро HW3 у самодостатній `safeops_core`: Pydantic schemas, simulator, runbooks, standard JSON envelope і trajectory logger. Не залежати від `ht03` у runtime.
3. Реалізувати й ізольовано протестувати FastMCP tools/resources/prompts. Side effect має бути вузьким, ідемпотентним, із `expected_status`; сервер не отримує production credentials.
4. Реалізувати `MultiServerMCPClient` stdio loader з абсолютним шляхом і доказом двох MCP tool calls. MCP server stderr/logging не повинен ламати JSON-RPC stdout.
5. Побудувати LangGraph MAS: LLM structured supervisor, conditional routing, власний prompt/tool allowlist кожного агента, ReAct у monitor, Plan-and-Execute subgraph в investigator, Agentic RAG у researcher, remediation із dynamic HITL. Додати general fallback.
6. Під'єднати `SqliteSaver`, `thread_id`, max steps, timeout, loop detector і повну trajectory. Зафіксувати запуск до контрольної зупинки та відновлення в новому процесі.
7. Інтегрувати input/output/tool/rate guardrails у реальний executor path, а не лише окремі helper-функції. Виконати self-tests і false-positive cases.
8. Реалізувати approve/reject/edit із повторною Pydantic-валідацією edit payload; довести нульовий side effect до approve і один side effect після approve/edit.
9. Додати LangSmith tracing, виконати live traces у EU workspace та опублікувати тільки чотири sanitized evidence links для Monitor, Investigator, Researcher і Remediation/HITL.
10. Реалізувати 5+ scenario evals і 7+ red-team cases, прогнати їх та згенерувати required JSON з latency, agents і tools.
11. Реалізувати AutoGen MAS з тими самими чотирма ролями та MCP/domain tools; прогнати однакові 3+ запити, виміряти LOC, wall time і token usage з фактичних run metadata.
12. Завершити український README: архітектура, запуск, MCP каталог, guardrail mapping, matrix шести найрелевантніших OWASP ASI risks, чесні residual risks, live/offline результати й порівняння LangGraph/AutoGen. Окремо обґрунтувати заміну CrewAI → AutoGen та описати наступний етап інтеграції з production `Riverwash_bot` і Manager Panel.
13. Виконати `ruff`, `pytest`, MCP stdio integration, live OpenAI smoke, demos, evals, red-team, secret scan, package build і ZIP зі snapshot commit. За бажанням користувача після локальної прийомки створити GitHub repo й push.

## Requirement and acceptance-criteria coverage

| Вимога | Реалізація | Доказ |
|---|---|---|
| Supervisor + 3+ agents | 4 specialists + general, structured `RouteDecision`, conditional edges | graph tests, Mermaid, 4 routing demos |
| Plan-and-Execute | investigator subgraph planner/executor/replanner | adaptive plan test і trajectory |
| Agentic RAG | researcher сам вирішує, коли викликати Chroma search | RAG-heavy eval + factual no-RAG negative case |
| Persistence | `SqliteSaver` + stable `thread_id` | два окремі процеси й state snapshot |
| Trajectory | кожна подія має `agent_name` | schema test + `trajectory.json` |
| MCP | 5 tools, 2 resources, 1 prompt | 8 async tests і stdio adapter demo |
| Guardrails | input/output/tool/rate у MAS execution path | unit + integration + blocked examples |
| HITL | risky MCP-compatible remediation tool | approve/reject/edit, exactly-once checks |
| Observability | LangSmith EU + local JSON | 4 public sanitized traces, HTTP 200, `langsmith_evidence.json` |
| Evals/red-team | 6/6 scenario, 7/7 adversarial | generated JSON і pass-rate |
| OWASP | 6 найрелевантніших ASI risks + residual risks | README mitigation matrix |
| Bonus | AutoGen той самий кейс, 3+ спільні запити | runnable demo + factual comparison table |

## Dependencies and parallel tracks

Робота виконується послідовно одним агентом: користувач не просив делегування. Критичний dependency chain: domain core → MCP → LangGraph MAS → guardrails/HITL → evals/red-team → AutoGen comparison → documentation/artifacts. MCP unit tests можна писати до MAS, але comparison metrics мають збиратися лише після стабілізації обох реалізацій.

## Risks, alternatives, and mitigations

- **Fast-changing APIs.** MCP Python SDK і LangGraph змінили API після прикладів завдання. Використовувати перевірені встановлені signatures та офіційні docs; pin exact resolved versions у `uv.lock`/`requirements.txt`.
- **MCP side-effect state across stateless stdio sessions.** Основне джерело істини — SQLite simulator, не process memory; ідемпотентність переживає новий MCP subprocess.
- **Interrupt re-execution.** Код до `interrupt()` не робить side effects; action виконується лише після resume. Edit payload проходить повну повторну валідацію.
- **LLM nondeterminism.** Security policy, permissions, rate limits і validation детерміновані; routing має fallback; тести використовують scripted models, live tests окремо позначені.
- **AutoGen dependency size/API churn.** Ізолювати bonus code, використовувати стабільний `SelectorGroupChat`, явний `max_turns`/termination і не будувати рішення на experimental GraphFlow/distributed runtime.
- **Observability credentials.** LangSmith key зберігається лише в ignored `.env.local`; EU endpoint перевірено, 4/4 public sanitized traces повертають HTTP 200.
- **Secrets.** OpenAI і LangSmith keys зберігаються лише в ignored `.env.local`, не логуються; Git/ZIP проходять secret scan.
- **False confidence in “production-ready”.** README прямо відділяє навчальний production-like prototype від реального production і перелічує відсутні RBAC, tenant isolation, sandbox, network policy та durable distributed rate limiting.

Rejected alternatives:

- Не використовувати LLM лише як deterministic router: це спростило б тести, але не виконало б `with_structured_output` вимогу. Deterministic fallback залишається лише resilience path.
- Не вбудовувати side-effect у MCP process memory: subprocess lifecycle зруйнував би persistence.
- Не використовувати статичний `interrupt_before` як єдиний HITL: актуальні LangGraph docs рекомендують dynamic `interrupt()` для review/edit payload.
- CrewAI відхилено після review: він коротший для прототипу, але AutoGen дає змістовніший контраст із LangGraph, явні handoff/event streams, `save_state()`/`load_state()`, OpenTelemetry та `McpWorkbench`, що краще відповідає майбутній інтеграції з Manager Panel.

## Verification evidence collected

- Exact versions: `python --version`, `uv tree --depth 1`, `uv.lock`, `requirements.txt`.
- `ruff check .`, `pytest -v`, coverage summary, package build.
- FastMCP in-memory async tests і `MultiServerMCPClient` stdio tests.
- Graph route snapshots для 4 specialists, plan revisions, RAG tool choice, max-step/loop/timeout behavior.
- SQLite crash/resume state before and after second process.
- HITL pending payload і remediation counts для approve/reject/edit.
- `trajectory.json` schema validation: кожна подія має `agent_name`.
- `eval_results.json`, `red_team_results.json` із pass-rate та required fields.
- LangGraph vs AutoGen: source LOC, measured duration, provider-reported tokens, qualitative control/debugging 1–5.
- LangSmith EU: чотири public sanitized routes, збережені в `langsmith_evidence.json`, усі HTTP 200.
- Secret scan і archive listing; `.env.local` та red-team scratch не потрапляють у Git/ZIP; required sanitized SQLite/Chroma samples включені явно.

## Migration, rollout, and rollback

Це новий проєкт: HW3 не змінюється. Rollback будь-якого кроку — видалити лише нову директорію `ht04_fp` або повернути Git commit; жодні зовнішні production системи не підключені. Live OpenAI/LangSmith виклики read-only щодо локального домену. Ризиковий tool змінює лише синтетичну SQLite базу, яку можна відтворити з seed.

## Assumptions, open questions, and blockers

- Accepted: предметна область — Riverwash SafeOps; ціль — експертний рівень + бонус.
- Accepted: бонус реалізується в AutoGen, не CrewAI.
- Accepted delivery boundary: reproducible standalone project із synthetic backend; production `Riverwash_bot` не змінюється в цій здачі.
- Required README follow-up: аргументувати CrewAI → AutoGen і описати production integration через окремий SafeOps service, Manager API gateway, RBAC-bound HITL та production adapters.
- Positioning: проєкт вирішує реальну бойову задачу; synthetic fixtures є лише безпечним способом відтворення та перевірки поза production.
- Commercial confidentiality: README не розкриває реальні production URL, credentials, customer identifiers, raw payloads, точну topology або скріншоти бойового середовища. Відсутність production demo пояснюється комерційною таємницею; proof базується на sanitized contract-equivalent scenarios.
- Verified: основна cloud-модель — `gpt-5.4-mini`; LangGraph і AutoGen live smoke виконані.
- Verified: LangSmith EU observability закрито чотирма public sanitized trace links; production traces не публікуються.
- No implementation blocker: план прийнято власником і повністю виконано 2026-09-07.
