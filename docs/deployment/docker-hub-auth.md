# Docker Image Registries

The AdCP Sales Agent is published to two container registries on every release:

| Registry | Image | Best For |
|----------|-------|----------|
| **GitHub Container Registry** | `ghcr.io/adcontextprotocol/salesagent` | GitHub-integrated workflows |
| **Docker Hub** | `adcontextprotocol/salesagent` | Universal access, all cloud providers |

## Pulling Images

### Docker Hub (Recommended for simplicity)
```bash
docker pull adcontextprotocol/salesagent:latest
docker pull adcontextprotocol/salesagent:0.2.1  # specific version
```

### GitHub Container Registry
```bash
docker pull ghcr.io/adcontextprotocol/salesagent:latest
```

## Cloud Provider Compatibility

| Cloud Provider | Docker Hub | ghcr.io | Notes |
|----------------|------------|---------|-------|
| **GCP (Cloud Run/GKE)** | Native | Requires setup | Docker Hub is zero-config |
| **AWS (ECS/EKS)** | Native | Pull-through cache | Docker Hub is simpler |
| **Azure (Container Apps/AKS)** | Native | Native | Both work well |
| **DigitalOcean** | Native | Native | Both work well |
| **Fly.io** | Native | Native | Both work well |

## GCP Deployment

With Docker Hub, GCP Cloud Run deployment is straightforward:

```bash
gcloud run deploy salesagent \
  --image adcontextprotocol/salesagent:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

No authentication or registry configuration needed.

## Rate Limits

### Docker Hub
- **Unauthenticated**: 10 pulls/hour per IP (as of April 2025)
- **Free authenticated**: 100 pulls/6 hours
- **Pro account**: Unlimited

For production deployments with frequent pulls, authenticate or use ghcr.io.

### GitHub Container Registry
- **Public images**: Unlimited pulls, no authentication needed
- **Private images**: Requires GitHub PAT

## Authenticating to Docker Hub (Optional)

If you hit rate limits, authenticate:

```bash
# Interactive login
docker login

# Or with credentials
echo $DOCKER_HUB_TOKEN | docker login -u $DOCKER_HUB_USERNAME --password-stdin
```

### In Kubernetes
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: dockerhub-secret
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: <base64-encoded-docker-config>
---
apiVersion: v1
kind: Pod
spec:
  imagePullSecrets:
    - name: dockerhub-secret
  containers:
    - name: salesagent
      image: adcontextprotocol/salesagent:latest
```

## Using ghcr.io with GCP (Alternative)

If you prefer ghcr.io, set up an Artifact Registry remote repository:

```bash
# Create remote repository as ghcr.io proxy
gcloud artifacts repositories create ghcr \
  --repository-format=docker \
  --location=us-central1 \
  --mode=remote-repository \
  --remote-docker-repo=https://ghcr.io

# Reference via Artifact Registry
gcloud run deploy salesagent \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT/ghcr/adcontextprotocol/salesagent:latest \
  --platform managed \
  --region us-central1
```

## CI/CD Configuration

To publish to Docker Hub in your own fork, add these GitHub repository secrets:
- `DOCKER_HUB_USERNAME`: Your Docker Hub username or organization
- `DOCKER_HUB_TOKEN`: Docker Hub access token (not password)

Create a token at: https://hub.docker.com/settings/security
