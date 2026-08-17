# Makefile — conferences.computer.science
#
#   make            validate, then build
#   make serve      build and preview on http://localhost:8000
#   make check      validate the data only
#   make deploy     upload to the host (dry run first: make deploy-dry)
#
# `build` depends on `check`, so a typo in a TOML file stops the build instead
# of quietly dropping a field from the site.

PYTHON  ?= python3
OUTPUT  ?= public
PORT    ?= 8000

# Never touched by any deploy, in either direction. `old/` holds the previous
# version of the site, which is not in this repository and must survive.
KEEP = --exclude-glob .DS_Store --exclude-glob 'front-*.html' --exclude old/
DATA    ?= data

# Host settings live in .env, which is git-ignored. See .env.example.
FTP_PROTO ?= sftp
-include .env

# OVH serves both protocols from the SAME host name, on different ports, so the
# port has to be stated: there is no sftp.* alias to point at.
FTP_PORT_sftp = 22
FTP_PORT_ftps = 21
FTP_PORT ?= $(FTP_PORT_$(FTP_PROTO))

# Protocol-specific lftp settings, chosen from FTP_PROTO.
#   sftp — accept the host key on first connection, then remember it
#   ftps — refuse to fall back to plaintext, and encrypt the data channel too
LFTP_SETTINGS_sftp = set sftp:auto-confirm yes; set net:timeout 20;
LFTP_SETTINGS_ftps = set ftp:ssl-force true; set ftp:ssl-protect-data true; \
                     set ssl:verify-certificate yes; set net:timeout 20;
LFTP_SETTINGS = $(LFTP_SETTINGS_$(FTP_PROTO))
REMOTE = $(FTP_PROTO)://$(FTP_HOST):$(FTP_PORT)

.DEFAULT_GOAL := build
.PHONY: build check check-strict preview serve clean deploy deploy-dry deploy-clean deploy-clean-dry remote-test remote-debug cache-clear links stats golive one cfps cfps-write help

## build: validate the data, then generate the site
build: check
	@$(PYTHON) build.py

## check: validate data/ against SCHEMA.md
check:
	@$(PYTHON) check.py --data $(DATA)

## check-strict: same, but warnings are fatal — use before a release
check-strict:
	@$(PYTHON) check.py --data $(DATA) --strict

## links: also verify that edition URLs still resolve (slow, needs network)
links:
	@$(PYTHON) check.py --data $(DATA) --network

## preview: build, then serve with PHP so the front page actually runs
#
# Use this one. The front page is PHP, and a static file server would offer it
# for download instead of running it.
preview: build
	@command -v php >/dev/null || { echo "php not found — install php-cli"; exit 1; }
	@echo "  http://localhost:$(PORT)/   (ctrl-c to stop)"
	@php -S localhost:$(PORT) -t $(OUTPUT) dev-server.php

## serve: preview the static pages only, without PHP
serve: build
	@$(PYTHON) build.py --serve

## one: build a single conference, e.g. make one SLUG=icfem
one:
	@$(PYTHON) build.py --only $(SLUG)

## clean: remove the generated site
clean:
	@rm -rf $(OUTPUT)
	@echo "removed $(OUTPUT)"

## stats: what is left to tidy up
stats:
	@echo "conferences : $$(ls -d $(DATA)/*/ 2>/dev/null | wc -l)"
	@echo "editions    : $$(find $(DATA) -name '2*.toml' | wc -l)"
	@echo "TODO verify : $$(grep -rl 'TODO: verify' $(DATA) | wc -l) files"
	@echo "TODO extract: $$(grep -rl 'TODO: extract' $(DATA) | wc -l) files"
	@echo "cities      : $$(grep -c '^\[' $(DATA)/cities.toml 2>/dev/null | tr -d '\n') listed, $$(grep -c '^lat =' $(DATA)/cities.toml 2>/dev/null | tr -d '\n') with coordinates"

## remote-test: connect and list, nothing else — run this first
#
# The commonest mistake is pointing lftp at the wrong protocol. OVH offers two
# separate endpoints and they are not interchangeable:
#
#   FTP_PROTO=sftp  host sftp.clusterXXX.hosting.ovh.net   (SSH, port 22)
#   FTP_PROTO=ftps  host ftp.clusterXXX.hosting.ovh.net    (FTP + TLS, port 21)
#
# SFTP is not "FTP with SSL": it is a different protocol carried over SSH.
# Aiming an FTP client at an SFTP host hangs during FEAT negotiation, which
# looks exactly like a network problem and is not one.
remote-test:
	@test -n "$(FTP_HOST)" || { echo "set FTP_HOST in .env — see .env.example"; exit 1; }
	@echo "connecting to $(REMOTE) as $(FTP_USER), then cd $(FTP_PATH)"
	@echo
	lftp -c "$(LFTP_SETTINGS) \
	  open -u $(FTP_USER),$(FTP_PASS) $(REMOTE); \
	  cd $(FTP_PATH); pwd; cls -l | head -20"

