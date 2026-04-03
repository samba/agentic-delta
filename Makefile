# This kit manages import of revised skills.

AGENT_DIRS := $(HOME)/.codex $(HOME)/.claude $(HOME)/.cursor
SKILL_PATH := ./skills

all: import

.PHONY: import
import:
	mkdir -p $(SKILL_PATH)
	for agent_dir in $(AGENT_DIRS); do \
		if test -d "$${agent_dir}/skills"; then \
			find "$${agent_dir}/skills" -maxdepth 2 -type f -name SKILL.md -exec sh -c 'skill_dir=$$(dirname "$$1"); dest="$(SKILL_PATH)/$$(basename "$$skill_dir")"; rm -rf "$$dest"; mkdir -p "$$dest"; cp -R "$$skill_dir"/. "$$dest"/' sh {} \;; \
		fi; \
		done
