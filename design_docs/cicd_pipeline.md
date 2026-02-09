# CI/CD Pipeline Specification

## Overview

This document specifies the complete CI/CD pipeline for Curious Now, using GitHub Actions for automation. The pipeline handles code quality checks, testing, building, and deployment across multiple environments.

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GitHub Repository                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │   PR/Push   │───▶│    Lint     │───▶│    Test     │───▶│    Build    │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│                                                                    │        │
│                                                                    ▼        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ Production  │◀───│   Staging   │◀───│  Preview    │◀───│   Docker    │  │
│  │   Deploy    │    │   Deploy    │    │   Deploy    │    │    Push     │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Environments

| Environment | Trigger | URL Pattern | Purpose |
|-------------|---------|-------------|---------|
| Preview | PR opened/updated | `pr-{number}.preview.curious.now` | Feature testing |
| Staging | Push to `main` | `staging.curious.now` | Integration testing |
| Production | Manual approval or tag | `curious.now` | Live users |

---

## Workflow Files

### 1. Pull Request Workflow

`.github/workflows/pr.yml`

```yaml
name: Pull Request

on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened]

concurrency:
  group: pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true

env:
  NODE_VERSION: '20'
  PYTHON_VERSION: '3.11'
  PNPM_VERSION: '8'

jobs:
  # ─────────────────────────────────────────────────────────────────
  # Code Quality Checks
  # ─────────────────────────────────────────────────────────────────
  lint-frontend:
    name: Lint Frontend
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup pnpm
        uses: pnpm/action-setup@v2
        with:
          version: ${{ env.PNPM_VERSION }}

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: 'pnpm'
          cache-dependency-path: frontend/pnpm-lock.yaml

      - name: Install dependencies
        working-directory: frontend
        run: pnpm install --frozen-lockfile

      - name: Run ESLint
        working-directory: frontend
        run: pnpm lint

      - name: Run TypeScript check
        working-directory: frontend
        run: pnpm typecheck

      - name: Run Prettier check
        working-directory: frontend
        run: pnpm format:check

  lint-backend:
    name: Lint Backend
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync --frozen

      - name: Run Ruff linter
        run: uv run ruff check .

      - name: Run Ruff formatter check
        run: uv run ruff format --check .

      - name: Run mypy
        run: uv run mypy src/

  # ─────────────────────────────────────────────────────────────────
  # Testing
  # ─────────────────────────────────────────────────────────────────
  test-frontend:
    name: Test Frontend
    runs-on: ubuntu-latest
    needs: lint-frontend
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup pnpm
        uses: pnpm/action-setup@v2
        with:
          version: ${{ env.PNPM_VERSION }}

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: 'pnpm'
          cache-dependency-path: frontend/pnpm-lock.yaml

      - name: Install dependencies
        working-directory: frontend
        run: pnpm install --frozen-lockfile

      - name: Run unit tests
        working-directory: frontend
        run: pnpm test:coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: frontend/coverage/lcov.info
          flags: frontend
          token: ${{ secrets.CODECOV_TOKEN }}

  test-backend:
    name: Test Backend
    runs-on: ubuntu-latest
    needs: lint-backend
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: curious_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync --frozen

      - name: Run migrations
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/curious_test
        run: uv run alembic upgrade head

      - name: Run tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/curious_test
          REDIS_URL: redis://localhost:6379
          ENVIRONMENT: test
        run: uv run pytest --cov=src --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: coverage.xml
          flags: backend
          token: ${{ secrets.CODECOV_TOKEN }}

  test-e2e:
    name: E2E Tests
    runs-on: ubuntu-latest
    needs: [test-frontend, test-backend]
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: curious_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports:
          - 6379:6379
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup pnpm
        uses: pnpm/action-setup@v2
        with:
          version: ${{ env.PNPM_VERSION }}

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: 'pnpm'
          cache-dependency-path: frontend/pnpm-lock.yaml

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install backend dependencies
        run: uv sync --frozen

      - name: Install frontend dependencies
        working-directory: frontend
        run: pnpm install --frozen-lockfile

      - name: Install Playwright browsers
        working-directory: frontend
        run: pnpm exec playwright install --with-deps chromium

      - name: Run migrations
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/curious_test
        run: uv run alembic upgrade head

      - name: Seed test data
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/curious_test
        run: uv run python scripts/seed_test_data.py

      - name: Start backend
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/curious_test
          REDIS_URL: redis://localhost:6379
          ENVIRONMENT: test
        run: |
          uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 &
          sleep 5

      - name: Build frontend
        working-directory: frontend
        env:
          NEXT_PUBLIC_API_URL: http://localhost:8000
        run: pnpm build

      - name: Start frontend
        working-directory: frontend
        run: |
          pnpm start &
          sleep 5

      - name: Run Playwright tests
        working-directory: frontend
        env:
          PLAYWRIGHT_BASE_URL: http://localhost:3000
        run: pnpm test:e2e

      - name: Upload Playwright report
        uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 7

  # ─────────────────────────────────────────────────────────────────
  # Build Docker Images
  # ─────────────────────────────────────────────────────────────────
  build-images:
    name: Build Docker Images
    runs-on: ubuntu-latest
    needs: [test-frontend, test-backend]
    permissions:
      contents: read
      packages: write
    outputs:
      frontend-image: ${{ steps.meta-frontend.outputs.tags }}
      backend-image: ${{ steps.meta-backend.outputs.tags }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata (frontend)
        id: meta-frontend
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}/frontend
          tags: |
            type=ref,event=pr
            type=sha,prefix=pr-${{ github.event.pull_request.number }}-

      - name: Build and push frontend
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          file: ./frontend/Dockerfile
          push: true
          tags: ${{ steps.meta-frontend.outputs.tags }}
          labels: ${{ steps.meta-frontend.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          build-args: |
            NEXT_PUBLIC_API_URL=${{ vars.PREVIEW_API_URL }}

      - name: Extract metadata (backend)
        id: meta-backend
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}/backend
          tags: |
            type=ref,event=pr
            type=sha,prefix=pr-${{ github.event.pull_request.number }}-

      - name: Build and push backend
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile
          push: true
          tags: ${{ steps.meta-backend.outputs.tags }}
          labels: ${{ steps.meta-backend.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ─────────────────────────────────────────────────────────────────
  # Preview Deployment
  # ─────────────────────────────────────────────────────────────────
  deploy-preview:
    name: Deploy Preview
    runs-on: ubuntu-latest
    needs: [build-images, test-e2e]
    environment:
      name: preview
      url: https://pr-${{ github.event.pull_request.number }}.preview.curious.now
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup kubectl
        uses: azure/setup-kubectl@v3

      - name: Configure kubeconfig
        run: |
          mkdir -p ~/.kube
          echo "${{ secrets.KUBE_CONFIG_PREVIEW }}" | base64 -d > ~/.kube/config

      - name: Deploy to preview
        env:
          PR_NUMBER: ${{ github.event.pull_request.number }}
          FRONTEND_IMAGE: ${{ needs.build-images.outputs.frontend-image }}
          BACKEND_IMAGE: ${{ needs.build-images.outputs.backend-image }}
        run: |
          # Create namespace if not exists
          kubectl create namespace preview-pr-${PR_NUMBER} --dry-run=client -o yaml | kubectl apply -f -

          # Apply Kubernetes manifests with envsubst
          envsubst < k8s/preview/deployment.yaml | kubectl apply -f -
          envsubst < k8s/preview/service.yaml | kubectl apply -f -
          envsubst < k8s/preview/ingress.yaml | kubectl apply -f -

          # Wait for rollout
          kubectl rollout status deployment/curious-frontend -n preview-pr-${PR_NUMBER} --timeout=300s
          kubectl rollout status deployment/curious-backend -n preview-pr-${PR_NUMBER} --timeout=300s

      - name: Comment PR with preview URL
        uses: actions/github-script@v7
        with:
          script: |
            const prNumber = context.payload.pull_request.number;
            const previewUrl = `https://pr-${prNumber}.preview.curious.now`;

            // Check if comment already exists
            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: prNumber,
            });

            const botComment = comments.find(c =>
              c.user.type === 'Bot' && c.body.includes('Preview deployment')
            );

            const body = `## 🚀 Preview deployment ready!

            | Environment | URL |
            |-------------|-----|
            | Frontend | ${previewUrl} |
            | API | ${previewUrl}/api |

            This preview will be automatically deleted when the PR is closed.`;

            if (botComment) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                comment_id: botComment.id,
                body,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: prNumber,
                body,
              });
            }
