---
name: Case study patterns
description: Tagged failure patterns from harness debugging — loaded on-demand by /debug and audit workflows, not at session start
---

# Case Study Patterns

> 20 failure patterns useful for debugging and design review. Each has a trigger condition.
> Loaded on demand — NOT at session start. Use when investigating failures or designing new constraints.

## Prompt Design Patterns

### CS-1: Permission Language (Case 1)
**Trigger:** Writing or reviewing skill/agent instruction files
Scattered "skip/directly/simple" lines compound into escape hatches. One exemption, one location, explicit scope.

### CS-3: Split-Audience Files (Case 3)
**Trigger:** Creating instruction files that serve multiple agent roles
One instruction file serving two roles (orchestrator + worker) serves neither well. Split by audience, progressive disclosure.

### CS-9: Structural Demotion (Case 9)
**Trigger:** Designing agent prompts with tool lists
Tools in a separate "Additional" section are treated as optional. Colocate all mandatory items in the same block. Separation = demotion.

### CS-11: Competing Namespace (Case 11)
**Trigger:** Adding new skills or commands that might collide with existing names
When multiple skill frameworks coexist, explicitly prohibit competing commands by name. Agent follows the structurally louder signal.

### CS-26: Tool Overload (Case 26)
**Trigger:** Designing agent tool lists
21 tools in one prompt creates selection ambiguity. Cap at 5-6 primary tools, pre-compute results from secondary tools at orchestrator level.

## Rule & Hook Authoring Patterns

### CS-2: Category Gaps (Case 2)
**Trigger:** Writing rules or hooks that enumerate specific cases
Rules covering one category ("test failures") leave adjacent categories ("review findings") unblocked. Write rules for intent, not instance.

### CS-27: Trust Inversion (Case 27)
**Trigger:** Designing verification or quality gates
Verification gates defaulting to trust are decoration. Invert: verify always, skip under narrow explicit conditions.

### CS-32: Asymmetric Set/Clear (Case 32)
**Trigger:** Writing hooks or state management with set/clear pairs
Lifecycle pairs (set/clear, acquire/release) must use identical criteria. If "set" is conditional on skill name, "clear" must check the same condition.

### CS-36: Warn→Block Escalation (Case 36)
**Trigger:** Reviewing hook effectiveness or audit findings
If a hook warning is routinely ignored under context pressure, escalate from `allow` (inform) to `block` (constrain). If the warning doesn't prevent the failure, it's decoration.

### CS-42: Guard Dependency Protection (Case 42)
**Trigger:** Designing guards or hooks with file-based state
A guard is only as strong as its dependencies. If the guard depends on a deletable file, protect that file. Ask: "Can an agent remove what the guard depends on?"

## Task Specification Patterns

### CS-5: Context Inheritance (Case 5)
**Trigger:** Adding new shared reference files or new agents
Shared reference files (style guides, principles, memory) must be audited as a matrix: agents x files. Every code-touching agent needs the style guide.

### CS-14: Infrastructure Orphan (Case 14)
**Trigger:** Writing task specs that involve symlinks, env vars, configs
Tasks with side effects beyond files must list those side effects explicitly. Agents don't know about operational dependencies.

### CS-29: Configuration Drift (Case 29)
**Trigger:** Defining agent capabilities or dispatch routing in multiple places
Agent capabilities defined in two places will drift. Establish single source of truth for dispatch type.

## Fix Propagation Patterns

### CS-16: Cross-Layer Propagation (Case 16)
**Trigger:** After fixing a behavioral issue in one agent/layer
Fixes at the orchestrator layer must propagate to every worker prompt that encounters the same category. Audit fixes across the full dispatch chain.

### CS-23: Unpropagated Fix (Case 23)
**Trigger:** After fixing a bug or vulnerability
Fixing one instance doesn't fix the class. After fixing a vulnerability, search for the same pattern at all analogous sites.

### CS-25: Incomplete Refactor (Case 25)
**Trigger:** Performing refactors or migrations
Add new pattern, verify it works, REMOVE the old pattern. Skipping step 3 creates contradictory instructions.

## Workflow Design Patterns

### CS-21: Orphaned Resource (Case 21)
**Trigger:** Creating workflows that produce external resources (PRs, deployments)
Workflows creating external resources need cleanup paths for session abandonment: retry cap + cleanup + session-resume detection.

### CS-34: Scaffold Without Activation (Case 34)
**Trigger:** Deploying new hooks or features with state dependencies
A hook registered and deployed but missing its runtime state producer is a no-op. Test the full activation chain: state producer → hook reads → hook acts.

## Audit & Review Patterns

### CS-33: Stale Calibration Constants (Case 33)
**Trigger:** Auditing hooks or configuration files
Hardcoded constants in hooks encode environmental assumptions. When the environment changes, constants become wrong silently. Audit constants against current reality.

### CS-38: Selective-Fix Costumes (Case 38)
**Trigger:** Reviewing agent output that recommends tiers or defers findings
Selective-fix has four costumes: P1-only, P3-deferral, critical-first, and advisor-mode. Tiered recommendations are selective-fix wearing consultancy clothes. Name all variants.
