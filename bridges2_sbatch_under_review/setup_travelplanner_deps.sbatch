#!/bin/bash
#SBATCH --job-name=glm47_tp_setup
#SBATCH --account=cis260113p
#SBATCH --partition=RM-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_tp_setup_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_tp_setup_%j.err

set -euo pipefail

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

set -a
source "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/bdi_env.env"
set +a

export PYTHONPATH="${BDI_REPO_ROOT}:${PYTHONPATH:-}"

TP_DIR="${BDI_PROJECT_ROOT}/TravelPlanner_official"

echo "=== TravelPlanner dependency setup ==="
echo "Node: $(hostname)"
echo "BDI_PROJECT_ROOT: ${BDI_PROJECT_ROOT}"
echo "TravelPlanner target: ${TP_DIR}"
echo "HF_HOME: ${HF_HOME}"
date
print_storage_snapshot "before setup"

# ---------------------------------------------------------------------------
# Step 1: Clone TravelPlanner repository if not already present
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 1: TravelPlanner repo ==="
if [[ -d "${TP_DIR}" ]]; then
    echo "SKIP: ${TP_DIR} already exists"
    echo "Existing contents (top-level):"
    ls "${TP_DIR}"
else
    echo "Cloning TravelPlanner into ${TP_DIR} ..."
    git clone --depth 1 https://github.com/OSU-NLP-Group/TravelPlanner.git "${TP_DIR}"
    echo "Clone complete."
fi

# ---------------------------------------------------------------------------
# Step 2: Verify required database/data files
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 2: Database file check ==="

DB_DIR="${TP_DIR}/database"
if [[ -d "${DB_DIR}" ]]; then
    echo "Contents of ${DB_DIR} (recursive csv/json files):"
    find "${DB_DIR}" -maxdepth 3 \( -name "*.csv" -o -name "*.json" -o -name "*.db" \) | sort
else
    echo "WARNING: ${DB_DIR} not found — database directory missing from clone"
fi

REQUIRED_FILES=(
    "poi_detail.csv"
    "flight.csv"
    "google_distance_matrix.csv"
    "attraction.csv"
    "accommodations.csv"
)

ALL_FOUND=1
for fname in "${REQUIRED_FILES[@]}"; do
    found=$(find "${TP_DIR}" -maxdepth 5 -name "${fname}" 2>/dev/null | head -1)
    if [[ -n "${found}" ]]; then
        echo "FOUND: ${found}"
    else
        echo "MISSING: ${fname} (not found under ${TP_DIR})"
        ALL_FOUND=0
    fi
done

if [[ "${ALL_FOUND}" -eq 1 ]]; then
    echo "All 5 required database files verified."
else
    echo ""
    echo "WARNING: One or more database files are missing."
    echo "The official TravelPlanner dataset files may need to be downloaded separately"
    echo "from the HuggingFace Hub (osunlp/TravelPlanner) or the project's data README."
    echo "Continuing — missing files will cause eval failures but not this setup job."
fi

# ---------------------------------------------------------------------------
# Step 3: Verify evaluation script exists
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 3: eval.py check ==="
EVAL_SCRIPT="${TP_DIR}/evaluation/eval.py"
if [[ -f "${EVAL_SCRIPT}" ]]; then
    echo "FOUND: ${EVAL_SCRIPT}"
else
    echo "ERROR: ${EVAL_SCRIPT} not found — required by src/bdi_llm/travelplanner/official.py" >&2
    echo "Listing ${TP_DIR}/evaluation/ if it exists:"
    if [[ -d "${TP_DIR}/evaluation" ]]; then
        ls "${TP_DIR}/evaluation/"
    else
        echo "  (evaluation/ directory does not exist)"
    fi
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 4: Pre-fetch HuggingFace dataset
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 4: HuggingFace dataset prefetch ==="
echo "HF_HOME=${HF_HOME}"

# bdi_env.env sets TRANSFORMERS_OFFLINE=1 and HF_DATASETS_OFFLINE=1 for
# production eval jobs. We must unset them here so the download actually runs.
unset TRANSFORMERS_OFFLINE
unset HF_DATASETS_OFFLINE
export TRANSFORMERS_OFFLINE=0
export HF_DATASETS_OFFLINE=0

echo "Fetching osunlp/TravelPlanner validation split ..."
python - <<'PY'
import sys

try:
    from datasets import load_dataset
    print("Loading validation split...")
    load_dataset("osunlp/TravelPlanner", "validation")
    print("validation split OK")
    print("Loading test split...")
    load_dataset("osunlp/TravelPlanner", "test")
    print("test split OK")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PY

echo "HuggingFace dataset prefetch complete."

# ---------------------------------------------------------------------------
# Step 5: Storage snapshot
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 5: Storage snapshot ==="
echo "TravelPlanner directory size:"
timeout 30s du -sh "${TP_DIR}" 2>/dev/null || echo "snapshot_timeout ${TP_DIR}"
echo "HF_HOME size:"
timeout 30s du -sh "${HF_HOME}" 2>/dev/null || echo "snapshot_timeout ${HF_HOME}"

date
print_storage_snapshot "after setup"

echo ""
echo "=== Setup complete ==="
echo "TravelPlanner: ${TP_DIR}"
echo "HuggingFace cache: ${HF_HOME}"
