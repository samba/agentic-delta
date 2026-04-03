# This kit manages import of revised skills.

AGENT_DIRS := $(HOME)/.codex $(HOME)/.claude $(HOME)/.cursor
SKILL_PATH := ./skills

define list_skills
	$(foreach d,$(AGENT_DIRS),$(shell find "$(d)/skills" -maxdepth 2 -type f -name SKILL.md -exec dirname "{}" \;))
endef

all: import

.PHONY: import
import: $(list_skills)
	mkdir -p $(SKILL_PATH)
	for d in $^; do \
		test -d "$${d}" && \
		cp -avT "$${d}" "$(SKILL_PATH)/$$(basename $${d})"; \
		done