```

### 2. Main Branch Workflow (Staging)

`.github/workflows/staging.yml`

```yaml
name: Deploy Staging

on:
  push:
    branches: [main]

concurrency:
  group: staging
  cancel-in-progress: false

env:
  NODE_VERSION: '20'
  PYTHON_VERSION: '3.11'
  PNPM_VERSION: '8'

jobs:
  # ─────────────────────────────────────────────────────────────────
  # Build and Push Production Images
  # ─────────────────────────────────────────────────────────────────
  build:
    name: Build Images
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      frontend-image: ${{ steps.meta-frontend.outputs.tags }}
      backend-image: ${{ steps.meta-backend.outputs.tags }}
      version: ${{ steps.version.outputs.version }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate version
        id: version
        run: |
          VERSION=$(git describe --tags --always --dirty)
          echo "version=${VERSION}" >> $GITHUB_OUTPUT

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata (frontend)
        id: meta-frontend
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}/frontend
          tags: |
            type=sha
            type=raw,value=staging
            type=raw,value=${{ steps.version.outputs.version }}

      - name: Build and push frontend
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          file: ./frontend/Dockerfile
          push: true
          tags: ${{ steps.meta-frontend.outputs.tags }}
          labels: ${{ steps.meta-frontend.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          build-args: |
            NEXT_PUBLIC_API_URL=${{ vars.STAGING_API_URL }}
            NEXT_PUBLIC_SENTRY_DSN=${{ vars.SENTRY_DSN }}

      - name: Extract metadata (backend)
        id: meta-backend
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}/backend
          tags: |
            type=sha
            type=raw,value=staging
            type=raw,value=${{ steps.version.outputs.version }}

      - name: Build and push backend
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile
          push: true
          tags: ${{ steps.meta-backend.outputs.tags }}
          labels: ${{ steps.meta-backend.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ─────────────────────────────────────────────────────────────────
  # Database Migration
  # ─────────────────────────────────────────────────────────────────
  migrate:
    name: Run Migrations
    runs-on: ubuntu-latest
    needs: build
    environment: staging
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync --frozen

      - name: Run migrations
        env:
          DATABASE_URL: ${{ secrets.STAGING_DATABASE_URL }}
        run: uv run alembic upgrade head

  # ─────────────────────────────────────────────────────────────────
  # Deploy to Staging
  # ─────────────────────────────────────────────────────────────────
  deploy:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: [build, migrate]
    environment:
      name: staging
      url: https://staging.curious.now
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup kubectl
        uses: azure/setup-kubectl@v3

      - name: Configure kubeconfig
        run: |
          mkdir -p ~/.kube
          echo "${{ secrets.KUBE_CONFIG_STAGING }}" | base64 -d > ~/.kube/config

      - name: Deploy to staging
        env:
          FRONTEND_IMAGE: ghcr.io/${{ github.repository }}/frontend:${{ needs.build.outputs.version }}
          BACKEND_IMAGE: ghcr.io/${{ github.repository }}/backend:${{ needs.build.outputs.version }}
          VERSION: ${{ needs.build.outputs.version }}
        run: |
          envsubst < k8s/staging/deployment.yaml | kubectl apply -f -
          kubectl rollout status deployment/curious-frontend -n staging --timeout=300s
          kubectl rollout status deployment/curious-backend -n staging --timeout=300s

      - name: Run smoke tests
        run: |
          # Wait for services to be ready
          sleep 30

          # Health checks
          curl -f https://staging.curious.now/api/health || exit 1
          curl -f https://staging.curious.now || exit 1

          echo "Smoke tests passed!"

      - name: Notify Slack
        if: always()
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "Staging deployment ${{ job.status }}",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*Staging Deployment ${{ job.status == 'success' && '✅' || '❌' }}*\n\nVersion: `${{ needs.build.outputs.version }}`\nCommit: <${{ github.server_url }}/${{ github.repository }}/commit/${{ github.sha }}|${{ github.sha }}>"
                  }
                }
              ]
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

