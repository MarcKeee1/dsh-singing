import os
from huggingface_hub import hf_hub_download


def load_custom_model_from_hf(repo_id, model_filename="pytorch_model.bin", config_filename=None):
    local_root = os.environ.get("DSH_SINGING_MODELS")
    if local_root:
        from pathlib import Path
        root = Path(local_root) / repo_id.replace("/", "--")
        model_path = root / model_filename
        if not model_path.is_file():
            raise FileNotFoundError(f"Local singing model missing: {model_path.name}")
        if config_filename is None:
            return str(model_path)
        config_path = root / config_filename
        if not config_path.is_file():
            raise FileNotFoundError(f"Local singing config missing: {config_path.name}")
        return str(model_path), str(config_path)
    os.makedirs("./checkpoints", exist_ok=True)
    model_path = hf_hub_download(repo_id=repo_id, filename=model_filename, cache_dir="./checkpoints")
    if config_filename is None:
        return model_path
    config_path = hf_hub_download(repo_id=repo_id, filename=config_filename, cache_dir="./checkpoints")

    return model_path, config_path
