SHELL := /usr/bin/env bash

PLUGIN_ID := itcaat.calendar
PLUGIN_DIR := $(HOME)/.config/omarchy/plugins
PLUGIN_LINK := $(PLUGIN_DIR)/$(PLUGIN_ID)

.PHONY: validate link rescan enable remove install

validate:
	omarchy plugin validate "$(CURDIR)"

link:
	mkdir -p "$(PLUGIN_DIR)"
	if [[ -L "$(PLUGIN_LINK)" && "$$(readlink "$(PLUGIN_LINK)")" == "$(CURDIR)" ]]; then \
		printf 'Plugin link already points to this checkout: %s\n' "$(PLUGIN_LINK)"; \
	elif [[ -e "$(PLUGIN_LINK)" || -L "$(PLUGIN_LINK)" ]]; then \
		printf 'Plugin path already exists: %s\n' "$(PLUGIN_LINK)" >&2; \
		exit 1; \
	else \
		ln -s "$(CURDIR)" "$(PLUGIN_LINK)"; \
	fi

rescan:
	omarchy-shell shell rescanPlugins
	for attempt in $$(seq 1 40); do \
		if omarchy-plugin-list --json | jq -e --arg id "$(PLUGIN_ID)" 'any(.[]; .id == $$id)' >/dev/null; then \
			exit 0; \
		fi; \
		sleep 0.05; \
	done; \
	echo "Plugin $(PLUGIN_ID) was not discovered after rescan" >&2; \
	exit 1

enable: rescan
	omarchy plugin enable "$(PLUGIN_ID)"

remove:
	if [[ -L "$(PLUGIN_LINK)" || -e "$(PLUGIN_LINK)" ]]; then \
		omarchy plugin remove "$(PLUGIN_ID)" --yes; \
	fi

install: remove validate
	@printf 'Installing local checkout: %s\n' "$(CURDIR)"
	mkdir -p "$(PLUGIN_DIR)"
	ln -s "$(CURDIR)" "$(PLUGIN_LINK)"
	@test -L "$(PLUGIN_LINK)" && test "$$(readlink "$(PLUGIN_LINK)")" = "$(CURDIR)" || \
		{ echo "Local plugin link was not created: $(PLUGIN_LINK)" >&2; exit 1; }
	$(MAKE) rescan
	omarchy plugin enable "$(PLUGIN_ID)"
