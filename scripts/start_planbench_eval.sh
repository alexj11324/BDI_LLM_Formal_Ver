#!/bin/bash
# Quick start script for PlanBench evaluation

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=================================================="
echo "  PlanBench Full Benchmark - Quick Start"
echo "=================================================="
echo ""

# Check API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}❌ ERROR: OPENAI_API_KEY not set${NC}"
    echo ""
    echo "Please set your API key:"
    echo "  export OPENAI_API_KEY=sk-..."
    echo ""
    exit 1
fi

# Create output directory
mkdir -p planbench_results

# Show menu
echo "Select evaluation mode:"
echo ""
echo "  1) Quick test (10 instances, blocksworld only)"
echo "  2) Small test (100 instances, blocksworld only)"
echo "  3) Medium test (500 instances, blocksworld only)"
echo "  4) Full blocksworld (2,207 instances)"
echo "  5) Full logistics (572 instances)"
echo "  6) Full depots (501 instances)"
echo "  7) All domains (4,430 instances) - LONG RUN"
echo "  8) Custom (specify parameters)"
echo ""
read -p "Enter choice [1-8]: " choice

case $choice in
    1)
        echo -e "${GREEN}Running quick test (10 instances)...${NC}"
        python run_planbench_full.py --domain blocksworld --max_instances 10
        ;;
    2)
        echo -e "${GREEN}Running small test (100 instances)...${NC}"
        python run_planbench_full.py --domain blocksworld --max_instances 100
        ;;
    3)
        echo -e "${YELLOW}Running medium test (500 instances)...${NC}"
        echo "This will take approximately 3-5 hours."
        read -p "Continue? [y/N]: " confirm
        if [ "$confirm" = "y" ]; then
            python run_planbench_full.py --domain blocksworld --max_instances 500
        fi
        ;;
    4)
        echo -e "${YELLOW}Running full blocksworld (2,207 instances)...${NC}"
        echo "This will take approximately 12-24 hours."
        read -p "Continue? [y/N]: " confirm
        if [ "$confirm" = "y" ]; then
            python run_planbench_full.py --domain blocksworld
        fi
        ;;
    5)
        echo -e "${GREEN}Running full logistics (572 instances)...${NC}"
        python run_planbench_full.py --domain logistics
        ;;
    6)
        echo -e "${GREEN}Running full depots (501 instances)...${NC}"
        python run_planbench_full.py --domain depots
        ;;
    7)
        echo -e "${RED}Running ALL domains (4,430 instances)...${NC}"
        echo "This will take 1-2 DAYS to complete."
        read -p "Are you sure? [y/N]: " confirm
        if [ "$confirm" = "y" ]; then
            python run_planbench_full.py --all_domains
        fi
        ;;
    8)
        echo "Custom mode - edit run_planbench_full.py directly"
        echo "Example:"
        echo "  python run_planbench_full.py --domain blocksworld --max_instances 50"
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✅ Evaluation complete!${NC}"
echo ""
echo "Results saved in: planbench_results/"
echo ""
echo "To analyze results, run:"
echo "  python analyze_planbench_results.py planbench_results/results_*.json"
