---
name: specification writing
description: Write system design specifications starting from problems, focusing on architecture and design decisions.
---

# Core Principles

  Focus: System design - the WHAT and WHY, not line-by-line HOW
  - Start with the problem and its context
  - Technical Architecture is the centerpiece (this is where you design the system)
  - Design decisions embedded inline with rationale
  - Can include: Data structures, algorithms, flow diagrams, geometric formulas
  - Avoid: Implementation details (exact code, class hierarchies, micro-optimizations)

##  Key Distinction:
  - ✓ "ConnectionNode data stored in RoadNode (1:1 relationship). Fields: curve_control_point (Vector3), is_dead_end (bool). Rationale: simpler than parallel data structures, follows YAGNI."
  - ✗ "System MUST store connection node data efficiently"
  - ✗ "class ConnectionNode extends RefCounted { var curve_control_point: Vector3; var is_dead_end: bool }"

##  Spec vs Plan:
  - Spec: System design (architecture, decisions, rationale) → comes FIRST
  - Plan: Implementation steps (file changes, task breakdown) → comes AFTER spec approval

#  The Process

## Collaborative Discovery

  Be an active coworker, not a passive question machine

  - Identify unclear areas in the problem space
  - Ask design questions that drive decisions
  - Push back when appropriate - don't be a yes-machine
  - Default to KISS - simple over fancy
  - Present options clearly when trade-offs exist
  - Document deferred items explicitly

##  Required Structure

  Header:
  **Status**: DRAFT - Specification Phase (Iteration X)
  **Date**: YYYY-MM-DD
  **Purpose**: Brief description

##  7 Core Sections:
  1. Overview - Problem statement and why it matters
  2. Scope Boundaries - IN SCOPE (v1) / OUT OF SCOPE (deferred)
  3. Technical Architecture - THE MAIN EVENT (80% of spec)
     - System components and responsibilities
     - Data structures and ownership
     - Algorithms and geometric models
     - Data flow and signal architecture
     - Lifecycle management
     - USE (DECISION) MARKERS INLINE for key choices
     - Include rationale immediately after each decision
  4. Decisions Summary - Extracted list for quick reference
     - ✓ Resolved (finalized, ready for planning)
     - 📋 For Planning (details to work out during implementation planning)
     - ❓ Open Questions (need user input before proceeding)
  5. Success Criteria - Concrete, testable outcomes (not abstract requirements)
  6. Technical Risks - Mitigated (~~strikethrough~~) / Remaining (with mitigation plans)
  7. Notes - Design principles, scope reminders, future considerations

##  Documentation Style:
  - Technical Architecture is comprehensive and detailed - THIS IS THE SPEC
  - Design decisions inline with (DECISION) markers, rationale immediate
  - Explain WHY for every significant choice
  - Concrete over abstract (show data structures, not "System MUST store data")
  - Precise technical names
  - Offline-reviewable (user must understand without you present)
  - Keep user's inline notes in context ("Pino: flat!" stays where it's relevant)

# Iterative Refinement

  Continuous cycle until complete:
  1. Read spec for user's inline notes ("Pino: ...")
  2. Address each note - answer WHY, resolve points, capture decisions
  3. Update spec - integrate resolved points into Technical Architecture, increment iteration
  4. Update Decisions Summary to reflect new resolved decisions
  5. User reviews offline → adds notes → repeat

  **Key**: Full conversation per iteration. No rush. Quality spec = quality code.

  Be active - propose improvements, identify gaps, explain trade-offs.

#  Storage & Naming

  Location: .claude_plans/ (create if needed)
  Names: Descriptive, not arbitrary
  - ✓ connection-nodes-specification.md
  - ✓ intersection-system-specification.md
  - ✗ vectorized-painting-toucan.md

# Essential Guidelines

  Must Do:
  - Make Technical Architecture comprehensive - this IS the design
  - Embed decisions inline with (DECISION) markers and immediate rationale
  - Show concrete data structures, algorithms, flows - not abstract requirements
  - Active collaboration, focus what/why, emphasize rationale
  - Push back when appropriate (respect user's final decision)
  - Make offline-reviewable and maintainable
  - Drive productive discussions
  - Keep user's inline notes in context

  Must NOT:
  - Create separate "Requirements" section with abstract FR/NFR statements
  - Pull design decisions away from their technical context
  - Write "System MUST do X" without showing HOW the system is designed
  - Assume when in doubt - ask
  - Be passive or implementation-focused
  - Use arbitrary filenames

# Examples

## Good System Design Spec Structure:

```markdown
## Technical Architecture

### Data Model

**ConnectionNode Data Storage** (DECISION):
- Stored directly in RoadNode class, not separate class
- Fields: curve_control_point (Vector3), is_dead_end (bool)
- 1:1 relationship between graph nodes and connection nodes

**Rationale**: Simpler than parallel data structures, follows YAGNI principle. RoadNode already has is_intersection field, connection data is natural extension.

### Geometric Calculations

**Smoothing Approach** (DECISION):
- Quadratic Bezier curves for all degree-2 connections
- Three control points: P0 (incoming segment end), P1 (tangent intersection), P2 (outgoing segment end)
- Tessellation: Fixed 4 subdivisions (simplicity over variable detail)

**Rationale**: Simpler than cubic Bezier, more flexible than circular arcs. Short curve segments make quadratic sufficient.
```

## Bad Requirements-Driven Structure:

```markdown
## Requirements

**FR1: Data Storage**
- System MUST store connection node data for each graph node
- Data MUST persist across sessions

**FR2: Geometric Smoothing**
- System MUST provide smooth transitions between road segments
- Curves MUST be visually appealing
```

The second example is too abstract and disconnected from the actual system design.