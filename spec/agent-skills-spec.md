# Agent Skills Spec

The spec is now located at <https://agentskills.io/specification>

## 本机速查

- Skill = 一个目录，必须含 `SKILL.md`（YAML frontmatter + Markdown 正文）
- 可选子目录：`scripts/`（可执行代码）、`references/`（按需加载的文档）、`assets/`（模板与静态资源）
- frontmatter 必填：`name`（小写字母/数字/单个连字符，≤64，必须等于目录名）、`description`（≤1024，写清"做什么 + 什么时候用"）
- frontmatter 可选：`license`、`compatibility`（≤500）、`metadata`、`allowed-tools`
- `SKILL.md` 正文建议 < 5000 tokens / < 500 行，长内容拆进 `references/`
- 文件引用用相对路径，保持一层深度，避免嵌套引用链
- 校验：`npx skillsref validate ./my-skill` 或 `python tools/validate_skill.py skills/*/`
