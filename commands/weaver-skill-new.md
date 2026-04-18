---
description: Scaffold a new weaver skill by parsing an existing codebase
argument-hint: <skill-name> <path-to-codebase> [--kind api|playwright|parser|domain]
---

Generate a skill scaffold derived from `$2`. Inferred public functions become actions.

```bash
weaver skill new "$1" --from-codebase "$2" --kind "${3:-api}"
```

Output lands under `skills_user/$1/`. Next steps after generation:
1. Open `skills_user/$1/_skill.py` and wire each action to the real library call
2. Declare `requires_secrets` on the manifest if the adapter needs tokens
3. `weaver skill list` to confirm registration
