#!/bin/bash
cd /app

pip install pytest pytest-django > /dev/null 2>&1
mkdir -p /logs/verifier

PYTHONPATH=/tests:/app DJANGO_SETTINGS_MODULE=test_settings \
pytest /tests/test_solution.py -v --ds=test_settings 2>&1

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
