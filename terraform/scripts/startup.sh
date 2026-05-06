#!/bin/bash
# Digital Twin VM Startup Script
# This script runs when the VM starts up

set -e

# Variables
PROJECT_ID=$(curl -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/project/project-id")
ZONE=$(curl -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/zone" | cut -d'/' -f4)
INSTANCE_NAME=$(curl -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/name")

echo "Starting Digital Twin VM initialization..."
echo "Project: $PROJECT_ID"
echo "Zone: $ZONE"
echo "Instance: $INSTANCE_NAME"

# Open port 8000 in COS iptables (COS has policy DROP by default — GCP firewall alone is not enough)
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    # Container-Optimized OS comes with Docker pre-installed
    # but let's make sure it's running
    sudo systemctl start docker
    sudo systemctl enable docker
else
    echo "Docker already installed"
fi

# Mount PostgreSQL data disk
echo "Mounting PostgreSQL data disk..."
sudo mkdir -p /mnt/stateful_partition/postgres-data

# Wait for disk to be attached (sometimes takes a moment)
sleep 5

# Mount the PostgreSQL data disk using the stable GCP device name
# GCP always exposes the disk at /dev/disk/by-id/google-<device_name>
DATA_DISK="/dev/disk/by-id/google-postgres-data"

if ! mount | grep -q "/mnt/stateful_partition/postgres-data"; then
    if [ -e "$DATA_DISK" ]; then
        echo "Found data disk at $DATA_DISK"

        # Format only if the disk has no filesystem yet
        if ! blkid $DATA_DISK &>/dev/null; then
            echo "Formatting data disk..."
            sudo mkfs.ext4 -F $DATA_DISK
        fi

        sudo mount $DATA_DISK /mnt/stateful_partition/postgres-data
        UUID=$(sudo blkid -s UUID -o value $DATA_DISK)
        echo "UUID=$UUID /mnt/stateful_partition/postgres-data ext4 defaults 0 2" | sudo tee -a /etc/fstab
    else
        echo "WARNING: Data disk not found at $DATA_DISK — using ephemeral storage (data will not persist)"
    fi
fi

# Set permissions
sudo chown -R 999:999 /mnt/stateful_partition/postgres-data  # PostgreSQL user

# Start PostgreSQL container (start existing or create new)
echo "Starting PostgreSQL..."
if docker inspect postgres &>/dev/null; then
  echo "PostgreSQL container exists, starting it..."
  docker start postgres
else
docker run -d \
  --name postgres \
  --restart unless-stopped \
  -e POSTGRES_DB=digitaltwin \
  -e POSTGRES_USER=digitaltwin \
  -e POSTGRES_PASSWORD=changeme \
  -v /mnt/stateful_partition/postgres-data/pgdata:/var/lib/postgresql/data \
  -p 5432:5432 \
  pgvector/pgvector:pg15
fi

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to start..."
for i in $(seq 1 30); do
    if docker exec postgres pg_isready -U digitaltwin -d digitaltwin -q 2>/dev/null; then
        echo "PostgreSQL is ready (attempt $i)"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: PostgreSQL did not become ready after 30 attempts"
        docker logs postgres --tail=20
        exit 1
    fi
    sleep 5
done

# Enable pgvector extension
echo "Enabling pgvector extension..."
docker exec postgres psql -U digitaltwin -d digitaltwin -c "CREATE EXTENSION IF NOT EXISTS vector;" || true

# TODO: Run Alembic migrations here
# For now, assume migrations are run manually or in the app startup

# Fetch secrets from Secret Manager via REST API (gcloud is not available on COS)
echo "Retrieving secrets from Secret Manager..."
SM_TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

fetch_secret() {
  local secret_name=$1
  local default_val=${2:-""}
  local result
  result=$(curl -sf -H "Authorization: Bearer $SM_TOKEN" \
    "https://secretmanager.googleapis.com/v1/projects/$PROJECT_ID/secrets/$secret_name/versions/latest:access" \
    | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode())" 2>/dev/null)
  echo "${result:-$default_val}"
}

export ANTHROPIC_API_KEY=$(fetch_secret "anthropic-api-key")
export VOYAGE_API_KEY=$(fetch_secret "voyage-api-key")
export ADMIN_API_KEY=$(fetch_secret "admin-api-key" "change-me-in-production")
export SUBJECT_ID=$(fetch_secret "subject-id" "default")
export SLACK_BOT_TOKEN=$(fetch_secret "slack-bot-token")
export SLACK_SIGNING_SECRET=$(fetch_secret "slack-signing-secret")
export SLACK_CHAT_CHANNEL_ID=$(fetch_secret "slack-chat-channel-id")
export SLACK_CORRECTIONS_CHANNEL_ID=$(fetch_secret "slack-corrections-channel-id")

# Validate that critical secrets are available
if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "placeholder-change-in-console" ]; then
  echo "ERROR: ANTHROPIC_API_KEY not set in Secret Manager. Please set it in GCP Console."
  exit 1
fi

if [ -z "$ADMIN_API_KEY" ] || [ "$ADMIN_API_KEY" = "change-me-in-production" ]; then
  echo "ERROR: ADMIN_API_KEY not set in Secret Manager. Please set it in GCP Console."
  exit 1
fi

echo "Secrets retrieved successfully"

# Start the Digital Twin application
echo "Starting Digital Twin application..."

# Authenticate Docker with GCR using the VM's service account token
# DOCKER_CONFIG must point to a writable directory (COS root fs is read-only)
echo "Authenticating Docker with GCR..."
export DOCKER_CONFIG=/tmp/docker-config
mkdir -p $DOCKER_CONFIG
GCR_TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "$GCR_TOKEN" | docker login -u oauth2accesstoken --password-stdin https://gcr.io

# Pull and run the latest Digital Twin container (start existing or create new)
echo "Starting Digital Twin application..."
if docker inspect digitaltwin &>/dev/null; then
  echo "Digital Twin container exists, starting it..."
  docker start digitaltwin
else
  echo "Pulling Digital Twin application container..."
  docker pull gcr.io/$PROJECT_ID/digitaltwin:latest
  docker run -d \
    --name digitaltwin \
    --restart unless-stopped \
    --network host \
    -e DATABASE_URL="postgresql+asyncpg://digitaltwin:changeme@localhost:5432/digitaltwin" \
    -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    -e VOYAGE_API_KEY="$VOYAGE_API_KEY" \
    -e ADMIN_API_KEY="$ADMIN_API_KEY" \
    -e SUBJECT_ID="$SUBJECT_ID" \
    -e SLACK_BOT_TOKEN="$SLACK_BOT_TOKEN" \
    -e SLACK_SIGNING_SECRET="$SLACK_SIGNING_SECRET" \
    -e APP_ENV="production" \
    -e LOG_LEVEL="INFO" \
    -p 8000:8000 \
    gcr.io/$PROJECT_ID/digitaltwin:latest
fi

echo "Waiting for application to start..."
sleep 10

# Run database migrations
echo "Running database migrations..."
docker exec digitaltwin alembic upgrade head || {
  echo "WARNING: Alembic migration failed — check container logs"
  docker logs digitaltwin --tail=20
}

# Register Slack channels in database (idempotent — safe to run on every boot)
docker exec -i digitaltwin python3 - <<PYEOF
import asyncio
from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.models.channel_config import ChannelConfig, ChannelType, PermissionLevel

CHANNELS = [
    ("slack:$SLACK_CHAT_CHANNEL_ID",        PermissionLevel.read_only_chat,  "dt_chat"),
    ("slack:$SLACK_CORRECTIONS_CHANNEL_ID", PermissionLevel.learn_candidate, "dt_corrections"),
]

async def setup():
    async with AsyncSessionLocal() as db:
        for channel_id, permission, name in CHANNELS:
            if not channel_id:
                print(f"WARNING: {name} channel ID not set, skipping")
                continue
            result = await db.execute(
                select(ChannelConfig).where(ChannelConfig.channel_id == channel_id)
            )
            if result.scalar_one_or_none() is None:
                db.add(ChannelConfig(
                    channel_id=channel_id,
                    channel_type=ChannelType.slack,
                    permission_level=permission,
                    is_active=True,
                ))
                print(f"Registered {name} ({channel_id}) as {permission.value}")
            else:
                print(f"Channel {name} already registered")
        await db.commit()

asyncio.run(setup())
PYEOF

echo "Digital Twin application started successfully!"

# Clear secrets from environment to prevent exposure
unset ANTHROPIC_API_KEY VOYAGE_API_KEY ADMIN_API_KEY SUBJECT_ID SLACK_BOT_TOKEN SLACK_SIGNING_SECRET
echo "Secrets cleared from environment"

# Signal that VM is ready (could publish to Pub/Sub)
echo "VM initialization complete!"
echo "PostgreSQL is running on port 5432"
echo "Digital Twin application is running on port 8000"
echo "Ready to start using Digital Twin application"

# Keep container running for debugging (remove in production)
# while true; do sleep 30; done