### 3. Production Deployment Workflow

`.github/workflows/production.yml`

```yaml
name: Deploy Production

on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Version to deploy (e.g., v1.2.3 or staging)'
        required: true
        default: 'staging'
      skip_approval:
        description: 'Skip manual approval (emergency only)'
        required: false
        type: boolean
        default: false

concurrency:
  group: production
  cancel-in-progress: false

jobs:
  # ─────────────────────────────────────────────────────────────────
  # Validate Version
  # ─────────────────────────────────────────────────────────────────
  validate:
    name: Validate Version
    runs-on: ubuntu-latest
    outputs:
      frontend-image: ${{ steps.resolve.outputs.frontend-image }}
      backend-image: ${{ steps.resolve.outputs.backend-image }}
    steps:
      - name: Resolve version to images
        id: resolve
        run: |
          VERSION="${{ github.event.inputs.version }}"

          # Check if images exist
          FRONTEND_IMAGE="ghcr.io/${{ github.repository }}/frontend:${VERSION}"
          BACKEND_IMAGE="ghcr.io/${{ github.repository }}/backend:${VERSION}"

          # Verify images exist (will fail if not)
          docker manifest inspect ${FRONTEND_IMAGE} > /dev/null
          docker manifest inspect ${BACKEND_IMAGE} > /dev/null

          echo "frontend-image=${FRONTEND_IMAGE}" >> $GITHUB_OUTPUT
          echo "backend-image=${BACKEND_IMAGE}" >> $GITHUB_OUTPUT
        env:
          DOCKER_CLI_EXPERIMENTAL: enabled

  # ─────────────────────────────────────────────────────────────────
  # Manual Approval Gate
  # ─────────────────────────────────────────────────────────────────
  approval:
    name: Approval Gate
    runs-on: ubuntu-latest
    needs: validate
    if: ${{ github.event.inputs.skip_approval != 'true' }}
    environment: production-approval
    steps:
      - name: Approval received
        run: echo "Deployment approved"

  # ─────────────────────────────────────────────────────────────────
  # Database Migration
  # ─────────────────────────────────────────────────────────────────
  migrate:
    name: Run Migrations
    runs-on: ubuntu-latest
    needs: [validate, approval]
    if: always() && needs.validate.result == 'success' && (needs.approval.result == 'success' || needs.approval.result == 'skipped')
    environment: production
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.inputs.version }}

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync --frozen

      - name: Create migration backup
        env:
          DATABASE_URL: ${{ secrets.PRODUCTION_DATABASE_URL }}
        run: |
          # Record current migration version for rollback
          uv run alembic current > /tmp/migration-before.txt
          echo "Current migration: $(cat /tmp/migration-before.txt)"

      - name: Run migrations
        env:
          DATABASE_URL: ${{ secrets.PRODUCTION_DATABASE_URL }}
        run: uv run alembic upgrade head

  # ─────────────────────────────────────────────────────────────────
  # Blue-Green Deployment
  # ─────────────────────────────────────────────────────────────────
  deploy:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: [validate, migrate]
    environment:
      name: production
      url: https://curious.now
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup kubectl
        uses: azure/setup-kubectl@v3

      - name: Configure kubeconfig
        run: |
          mkdir -p ~/.kube
          echo "${{ secrets.KUBE_CONFIG_PRODUCTION }}" | base64 -d > ~/.kube/config

      - name: Determine deployment slot
        id: slot
        run: |
          # Check which slot is currently active
          CURRENT=$(kubectl get service curious-frontend -n production -o jsonpath='{.spec.selector.slot}' 2>/dev/null || echo "blue")
          if [ "$CURRENT" = "blue" ]; then
            TARGET="green"
          else
            TARGET="blue"
          fi
          echo "current=${CURRENT}" >> $GITHUB_OUTPUT
          echo "target=${TARGET}" >> $GITHUB_OUTPUT

      - name: Deploy to inactive slot
        env:
          FRONTEND_IMAGE: ${{ needs.validate.outputs.frontend-image }}
          BACKEND_IMAGE: ${{ needs.validate.outputs.backend-image }}
          SLOT: ${{ steps.slot.outputs.target }}
          VERSION: ${{ github.event.inputs.version }}
        run: |
          envsubst < k8s/production/deployment-${SLOT}.yaml | kubectl apply -f -
          kubectl rollout status deployment/curious-frontend-${SLOT} -n production --timeout=600s
          kubectl rollout status deployment/curious-backend-${SLOT} -n production --timeout=600s

      - name: Run health checks on new deployment
        env:
          SLOT: ${{ steps.slot.outputs.target }}
        run: |
          # Get pod IPs and test directly
          FRONTEND_POD=$(kubectl get pod -n production -l app=curious-frontend,slot=${SLOT} -o jsonpath='{.items[0].status.podIP}')
          BACKEND_POD=$(kubectl get pod -n production -l app=curious-backend,slot=${SLOT} -o jsonpath='{.items[0].status.podIP}')

          # Health checks
          kubectl exec -n production deploy/curious-backend-${SLOT} -- curl -f http://localhost:8000/health
          kubectl exec -n production deploy/curious-frontend-${SLOT} -- curl -f http://localhost:3000/api/health

      - name: Switch traffic to new slot
        env:
          SLOT: ${{ steps.slot.outputs.target }}
        run: |
          kubectl patch service curious-frontend -n production -p "{\"spec\":{\"selector\":{\"slot\":\"${SLOT}\"}}}"
          kubectl patch service curious-backend -n production -p "{\"spec\":{\"selector\":{\"slot\":\"${SLOT}\"}}}"

      - name: Verify production
        run: |
          sleep 10
          curl -f https://curious.now/api/health || exit 1
          curl -f https://curious.now || exit 1

      - name: Scale down old slot
        env:
          OLD_SLOT: ${{ steps.slot.outputs.current }}
        run: |
          # Keep old slot running for 10 minutes for quick rollback
          echo "Old slot ${OLD_SLOT} kept running for rollback capability"
          # Schedule scale-down after 10 minutes
          kubectl annotate deployment curious-frontend-${OLD_SLOT} -n production scale-down-at="$(date -d '+10 minutes' -Iseconds)" --overwrite
          kubectl annotate deployment curious-backend-${OLD_SLOT} -n production scale-down-at="$(date -d '+10 minutes' -Iseconds)" --overwrite

  # ─────────────────────────────────────────────────────────────────
  # Post-Deployment
  # ─────────────────────────────────────────────────────────────────
  notify:
    name: Notify
    runs-on: ubuntu-latest
    needs: deploy
    if: always()
    steps:
      - name: Notify Slack
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "Production deployment ${{ needs.deploy.result }}",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*Production Deployment ${{ needs.deploy.result == 'success' && '✅' || '❌' }}*\n\nVersion: `${{ github.event.inputs.version }}`\nTriggered by: @${{ github.actor }}"
                  }
                }
              ]
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}

      - name: Create GitHub Release
        if: needs.deploy.result == 'success' && startsWith(github.event.inputs.version, 'v')
        uses: actions/github-script@v7
        with:
          script: |
            const version = '${{ github.event.inputs.version }}';
            await github.rest.repos.createRelease({
              owner: context.repo.owner,
              repo: context.repo.repo,
              tag_name: version,
              name: `Release ${version}`,
              generate_release_notes: true,
            });
```

