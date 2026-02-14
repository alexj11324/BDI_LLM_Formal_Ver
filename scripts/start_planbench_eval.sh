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

# Resolve repo root and defaults
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/runs/planbench_results"
PYTHON_BIN="${PYTHON_BIN:-python}"

# Check API credentials
if [ -z "$OPENAI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ] && [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo -e "${RED}ERROR: No API credential set${NC}"
    echo ""
    echo "Please set one of:"
    echo "  export OPENAI_API_KEY=sk-..."
    echo "  export GOOGLE_API_KEY=..."
    echo "  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json"
    echo ""
    exit 1
fi

# Create output directory
mkdir -p "${OUTPUT_DIR}"

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
        "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/run_planbench_full.py" \
            --domain blocksworld --max_instances 10 --output_dir "${OUTPUT_DIR}"
        ;;
    2)
        echo -e "${GREEN}Running small test (100 instances)...${NC}"
        "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/run_planbench_full.py" \
            --domain blocksworld --max_instances 100 --output_dir "${OUTPUT_DIR}"
        ;;
    3)
        echo -e "${YELLOW}Running medium test (500 instances)...${NC}"
        echo "This will take approximately 3-5 hours."
        read -p "Continue? [y/N]: " confirm
        if [ "$confirm" = "y" ]; then
            "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/run_planbench_full.py" \
                --domain blocksworld --max_instances 500 --output_dir "${OUTPUT_DIR}"
        fi
        ;;
    4)
        echo -e "${YELLOW}Running full blocksworld (2,207 instances)...${NC}"
        echo "This will take approximately 12-24 hours."
        read -p "Continue? [y/N]: " confirm
        if [ "$confirm" = "y" ]; then
            "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/run_planbench_full.py" \
                --domain blocksworld --output_dir "${OUTPUT_DIR}"
        fi
        ;;
    5)
        echo -e "${GREEN}Running full logistics (572 instances)...${NC}"
        "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/run_planbench_full.py" \
            --domain logistics --output_dir "${OUTPUT_DIR}"
        ;;
    6)
        echo -e "${GREEN}Running full depots (501 instances)...${NC}"
        "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/run_planbench_full.py" \
            --domain depots --output_dir "${OUTPUT_DIR}"
        ;;
    7)
        echo -e "${RED}Running ALL domains (4,430 instances)...${NC}"
        echo "This will take 1-2 DAYS to complete."
        read -p "Are you sure? [y/N]: " confirm
        if [ "$confirm" = "y" ]; then
            "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/run_planbench_full.py" \
                --all_domains --output_dir "${OUTPUT_DIR}"
        fi
        ;;
    8)
        echo "Custom mode - edit run_planbench_full.py directly"
        echo "Example:"
        echo "  python scripts/run_planbench_full.py --domain blocksworld --max_instances 50 --output_dir runs/planbench_results"
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✅ Evaluation complete!${NC}"
echo ""
echo "Results saved in: ${OUTPUT_DIR}/"
