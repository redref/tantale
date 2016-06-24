#!/bin/bash

# Save state not part of commit
git stash -q --keep-index

# Enforce version by calling setup.py
python setup.py help 2>/dev/null
git add -A

# Restore
git stash pop -q
