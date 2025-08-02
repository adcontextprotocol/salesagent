#!/bin/bash
# Manual test script for CI database initialization

echo "🧪 Manual CI Database Test"
echo "========================="

# Test 1: SQLite (default)
echo -e "\n1️⃣ Testing with SQLite..."
DB_TYPE=sqlite DATABASE_URL=sqlite:///test_ci.db python init_database_ci.py

# Test 2: PostgreSQL (if available locally)
echo -e "\n2️⃣ Testing with PostgreSQL..."
echo "If you have PostgreSQL running locally, use:"
echo "DB_TYPE=postgresql DATABASE_URL=postgresql://user:pass@localhost:5432/testdb python init_database_ci.py"

# Test 3: PostgreSQL with Docker
echo -e "\n3️⃣ Testing with PostgreSQL (Docker)..."
echo "To test with Docker PostgreSQL:"
echo "docker run -d --name test-pg -e POSTGRES_PASSWORD=test -p 5433:5432 postgres:15"
echo "# Wait a few seconds for it to start"
echo "DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres python init_database_ci.py"
echo "docker stop test-pg && docker rm test-pg"