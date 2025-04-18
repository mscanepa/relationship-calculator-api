#!/bin/bash
cd "$(dirname "$0")"
export PYTHONPATH=$PYTHONPATH:$(pwd)
uvicorn main:app --reload --host 0.0.0.0 --port 8001 