-include .env
PROJECTNAME=$(shell basename "$(PWD)")
BINARY=template
VERSION=0.10
EXCLUDE_DIRS=burr_src_code_for_llm_read,nicegui_src_for_llm_read

MAKEFILAGS += --silent

.PHONY: help
all: help
help: Makefile
	@echo
	@echo " Choose a command run in "$(PROJECTNAME)":"
	@echo
	@sed -n 's/^##//p' $< | column -t -s ':' | sed -e 's/^/ /'
	@echo

## install: Install dependency
install:
	@echo " > Installing dependency"
	@uv pip install -r dev-requirements.txt

## ruff: ruff check pep8
ruff:
	@echo " > Checking pep8"
	@ruff check . --exclude=$(EXCLUDE_DIRS)

## mypy: run mypy check
mypy:
	@echo " > Checking types"
	@mypy --exclude burr_src_code_for_llm_read --exclude nicegui_src_for_llm_read .

## rufffix: Fix pep8
rufffix:
	@echo " > Fixing pep8"
	@ruff check . --fix --exclude=$(EXCLUDE_DIRS)

## format: Auto format code
format:
	@echo " > Formating code..."
	@ruff format . --exclude=$(EXCLUDE_DIRS)

## unittest: Run all unit test
unittest:
	@echo " > Testing..."
	@python -m pytest --cov=./

## flake8: Run flake8
flake8:
	@echo " > Running flake8 check"
	@flake8 . --exclude=$(EXCLUDE_DIRS) --count --exit-zero --max-complexity=8 --max-line-length=80 --statistic

## build: Build pyinstaller package
build: clean
	@echo " > Creating release file..."
	@python pyinstaller.py

## clean: Clean release file
clean:
	@echo " > Cleaning release file"
	@rm  ./dist/* 2> /dev/null || true

## piptar: Pip build a tar package
piptar: clean
	@echo " > Pip building..."
	@python -m build

## pipedit: Pip install in edit mode
pipedit:
	@echo " > Pip Install in edit mode"
	@pip install -e .

## submodule: Sync and update git submodules
submodule:
	@echo " > Syncing and updating git submodules"
	@git submodule sync
	@git submodule update --init --recursive

## pypitest: Upload package to testpypi
pypitest: piptar
	@echo "Uploading to testpypi"
	@python -m twine upload --repository testpypi dist/*
