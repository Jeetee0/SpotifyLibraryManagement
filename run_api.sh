#!/bin/bash

export PYTHONPATH=${PYTHONPATH:-.}
echo "PYTHONPATH set to ${PYTHONPATH}"

pip install -r requirements.txt

uvicorn spot_lib_mng.api:app --reload --host 0.0.0.0 --port 8080