### 4. Cleanup Workflow (Preview Environments)

`.github/workflows/cleanup.yml`

```yaml
name: Cleanup Preview

on:
  pull_request:
    types: [closed]

jobs:
  cleanup:
    name: Delete Preview Environment
    runs-on: ubuntu-latest
    steps:
      - name: Setup kubectl
        uses: azure/setup-kubectl@v3

      - name: Configure kubeconfig
        run: |
          mkdir -p ~/.kube
          echo "${{ secrets.KUBE_CONFIG_PREVIEW }}" | base64 -d > ~/.kube/config

      - name: Delete preview namespace
        run: |
          NAMESPACE="preview-pr-${{ github.event.pull_request.number }}"
          kubectl delete namespace ${NAMESPACE} --ignore-not-found=true

      - name: Delete preview images
        uses: actions/github-script@v7
        with:
          script: |
            const prNumber = context.payload.pull_request.number;

            // List and delete preview images
            const packages = ['frontend', 'backend'];
            for (const pkg of packages) {
              try {
                const versions = await github.rest.packages.getAllPackageVersionsForPackageOwnedByOrg({
                  package_type: 'container',
                  package_name: `${context.repo.repo}/${pkg}`,
                  org: context.repo.owner,
                });

                for (const version of versions.data) {
                  if (version.metadata?.container?.tags?.some(t => t.includes(`pr-${prNumber}`))) {
                    await github.rest.packages.deletePackageVersionForOrg({
                      package_type: 'container',
                      package_name: `${context.repo.repo}/${pkg}`,
                      org: context.repo.owner,
                      package_version_id: version.id,
                    });
                  }
                }
              } catch (e) {
                console.log(`Could not clean up ${pkg}: ${e.message}`);
              }
            }
```

