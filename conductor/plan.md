# Update GitHub Actions Workflow for Node 24

## Background & Motivation
GitHub Actions will deprecate Node.js 20 in actions like `actions/checkout@v4` and `astral-sh/setup-uv@v4`. A lint warning recommends setting the `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` environment variable to opt into Node 24.

## Objective
Add the top-level `env` block to the GitHub Actions CI workflow to enforce Node.js 24 and resolve the deprecation lint warning.

## Key Files & Context
- `.github/workflows/ci.yml`: The CI workflow definition file.

## Implementation Steps
1. Modify `.github/workflows/ci.yml`.
2. Add the `env` block directly beneath the `on` triggers.
   ```yaml
   env:
     FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
   ```

## Verification & Testing
- The next GitHub Actions run should use Node 24 and stop showing the Node.js 20 deprecation warning.
