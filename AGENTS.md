# AGENTS.md — jstdata workflows

Guidance for humans and agents extending the interactive CLI.

## Architecture

`jstdata` centers on three ideas:

1. **Session** — portable analytical intent (`metric` / `entity` / `series` + filters). Mirrors `JSTDataClient.query` parameters. No observations; can execute, export CSV, or render Python/CLI snippets. **Source of truth** for what is staged.
2. **Step** — a self-describing interactive TUI that edits a shared `Session`. Steps are order-agnostic: any step must accept an empty or arbitrary session.
3. **Host** — `WorkflowHost` runs one process over a pipeline of steps. It owns the session for the lifetime of the run, plus a UI-only `labels: dict[id, str]` cache (hydrated from the API; never persisted). Universal UI every step gets for free:
   - `s` session modal (list / remove / inspect API JSON)
   - `f` find modal (search catalog / add to session / inspect)
   - `e` export modal (copy Python, copy CLI, write session JSON)
   - `n` / `p` next / previous step
   - `q` quit
   - `?` step-specific keybindings (from the step’s catalog entry)

Composition happens in the **shell**, not a custom DSL:

```bash
jst run STEP [ARGS...] : STEP [ARGS...] : ...
```

Catalog + parsing live in `jstdata/workflows/`. Registration is import-time (`register(StepSpec)`). The console is one step among many (`jstdata/workflows/console.py`).

## Why steps matter

A step is the unit of product surface area. New research workflows should almost always be **new steps**, not forks of the console.

Because steps share a `Session` and the host’s session/export chrome:

- Users can chain specialized UIs without leaving the process.
- Export and session management stay consistent.
- Agents/humans can discover steps via `jst steps` / `jst step <id> [--json]` without reading TUI code.

Do **not** encode step ordering in metadata. Compatibility is “works with any session,” including empty.

## How to create a step

1. **Add a module** under `jstdata/workflows/` (e.g. `company_selector.py`).
2. **Implement a screen factory**:

   ```python
   def create_my_screen(client, session, **kwargs):
       # kwargs come from StepArgument CLI flags
       return MyScreen(client, session, **kwargs)
   ```

3. **Register a `StepSpec`**:

   ```python
   from .base import StepArgument, StepBinding, StepSpec, register

   MY_STEP = register(
       StepSpec(
           id="my-step",                 # CLI id
           name="My Step",
           description="One sentence.",
           create_screen=create_my_screen,
           arguments=(
               StepArgument(
                   name="industry",
                   type="string",
                   description="Industry filter",
               ),
           ),
           bindings=(
               StepBinding("i", "inspect", "Inspect highlighted item"),
               # Shown under ? and in `jst step my-step`
           ),
           example="jst run my-step --industry semiconductors : console",
       )
   )
   ```

4. **Import the module** from `jstdata/workflows/__init__.py` so it registers (same pattern as `console`).
5. **Implement the Textual `Screen`** so it mutates `session` only. When adding a resource, also call `app.remember_label(id, label)` so host UI can show names. Rely on host `s` / `f` / `e` for shared session/find/export UI; only declare step-local keys on `bindings` and implement matching `action_*` methods.

Seed flags go on `arguments`. They configure the TUI; they do not replace interactive use.

## How to use a step

| Goal | Command |
|------|---------|
| List steps | `jst steps` / `jst steps --json` |
| Describe one step | `jst step <id>` / `jst step <id> --json` |
| Run alone | `jst run console` |
| Preload session JSON | `jst run --session path.json console` |
| Set default export path | `jst run --output out.json console` |
| Chain steps | `jst run selector --industry semis : console` |
| Inside the TUI | `s` session · `f` find · `e` export · `n`/`p` navigate · `?` step keys · `q` quit |

There is **no in-UI “load session” picker**. To reload, quit, recall the command from shell history, and add `--session`.

Session writes happen from the export modal (`e`). The host picks a unique default filename unless `--output` is set.
