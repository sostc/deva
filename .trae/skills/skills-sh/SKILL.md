---
name: "skills-sh"
description: "Manage and use skills from the Skills.sh ecosystem. Use when users need to install, search, discover, or integrate skills from the Skills.sh directory."
---

# Skills.sh Integration

A skill for managing and using skills from the Skills.sh ecosystem.

## Overview

Skills.sh is an open agent skills ecosystem that provides reusable capabilities for AI agents. This skill enables users to:

- Install skills from Skills.sh
- Search for available skills
- Discover popular skills
- Integrate skills into their workflows

## Core Features

### Installing Skills

To install a skill from Skills.sh, use the following command:

```bash
npx skillsadd <owner/repo>
```

**Example:**
```bash
npx skillsadd user/awesome-skill
```

### Searching for Skills

To search for skills, you can browse the Skills.sh directory or use the search functionality to find skills based on keywords, categories, or popularity.

### Discovering Popular Skills

The Skills.sh platform features a leaderboard of popular skills based on install counts. This helps users discover widely-used and well-regarded skills.

## Usage Guidelines

1. **Installing Skills:** Use the `npx skillsadd` command to add skills to your project.
2. **Managing Skills:** Track installed skills and their versions.
3. **Integrating Skills:** Incorporate skills into your agent workflows for enhanced capabilities.
4. **Updating Skills:** Regularly check for updates to installed skills to benefit from improvements.

## Best Practices

- **Skill Selection:** Choose skills that align with your specific use cases and requirements.
- **Skill Compatibility:** Ensure skills are compatible with your agent environment and other installed skills.
- **Security:** Only install skills from trusted sources to avoid potential security risks.
- **Performance:** Monitor the performance impact of installed skills on your agent's execution.

## Troubleshooting

### Common Issues

- **Installation Failures:** Check your network connection and ensure you have the latest version of npm.
- **Skill Conflicts:** Resolve conflicts between different skills by checking their dependencies and compatibility.
- **Performance Issues:** If skills are causing performance problems, consider removing unused skills or optimizing their usage.

### Support

For additional support, visit the Skills.sh website or consult the documentation for specific skills.

## Examples

### Example 1: Installing a Skill

**Input:** "I need to install a skill for data visualization"
**Output:** "You can install a data visualization skill using: `npx skillsadd user/data-visualization-skill`"

### Example 2: Searching for Skills
**Input:** "What skills are available for natural language processing?"
**Output:** "You can find NLP skills by browsing the Skills.sh directory or searching for keywords like 'nlp' or 'natural language processing'."

### Example 3: Discovering Popular Skills
**Input:** "What are the most popular skills right now?"
**Output:** "You can check the Skills.sh leaderboard for the most installed skills. Currently, top skills include: [list of popular skills]."

## Conclusion

The Skills.sh ecosystem provides a rich collection of reusable capabilities for AI agents. By leveraging this skill, users can easily discover, install, and integrate skills to enhance their agent's functionality and performance.