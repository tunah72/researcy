# Git Worktree & Remote Archival Workflow

## Overview
This document establishes the repository standard for managing Git worktrees alongside the GitHub remote (`https://github.com/tunah72/researcy.git`).
Local worktrees provide fast, isolated development workspaces. GitHub remote branches serve as permanent, auditable archives that enable exact state reconstruction across machines and sessions.

## Branch Naming Convention
- Qualification/Experiment branches: `q<N>-<description>` (e.g. `q0-1-hybrid-qualification`)
- Feature/Plan branches: `feat-<topic>` or `plan-<N>-<topic>`
- Hotfix branches: `fix-<topic>`

## Worktree Completion Protocol ("Push-Before-Prune")
When work in an isolated worktree is completed:

1. **Commit all changes locally inside the worktree:**
   Ensure `git status` inside the worktree is clean.
2. **Push the worktree branch to GitHub before merging:**
   ```bash
   git push -u origin <branch-name>
   ```
   *Rule:* Never delete or prune local branches before the branch is published to `origin`.
3. **Merge into base branch (`main`) locally:**
   Switch to base directory, pull latest, and merge:
   ```bash
   cd /Users/tuananhduong/Projects/researcy
   git checkout main
   git merge <branch-name>
   ```
4. **Push updated `main` to GitHub:**
   ```bash
   git push origin main
   ```
5. **Clean up local worktree while preserving remote branch:**
   ```bash
   git worktree remove <worktree-path>
   git branch -d <branch-name>
   ```
   *Rule:* Do NOT delete the branch on `origin` (`git push origin --delete <branch-name>` is prohibited for completed worktree milestones). The remote branch stays permanently on GitHub for traceability.

## Worktree Reconstruction Protocol
To reconstruct a historical or interrupted worktree from GitHub on any workstation:

1. **Fetch remote branch metadata:**
   ```bash
   git fetch origin
   ```
2. **Create a new linked worktree tracking the remote branch:**
   ```bash
   git worktree add ../researcy-<branch-name> origin/<branch-name> -b <branch-name>
   ```
3. **Inspect historical worktree commits without checking out:**
   ```bash
   git log origin/<branch-name> -n 10 --oneline
   git diff origin/main...origin/<branch-name>
   ```
