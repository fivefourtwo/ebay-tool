#!/bin/bash
source .venv/bin/activate
cd backend
uvicorn main:app --reload
