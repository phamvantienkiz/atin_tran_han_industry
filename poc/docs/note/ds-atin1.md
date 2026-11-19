# IOC Platform

## Mission

Create implementation-ready, token-driven UI guidance for IOC Platform that is optimized for consistency, accessibility, and fast delivery across dashboard web app.

## Brand

- Product/brand: IOC Platform
- URL: https://aioc.atin.vn/login
- Audience: authenticated users and operators
- Product surface: dashboard web app

## Style Foundations

- Visual style: structured, tokenized, content-first
- Main font style: `font.family.primary=Inter`, `font.family.stack=Inter, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif`, `font.size.base=16px`, `font.weight.base=400`, `font.lineHeight.base=25.6px`
- Typography scale: `font.size.xs=14px`, `font.size.sm=16px`, `font.size.md=24px`, `font.size.lg=43.2px`
- Color palette: `color.text.primary=#4a5d80`, `color.text.secondary=#17233c`, `color.text.tertiary=#0044a4`, `color.text.inverse=#5b6d90`, `color.surface.base=#000000`, `color.surface.muted=#ffffff`, `color.surface.raised=#f8fafc`, `color.border.default=#dde5f1`
- Spacing scale: `space.1=4px`, `space.2=8px`, `space.3=12px`, `space.4=16px`, `space.5=20px`, `space.6=24px`, `space.7=32px`, `space.8=42px`
- Radius/shadow/motion tokens: `radius.xs=4px`, `radius.sm=9px`, `radius.md=99px` | `shadow.1=rgba(20, 40, 80, 0.1) 0px 6px 20px 0px`, `shadow.2=rgba(246, 147, 29, 0.26) 0px 8px 22px 0px`, `shadow.3=rgba(246, 147, 29, 0.35) 0px 1px 3px 0px` | `motion.duration.instant=120ms`, `motion.duration.fast=150ms`

## Accessibility

- Target: WCAG 2.2 AA
- Keyboard-first interactions required.
- Focus-visible rules required.
- Contrast constraints required.

## Writing Tone

Concise, confident, implementation-focused.

## Rules: Do

- Use semantic tokens, not raw hex values, in component guidance.
- Every component must define states for default, hover, focus-visible, active, disabled, loading, and error.
- Component behavior should specify responsive and edge-case handling.
- Interactive components must document keyboard, pointer, and touch behavior.
- Accessibility acceptance criteria must be testable in implementation.

## Rules: Don't

- Do not allow low-contrast text or hidden focus indicators.
- Do not introduce one-off spacing or typography exceptions.
- Do not use ambiguous labels or non-descriptive actions.
- Do not ship component guidance without explicit state rules.

## Guideline Authoring Workflow

1. Restate design intent in one sentence.
2. Define foundations and semantic tokens.
3. Define component anatomy, variants, interactions, and state behavior.
4. Add accessibility acceptance criteria with pass/fail checks.
5. Add anti-patterns, migration notes, and edge-case handling.
6. End with a QA checklist.

## Required Output Structure

- Context and goals.
- Design tokens and foundations.
- Component-level rules (anatomy, variants, states, responsive behavior).
- Accessibility requirements and testable acceptance criteria.
- Content and tone standards with examples.
- Anti-patterns and prohibited implementations.
- QA checklist.

## Component Rule Expectations

- Include keyboard, pointer, and touch behavior.
- Include spacing and typography token requirements.
- Include long-content, overflow, and empty-state handling.
- Include known page component density: buttons (7), inputs (3), lists (1).

- Extraction diagnostics: Low sample size: fewer than 30 visible elements were extracted. Audience and product surface inference confidence is low; verify generated brand context.

## Quality Gates

- Every non-negotiable rule must use "must".
- Every recommendation should use "should".
- Every accessibility rule must be testable in implementation.
- Teams should prefer system consistency over local visual exceptions.
