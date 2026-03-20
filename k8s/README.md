# Jennifer — Kubernetes Manifests

Compatible with Docker Desktop K8s and microk8s.

SD/LLM backends are external (Tailscale) — only the bot pod runs in-cluster.

## Quick Start

### 1. Generate the config secret
```bash
kubectl create secret generic jennifer-config \
  --from-file=config.json=./config/config.json \
  -n jennifer --dry-run=client -o yaml > k8s/secret.yaml
```

### 2. Deploy
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
```

Or with kustomize (after secret.yaml is generated):
```bash
kubectl apply -k k8s/
```

### 3. Check status
```bash
kubectl get pods -n jennifer
kubectl logs -n jennifer deploy/jennifer -f
```

## Notes

- `secret.yaml` is gitignored — never commit it
- `OpenClawGateway` in config.json must be the Tailscale/external URL (not localhost)
- SD and LLM endpoints in config.json must be Tailscale-reachable hostnames
- For microk8s: enable storage addon first: `microk8s enable storage`
- For GPU nodes (future): add `nvidia.com/gpu: 1` resource limit to the LLM container
