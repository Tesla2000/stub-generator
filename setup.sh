#!/usr/bin/env bash
set -e

uv sync
pre-commit install --hook-type pre-commit --hook-type pre-push
