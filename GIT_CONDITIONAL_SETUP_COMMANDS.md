================================================================================
GIT SETUP - CONDITIONAL INITIALIZATION (Inspect Before Overwrite)
================================================================================

DATE: 2026-10-13T10:27:18.732Z
STATUS: Commands prepared for safe conditional setup

================================================================================
STRATEGY: INSPECT FIRST, INITIALIZE ONLY IF NEEDED
================================================================================

These commands will:
1. Check if Git is already initialized
2. Check if remote is already configured
3. Verify Git identity is set
4. Only create/configure if missing (no overwrites)

================================================================================
EXACT COMMAND SEQUENCE (Copy-Paste Ready)
================================================================================

```bash
# Navigate to project
cd "D:/Work Folder/RAG-Q&A-Project"

# ============================================================================
# STEP 1: CHECK IF GIT IS ALREADY INITIALIZED
# ============================================================================

# This will show either:
# - "On branch main/master" if Git is initialized
# - "fatal: not a git repository" if not initialized
git status

# ============================================================================
# STEP 2: IF GIT NOT INITIALIZED, INITIALIZE IT
# ============================================================================

# Only runs if git status failed above
# Creates .git folder
git init

# ============================================================================
# STEP 3: VERIFY GIT WAS INITIALIZED
# ============================================================================

git status

# ============================================================================
# STEP 4: CHECK IF ORIGIN REMOTE EXISTS
# ============================================================================

# This will show:
# - List of remotes if any exist
# - Empty if no remotes configured
git remote -v

# ============================================================================
# STEP 5: ADD ORIGIN REMOTE IF NOT ALREADY CONFIGURED
# ============================================================================

# First check if origin exists (non-destructive)
git remote get-url origin 2>/dev/null || \
  git remote add origin https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant

# ============================================================================
# STEP 6: VERIFY ORIGIN REMOTE
# ============================================================================

git remote -v

# ============================================================================
# STEP 7: VERIFY GIT IDENTITY (NON-DESTRUCTIVE CHECK)
# ============================================================================

echo "=== Git Identity ==="
echo "Name: $(git config user.name)"
echo "Email: $(git config user.email)"

# ============================================================================
# STEP 8: FINAL VERIFICATION
# ============================================================================

echo ""
echo "=== Git Configuration Summary ==="
git config --list | grep -E "(user\.|remote\.origin)"
```

================================================================================
SAFER STEP-BY-STEP BREAKDOWN (For Understanding)
================================================================================

### STEP 1: Check if Git Initialized
```bash
cd "D:/Work Folder/RAG-Q&A-Project"
git status
```
- If shows "On branch main/master" → Git is already initialized
- If shows "fatal: not a git repository" → Git needs initialization
- Either way, output tells us what to do next

### STEP 2: Initialize Git (Only if Needed)
```bash
git init
```
- Creates .git/ folder
- Safe to run even if already initialized (non-destructive)
- Output will say "Reinitialized existing Git repository" if already exists

### STEP 3: Check Remotes
```bash
git remote -v
```
- Shows all configured remotes
- Empty output = no remotes yet
- Shows origin URL if already configured

### STEP 4: Add Origin (Only if Not Exists)
```bash
git remote get-url origin 2>/dev/null || \
  git remote add origin https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant
```
- First tries to GET existing origin URL (read-only)
- If origin doesn't exist (error), adds it
- If origin already exists, displays it (no overwrite)

### STEP 5: Verify Origin
```bash
git remote -v
```
- Shows configured remotes
- Confirms origin is set correctly

### STEP 6: Verify Identity
```bash
echo "=== Git Identity ==="
echo "Name: $(git config user.name)"
echo "Email: $(git config user.email)"
```
- Shows your configured Git identity
- Uses global config (already verified as Harshsinghrajpurohit)

### STEP 7: Final Summary
```bash
git config --list | grep -E "(user\.|remote\.origin)"
```
- Shows all user and remote.origin configuration
- Quick summary of Git setup

================================================================================
WHAT THIS WILL NOT DO
================================================================================

✗ Will NOT overwrite existing remote
✗ Will NOT modify application files
✗ Will NOT stage any files
✗ Will NOT create commits
✗ Will NOT push to GitHub
✗ Will NOT change Git identity
✗ Will NOT delete anything

================================================================================
EXPECTED OUTPUT SCENARIOS
================================================================================

### SCENARIO A: Git Not Initialized (Current State)
```
fatal: not a git repository (or any of the parent directories): .git
[git init creates .git folder]
On branch main
...
[remote -v shows nothing]
[git remote add origin ... adds it]
origin  https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant (fetch)
origin  https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant (push)

=== Git Identity ===
Name: Harshsinghrajpurohit
Email: harshrajpurohit412005@gmail.com
```

### SCENARIO B: Git Already Initialized, No Remote
```
On branch main
...
[git remote -v shows nothing]
[git remote add origin ... adds it]
origin  https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant (fetch)
origin  https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant (push)

=== Git Identity ===
Name: Harshsinghrajpurohit
Email: harshrajpurohit412005@gmail.com
```

### SCENARIO C: Git Already Initialized, Origin Already Configured
```
On branch main
...
[git remote -v shows]
origin  https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant (fetch)
origin  https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant (push)
[git remote add origin skipped, origin already exists]
origin  https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant (fetch)
origin  https://github.com/Harshsinghrajpurohit/hybrid-rag-document-assistant (push)

=== Git Identity ===
Name: Harshsinghrajpurohit
Email: harshrajpurohit412005@gmail.com
```

================================================================================
FILES AFFECTED
================================================================================

| File/Folder | Change | Safe? |
|-------------|--------|-------|
| `.git/` | Created (if not exists) | Yes - Git metadata only |
| `.git/config` | Updated with remote (if not exists) | Yes - Configuration only |
| All other files | None | Yes - No changes |

No application code or project files are modified.

================================================================================
SAFETY CHECKS INCLUDED
================================================================================

1. ✓ Check before add: `git remote get-url origin` verifies first
2. ✓ Non-destructive: Uses `||` operator (only adds if missing)
3. ✓ Read-only verification: `git status`, `git remote -v`, `git config`
4. ✓ Error handling: `2>/dev/null` suppresses expected error messages
5. ✓ Display summary: Final config check shows what was set

================================================================================
READY FOR APPROVAL
================================================================================

Commands are prepared. Ready to execute conditional Git setup:
1. Initialize Git (if needed)
2. Verify identity (inspect, don't change)
3. Configure origin remote (if missing)
4. Display final configuration

No files staged. No commits created. No pushes executed.

Awaiting your explicit approval to proceed.

================================================================================
