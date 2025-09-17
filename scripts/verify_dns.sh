#!/bin/bash

# DNS Verification Script for sales-agent.scope3.com
# Run this script to check if DNS is configured correctly

echo "🔍 Verifying DNS setup for sales-agent.scope3.com"
echo "=================================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check DNS record
check_dns() {
    local record_type=$1
    local domain=$2
    local expected=$3

    echo -n "Checking $record_type record for $domain... "

    result=$(dig +short $record_type $domain)

    if [[ -z "$result" ]]; then
        echo -e "${RED}MISSING${NC}"
        return 1
    elif [[ "$result" == *"$expected"* ]] || [[ -z "$expected" ]]; then
        echo -e "${GREEN}OK${NC} ($result)"
        return 0
    else
        echo -e "${YELLOW}UNEXPECTED${NC} (got: $result)"
        return 1
    fi
}

echo
echo "📍 Checking apex domain records..."

# Check A record
check_dns "A" "sales-agent.scope3.com" "66.241.125.123"
a_result=$?

# Check AAAA record
check_dns "AAAA" "sales-agent.scope3.com" "2a09:8280:1"
aaaa_result=$?

echo
echo "🌟 Checking wildcard subdomain records..."

# Check wildcard CNAME via test subdomain
check_dns "CNAME" "test.sales-agent.scope3.com" "adcp-sales-agent.fly.dev"
wildcard_result=$?

# Check specific tenant subdomains
check_dns "A" "default.sales-agent.scope3.com" "66.241.125.123"
default_result=$?

check_dns "A" "scribd.sales-agent.scope3.com" "66.241.125.123"
scribd_result=$?

echo
echo "🔐 Testing HTTP connectivity (requires certificates)..."

# Test HTTP connectivity
test_http() {
    local url=$1
    echo -n "Testing $url... "

    if curl -s -I --connect-timeout 5 "$url" >/dev/null 2>&1; then
        echo -e "${GREEN}CONNECTED${NC}"
        return 0
    else
        echo -e "${RED}FAILED${NC} (cert needed?)"
        return 1
    fi
}

test_http "https://sales-agent.scope3.com/health"
test_http "https://default.sales-agent.scope3.com/health"
test_http "https://scribd.sales-agent.scope3.com/health"

echo
echo "📋 Summary"
echo "=========="

if [[ $a_result -eq 0 && $aaaa_result -eq 0 && $wildcard_result -eq 0 ]]; then
    echo -e "${GREEN}✅ DNS Configuration: READY${NC}"
    echo "Next steps:"
    echo "1. Run: fly certs create \"sales-agent.scope3.com\" --app adcp-sales-agent"
    echo "2. Run: fly certs create \"*.sales-agent.scope3.com\" --app adcp-sales-agent"
    echo "3. Add DNS validation records when prompted"
else
    echo -e "${RED}❌ DNS Configuration: INCOMPLETE${NC}"
    echo "Please fix the failed DNS records above"
fi

echo
echo "💡 Useful commands:"
echo "- Check DNS propagation: https://www.whatsmydns.net/#A/sales-agent.scope3.com"
echo "- View certificates: fly certs list --app adcp-sales-agent"
echo "- Test with curl: curl -I https://sales-agent.scope3.com/health"
