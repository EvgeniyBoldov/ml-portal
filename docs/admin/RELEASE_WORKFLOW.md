# Release Workflow

## Ownership

- GitHub is the source repository: application code, local development compose,
  build compose and production templates.
- Production GitLab is cloned by DevOps. It has `origin` pointing at GitLab and
  a `source` remote pointing at GitHub. It owns the real `docker-compose.prod.yml`,
  `release.env` and `.gitlab-ci.yml` copied from the templates in this repository.
- The GitLab Runner is installed on the production VM. It deploys only; images
  are built and pushed from the DevOps workstation.

## Initial production repository setup

1. Clone the production GitLab repository and add the GitHub source remote:

   ```bash
   git remote add source git@github.com:EvgeniyBoldov/ml-portal.git
   ```

2. Copy `docker-compose.prod.example.yml` to `docker-compose.prod.yml` and
   apply production-only mounts/configuration.
3. Copy `release.env.example` to `release.env`, set `IMAGE_REPOSITORY` to the
   internal GitLab Container Registry path, and commit it.
4. Copy `gitlab-ci.example.yml` to `.gitlab-ci.yml`; set protected CI variables
   `PROD_ENV_FILE` and, for private registry authentication, `REGISTRY_USERNAME`
   and `REGISTRY_PASSWORD`.

The registry path must be a single internal DNS endpoint, including its port,
reachable by both the DevOps workstation and production VM. Do not use
`127.0.0.1`, `localhost`, `latest`, or unqualified `ml-portal/...` images.

## Release

On the DevOps workstation:

```bash
make update-source
make release-preview
make test
make release
```

`make release` increments the application patch version, publishes every image
declared in `docker-compose.build.yml`, records the source commit and Alembic
head in `release.env`, and pushes the resulting GitLab release commit. It only
publishes a new base image when the fingerprint of the base Dockerfile or base
requirements changes.

The deploy pipeline checks out that exact release commit, pulls only application
images from `IMAGE_REPOSITORY`, upgrades the database forward to `DB_REVISION`,
and starts the compose stack. A retry of an older pipeline restores its code,
compose and image tags; database downgrades remain a separately controlled
manual operation.
