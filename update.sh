#!/bin/bash

if [ "$(id -un)" != "root" ]; then
    exec sudo "$0" "$@"
fi

cd "$(dirname "$0")/ansible"
ansible-playbook -i inventory/localhost.yml update.yml

