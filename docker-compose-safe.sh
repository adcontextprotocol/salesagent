#!/bin/bash
# Safe docker-compose wrapper that checks port availability first

# Load environment variables
if [ -f .env ]; then
    set -a  # automatically export all variables
    source .env
    set +a
fi

# Check if ports are available
echo "Checking port availability before starting services..."
python3 check_ports.py

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Cannot start services due to port conflicts."
    echo "Please either:"
    echo "  1. Stop the conflicting services"
    echo "  2. Change the ports in your .env file"
    exit 1
fi

# If all ports are available, proceed with docker-compose
echo ""
echo "Starting docker-compose services..."
docker-compose "$@"