## remote-debug: same as remote-test, with lftp's protocol trace
#
# Use when remote-test hangs. The last line before the silence says which step
# failed: name resolution, TCP connect, key exchange, or authentication.
remote-debug:
	@test -n "$(FTP_HOST)" || { echo "set FTP_HOST in .env"; exit 1; }
	lftp -d -c "$(LFTP_SETTINGS) \
	  open -u $(FTP_USER),$(FTP_PASS) $(REMOTE); \
	  cd $(FTP_PATH); pwd"

## deploy-dry: show what would be uploaded, change nothing
deploy-dry: build
	@test -n "$(FTP_HOST)" || { echo "set FTP_HOST in .env — see .env.example"; exit 1; }
	lftp -c "$(LFTP_SETTINGS) \
	  open -u $(FTP_USER),$(FTP_PASS) $(REMOTE); \
	  cd $(FTP_PATH); \
	  mirror --reverse --dry-run --verbose \
	         $(KEEP) \
	         $(OUTPUT)/ ."

## cache-clear: delete the front-page cache on the server
#
# Not normally needed — the cache key contains a fingerprint of the build, so a
# deploy invalidates it by itself. Useful when something looks stuck, and to
# rehearse what happens at midnight UTC.
cache-clear:
	@test -n "$(FTP_HOST)" || { echo "set FTP_HOST in .env"; exit 1; }
	lftp -c "$(LFTP_SETTINGS) \
	  open -u $(FTP_USER),$(FTP_PASS) $(REMOTE); \
	  cd $(FTP_PATH)/cache; \
	  glob -a rm -f front-*.html || echo 'nothing to remove'"

## deploy: upload the site
#
# No --delete on purpose: the old index.php must survive while the new pages
# are reviewed alongside it. Add it only after the switch-over.
deploy: build
	@test -n "$(FTP_HOST)" || { echo "set FTP_HOST in .env — see .env.example"; exit 1; }
	lftp -c "$(LFTP_SETTINGS) \
	  open -u $(FTP_USER),$(FTP_PASS) $(REMOTE); \
	  cd $(FTP_PATH); \
	  mirror --reverse --verbose --parallel=4 \
	         $(KEEP) \
	         $(OUTPUT)/ ."
	@echo
	@echo "Uploaded. While site.toml has draft = true, every page carries noindex."

## deploy-clean: upload AND delete anything on the server that is not in public/
#
# The final state, once the changeover is done and you are sure. `old/` is
# excluded from the deletion as well as from the upload, so the previous site
# survives this too.
#
# Run deploy-clean-dry first. Always.
deploy-clean-dry: build
	@test -n "$(FTP_HOST)" || { echo "set FTP_HOST in .env"; exit 1; }
	@echo "*** DRY RUN — showing what --delete would remove ***"
	lftp -c "$(LFTP_SETTINGS) \
	  open -u $(FTP_USER),$(FTP_PASS) $(REMOTE); \
	  cd $(FTP_PATH); \
	  mirror --reverse --delete --dry-run --verbose \
	         $(KEEP) \
	         $(OUTPUT)/ ."

deploy-clean: build
	@test -n "$(FTP_HOST)" || { echo "set FTP_HOST in .env"; exit 1; }
	@printf "This deletes remote files absent from $(OUTPUT)/. Type yes: " && read a && [ "$$a" = yes ]
	lftp -c "$(LFTP_SETTINGS) \
	  open -u $(FTP_USER),$(FTP_PASS) $(REMOTE); \
	  cd $(FTP_PATH); \
	  mirror --reverse --delete --verbose --parallel=4 \
	         $(KEEP) \
	         $(OUTPUT)/ ."

## golive: what to change on launch day (prints instructions, changes nothing)
golive:
	@echo "In site.toml:"
	@echo "    front_page = \"index\"     (currently: $$(grep '^front_page' site.toml | sed 's/.*= *//'))"
	@echo "    draft = false            (currently: $$(grep '^draft' site.toml | awk '{print $$3}'))"
	@echo
	@echo "Then: make deploy"
	@echo "Then, once the old site is gone, add --delete to the deploy target."

## cfps: file a folder of collected calls into data/ — make cfps FROM=~/cfps
cfps:
	@test -n "$(FROM)" || { echo "usage: make cfps FROM=~/path/to/calls"; exit 1; }
	@$(PYTHON) import_cfps.py "$(FROM)" --data $(DATA)

## cfps-write: same, but actually copy and edit
cfps-write:
	@test -n "$(FROM)" || { echo "usage: make cfps-write FROM=~/path/to/calls"; exit 1; }
	@$(PYTHON) import_cfps.py "$(FROM)" --data $(DATA) --write

## help: list the targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  /'
