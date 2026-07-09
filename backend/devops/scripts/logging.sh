#!/bin/bash

log() {
    local level="$1"
    local timestamp="$(date +'%Y-%m-%d %H:%M:%S')"
    local message="$2"
    echo "[$level] $timestamp - $message"
}

log_info() {
    echo "[INFO] $(date +'%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo "[ERROR] $(date +'%Y-%m-%d %H:%M:%S') - $1" >&2
}

log_warn() {
    echo "[WARN] $(date +'%Y-%m-%d %H:%M:%S') - $1"
}

log_debug() {
    if [ "$VERBOSE" = true ]; then
        echo "[DEBUG] $(date +'%Y-%m-%d %H:%M:%S') - $1"
    fi
}