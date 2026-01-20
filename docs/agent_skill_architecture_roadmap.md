# General Agent Architecture & Skill Integration Roadmap

## 1. Core Concept: Vibe Workflow vs. Skills
The key realization is that **Vibe Workflow** and **Skills** are complementary, not mutually exclusive.

*   **Skills (Definition / Interface):**
    *   Follows the **Anthropic/Claude Skill Standard** (Markdown based).
    *   Defines **"What to do"**. It acts as the "Task Book" or User Interface.
    *   Contains Prompts, Metadata (Tool dependencies), and Context.
    *   *Static & Declarative.*

*   **Vibe Workflow (Runtime / Engine):**
    *   Uses **Burr** state machine.
    *   Defines **"How to do it"**. It acts as the "Brain" and "Execution Engine".
    *   Handles Planning (breaking complex skills into steps), Context Management (Sub-agents), and Robustness.
    *   *Dynamic & Operational.*

**Conclusion:** Do not discard Vibe Workflow. Instead, refactor it to become the **Runtime Engine** that executes the standard Skill definitions.

---

## 2. Architecture Comparison

| Feature | ReAct Loop (Standard) | Task Queue (TODO) | Vibe Workflow (Planner) |
| :--- | :--- | :--- | :--- |
| **Mechanism** | Thought -> Act -> Observe Loop | Dynamic List (Add/Complete) | Plan (List Steps) -> Execute Sequence |
| **Best For** | Simple, short queries | Open-ended exploration | Complex Engineering, Long-horizon tasks |
| **Context** | Single shared context (Explodes easily) | Hard to isolate history | **Sub-Agent Isolation** (Clean context per step) |
| **Stability** | Low (Can get lost) | Low (Rabbit Holes) | **High** (Rigid structure) |

**Recommendation:** Adopt a **Dual-Mode Engine**:
1.  **ReAct Mode:** For simple Skills/Queries.
2.  **Vibe Planner Mode:** For complex Engineering/Coding Skills (requiring global view & context isolation).

---

## 3. Implementation Roadmap

### Phase 1: Skill Standardization (The Interface)
*   Create a `skills/` directory structure following Claude's spec.
*   Example structure:
    ```text
    skills/
    ├── calculator/
    │   └── SKILL.md
    └── data_analysis/
        ├── SKILL.md
        └── scripts/
    ```
*   Implement a `SkillLoader` to parse Frontmatter and Markdown prompts.

### Phase 2: Refactoring Vibe (The Engine)
*   **Decouple:** Remove hardcoded `workflows` from `config.yaml`.
*   **Inject:** Update `vibe_workflow.py` to accept a loaded `Skill` object as input.
    *   The Skill's `prompt` becomes the `current_goal`.
    *   The Skill's `allowed-tools` configures the available toolset.

### Phase 3: Capability Upgrade
*   **Replanning:** Enhance Vibe Executor to trigger a "Replan" signal instead of failing when a step gets stuck.
*   **Router:** Implement an Intent Classifier to route user input to the correct `skills/{name}/SKILL.md`.

---

## 4. Summary
**"Skills are the Cartridges, Vibe is the Console."**
By standardizing on the Claude Skill format, the agent gains ecosystem compatibility. By retaining Vibe, the agent maintains the robustness required for software engineering tasks that simple ReAct loops cannot handle.