### 5. Scheduled Jobs Workflow

`.github/workflows/scheduled.yml`

```yaml
name: Scheduled Jobs

on:
  schedule:
    # Run dependency updates check weekly
    - cron: '0 9 * * 1'
    # Run security scan daily
    - cron: '0 6 * * *'
  workflow_dispatch:

jobs:
  # ─────────────────────────────────────────────────────────────────
  # Security Scanning
  # ─────────────────────────────────────────────────────────────────
  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'

      - name: Upload Trivy scan results
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'

      - name: Run npm audit (frontend)
        working-directory: frontend
        run: npm audit --audit-level=high
        continue-on-error: true

      - name: Run pip-audit (backend)
        run: |
          pip install ".[dev]"
          pip install pip-audit
          pip-audit
        continue-on-error: true

  # ─────────────────────────────────────────────────────────────────
  # Dependency Updates
  # ─────────────────────────────────────────────────────────────────
  dependency-updates:
    name: Check Dependency Updates
    runs-on: ubuntu-latest
    if: github.event.schedule == '0 9 * * 1'
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Check for outdated npm packages
        working-directory: frontend
        run: |
          npx npm-check-updates -u --target minor
          git diff package.json || echo "No updates available"

      - name: Check for outdated Python packages
        run: |
          pip install pip-tools
          pip-compile pyproject.toml --extra dev --upgrade --dry-run || echo "No updates available"
```

