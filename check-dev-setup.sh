#!/bin/bash

# ML Portal Development Setup Checker
echo "🔍 ML Portal Development Setup Checker"
echo "========================================"

# Check Docker
echo "📦 Checking Docker..."
if command -v docker &> /dev/null; then
    docker_version=$(docker --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
    echo "   ✅ Docker $docker_version installed"
else
    echo "   ❌ Docker not installed"
    exit 1
fi

# Check Docker Compose
echo "📋 Checking Docker Compose..."
if command -v docker-compose &> /dev/null; then
    compose_version=$(docker-compose --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
    echo "   ✅ Docker Compose $compose_version installed"
elif docker compose version &> /dev/null; then
    compose_version=$(docker compose version | grep -oE '[0-9]+\.[0-9]+' | head -1)
    echo "   ✅ Docker Compose (plugin) $compose_version installed"
else
    echo "   ❌ Docker Compose not installed"
    exit 1
fi

# Check system resources
echo "💾 Checking system resources..."
total_mem=$(free -m | awk 'NR==2{printf "%dGB", $2/1024}')
total_disk=$(df -BG . | awk 'NR==2{print $4}' | sed 's/G//')

echo "   📊 RAM: $total_mem"
echo "   💽 Free disk: ${total_disk}GB"

if [ ${total_mem%.*} -lt 8 ]; then
    echo "   ⚠️  Warning: Recommended 8GB+ RAM for full dev environment"
fi

if [ ${total_disk} -lt 20 ]; then
    echo "   ⚠️  Warning: Recommended 20GB+ free disk space"
fi

# Check required files
echo "📁 Checking required files..."
required_files=(
    "docker-compose.dev.yml"
    "env.example"
    "infra/docker/api/Dockerfile.api"
    "apps/web/package.json"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✅ $file"
    else
        echo "   ❌ Missing $file"
        exit 1
    fi
done

# Check environment file
if [ -f ".env" ]; then
    echo "   ✅ .env file exists"
else
    echo "   ⚠️  .env file not found (will use env.dev)"
fi

# Check models directory
if [ -d "models" ] && [ "$(ls -A models)" ]; then
    echo "   ✅ ML models directory exists and not empty"
else
    echo "   ⚠️  ML models directory is empty (services will work but ML features may be limited)"
fi

# Port availability check
echo "🔌 Checking port availability..."
ports=("5432" "6379" "8080" "9000" "5173")

for port in "${ports[@]}"; do
    if lsof -i :$port &> /dev/null; then
        echo "   ⚠️  Port $port is in use"
    else
        echo "   ✅ Port $port is available"
    fi
done

echo ""
echo "🎉 Setup check completed!"
echo ""
echo "Next steps:"
echo "1. Create .env file:"
echo "   cp env.example .env"
echo ""
echo "2. Start development environment:"
echo "   docker-compose -f docker-compose.dev.yml up --build"
echo ""
echo "3. Access applications:"
echo "   Frontend:    http://localhost:5173"
echo "   API:         http://localhost:8000"
echo "   MinIO UI:    http://localhost:9001"
echo "   RabbitMQ:    http://localhost:15672"
echo ""
echo "4. Default admin user:"
echo "   Login: admin"
echo "   Password: admin123"
