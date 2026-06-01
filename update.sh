#!/bin/bash

cd "$(dirname "$0")/ansible"
ansible-playbook -i inventory/localhost.yml update.yml

