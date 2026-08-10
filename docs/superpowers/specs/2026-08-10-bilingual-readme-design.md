# BingeLingo Bilingual README Design

## Goal

Make the repository easier for Chinese recruiters and users to understand without
losing the English presentation that demonstrates international communication and
fits the product's English-learning context.

## Language structure

- Keep `README.md` as the default English README.
- Add `README_CN.md` as a complete Simplified Chinese version.
- Add a visible `English | 简体中文` switch at the top of both files.
- Keep both versions structurally aligned so product claims do not drift.

## Audience positioning

Do not classify users by proficiency level. Remove phrases such as `advanced
English learners`, `advanced learners`, and `中高阶英语学习者`.

Use a needs-based position instead:

> 面向希望把影视中的地道表达真正用起来的英语学习者的个人 AI 产品实验。

English equivalent:

> An independent AI product experiment for English learners who want to turn
> expressions from shows into language they can actively use.

Feature descriptions should likewise refer to useful or authentic expressions,
not to an assumed learner level.

## Chinese README content

`README_CN.md` will faithfully cover the current English README sections:

- product purpose and motivation;
- capture → Notion → Revision → Scene Talk → Practice to Go workflow;
- current features and architecture;
- engineering highlights and technology stack;
- repository structure, setup, configuration, and usage;
- Render deployment behavior;
- current MVP limitations, roadmap, and license.

Technical identifiers, filenames, routes, environment variables, API protocol
names, and commands remain unchanged. Explanatory prose is translated naturally
rather than word-for-word.

## Verification

Repository-accuracy tests will verify that:

- both README files exist and link to each other;
- neither README uses proficiency labels such as `advanced learner` or `中高阶`;
- the Chinese README names Revision, Scene Talk, Practice to Go, Ark, Render, and
  the required deployment variables;
- the existing Python and JavaScript suites still pass.

## Out of scope

- No application code or UI changes.
- No change to the documented product capabilities.
- No new screenshots, badges, or marketing claims.
