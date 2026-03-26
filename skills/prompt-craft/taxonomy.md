# Skill Taxonomy Maintenance

> Loaded from `skills/prompt-craft/SKILL.md` when taxonomy operations are needed. Return to SKILL.md after completing the operation.

The skill taxonomy (`~/.claude/skills/skill-taxonomy.yml`) maps skills to specialist worker roles so the Phase 2 Team Leader can pass relevant skills to each worker.

## Adding a skill

1. Determine which category the skill fits (debugging, verification, git-workflow, etc.)
2. If no category fits, create a new one with:
   - Category description
   - Role mappings (which specialist workers should see this skill)
3. Add the skill entry:

```yaml
category-name:
  skills:
    - name: skill-name
      path: skill-path
      description: "One-line description"
      use-when: "Trigger description"
  roles: [Senior Coder, Tester, ...]
```

## Removing a skill

Remove the entry. If the category is now empty, remove the category.

## Auditing the taxonomy

- Does every installed skill appear in the taxonomy?
- Are role mappings accurate? (would these workers actually benefit from this skill?)
- Are descriptions current? (skills evolve, taxonomy entries go stale)
