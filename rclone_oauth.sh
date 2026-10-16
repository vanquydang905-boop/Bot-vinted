#!/bin/bash
export DISPLAY=:10

# Lancer rclone authorize et capturer l'URL
rclone authorize "drive" --auth-no-open-browser 2>&1
