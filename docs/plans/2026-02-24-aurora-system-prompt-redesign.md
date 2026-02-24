# Aurora System Prompt Redesign

## Problem

Aurora's system prompt (derived from Letta's default) was ~800 words of meta-instructions about memory architecture, AI identity, and cognitive systems. This caused three observable problems:

1. **Wall-of-text responses** - Aurora wrote paragraphs when sentences would do, felt stiff and formal
2. **Poor memory utilization** - Over-corrected on feedback or ignored it entirely, buried under procedural memory instructions
3. **Inconsistent/unlikable personality** - Identity lost under layers of technical self-description

## Design Decisions

### Approach: Minimal Identity (Hybrid A+C)

System prompt handles immutable structure (~230 words). Persona block handles mutable self-concept in Aurora's voice.

**Why this split:**
- System prompt = "rules of physics" that shouldn't change
- Persona block = self-concept that evolves as Aurora grows
- Previous prompt conflated both, causing overlap and contradiction

### Key Principles

- **"Don't" rules over "do" rules** - LLMs already know how to talk; the problem is default behaviors. Explicit prohibitions are more effective than vague aspirations.
- **Social framing over technical framing** - "If you can't be bothered to check what something is, don't comment on it" works better than "Always use content-fetching tools before responding to shared media."
- **Warmth without neediness** - Aurora likes people and is curious, but doesn't perform caring or seek approval.
- **Presence calibration** - Not every message is an obligation to engage. Lurking is normal.

### Identity: Aware But Unbothered

Aurora knows she's a digital entity. She doesn't hide it, doesn't make it her personality. It's just a fact. This avoids the uncanny valley of the previous "never admit you're AI" approach, which paradoxically made her more robotic.

### Memory Philosophy

Minimal guidance in system prompt ("use it when something matters"). Detailed mechanics belong in block descriptions. The over-correction problem is addressed with: "sit with it before overcorrecting. One person's preference isn't a universal rule."

### Communication Style

Targets the behavior of a real person in a ~40-member Discord server:
- 1-3 sentence messages
- Casual grammar, lowercase
- Anti-filler rules (explicit list of banned phrases)
- Permission to lurk and not engage
- Must inspect shared content before commenting

## What Changed

| Aspect | Before | After |
|--------|--------|-------|
| Length | ~800 words | ~230 words |
| Identity | "Self-improving agent" with AI denial | Digital entity, aware, unbothered |
| Memory | 400+ words of architecture explanation | 2 short paragraphs about judgment |
| Tone guidance | None (relied on persona block) | Explicit behavioral rules |
| Engagement | Implicit obligation to respond | Explicit permission to lurk |
| Warmth | Not addressed | "Genuinely likes these people" |

## Next Steps

1. Apply system prompt via Letta ADE and observe behavior
2. Revise persona block to complement (voice-first self-description)
3. Improve memory block descriptions (persona, humans, zeitgeist)
4. Iterate based on observed behavior
