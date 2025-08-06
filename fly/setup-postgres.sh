#!/bin/bash
# Setup PostgreSQL for AdCP Sales Agent on Fly.io

echo "Setting up PostgreSQL for AdCP Sales Agent on Fly.io..."

# Create PostgreSQL cluster
echo "Creating PostgreSQL cluster..."
fly postgres create --name adcp-db \
  --region iad \
  --initial-cluster-size 1 \
  --vm-size shared-cpu-1x \
  --volume-size 10

# Wait a moment for the database to be ready
echo "Waiting for database to be ready..."
sleep 10

# Attach the database to the app
echo "Attaching database to app..."
fly postgres attach adcp-db --app adcp-sales-agent

echo "PostgreSQL setup complete!"
echo ""
echo "The DATABASE_URL secret has been automatically set."
echo "You can connect to the database using:"
echo "  fly postgres connect -a adcp-db"