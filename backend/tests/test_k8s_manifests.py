"""Guard for the k8s manifests: local-only clinicpilot/*:latest images must
pin imagePullPolicy, because :latest defaults to Always and the README cluster
flow (minikube/kind image load) puts those tags on the node only — a registry
pull can never succeed (permanent ImagePullBackOff)."""

from pathlib import Path

import yaml

K8S_DIR = Path(__file__).resolve().parents[2] / "k8s"


def _clinicpilot_containers() -> list[tuple[Path, dict]]:
    found: list[tuple[Path, dict]] = []
    for path in sorted(K8S_DIR.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            containers = ((doc or {}).get("spec", {}).get("template", {}).get("spec", {})).get("containers", [])
            found.extend((path, c) for c in containers if str(c.get("image", "")).startswith("clinicpilot/"))
    return found


def test_local_latest_images_pin_if_not_present() -> None:
    containers = _clinicpilot_containers()
    assert len(containers) == 3, "backend/ai/frontend — any new clinicpilot container must obey too"
    for path, container in containers:
        assert container.get("imagePullPolicy") == "IfNotPresent", f"{path.name}: {container['image']}"
