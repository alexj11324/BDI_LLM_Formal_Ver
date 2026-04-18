## Learned User Preferences
- 用户偏好中文（简体）回复。
- 用户在 `.gitignore` 规则上偏好“通用且递归”的缓存忽略策略，要求举一反三覆盖 ML 场景（如 Python 字节码、训练日志与常见缓存目录）。

## Learned Workspace Facts
- 该仓库的 `requirements.txt` 是精简依赖；开发/测试依赖以 `pyproject.toml` 的 `dev` extras 为准。
- CI 安装依赖应优先使用 `pip install -e ".[dev]"` 以覆盖测试所需包（如 `pandas`、`datasets`）。
- Bridges2 上与 BDI 项目相关的一切环境、cache、日志、临时目录应放在 `/ocean/projects/cis260113p/zjiang9/` 下，禁止把项目依赖安装进 `HOME`。
- Bridges2 上同步代码到远端仓库时，必须使用 Git；禁止手动上传目录、覆盖远端工作区，尤其是在远端工作区已经有未提交改动时。
- Bridges2 的 `RM-shared` 分区有 `2000M/core` 的内存上限；CPU 安装类 job 必须按这个约束申请资源。
- `GLM-4.7-Flash` 在 Bridges2 上优先走 `Apptainer/Singularity` 容器路线，而不是宿主机直装最新 `vLLM` wheel。宿主机方案已经验证会撞上旧 `glibc` / 驱动边界。
- PSC 当前可见的 AI 模块环境过旧，不适合 `GLM-4.7-Flash`；当前更靠谱的基底是 `/ocean/containers/ngc/pytorch/pytorch_25.02-py3.sif` 这类 PSC 提供的 NGC 容器。
