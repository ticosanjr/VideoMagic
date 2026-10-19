# ADR-0006 — Typed XML builder, Jinja2 only for prompts and ASS

Status: accepted. Date: 2026-10-19.

## Context

The brief lists Jinja2 under the media engine and implies templates for FCPXML.
FCPXML and xmeml are strict, nested documents with escaping rules, rational
times, and ID references. String templates make invalid XML easy and validation
late. A single unescaped file name breaks an import.

## Decision

- Build FCPXML and xmeml with a typed XML builder (`xml.etree.ElementTree`) and
  small element helpers.
- Keep resource ids and references in one structure.
- Validate the timeline before writing; tests parse every artifact back.
- Use Jinja2 only for LLM prompt text and ASS subtitle templates.
- Escape all interpolated text. Never concatenate an XML string by hand.

## Consequences

- Structural errors surface before write.
- Attribute and time formatting live in one place.
- Golden-file tests compare normalized trees.
- The standard library is enough; no XML dependency is required for the writers.
- Slightly more code than a template, much less debugging in three NLEs.
- ASS templates stay readable, which is their advantage.

## Alternatives rejected

- Jinja2 for XML: no structural guarantee, risky escaping.
- f-strings: worse.
- A third-party FCPXML library: immature coverage of the attributes this product
  needs, and it would hide the dialect decisions.