---

## Required Secrets

Configure these secrets in GitHub repository settings:

### Repository Secrets

| Secret | Description | Environment |
|--------|-------------|-------------|
| `CODECOV_TOKEN` | Codecov upload token | All |
| `SLACK_WEBHOOK_URL` | Slack notifications | All |
| `KUBE_CONFIG_PREVIEW` | Base64 encoded kubeconfig | Preview |
| `KUBE_CONFIG_STAGING` | Base64 encoded kubeconfig | Staging |
| `KUBE_CONFIG_PRODUCTION` | Base64 encoded kubeconfig | Production |
| `STAGING_DATABASE_URL` | PostgreSQL connection string | Staging |
| `PRODUCTION_DATABASE_URL` | PostgreSQL connection string | Production |

### Environment Variables (Repository Level)

| Variable | Description | Example |
|----------|-------------|---------|
| `PREVIEW_API_URL` | Preview environment API | `https://api.preview.curious.now` |
| `STAGING_API_URL` | Staging environment API | `https://api.staging.curious.now` |
| `SENTRY_DSN` | Sentry error tracking | `https://xxx@sentry.io/xxx` |

---

## Branch Protection Rules

### `main` Branch

```yaml
# Settings > Branches > Branch protection rules
required_status_checks:
  strict: true
  contexts:
    - "Lint Frontend"
    - "Lint Backend"
    - "Test Frontend"
    - "Test Backend"
    - "E2E Tests"

required_pull_request_reviews:
  required_approving_review_count: 1
  dismiss_stale_reviews: true
  require_code_owner_reviews: true

restrictions:
  users: []
  teams: ["maintainers"]

enforce_admins: true
required_linear_history: true
allow_force_pushes: false
allow_deletions: false
```

