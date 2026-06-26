#!/bin/sh

/usr/sbin/asterisk -rx "logger rotate"
find /var/log/asterisk -type f  -mtime +7 -delete

