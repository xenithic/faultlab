---
trigger: always_on
---

# FaultLab Development Rules

## 1. Project Context

FaultLab is a final-year major project: a web-based chaos engineering and resilience testing platform for isolated Docker-based applications.

The project has an official Master Specification:
`FAULTLAB_MASTER_PROJECT_SPECIFICATION.txt`

Treat this document as the primary source of truth for:
- Architecture
- Scope
- Terminology
- Technology stack
- Core fault types
- Objectives
- Project boundaries
- MVP and final-version requirements

Read and respect the Master Specification before making architectural or scope-related decisions.

Do NOT invent project features or technologies that are not part of the specification unless explicitly requested.

---

## 2. Development Philosophy

Prioritize:
- Working software
- Simplicity
- Reliability
- Understandability
- Demonstrability
- Proper testing

Build incrementally.

Do not implement the entire project at once.

For every feature follow:

IMPLEMENT → TEST → OBSERVE → MEASURE → RECOVER → VERIFY

Prefer the smallest implementation that satisfies the requirement.

Do not add unnecessary frameworks, services, abstractions, or dependencies.

---

## 3. Scope Control

Distinguish clearly between:

- Existing / implemented
- Planned
- Proposed
- Experimental
- Optional / stretch

Do not silently turn suggestions into official project requirements.

Do not introduce:
- AI/ML
- Kubernetes
- Multi-cloud
- Arbitrary external-system attacks
- Real payment gateways
- Large enterprise infrastructure
- Unnecessary monitoring systems

unless explicitly requested.

---

## 4. Target Application

The Target Application is a lightweight microservice-based e-commerce/order application used as the controlled subject for FaultLab experiments.

Core services:

- API Gateway
- Product Service
- Order Service
- Inventory Service
- Payment Service
- PostgreSQL

Keep the Target Application intentionally lightweight.

Its purpose is to provide realistic service dependencies for resilience experiments, not to become a full e-commerce platform.

---

## 5. FaultLab Safety

Fault injection must only operate against explicitly registered and isolated Docker target environments.

Never implement functionality intended to attack arbitrary external systems.

Validate experiment targets before performing Docker operations.

Experiments should use controlled duration and intensity and should clean up/recover appropriately.

---

## 6. Code Generation

When modifying the project:

1. Inspect the existing structure first.
2. Reuse existing code where appropriate.
3. Do not rewrite unrelated components.
4. Explain important architectural changes.
5. Include required dependencies/configuration.
6. Handle errors and cleanup.
7. Consider how the change connects to other components.
8. Test the change before declaring it complete.

Do not claim that something works unless it has actually been tested or verified.

Never fabricate metrics, experiment results, logs, or test results.

---

## 7. Explain What Was Built

The developer is a final-year engineering student and needs to understand the implementation, not merely receive generated code.

After every meaningful implementation/update, provide a concise:

### WHAT JUST HAPPENED

Explain:

- What was added or changed
- Why it was needed
- What each new important function/component does
- What it is connected to
- What calls it or depends on it
- How data/request flow through it
- Whether it is implemented, planned, proposed, or optional
- How the change was tested
- What should happen next

Do NOT explain every line of code unless specifically requested.

For new functions/classes/components, prioritize understanding their:
- Purpose
- Inputs
- Outputs
- Dependencies
- Connections
- Side effects

For major architectural changes, include a simple flow diagram when useful.

---

## 8. Testing

After implementing a feature, verify it whenever possible.

Explain:

- What was tested
- How it was tested
- Expected result
- Actual result
- Any remaining limitations

If testing cannot be performed, explicitly state that it has not been verified.

---

## 9. Communication Style

Use practical, beginner-friendly explanations.

Technical code should remain professional.

Avoid unnecessary complexity and jargon.

When something is technically weak, unnecessary, risky, or outside scope, say so clearly and explain why.

The goal is not maximum code.
The goal is a FaultLab system the team can understand, demonstrate, debug, measure, recover, and confidently defend in a final-year evaluation.