---

## Rollback Procedures

### Automatic Rollback (Production)

```bash
# Immediately switch back to previous slot
kubectl patch service curious-frontend -n production -p '{"spec":{"selector":{"slot":"blue"}}}'
kubectl patch service curious-backend -n production -p '{"spec":{"selector":{"slot":"blue"}}}'
```

### Database Rollback

```bash
# Check current migration
alembic current

# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision_id>
```

### Image Rollback

```bash
# Deploy previous version
gh workflow run production.yml -f version=<previous-version>
```

---

## Monitoring Integration

### Health Check Endpoints

```
GET /health          # Basic health
GET /health/ready    # Readiness (DB + Redis connected)
GET /health/live     # Liveness (process alive)
```

### Deployment Metrics

Track in monitoring dashboard:
- Deployment frequency
- Lead time for changes
- Mean time to recovery (MTTR)
- Change failure rate

---

## Local Development Scripts

`scripts/ci-local.sh`

```bash
#!/bin/bash
# Run CI checks locally before pushing

set -e

echo "=== Running Frontend Checks ==="
cd frontend
pnpm lint
pnpm typecheck
pnpm test
cd ..

echo "=== Running Backend Checks ==="
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest

echo "=== All checks passed! ==="
```

---

## Pipeline Diagram

```
                                    Pull Request
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
                    ▼                    ▼                    ▼
              ┌──────────┐        ┌──────────┐        ┌──────────┐
              │  Lint    │        │  Lint    │        │ Security │
              │ Frontend │        │ Backend  │        │   Scan   │
              └────┬─────┘        └────┬─────┘        └──────────┘
                   │                   │
                   ▼                   ▼
              ┌──────────┐        ┌──────────┐
              │  Test    │        │  Test    │
              │ Frontend │        │ Backend  │
              └────┬─────┘        └────┬─────┘
                   │                   │
                   └─────────┬─────────┘
                             │
                             ▼
                       ┌──────────┐
                       │   E2E    │
                       │  Tests   │
                       └────┬─────┘
                            │
                            ▼
                       ┌──────────┐
                       │  Build   │
                       │  Images  │
                       └────┬─────┘
                            │
                            ▼
                       ┌──────────┐
                       │  Deploy  │
                       │ Preview  │
                       └──────────┘


                        Push to main
                             │
                             ▼
                       ┌──────────┐
                       │  Build   │
                       │  Images  │
                       └────┬─────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ Migrate  │  │  Deploy  │  │  Notify  │
        │    DB    │──│ Staging  │──│  Slack   │
        └──────────┘  └──────────┘  └──────────┘


                      Manual Trigger
                             │
                             ▼
                       ┌──────────┐
                       │ Validate │
                       │ Version  │
                       └────┬─────┘
                            │
                            ▼
                       ┌──────────┐
                       │ Approval │
                       │   Gate   │
                       └────┬─────┘
                            │
                            ▼
                       ┌──────────┐
                       │ Migrate  │
                       │    DB    │
                       └────┬─────┘
                            │
                            ▼
                       ┌──────────┐
                       │  Deploy  │
                       │Production│
                       └────┬─────┘
                            │
                            ▼
                       ┌──────────┐
                       │  Notify  │
                       │ + Release│
                       └──────────┘
```
