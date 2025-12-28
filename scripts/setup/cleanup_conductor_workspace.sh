#!/bin/bash
# cleanup_conductor_workspace.sh - Clean up resources when archiving a Conductor workspace

echo "Cleaning up Conductor workspace: ${CONDUCTOR_WORKSPACE_NAME:-unknown}"

# Stop any running containers and remove workspace-specific volumes
if [ -f "docker-compose.yml" ]; then
    echo "Stopping Docker containers..."
    docker compose down --remove-orphans 2>/dev/null || true

    # Clean up volumes prefixed with this workspace name
    if [ -n "$CONDUCTOR_WORKSPACE_NAME" ]; then
        echo "Removing workspace-specific volumes (${CONDUCTOR_WORKSPACE_NAME}_*)..."
        docker volume ls -q | grep "^${CONDUCTOR_WORKSPACE_NAME}_" | xargs -r docker volume rm 2>/dev/null || true
    fi
fi

echo "Cleanup complete"
