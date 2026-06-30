#!/usr/bin/env bash

set -e

uv run ruff format .
uv run ruff check .
uv run mypy src tests
uv run pytest
