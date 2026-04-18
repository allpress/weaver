# Linking Weaver into another project

Copy or symlink `commands/*.md` into the target project's `.claude/commands/` so its slash commands become available inside that project's Claude Code session:

```bash
# from target project root:
mkdir -p .claude/commands
for f in /path/to/weaver/commands/*.md; do
    ln -sf "$f" ".claude/commands/$(basename "$f")"
done
```

Then, in the target project's `CLAUDE.md`, add:

```markdown
## Weaver integration

Weaver is linked at `/path/to/weaver`. Use it to query context across our ecosystem.

- `/weaver-context list` — show available contexts
- `/weaver-clone <ctx> <gitlab-url> <group>` — ingest a GitLab group
- `/weaver-query <ctx> <question>` — RAG+graph query
- `/weaver-skill-new <name> --from-codebase <path>` — scaffold a new skill
```

For a given context, prefer `/weaver-query <this-project>` before spelunking by hand.
