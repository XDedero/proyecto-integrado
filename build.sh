#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

python -m pip install --upgrade 'pip>=26.2,<27'
python -m pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
