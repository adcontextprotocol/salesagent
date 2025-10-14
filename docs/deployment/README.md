# Deployment Guides

Guides for deploying and operating the AdCP Sales Agent in production.

## Guides

- **[Docker Hub Auth](docker-hub-auth.md)** - Authenticating with Docker Hub for container deployments

## Platform Options

This reference implementation supports deployment to multiple platforms:

### Container Platforms
- **Docker** - Any platform supporting Docker containers
- **Kubernetes** - Enterprise deployments with orchestration
- **Docker Compose** - Multi-container local development

### Cloud Providers
- **AWS** - EC2, ECS, Fargate, EKS
- **Google Cloud Platform** - Compute Engine, GKE, Cloud Run
- **Microsoft Azure** - Virtual Machines, AKS, Container Instances
- **DigitalOcean** - Droplets, App Platform, Kubernetes

### Platform Services
- **Fly.io** - Reference implementation deployment
- **Heroku** - Container-based deployment
- **Railway** - Git-based deployment
- **Render** - Managed container hosting

See [../deployment.md](../deployment.md) for platform-specific deployment guides and configuration.

## Related Documentation

- [../deployment.md](../deployment.md) - Main deployment guide with platform-specific instructions
- [../SETUP.md](../SETUP.md) - Initial setup and configuration
- [../security.md](../security.md) - Production security considerations
