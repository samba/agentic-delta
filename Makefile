# This kit manages installation of version-controlled skills, and import of revised skills.
# Behavior summary:
# - `import` discovers skills from available agent homes and copies them into `./skills`.
# - `install` discovers versioned skills in `./skills` and copies them into available agent homes.
# - Copy semantics are replace-in-place per skill directory.

AGENT_DIRS := $(HOME)/.codex $(HOME)/.claude $(HOME)/.cursor
SKILL_PATH := ./skills

# find_skill_dirs(root):
# Emit directories containing SKILL.md under `root`, using null-safe find|xargs.
define find_skill_dirs
	find "$(1)" -type f -name SKILL.md -print0 | xargs -0 -I{} dirname "{}"
endef

# sync_skill_dirs(src_root, dest_root):
# For each discovered skill dir under src_root, replace same-named dir under dest_root.
define sync_skill_dirs
	$(call find_skill_dirs,$(1)) | while IFS= read -r src_dir; do \
		dest_dir="$(2)/$$(basename "$$src_dir")"; \
		rm -rf "$$dest_dir"; \
		mkdir -p "$$dest_dir"; \
		cp -R "$$src_dir"/. "$$dest_dir"/; \
	done
endef

# import_one_agent(agent_root):
# If agent has a skills dir, sync agent skills into repository skill path.
define import_one_agent
test -d "$(1)/skills" && $(call sync_skill_dirs,$(1)/skills,$(SKILL_PATH)) || true;
endef

# install_one_agent(agent_root):
# If agent root exists, ensure skills dir exists and sync repository skills into it.
define install_one_agent
test -d "$(1)" && mkdir -p "$(1)/skills" && $(call sync_skill_dirs,$(SKILL_PATH),$(1)/skills) || true;
endef

# for_each_agent(fn_name):
# Invoke the named helper function for each configured agent root in AGENT_DIRS.
define for_each_agent
$(foreach a,$(AGENT_DIRS),$(call $(1),$(a)))
endef

all: import

.PHONY: import install
import:
	mkdir -p $(SKILL_PATH)
	$(call for_each_agent,import_one_agent)

install:
	$(call for_each_agent,install_one_agent)
