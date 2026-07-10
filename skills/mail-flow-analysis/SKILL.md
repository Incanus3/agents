---
name: mail-flow-analysis
description: Use when analyzing communication patterns with a contact - finds all mails in both directions, groups by temporal proximity, and identifies recurring flows
---

# Mail Flow Analysis

## Overview

Analyze email communication patterns between you and a contact to identify recurring workflows and temporal groupings.

## Core Principle

**Always search BOTH directions** - `from:contact` AND `to:contact`. Single-direction searches miss half the conversation and produce incomplete flow analysis.

## When to Use

- User asks about communication patterns with someone
- Analyzing recurring workflows via email
- Understanding relationship dynamics over time
- Finding all threads with a specific person

## Process

### 1. Find All Communication

```bash
gog gmail search 'from:contact@example.com OR to:contact@example.com'
```

Use pagination (`--page`) to get all results if needed.

### 2. Group by Temporal Proximity

Emails within ~1 month of each other likely belong to the same interaction cycle. Group them:

| Group | Date Range | Messages | Thread IDs |
|-------|------------|----------|------------|
| 2025 Tax Season | Feb-Mar 2025 | 11 msgs | 1950a4b9e3fa4bf4, 195586d982342deb |
| 2024 Tax Season | Mar-Apr 2024 | 3 msgs | 18e816efa262b6b1 |

**CRITICAL**: List ALL unique thread IDs within each temporal group. A single cycle often spans MULTIPLE threads with different subjects (e.g., "DP 2024" for initiation → "DPFO 2024" for deliverable).

### 3. Load Thread Content

**CRITICAL**: Fetch and read full content for ALL threads in each temporal group, not just ones with obvious subject names. Do not infer flow patterns from subject lines alone.

```bash
gog gmail thread <threadId> --json
```

**Why this matters:**
- Initiation often has a generic subject (e.g., "DP 2024")
- Deliverable has the formal name (e.g., "DPFO 2024")
- They may be SEPARATE threads created days/weeks apart
- Skipping threads means missing who initiated the cycle

**Process:**
1. Fetch every thread ID listed in the temporal group
2. Read the earliest messages first to identify initiation
3. Do not assume one thread contains the complete flow

Read the actual message bodies to identify:
- Who initiates each cycle (check EARLIEST messages in the date range)
- What documents/materials are exchanged at each phase
- The precise sequence of interactions

### 4. Identify Flow Patterns

Within each temporal group, identify the complete sequence. Common phases:

1. **Initiation** - Who starts the cycle? What do they ask?
2. **Confirmation & Request** - Response acknowledging request, asking for documents/materials
3. **Document Exchange** - Attachments, materials, information sent
4. **Deliverable** - Work product delivered (forms, reports, etc.)
5. **Follow-up** - Payment, confirmations, minor clarifications, issues

**Important**: The Initiation and Document Exchange phases are often separate and distinct. A typical professional service flow is:

```
Client initiates → Provider confirms & requests documents → Client sends documents → Provider delivers work → Follow-up
```

### 5. Compare Across Groups

Identify recurring patterns across temporal groups:
- Does the flow repeat each year/quarter?
- Are there consistent phases in the same order?
- Who initiates each cycle?
- What varies between cycles?

## Attachment Handling

**Never load attachment contents** unless explicitly requested. Use metadata only:
- Filename
- Size
- MIME type

## Quick Reference

| Step | Command |
|------|---------|
| Find all mails | `gog gmail search 'from:X OR to:X'` |
| Get thread | `gog gmail thread <id> --json` |
| Paginate | `--page <token>` |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Searching only `from:` | Always use `from:X OR to:X` |
| Loading attachment content | Use metadata only |
| Ignoring thread structure | Fetch full threads, not just individual messages |
| Missing temporal patterns | Group by proximity, compare across groups |
| Inferring flow from subjects only | Read actual message content in threads |
| Skipping early phases | Check for initiation and document request phases |
| **Assuming one thread per cycle** | **Fetch ALL threads in temporal group; initiation may be in separate thread** |
| **Cherry-picking threads by subject** | **Use thread IDs from search results, not subject names** |

## Output Format

Present findings as:

1. **Summary** - Total emails, date range, main patterns
2. **Temporal Groups** - Table of grouped interactions
3. **Flow Pattern** - Complete phase-by-phase breakdown including who initiates
4. **Variations** - What differs between cycles
